"""MAX send adapter: TG reply_markup → UnifiedSendPort / MaxClient."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from bot.transports.contracts import NormalizedOutput
from bot.transports.max.client import MaxClient
from bot.transports.unified_send_port import _build_inline_keyboard
from bot.utils.message_utils import _build_normalized_output

logger = logging.getLogger(__name__)

# Возвращает message_id при успехе, иначе None.
SendFunc = Callable[..., Awaitable[Optional[str]]]


def claim_pending_status_id(send_func: SendFunc) -> Optional[str]:
    """Забирает status message_id, оставленный предыдущим шагом (например STT)."""
    pending = getattr(send_func, 'pending_status_id', None)
    # AsyncMock/MagicMock могут автосоздавать атрибут — принимаем только реальный id.
    if not isinstance(pending, str) or not pending.strip():
        return None
    try:
        send_func.pending_status_id = None  # type: ignore[attr-defined]
    except Exception:
        pass
    return pending.strip()


async def edit_or_send(
    send_func: SendFunc,
    message_id: Optional[str],
    text: str,
    reply_markup: Any = None,
) -> Optional[str]:
    """
    Редактирует status-сообщение в итоговый ответ.
    Если edit недоступен — отправляет новое сообщение.
    """
    edit = getattr(send_func, 'edit_or_send', None)
    if callable(edit):
        return await edit(message_id, text, reply_markup)
    return await send_func(text, reply_markup)


async def ensure_processing_status(
    send_func: SendFunc,
    language: str,
    message_key: str = 'processing',
) -> Optional[str]:
    """
    Показывает статусное «обрабатываю…».

    Если у send_func уже есть pending_status_id (голос/STT) — редактирует его,
    иначе отправляет новое сообщение.
    """
    from messages import get_message

    text = get_message(message_key, language)
    pending = claim_pending_status_id(send_func)
    if pending:
        await edit_or_send(send_func, pending, text)
        return pending
    return await send_func(text)


def build_send_func(
    max_client: MaxClient,
    *,
    max_id: int,
    chat_id: Optional[int] = None,
    callback_id: Optional[str] = None,
) -> SendFunc:
    """
    Возвращает async send_func(text, reply_markup=None) -> Optional[str].

    Если есть callback_id, первый вызов отвечает через POST /answers с message
    (правка исходного сообщения с кнопкой — как требует клиент MAX).
    Повторные вызовы в том же апдейте идут обычным POST /messages.
    """

    state = {'callback_answered': False}

    async def send_func(text: str, reply_markup: Any = None) -> Optional[str]:
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
                # /answers редактирует callback-сообщение; отдельного message_id нет.
                return None
            logger.warning(
                '[MAX send] /answers with message failed, fallback to /messages; callback_id=%s',
                callback_id[:40],
            )

        sent = await max_client.send_message(
            user_id=max_id,
            chat_id=chat_id,
            text=output.text,
            reply_markup=keyboard,
        )
        if isinstance(sent, tuple):
            ok = bool(sent[0])
            message_id = sent[1] if len(sent) > 1 else None
        else:
            ok = bool(sent)
            message_id = None
        logger.info(
            '[MAX send] POST /messages ok=%s user_id=%s has_keyboard=%s message_id=%s',
            ok,
            max_id,
            keyboard is not None,
            (message_id or '')[:40] or None,
        )
        return message_id if ok else None

    async def edit_or_send_impl(
        message_id: Optional[str],
        text: str,
        reply_markup: Any = None,
    ) -> Optional[str]:
        if message_id:
            output = _build_normalized_output(text=text or '', reply_markup=reply_markup)
            if output is None:
                output = NormalizedOutput(text=text or '')
            keyboard = _build_inline_keyboard(output)
            edited = await max_client.edit_message(
                message_id=message_id,
                text=output.text,
                reply_markup=keyboard,
            )
            if edited:
                logger.info(
                    '[MAX send] edited status message_id=%s user_id=%s',
                    message_id[:40],
                    max_id,
                )
                return message_id
            logger.warning(
                '[MAX send] edit failed, fallback to send; message_id=%s user_id=%s',
                message_id[:40],
                max_id,
            )
        return await send_func(text, reply_markup)

    def was_callback_answered() -> bool:
        return bool(state['callback_answered'])

    async def ack_callback(notification: str = '✓') -> bool:
        """Снимает спиннер кнопки без правки исходного сообщения."""
        if not callback_id:
            return False
        if state['callback_answered']:
            return True
        answered = await max_client.answer_callback(
            callback_id=callback_id,
            notification=notification or '✓',
        )
        if answered:
            state['callback_answered'] = True
            logger.info(
                '[MAX send] answered callback via /answers notification user_id=%s',
                max_id,
            )
        return bool(answered)

    send_func.was_callback_answered = was_callback_answered  # type: ignore[attr-defined]
    send_func.ack_callback = ack_callback  # type: ignore[attr-defined]
    send_func.edit_or_send = edit_or_send_impl  # type: ignore[attr-defined]
    send_func.pending_status_id = None  # type: ignore[attr-defined]
    return send_func
