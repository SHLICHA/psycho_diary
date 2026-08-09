"""MAX send adapter: TG reply_markup → UnifiedSendPort / MaxClient."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from bot.transports.contracts import NormalizedOutput
from bot.transports.max.client import MaxClient
from bot.transports.unified_send_port import _build_inline_keyboard
from bot.utils.message_utils import _build_normalized_output

SendFunc = Callable[..., Awaitable[bool]]


def build_send_func(
    max_client: MaxClient,
    *,
    max_id: int,
    chat_id: Optional[int] = None,
) -> SendFunc:
    """
    Возвращает async send_func(text, reply_markup=None) -> bool.
    reply_markup — aiogram InlineKeyboardMarkup (как в TG handlers).
    """

    async def send_func(text: str, reply_markup: Any = None) -> bool:
        output = _build_normalized_output(text=text or '', reply_markup=reply_markup)
        if output is None:
            output = NormalizedOutput(text=text or '')
        keyboard = _build_inline_keyboard(output)
        return await max_client.send_message(
            user_id=max_id,
            chat_id=chat_id,
            text=output.text,
            reply_markup=keyboard,
        )

    return send_func
