"""Wave 6 MAX: therapy chat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from asgiref.sync import sync_to_async

from messages import get_message
from bot.handlers.max import state as max_state
from bot.keyboards import get_purchase_options_keyboard, get_single_button_keyboard
from bot.states.therapy_chat_states import TherapyChatStates
from diary.services.therapy_chat_service import (
    build_therapy_chat_error_recovery_view,
    build_therapy_chat_welcome_view,
    process_user_message_in_chat,
    start_therapy_chat,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)

TOKEN_COST = 1


async def _charge_tokens(user: 'User', *, feature_name: str) -> dict:
    """Premium skip; else charge. Returns {ok, insufficient?}."""
    if getattr(user, 'is_premium', False):
        return {'ok': True, 'charged': False}
    balance = getattr(user, 'token_balance', 0) or 0
    if balance < TOKEN_COST:
        return {'ok': False, 'insufficient': True, 'balance': balance}
    from users.models import TokenTransaction

    try:
        await sync_to_async(TokenTransaction.create_and_update_balance)(
            user=user,
            amount=-TOKEN_COST,
            transaction_type='feature_usage',
            description=f'Использование платной функции: {feature_name}',
        )
        return {'ok': True, 'charged': True}
    except Exception as exc:
        logger.error('[MAX therapy] token charge failed: %s', exc, exc_info=True)
        return {'ok': False, 'error': True}


async def _refund_tokens(user: 'User', *, feature_name: str) -> None:
    if getattr(user, 'is_premium', False):
        return
    from users.models import TokenTransaction

    try:
        await sync_to_async(TokenTransaction.create_and_update_balance)(
            user=user,
            amount=TOKEN_COST,
            transaction_type='refund_on_error',
            description=f'Возврат токенов за ошибку в функции: {feature_name}',
        )
    except Exception as exc:
        logger.error('[MAX therapy] token refund failed: %s', exc, exc_info=True)


async def handle_start_therapy_chat(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    try:
        init_result = await start_therapy_chat(user)
        if not init_result.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': 'start_therapy_chat', 'error': True}
        view = build_therapy_chat_welcome_view(user, language)
        max_state.set_fsm_state(
            max_id,
            TherapyChatStates.in_therapy_chat,
            therapy_history=init_result.get('initial_history') or [],
        )
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': 'start_therapy_chat'}
    except Exception as exc:
        logger.error('[MAX therapy] start failed: %s', exc, exc_info=True)
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'start_therapy_chat', 'error': True}


async def process_therapy_text(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not max_state.matches_state(max_id, TherapyChatStates.in_therapy_chat):
        return None

    language = user.language or 'ru'
    user_message_text = (text or '').strip()
    if not user_message_text:
        await send_func(get_message('invalid_input', language))
        return {'ok': True, 'handled': 'therapy_message', 'error': 'empty'}

    charge = await _charge_tokens(user, feature_name='therapy_chat_message')
    if charge.get('insufficient'):
        await send_func(
            get_message('insufficient_tokens', language),
            get_purchase_options_keyboard(language),
        )
        return {'ok': True, 'handled': 'therapy_message', 'mode': 'insufficient_tokens'}
    if not charge.get('ok'):
        await send_func(get_message('error_processing', language))
        return {'ok': True, 'handled': 'therapy_message', 'error': True}

    try:
        await send_func(get_message('processing', language))
        raw = max_state.get_raw_state(max_id)
        current_history = raw.get('therapy_history') or []
        service_result = await process_user_message_in_chat(
            user=user,
            user_message_text=user_message_text,
            current_history=current_history,
        )
        if not service_result.get('success'):
            if charge.get('charged'):
                await _refund_tokens(user, feature_name='therapy_chat_message')
            await send_func(get_message('error_processing', language))
            return {'ok': True, 'handled': 'therapy_message', 'error': True}

        max_state.update_state_data(
            max_id, therapy_history=service_result.get('updated_history') or current_history
        )
        await send_func(
            service_result['response_text'],
            get_single_button_keyboard(language, 'main_menu', 'btn_end_chat'),
        )
        return {'ok': True, 'handled': 'therapy_message'}
    except Exception as exc:
        logger.error('[MAX therapy] message failed: %s', exc, exc_info=True)
        if charge.get('charged'):
            await _refund_tokens(user, feature_name='therapy_chat_message')
        try:
            recovery = await build_therapy_chat_error_recovery_view(user, language)
            await send_func(recovery['text'], recovery.get('reply_markup'))
            if recovery.get('clear_state'):
                max_state.clear_fsm_state(max_id)
        except Exception:
            await send_func(get_message('error_processing', language))
        return {'ok': True, 'handled': 'therapy_message', 'error': True}


def is_wave6_therapy_callback(payload: str) -> bool:
    return payload == 'start_therapy_chat'


async def route_wave6_therapy_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not is_wave6_therapy_callback(payload):
        return None
    return await handle_start_therapy_chat(user, send_func, max_id=max_id)
