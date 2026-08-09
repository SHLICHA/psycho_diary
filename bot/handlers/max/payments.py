"""Wave 3 MAX: premium / tokens payments."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from messages import get_message
from bot.handlers.max import state as max_state
from bot.keyboards import get_single_button_keyboard
from bot.keyboards.identity_merge_keyboard import get_requester_merge_confirmation_keyboard
from bot.states.payment_states import PaymentStates
from diary.services.payment_service import (
    build_email_payment_result_view,
    build_payment_initiation_view,
    build_premium_menu_view,
    build_token_purchase_options_view,
    initiate_subscription_payment,
    initiate_token_payment,
    is_payment_cancel_command,
    process_user_email_for_pending_payment,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)


async def handle_premium_menu(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    max_state.clear_fsm_state(max_id)
    view = build_premium_menu_view(user, language)
    await send_func(view['text'], view.get('reply_markup'))
    return {'ok': True, 'handled': 'premium'}


async def handle_purchase_subscription(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict:
    language = user.language or 'ru'
    plan = payload.split(':', 1)[1]
    result = await initiate_subscription_payment(user, plan)
    view = build_payment_initiation_view(result, language, payment_kind='subscription')

    if view.get('mode') == 'error':
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'purchase_subscription', 'error': True}

    if view.get('mode') == 'requires_email':
        max_state.set_fsm_state(
            max_id,
            PaymentStates.waiting_for_email,
            pending_payment_data=view.get('pending_payment_data'),
            payment_kind='subscription',
        )
        await send_func(
            view['text'],
            get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel'),
        )
        return {'ok': True, 'handled': 'purchase_subscription', 'mode': 'requires_email'}

    await send_func(view['text'])
    return {'ok': True, 'handled': 'purchase_subscription', 'mode': view.get('mode')}


async def handle_purchase_tokens_start(user: 'User', send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    view = build_token_purchase_options_view(language)
    await send_func(view['text'], view.get('reply_markup'))
    return {'ok': True, 'handled': 'purchase_tokens_start'}


async def handle_purchase_tokens(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict:
    language = user.language or 'ru'
    action = payload.split(':', 1)[1]
    if action == 'start':
        return await handle_purchase_tokens_start(user, send_func)
    try:
        token_count = int(action)
    except ValueError:
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'purchase_tokens', 'error': 'invalid'}

    result = await initiate_token_payment(user, token_count)
    view = build_payment_initiation_view(result, language, payment_kind='tokens')

    if view.get('mode') == 'error':
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'purchase_tokens', 'error': True}

    if view.get('mode') == 'requires_email':
        max_state.set_fsm_state(
            max_id,
            PaymentStates.waiting_for_tokens_email,
            pending_payment_data=view.get('pending_payment_data'),
            payment_kind='tokens',
        )
        await send_func(
            view['text'],
            get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel'),
        )
        return {'ok': True, 'handled': 'purchase_tokens', 'mode': 'requires_email'}

    await send_func(view['text'])
    return {'ok': True, 'handled': 'purchase_tokens', 'mode': view.get('mode')}


async def handle_cancel_payment(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    return await handle_premium_menu(user, send_func, max_id=max_id)


async def process_payment_email_text(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    """Handle payment FSM email input. None if not in payment FSM."""
    fsm = max_state.get_fsm_state(max_id)
    if fsm == PaymentStates.waiting_for_email.state:
        payment_kind = 'subscription'
    elif fsm == PaymentStates.waiting_for_tokens_email.state:
        payment_kind = 'tokens'
    else:
        return None

    language = user.language or 'ru'
    email = (text or '').strip()
    if is_payment_cancel_command(email):
        max_state.clear_fsm_state(max_id)
        if payment_kind == 'tokens':
            return await handle_purchase_tokens_start(user, send_func)
        return await handle_premium_menu(user, send_func, max_id=max_id)

    pending = max_state.get_raw_state(max_id).get('pending_payment_data')
    if not pending:
        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'payment_email', 'error': 'missing_pending'}

    result = await process_user_email_for_pending_payment(user, email, pending)
    view = build_email_payment_result_view(result, payment_kind, language)
    if view.get('clear_state'):
        max_state.clear_fsm_state(max_id)

    if view.get('mode') == 'payment_ready':
        for msg_text in view.get('messages') or []:
            await send_func(msg_text)
        return {'ok': True, 'handled': 'payment_email', 'mode': 'payment_ready'}

    if view.get('mode') == 'merge_confirmation':
        merge_request_id = view.get('merge_request_id')
        markup = (
            get_requester_merge_confirmation_keyboard(merge_request_id, language)
            if merge_request_id
            else None
        )
        await send_func(view['text'], markup)
        return {'ok': True, 'handled': 'payment_email', 'mode': 'merge_confirmation'}

    await send_func(view.get('text') or get_message('error_generic', language))
    return {'ok': True, 'handled': 'payment_email', 'mode': view.get('mode')}


def is_wave3_callback(payload: str) -> bool:
    exact = {'settings_premium', 'cancel_payment', 'premium_subscribe'}
    if payload in exact:
        return True
    return (
        payload.startswith('purchase_subscription:')
        or payload.startswith('purchase_tokens:')
    )


async def route_wave3_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not is_wave3_callback(payload):
        return None

    if payload in {'settings_premium', 'premium_subscribe'}:
        return await handle_premium_menu(user, send_func, max_id=max_id)
    if payload == 'cancel_payment':
        return await handle_cancel_payment(user, send_func, max_id=max_id)
    if payload.startswith('purchase_subscription:'):
        return await handle_purchase_subscription(user, payload, send_func, max_id=max_id)
    if payload.startswith('purchase_tokens:'):
        return await handle_purchase_tokens(user, payload, send_func, max_id=max_id)
    return {'ok': True, 'handled': 'wave3_unhandled', 'payload': payload}
