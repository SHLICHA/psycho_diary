"""MAX API client with resilient delivery and polling/webhook support."""

from __future__ import annotations

import json
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
        self._last_failure_reason: str | None = None
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

    @property
    def last_failure_reason(self) -> str | None:
        return self._last_failure_reason

    @staticmethod
    def classify_send_failure(status_code: int, body: Any) -> str | None:
        """Возвращает код ошибки доставки или None для неизвестных сбоев."""
        if status_code != 403:
            return None

        if isinstance(body, dict):
            code = str(body.get('code', '')).lower()
            message = str(body.get('message', '')).lower()
            if code == 'chat.denied' or 'dialog.suspended' in message:
                return 'dialog_suspended'

        body_text = MaxClient._extract_text_from_body(body).lower()
        if 'dialog.suspended' in body_text or 'chat.denied' in body_text:
            return 'dialog_suspended'
        return None

    @staticmethod
    def _is_keyboard_payload_error(body: Any) -> bool:
        text = MaxClient._extract_text_from_body(body).lower()
        return (
            'keyboard' in text
            or 'attachment' in text
            or 'proto.payload' in text
            or "can't deserialize" in text
            or 'deserialize body' in text
        )

    @staticmethod
    def _extract_message_id(body: Any) -> str | None:
        """Достаёт message_id/mid из ответа POST /messages (оба известных формата)."""
        if not isinstance(body, dict):
            return None

        for key in ('message_id', 'mid'):
            value = body.get(key)
            if value:
                return str(value)

        message = body.get('message')
        if isinstance(message, dict):
            for key in ('message_id', 'mid'):
                value = message.get(key)
                if value:
                    return str(value)
            nested_body = message.get('body')
            if isinstance(nested_body, dict):
                for key in ('mid', 'message_id'):
                    value = nested_body.get(key)
                    if value:
                        return str(value)

        nested_body = body.get('body')
        if isinstance(nested_body, dict):
            for key in ('mid', 'message_id'):
                value = nested_body.get(key)
                if value:
                    return str(value)
        return None

    async def _send_single_message(
        self,
        *,
        target_key: str,
        target_value: int,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        text_format: str | None = 'html',
    ) -> tuple[bool, int, Any]:
        params = {target_key: str(target_value)}
        payload: dict[str, Any] = {'text': text}
        # MAX рендерит <b>/<i>/… только при явном format=html|markdown.
        if text_format in {'html', 'markdown'}:
            payload['format'] = text_format
        if attachments:
            payload['attachments'] = attachments

        response_status, response_body = await self._request_json(
            method='POST',
            path='/messages',
            params=params,
            payload=payload,
        )
        return (200 <= response_status < 300), response_status, response_body

    async def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
        text: str | None = None,
        reply_markup: Any = None,
        text_format: str | None = 'html',
    ) -> bool:
        """
        POST /answers?callback_id=...

        Для снятия ошибки/спиннера на кнопке надёжнее слать непустой
        `notification`. Редактирование через `message` оставляем опциональным.
        """
        callback_id = (callback_id or '').strip()
        if not callback_id:
            logger.warning('[MaxClient] answer_callback skipped: empty callback_id')
            return False

        message_variants: list[dict[str, Any] | None]
        if message is not None:
            message_variants = [message]
        elif text is not None:
            safe_text = str(text).strip() or '·'
            base: dict[str, Any] = {'text': safe_text}
            if text_format in {'html', 'markdown'}:
                base['format'] = text_format
            keyboard_variants = self._build_keyboard_attachment_variants(reply_markup)
            if keyboard_variants:
                message_variants = [
                    {**base, 'attachments': [attachment]}
                    for attachment in keyboard_variants
                ]
                message_variants.append(dict(base))
            else:
                message_variants = [base]
        else:
            message_variants = [None]

        last_status: int | None = None
        last_body: Any = None
        for message_body in message_variants:
            payload: dict[str, Any] = {}
            if message_body is not None:
                payload['message'] = message_body
            # notification обязателен, если нет message; при message тоже полезен для UI.
            if notification is not None:
                payload['notification'] = notification
            elif 'message' not in payload:
                payload['notification'] = '✓'

            status, body = await self._request_json(
                method='POST',
                path='/answers',
                params={'callback_id': callback_id},
                payload=payload,
            )
            last_status, last_body = status, body
            success_flag = None
            if isinstance(body, dict) and 'success' in body:
                success_flag = bool(body.get('success'))

            logger.info(
                '[MaxClient] answer_callback status=%s success=%s has_message=%s callback_id=%s',
                status,
                success_flag,
                'message' in payload,
                callback_id[:40],
            )

            if 200 <= status < 300 and success_flag is not False:
                return True

            if (
                message_body is not None
                and message_body.get('attachments')
                and self._is_keyboard_payload_error(body)
            ):
                continue
            break

        logger.error(
            '[MaxClient] answer_callback failed: status=%s body=%s callback_id=%s',
            last_status,
            last_body,
            callback_id[:40],
        )
        return False

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

    @staticmethod
    def _sanitize_button_text(text: Any) -> str:
        """MAX отклоняет whitespace-only text (errors.required) — как в ячейках календаря."""
        value = str(text or '').strip()
        return value if value else '·'

    @staticmethod
    def _extract_aiogram_button_rows(reply_markup: Any) -> list[list[dict[str, str]]]:
        """Convert aiogram InlineKeyboardMarkup into raw text/payload rows."""
        if not reply_markup or not hasattr(reply_markup, 'inline_keyboard'):
            return []

        result: list[list[dict[str, str]]] = []
        for row in getattr(reply_markup, 'inline_keyboard', []) or []:
            converted_row: list[dict[str, str]] = []
            for button in row:
                text = getattr(button, 'text', None)
                callback_data = getattr(button, 'callback_data', None)
                url = getattr(button, 'url', None)
                if callback_data is not None:
                    converted_row.append(
                        {
                            'text': MaxClient._sanitize_button_text(text),
                            'payload': str(callback_data),
                        }
                    )
                elif url:
                    # MAX link button (share / deep-link open).
                    converted_row.append(
                        {
                            'type': 'link',
                            'text': MaxClient._sanitize_button_text(text),
                            'url': str(url),
                        }
                    )
                else:
                    continue
            if converted_row:
                result.append(converted_row)
        return result

    @staticmethod
    def _normalize_keyboard_rows(
        rows: list[list[dict[str, str]]],
        *,
        mode: str = 'callback_string',
    ) -> list[list[dict[str, Any]]]:
        """
        Normalize button rows to a MAX API keyboard variant.

        Modes:
        - callback_string: type=callback, payload="..."  (канон MAX API)
        - legacy: без type, payload="..."
        """
        normalized_rows: list[list[dict[str, Any]]] = []
        for row in rows:
            # MAX: до 7 кнопок в ряду.
            truncated_row = row[:7]
            normalized_row: list[dict[str, Any]] = []
            for button in truncated_row:
                text = MaxClient._sanitize_button_text(button.get('text'))
                if button.get('type') == 'link' and button.get('url'):
                    normalized_row.append(
                        {
                            'type': 'link',
                            'text': text,
                            'url': str(button['url']),
                        }
                    )
                    continue
                raw_payload = button.get('payload')
                if mode == 'legacy':
                    normalized_button: dict[str, Any] = {'text': text}
                    if raw_payload is not None:
                        normalized_button['payload'] = str(raw_payload)
                else:
                    # Канон docs: type=callback, text, payload=string (без intent).
                    normalized_button = {
                        'type': 'callback',
                        'text': text,
                    }
                    if raw_payload is not None:
                        normalized_button['payload'] = str(raw_payload)
                normalized_row.append(normalized_button)
            if normalized_row:
                normalized_rows.append(normalized_row)
        # MAX: до 30 рядов / 210 кнопок.
        return normalized_rows[:30]

    def _build_keyboard_attachment_variants(self, reply_markup: Any) -> list[dict[str, Any]]:
        """
        MAX platform-api2 принимает payload кнопки только как строку.
        Вариант с payload={"action":...} даёт proto.payload — не используем.
        """
        rows = self._extract_aiogram_button_rows(reply_markup)
        if not rows:
            return []

        variants: list[dict[str, Any]] = []
        for mode in ('callback_string', 'legacy'):
            normalized = self._normalize_keyboard_rows(rows, mode=mode)
            if not normalized:
                continue
            variants.append(
                {
                    'type': 'inline_keyboard',
                    'payload': {'buttons': normalized},
                }
            )
        return variants

    async def send_message(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        text: str,
        reply_markup: Any = None,
        text_format: str | None = 'html',
    ) -> tuple[bool, str | None]:
        """Send MAX message with fallback and chunking.

        Returns:
            (ok, message_id) — message_id берётся из последнего успешно
            отправленного чанка (для edit-in-place статусного сообщения).
        """
        self._last_failure_reason = None

        if not self.api_token:
            logger.warning('[MaxClient] Skip send: MAX_BOT_TOKEN is empty')
            self._last_failure_reason = 'missing_token'
            return False, None

        if user_id is None and chat_id is None:
            logger.error('[MaxClient] Skip send: neither user_id nor chat_id provided')
            self._last_failure_reason = 'missing_target'
            return False, None

        text_chunks = self._chunk_text(text)
        keyboard_variants = self._build_keyboard_attachment_variants(reply_markup)

        # В личке с ботом надёжнее user_id (см. docs POST /messages).
        if user_id is not None:
            primary_target = ('user_id', int(user_id))
            fallback_target = ('chat_id', int(chat_id)) if chat_id is not None else None
        else:
            primary_target = ('chat_id', int(chat_id))
            fallback_target = None

        last_message_id: str | None = None
        for index, chunk in enumerate(text_chunks):
            # Клавиатуру вешаем только на последний чанк.
            variants_to_try: list[dict[str, Any] | None]
            if index == len(text_chunks) - 1 and keyboard_variants:
                variants_to_try = list(keyboard_variants) + [None]
            else:
                variants_to_try = [None]

            sent = False
            last_status = 0
            last_body: Any = None
            for variant_index, keyboard_attachment in enumerate(variants_to_try):
                attachments = [keyboard_attachment] if keyboard_attachment else None
                ok, status_code, body = await self._send_single_message(
                    target_key=primary_target[0],
                    target_value=primary_target[1],
                    text=chunk,
                    attachments=attachments,
                    text_format=text_format,
                )
                # Fallback на chat_id только если ошибка не про keyboard schema.
                if (
                    not ok
                    and fallback_target is not None
                    and not (attachments and self._is_keyboard_payload_error(body))
                ):
                    logger.warning(
                        '[MaxClient] Fallback send from %s to %s',
                        primary_target[0],
                        fallback_target[0],
                    )
                    ok, status_code, body = await self._send_single_message(
                        target_key=fallback_target[0],
                        target_value=fallback_target[1],
                        text=chunk,
                        attachments=attachments,
                        text_format=text_format,
                    )

                if ok:
                    sent = True
                    last_message_id = self._extract_message_id(body) or last_message_id
                    break

                last_status, last_body = status_code, body
                if (
                    keyboard_attachment is not None
                    and self._is_keyboard_payload_error(body)
                    and variant_index < len(variants_to_try) - 1
                ):
                    logger.warning(
                        '[MaxClient] Keyboard variant %s/%s rejected, trying next. body=%s',
                        variant_index + 1,
                        len(variants_to_try) - 1,
                        body,
                    )
                    continue
                break

            if not sent:
                self._last_failure_reason = (
                    self.classify_send_failure(last_status, last_body) or 'send_failed'
                )
                logger.error(
                    '[MaxClient] MAX message send failed: status=%s body=%s reason=%s',
                    last_status,
                    last_body,
                    self._last_failure_reason,
                )
                return False, None

        return True, last_message_id

    async def edit_message(
        self,
        *,
        message_id: str,
        text: str,
        reply_markup: Any = None,
        text_format: str | None = 'html',
        clear_attachments_if_no_keyboard: bool = True,
    ) -> bool:
        """PUT /messages?message_id=... — редактирует ранее отправленное сообщение бота."""
        message_id = (message_id or '').strip()
        if not message_id:
            logger.warning('[MaxClient] edit_message skipped: empty message_id')
            return False
        if not self.api_token:
            logger.warning('[MaxClient] Skip edit: MAX_BOT_TOKEN is empty')
            return False

        # Edit рассчитан на одно сообщение; длинный текст лучше отправлять заново.
        if len(self._chunk_text(text)) > 1:
            logger.info(
                '[MaxClient] edit_message fallback: text too long for single edit message_id=%s',
                message_id[:40],
            )
            return False

        keyboard_variants = self._build_keyboard_attachment_variants(reply_markup)
        variants_to_try: list[list[dict[str, Any]] | None]
        if keyboard_variants:
            variants_to_try = [[variant] for variant in keyboard_variants] + [None]
        elif clear_attachments_if_no_keyboard:
            # Пустой список удаляет старые вложения; null оставляет как было.
            variants_to_try = [[]]
        else:
            variants_to_try = [None]

        last_status = 0
        last_body: Any = None
        for variant_index, attachments in enumerate(variants_to_try):
            payload: dict[str, Any] = {'text': text}
            if text_format in {'html', 'markdown'}:
                payload['format'] = text_format
            if attachments is not None:
                payload['attachments'] = attachments

            status_code, body = await self._request_json(
                method='PUT',
                path='/messages',
                params={'message_id': message_id},
                payload=payload,
            )
            ok = 200 <= status_code < 300
            if ok and isinstance(body, dict) and body.get('success') is False:
                ok = False

            if ok:
                logger.info(
                    '[MaxClient] edit_message ok message_id=%s has_keyboard=%s',
                    message_id[:40],
                    bool(attachments),
                )
                return True

            last_status, last_body = status_code, body
            if (
                attachments
                and self._is_keyboard_payload_error(body)
                and variant_index < len(variants_to_try) - 1
            ):
                logger.warning(
                    '[MaxClient] edit keyboard variant %s/%s rejected, trying next. body=%s',
                    variant_index + 1,
                    len(variants_to_try) - 1,
                    body,
                )
                continue
            break

        logger.error(
            '[MaxClient] edit_message failed: status=%s body=%s message_id=%s',
            last_status,
            last_body,
            message_id[:40],
        )
        return False

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
        """Request upload endpoint from MAX (`POST /uploads?type=...`)."""
        response_status, response_body = await self._request_json(
            method='POST',
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

    @staticmethod
    def _resolve_upload_attachment_payload(
        upload_result: Any,
        *,
        upload_type: str,
        preexisting_token: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Нормализует ответ multipart-загрузки в payload для attachments.

        Для image MAX часто возвращает ``photos`` map вместо плоского ``token``.
        """
        if not isinstance(upload_result, dict):
            upload_result = {}

        token = upload_result.get('token')
        if not (isinstance(token, str) and token.strip()):
            nested = upload_result.get('payload')
            if isinstance(nested, dict):
                token = nested.get('token')
        if isinstance(token, str) and token.strip():
            return {'token': token.strip()}

        photos = upload_result.get('photos')
        if not isinstance(photos, dict) or not photos:
            nested = upload_result.get('payload')
            if isinstance(nested, dict):
                photos = nested.get('photos')
        if isinstance(photos, dict) and photos:
            # Иногда token лежит внутри photos[*].token — оставляем map как есть (как в MAX SDK).
            return {'photos': photos}

        url = upload_result.get('url')
        if upload_type == 'image' and isinstance(url, str) and url.strip():
            # Не путать upload URL с публичным image url; только если похоже на готовый CDN.
            if 'upload' not in url.lower():
                return {'url': url.strip()}

        if preexisting_token and upload_type in {'video', 'audio'}:
            return {'token': preexisting_token}
        return None

    async def upload_bytes(
        self,
        data: bytes,
        *,
        upload_type: str = 'image',
        filename: str = 'file.bin',
        content_type: str = 'application/octet-stream',
    ) -> dict[str, Any] | None:
        """
        Upload bytes to MAX and return attachment payload ({token} | {photos} | {url}).
        Flow: POST /uploads → POST multipart/binary to returned url.
        """
        meta = await self.get_upload_url(upload_type)
        if not meta:
            return None
        upload_url = meta.get('url')
        preexisting_token = meta.get('token')
        if isinstance(preexisting_token, str):
            preexisting_token = preexisting_token.strip() or None
        else:
            preexisting_token = None

        if not upload_url:
            if preexisting_token and upload_type in {'video', 'audio'}:
                return {'token': preexisting_token}
            logger.error('[MaxClient] upload meta missing url: %s', meta)
            return None

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
                raw_text = await response.text()
                if not (200 <= response.status < 300):
                    logger.error(
                        '[MaxClient] upload failed: status=%s body=%s',
                        response.status,
                        raw_text[:300],
                    )
                    if preexisting_token and upload_type in {'video', 'audio'}:
                        return {'token': preexisting_token}
                    return None
                body_json: Any = {}
                if raw_text.strip():
                    try:
                        body_json = json.loads(raw_text)
                    except Exception:
                        body_json = {}
                payload = self._resolve_upload_attachment_payload(
                    body_json,
                    upload_type=upload_type,
                    preexisting_token=preexisting_token,
                )
                if payload:
                    return payload
                logger.error(
                    '[MaxClient] upload ok but no attachment payload: type=%s body=%s',
                    upload_type,
                    raw_text[:300],
                )
                return None
        except Exception as exc:
            logger.error('[MaxClient] upload exception: %s', exc, exc_info=True)
            if preexisting_token and upload_type in {'video', 'audio'}:
                return {'token': preexisting_token}
            return None

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
        image_payload = await self.upload_bytes(
            image_bytes,
            upload_type='image',
            filename=filename,
            content_type='image/png' if filename.lower().endswith('.png') else 'image/jpeg',
        )
        if not image_payload:
            logger.warning('[MaxClient] send_image aborted: upload payload missing')
            return False

        if not self.api_token:
            return False
        if user_id is None and chat_id is None:
            return False

        keyboard_variants = self._build_keyboard_attachment_variants(reply_markup)
        keyboard_attachment = keyboard_variants[0] if keyboard_variants else None
        attachments: list[dict[str, Any]] = [
            {'type': 'image', 'payload': image_payload},
        ]
        if keyboard_attachment:
            attachments.append(keyboard_attachment)

        primary_target = ('chat_id', int(chat_id)) if chat_id is not None else ('user_id', int(user_id))
        ok, status_code, body = await self._send_single_message(
            target_key=primary_target[0],
            target_value=primary_target[1],
            text=caption or '',
            attachments=attachments,
            text_format='html' if caption else None,
        )
        if ok:
            return True
        if chat_id is not None and user_id is not None:
            ok, status_code, body = await self._send_single_message(
                target_key='user_id',
                target_value=int(user_id),
                text=caption or '',
                attachments=attachments,
                text_format='html' if caption else None,
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
