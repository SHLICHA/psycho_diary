"""MAX API client with resilient delivery and polling/webhook support."""

from __future__ import annotations

import logging
import ssl
from pathlib import Path
from typing import Any

import aiohttp
from django.conf import settings

from .rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class MaxClient:
    """MAX API client for transport layer."""

    def __init__(
        self,
        api_token: str,
        base_url: str,
        timeout_seconds: int = 10,
        rate_limit_rps: float = 10,
        rate_limit_burst: int = 50,
        max_message_length: int = 3500,
        ca_cert_paths: list[str] | None = None,
    ):
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.max_message_length = max(int(max_message_length), 100)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = TokenBucketRateLimiter(rate_limit_rps, rate_limit_burst)
        if ca_cert_paths is None:
            ca_cert_paths = list(getattr(settings, 'MAX_API_CA_CERT_PATHS', []) or [])
        self.ca_cert_paths = [str(path).strip() for path in ca_cert_paths if str(path).strip()]

    def _build_headers(self) -> dict[str, str]:
        return {'Authorization': self.api_token, 'Content-Type': 'application/json'}

    def _build_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=self.timeout_seconds)

    def _resolve_cert_path(self, ca_path: str) -> Path:
        cert_path = Path(ca_path)
        if cert_path.is_absolute():
            return cert_path
        base_dir = Path(getattr(settings, 'BASE_DIR', Path.cwd()))
        return base_dir / cert_path

    def _build_ssl_connector(self) -> aiohttp.TCPConnector | None:
        """Build TCPConnector with Минцифра CA chain when configured."""
        if not self.ca_cert_paths:
            return None

        ssl_context = ssl.create_default_context()
        loaded: list[str] = []
        for raw_path in self.ca_cert_paths:
            cert_path = self._resolve_cert_path(raw_path)
            if not cert_path.is_file():
                logger.warning('[MaxClient] MAX CA certificate file not found: %s', cert_path)
                continue
            try:
                ssl_context.load_verify_locations(cafile=str(cert_path))
                loaded.append(str(cert_path))
            except ssl.SSLError as cert_error:
                logger.warning(
                    '[MaxClient] Invalid MAX CA certificate (%s): %s',
                    cert_path,
                    cert_error,
                )
            except OSError as cert_error:
                logger.warning(
                    '[MaxClient] Cannot load MAX CA certificate (%s): %s',
                    cert_path,
                    cert_error,
                )

        if not loaded:
            logger.warning(
                '[MaxClient] No valid custom MAX CA certificates loaded, using system trust store'
            )
            return None

        logger.info('[MaxClient] Loaded custom MAX CA certificates: %s', ', '.join(loaded))
        return aiohttp.TCPConnector(ssl=ssl_context)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = self._build_ssl_connector()
            if connector is not None:
                self._session = aiohttp.ClientSession(
                    timeout=self._build_timeout(),
                    connector=connector,
                )
            else:
                self._session = aiohttp.ClientSession(timeout=self._build_timeout())
        return self._session

    async def _request_json(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[int, Any]:
        if not self.api_token:
            return 401, None

        await self._rate_limiter.acquire()

        url = f"{self.base_url}{path}"
        session = await self._get_session()
        request_timeout = (
            aiohttp.ClientTimeout(total=timeout_seconds)
            if timeout_seconds is not None
            else None
        )
        async with session.request(
            method,
            url,
            params=params,
            json=payload,
            headers=self._build_headers(),
            timeout=request_timeout,
        ) as response:
            status = response.status
            if status == 204:
                return status, None
            content_type = (response.headers.get('Content-Type') or '').lower()
            if 'application/json' in content_type:
                return status, await response.json()
            return status, await response.text()

    @staticmethod
    def _extract_text_from_body(body: Any) -> str:
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            return str(body.get('message') or body.get('error') or body)
        return str(body)

    @staticmethod
    def _is_keyboard_payload_error(body: Any) -> bool:
        text = MaxClient._extract_text_from_body(body).lower()
        return ('keyboard' in text) or ('attachment' in text) or ('payload' in text)

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= self.max_message_length:
            return [text]

        chunks: list[str] = []
        current = text
        while len(current) > self.max_message_length:
            split_at = current.rfind('\n', 0, self.max_message_length)
            if split_at <= 0:
                split_at = current.rfind(' ', 0, self.max_message_length)
            if split_at <= 0:
                split_at = self.max_message_length
            chunks.append(current[:split_at].rstrip())
            current = current[split_at:].lstrip()

        if current:
            chunks.append(current)
        return chunks or [text]

    async def _send_single_message(
        self,
        *,
        target_key: str,
        target_value: int,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, int, Any]:
        params = {target_key: str(target_value)}
        payload: dict[str, Any] = {'text': text}
        if attachments:
            payload['attachments'] = attachments

        response_status, response_body = await self._request_json(
            method='POST',
            path='/messages',
            params=params,
            payload=payload,
        )
        return (200 <= response_status < 300), response_status, response_body

    @staticmethod
    def _serialize_inline_keyboard(reply_markup: Any) -> list[list[dict[str, str]]] | None:
        """Convert aiogram InlineKeyboardMarkup into MAX buttons format."""
        if not reply_markup or not hasattr(reply_markup, 'inline_keyboard'):
            return None

        result: list[list[dict[str, str]]] = []
        for row in getattr(reply_markup, 'inline_keyboard', []) or []:
            converted_row: list[dict[str, str]] = []
            for button in row:
                text = getattr(button, 'text', None)
                callback_data = getattr(button, 'callback_data', None)
                if not text or not callback_data:
                    continue
                converted_row.append({'text': str(text), 'payload': str(callback_data)})
            if converted_row:
                result.append(converted_row)

        return result or None

    async def send_message(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        text: str,
        reply_markup: Any = None,
    ) -> bool:
        """Send MAX message with fallback chat_id->user_id and chunking."""
        if not self.api_token:
            logger.warning('[MaxClient] Skip send: MAX_BOT_TOKEN is empty')
            return False

        if user_id is None and chat_id is None:
            logger.error('[MaxClient] Skip send: neither user_id nor chat_id provided')
            return False

        text_chunks = self._chunk_text(text)

        buttons = self._serialize_inline_keyboard(reply_markup)
        attachments = [{'type': 'inline_keyboard', 'buttons': buttons}] if buttons else None

        primary_target = ('chat_id', int(chat_id)) if chat_id is not None else ('user_id', int(user_id))
        fallback_target = None
        if chat_id is not None and user_id is not None:
            fallback_target = ('user_id', int(user_id))

        for index, chunk in enumerate(text_chunks):
            chunk_attachments = attachments if index == len(text_chunks) - 1 else None

            ok, status_code, body = await self._send_single_message(
                target_key=primary_target[0],
                target_value=primary_target[1],
                text=chunk,
                attachments=chunk_attachments,
            )

            if not ok and chunk_attachments and self._is_keyboard_payload_error(body):
                logger.warning('[MaxClient] Retry without keyboard due to payload error')
                ok, status_code, body = await self._send_single_message(
                    target_key=primary_target[0],
                    target_value=primary_target[1],
                    text=chunk,
                    attachments=None,
                )

            if not ok and fallback_target is not None:
                logger.warning('[MaxClient] Fallback send from %s to %s', primary_target[0], fallback_target[0])
                ok, status_code, body = await self._send_single_message(
                    target_key=fallback_target[0],
                    target_value=fallback_target[1],
                    text=chunk,
                    attachments=chunk_attachments,
                )
                if not ok and chunk_attachments and self._is_keyboard_payload_error(body):
                    ok, status_code, body = await self._send_single_message(
                        target_key=fallback_target[0],
                        target_value=fallback_target[1],
                        text=chunk,
                        attachments=None,
                    )

            if not ok:
                logger.error('[MaxClient] MAX message send failed: status=%s body=%s', status_code, body)
                return False

        return True

    async def download_file(self, url: str) -> bytes | None:
        """Download binary content from a MAX media URL."""
        if not url:
            return None
        await self._rate_limiter.acquire()
        session = await self._get_session()
        headers = {'Authorization': self.api_token} if self.api_token else {}
        try:
            async with session.get(url, headers=headers) as response:
                if not (200 <= response.status < 300):
                    logger.error(
                        '[MaxClient] media download failed: status=%s url=%s',
                        response.status,
                        url[:120],
                    )
                    return None
                return await response.read()
        except Exception as exc:
            logger.error('[MaxClient] media download exception: %s', exc, exc_info=True)
            return None

    async def get_upload_url(self, upload_type: str = 'image') -> dict[str, Any] | None:
        """Request upload endpoint from MAX (`/uploads?type=...`)."""
        response_status, response_body = await self._request_json(
            method='GET',
            path='/uploads',
            params={'type': upload_type},
        )
        if not (200 <= response_status < 300) or not isinstance(response_body, dict):
            logger.error(
                '[MaxClient] get_upload_url failed: status=%s body=%s',
                response_status,
                response_body,
            )
            return None
        return response_body

    async def upload_bytes(
        self,
        data: bytes,
        *,
        upload_type: str = 'image',
        filename: str = 'file.bin',
        content_type: str = 'application/octet-stream',
    ) -> str | None:
        """
        Upload bytes to MAX and return attachment token.
        Flow: GET /uploads → POST multipart/binary to returned url.
        """
        meta = await self.get_upload_url(upload_type)
        if not meta:
            return None
        upload_url = meta.get('url')
        # Some MAX responses already include token for video/audio; for image usually after POST.
        preexisting_token = meta.get('token')
        if not upload_url:
            return str(preexisting_token) if preexisting_token else None

        await self._rate_limiter.acquire()
        session = await self._get_session()
        form = aiohttp.FormData()
        form.add_field(
            'data',
            data,
            filename=filename,
            content_type=content_type,
        )
        headers = {'Authorization': self.api_token} if self.api_token else {}
        try:
            async with session.post(upload_url, data=form, headers=headers) as response:
                if not (200 <= response.status < 300):
                    body = await response.text()
                    logger.error(
                        '[MaxClient] upload failed: status=%s body=%s',
                        response.status,
                        body[:200],
                    )
                    return str(preexisting_token) if preexisting_token else None
                try:
                    body_json = await response.json(content_type=None)
                except Exception:
                    body_json = {}
                token = None
                if isinstance(body_json, dict):
                    token = (
                        body_json.get('token')
                        or (body_json.get('payload') or {}).get('token')
                        or preexisting_token
                    )
                return str(token) if token else (str(preexisting_token) if preexisting_token else None)
        except Exception as exc:
            logger.error('[MaxClient] upload exception: %s', exc, exc_info=True)
            return str(preexisting_token) if preexisting_token else None

    async def send_image(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        image_bytes: bytes,
        caption: str = '',
        filename: str = 'image.png',
        reply_markup: Any = None,
    ) -> bool:
        """Upload image and send as MAX attachment with optional caption/keyboard."""
        token = await self.upload_bytes(
            image_bytes,
            upload_type='image',
            filename=filename,
            content_type='image/png' if filename.lower().endswith('.png') else 'image/jpeg',
        )
        if not token:
            logger.warning('[MaxClient] send_image aborted: upload token missing')
            return False

        if not self.api_token:
            return False
        if user_id is None and chat_id is None:
            return False

        buttons = self._serialize_inline_keyboard(reply_markup)
        attachments: list[dict[str, Any]] = [
            {'type': 'image', 'payload': {'token': token}},
        ]
        if buttons:
            attachments.append({'type': 'inline_keyboard', 'buttons': buttons})

        primary_target = ('chat_id', int(chat_id)) if chat_id is not None else ('user_id', int(user_id))
        ok, status_code, body = await self._send_single_message(
            target_key=primary_target[0],
            target_value=primary_target[1],
            text=caption or '',
            attachments=attachments,
        )
        if ok:
            return True
        if chat_id is not None and user_id is not None:
            ok, status_code, body = await self._send_single_message(
                target_key='user_id',
                target_value=int(user_id),
                text=caption or '',
                attachments=attachments,
            )
            if ok:
                return True
        logger.error('[MaxClient] send_image failed: status=%s body=%s', status_code, body)
        return False

    async def fetch_updates(
        self,
        *,
        marker: str | None = None,
        timeout_seconds: int = 30,
        update_types: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch batch of MAX updates via long polling."""
        params: dict[str, Any] = {'timeout': str(timeout_seconds)}
        if marker:
            params['marker'] = marker
        if update_types:
            params['types'] = ','.join(update_types)

        # Long poll waits up to timeout_seconds; HTTP client must outlive that.
        http_timeout = max(float(self.timeout_seconds), float(timeout_seconds) + 10.0)
        response_status, response_body = await self._request_json(
            method='GET',
            path='/updates',
            params=params,
            timeout_seconds=http_timeout,
        )
        if not (200 <= response_status < 300):
            logger.error(
                '[MaxClient] MAX updates polling failed: status=%s body=%s',
                response_status,
                response_body,
            )
            return [], marker

        data = response_body if isinstance(response_body, dict) else {}
        updates = data.get('updates') or data.get('items') or []
        if not isinstance(updates, list):
            updates = []
        next_marker = data.get('marker') or data.get('next_marker') or marker
        return updates, next_marker

    async def register_webhook(self, webhook_url: str, update_types: list[str] | None = None) -> bool:
        """Register webhook subscription in MAX."""
        if not webhook_url:
            logger.warning('[MaxClient] Skip webhook registration: webhook_url is empty')
            return False
        payload: dict[str, Any] = {'url': webhook_url}
        if update_types:
            payload['update_types'] = update_types

        response_status, response_body = await self._request_json(
            method='POST',
            path='/subscriptions',
            payload=payload,
        )
        if 200 <= response_status < 300:
            return True
        logger.error(
            '[MaxClient] MAX webhook registration failed: status=%s body=%s',
            response_status,
            response_body,
        )
        return False

    async def close(self) -> None:
        """Close internal aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
