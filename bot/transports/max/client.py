"""MAX API client with resilient delivery and polling/webhook support."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

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
    ):
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.max_message_length = max(int(max_message_length), 100)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = TokenBucketRateLimiter(rate_limit_rps, rate_limit_burst)

    def _build_headers(self) -> dict[str, str]:
        return {'Authorization': self.api_token, 'Content-Type': 'application/json'}

    def _build_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=self.timeout_seconds)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._build_timeout())
        return self._session

    async def _request_json(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        if not self.api_token:
            return 401, None

        await self._rate_limiter.acquire()

        url = f"{self.base_url}{path}"
        session = await self._get_session()
        async with session.request(
            method,
            url,
            params=params,
            json=payload,
            headers=self._build_headers(),
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

        response_status, response_body = await self._request_json(
            method='GET',
            path='/updates',
            params=params,
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
