"""MAX send adapter: TG reply_markup → UnifiedSendPort / MaxClient."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from bot.transports.contracts import NormalizedOutput
from bot.transports.max.client import MaxClient
from bot.transports.unified_send_port import _build_inline_keyboard
from bot.utils.message_utils import _build_normalized_output

logger = logging.getLogger(__name__)

SendFunc = Callable[..., Awaitable[bool]]


def build_send_func(
    max_client: MaxClient,
    *,
    max_id: int,
    chat_id: Optional[int] = None,
    callback_id: Optional[str] = None,
) -> SendFunc:
    """
    Возвращает async send_func(text, reply_markup=None) -> bool.

    Если есть callback_id, первый вызов отвечает через POST /answers с message
    (правка исходного сообщения с кнопкой — как требует клиент MAX).
    Повторные вызовы в том же апдейте идут обычным POST /messages.
    """

    state = {'callback_answered': False}

    async def send_func(text: str, reply_markup: Any = None) -> bool:
        output = _build_normalized_output(text=text or '', reply_markup=reply_markup)
        if output is None:
            output = NormalizedOutput(text=text or '')
        keyboard = _build_inline_keyboard(output)

        if callback_id and not state['callback_answered']:
            answered = await max_client.answer_callback(
                callback_id=callback_id,
                text=output.text,
                reply_markup=keyboard,
                notification='✓',
            )
            if answered:
                state['callback_answered'] = True
                logger.info(
                    '[MAX send] answered callback via /answers message user_id=%s',
                    max_id,
                )
                return True
            logger.warning(
                '[MAX send] /answers with message failed, fallback to /messages; callback_id=%s',
                callback_id[:40],
            )

        ok = await max_client.send_message(
            user_id=max_id,
            chat_id=chat_id,
            text=output.text,
            reply_markup=keyboard,
        )
        logger.info(
            '[MAX send] POST /messages ok=%s user_id=%s has_keyboard=%s',
            ok,
            max_id,
            keyboard is not None,
        )
        return ok

    def was_callback_answered() -> bool:
        return bool(state['callback_answered'])

    send_func.was_callback_answered = was_callback_answered  # type: ignore[attr-defined]
    return send_func
