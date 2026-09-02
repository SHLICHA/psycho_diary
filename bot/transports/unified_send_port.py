"""Concrete send port implementation for Telegram and MAX transports."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramAPIError
from django.conf import settings

from bot.bot_instance import bot
from bot.transports.max import MaxClient

from .contracts import NormalizedOutput
from .send_port import SendPort, SendResult


def _build_inline_keyboard(output: NormalizedOutput) -> InlineKeyboardMarkup | None:
    if not output.buttons:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    for row in output.buttons:
        rows.append(
            [
                InlineKeyboardButton(text=button.text, callback_data=button.callback_data)
                for button in row
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class UnifiedSendPort(SendPort):
    async def send(self, *, platform: str, recipient_id: int, output: NormalizedOutput) -> SendResult:
        if platform == 'telegram':
            return await self._send_telegram(recipient_id=recipient_id, output=output)
        if platform == 'max':
            return await self._send_max(recipient_id=recipient_id, output=output)
        return SendResult(success=False, reason=f'unsupported_platform:{platform}')

    async def _send_telegram(self, *, recipient_id: int, output: NormalizedOutput) -> SendResult:
        try:
            await bot.send_message(
                chat_id=recipient_id,
                text=output.text,
                reply_markup=_build_inline_keyboard(output),
            )
            return SendResult(success=True, reason='sent')
        except TelegramForbiddenError:
            return SendResult(success=False, reason='telegram_forbidden')
        except TelegramBadRequest as exc:
            error_message = str(exc).lower()
            if (
                'bot was blocked by the user' in error_message
                or 'user is deactivated' in error_message
                or 'chat not found' in error_message
                or 'forbidden' in error_message
            ):
                return SendResult(success=False, reason='telegram_blocked_or_chat_not_found')
            return SendResult(success=False, reason='telegram_bad_request')
        except TelegramAPIError:
            return SendResult(success=False, reason='telegram_api_error')
        except Exception:
            return SendResult(success=False, reason='telegram_send_failed')

    async def _send_max(self, *, recipient_id: int, output: NormalizedOutput) -> SendResult:
        max_client = MaxClient(
            api_token=getattr(settings, 'MAX_BOT_TOKEN', ''),
            base_url=getattr(settings, 'MAX_API_BASE_URL', 'https://platform-api2.max.ru'),
            timeout_seconds=getattr(settings, 'MAX_API_TIMEOUT_SECONDS', 10),
        )
        try:
            sent = await max_client.send_message(
                user_id=recipient_id,
                text=output.text,
                reply_markup=_build_inline_keyboard(output),
            )
            ok = sent[0] if isinstance(sent, tuple) else bool(sent)
            if ok:
                return SendResult(success=True, reason='sent')

            failure_reason = max_client.last_failure_reason or 'send_failed'
            if failure_reason == 'dialog_suspended':
                return SendResult(success=False, reason='max_dialog_suspended')
            return SendResult(success=False, reason=f'max_{failure_reason}')
        finally:
            await max_client.close()
