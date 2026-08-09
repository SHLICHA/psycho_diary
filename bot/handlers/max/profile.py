"""Wave 6 MAX: user profile, email edit, merge_requester."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from messages import get_button_text, get_message
from bot.handlers.max import state as max_state
from bot.keyboards import (
    get_account_deletion_confirmation_keyboard,
    get_single_button_keyboard,
)
from bot.keyboards.identity_merge_keyboard import get_requester_merge_confirmation_keyboard
from bot.states.settings_states import SettingsStates
from bot.transports.identity_merge_dispatcher import dispatch_target_merge_confirmation
from diary.services.user_profile_service import (
    anonymize_user_account,
    build_account_deletion_menu_view,
    build_edit_profile_menu_view,
    build_list_field_edit_prompt,
    build_profile_screen_view,
    build_psychology_profile_view,
    build_referral_link_view,
    get_user_profile_field,
    get_user_transaction_history,
    process_profile_field_update,
)
from users.services.email_merge_service import (
    EmailMergeService,
    build_requester_merge_result_view,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)

MAX_INLINE_FIELD_LENGTH = 3000

PROFILE_FIELD_ASK_MESSAGE_KEYS = {
    'first_name': 'ask_new_name',
    'email': 'ask_new_email',
    'date_of_birth': 'ask_new_dob',
    'hobbies': 'ask_new_hobbies',
    'life_facts': 'ask_new_life_facts',
}

FIELD_EDIT_CALLBACKS = {
    'edit_profile_name': ('first_name', SettingsStates.waiting_for_name_input, 'ask_new_name'),
    'edit_profile_email': ('email', SettingsStates.waiting_for_email_input, 'ask_new_email'),
    'edit_profile_dob': (
        'date_of_birth',
        SettingsStates.waiting_for_date_of_birth_input,
        'ask_new_dob',
    ),
}

PROFILE_FSM_FIELDS = {
    SettingsStates.waiting_for_name_input.state: ('first_name', 'edit_profile'),
    SettingsStates.waiting_for_email_input.state: ('email', 'edit_profile'),
    SettingsStates.waiting_for_date_of_birth_input.state: ('date_of_birth', 'edit_profile'),
    SettingsStates.waiting_for_hobbies_input.state: ('hobbies', 'edit_profile'),
    SettingsStates.waiting_for_life_facts_input.state: ('life_facts', 'edit_profile'),
}


async def handle_user_profile(user: 'User', send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    view = await build_profile_screen_view(user, language)
    await send_func(view['text'], view.get('reply_markup'))
    return {'ok': True, 'handled': 'user_profile'}


async def _show_edit_menu(user: 'User', send_func: 'SendFunc') -> None:
    language = user.language or 'ru'
    view = await build_edit_profile_menu_view(user, language)
    await send_func(view['text'], view.get('reply_markup'))


async def process_profile_text(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    fsm = max_state.get_fsm_state(max_id)
    language = user.language or 'ru'

    if fsm == SettingsStates.waiting_for_deletion_confirmation_text.state:
        return await _process_deletion_confirm(user, text, send_func, max_id=max_id)

    field_meta = PROFILE_FSM_FIELDS.get(fsm)
    if not field_meta:
        return None

    field_name, back_cb = field_meta
    new_value = (text or '').strip()
    if new_value.lower() in {'назад', 'back', '/start', '/menu'}:
        max_state.clear_fsm_state(max_id)
        await _show_edit_menu(user, send_func)
        return {'ok': True, 'handled': 'profile_field', 'mode': 'cancel'}

    if not new_value:
        await send_func(get_message('invalid_input', language))
        return {'ok': True, 'handled': 'profile_field', 'error': 'empty'}

    update_result = await process_profile_field_update(
        user, field_name, new_value, source_platform='max'
    )
    if not update_result.get('success'):
        error_code = update_result.get('error_code') or update_result.get('error')
        if error_code == 'email_confirmation_required':
            merge_request_id = update_result.get('merge_request_id')
            await send_func(
                get_message('merge_requester_confirmation_prompt', language),
                (
                    get_requester_merge_confirmation_keyboard(merge_request_id, language)
                    if merge_request_id
                    else None
                ),
            )
            return {'ok': True, 'handled': 'profile_field', 'mode': 'merge_required'}
        if error_code == 'email_already_exists':
            await send_func(get_message('email_already_exists', language))
            return {'ok': True, 'handled': 'profile_field', 'error': error_code}
        if error_code in {
            'invalid_email_format',
            'invalid_date_format',
            'invalid_date_future',
            'invalid_input',
            'invalid_format',
        }:
            message_key = (
                'invalid_date_format' if error_code == 'invalid_format' else error_code
            )
            await send_func(get_message(message_key, language))
            ask_key = PROFILE_FIELD_ASK_MESSAGE_KEYS.get(field_name, f'ask_new_{field_name}')
            await send_func(
                get_message(ask_key, language),
                get_single_button_keyboard(language, back_cb, 'btn_back'),
            )
            return {'ok': True, 'handled': 'profile_field', 'error': error_code}

        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'profile_field', 'error': True}

    await send_func(get_message('profile_updated', language))
    max_state.clear_fsm_state(max_id)
    await _show_edit_menu(user, send_func)
    return {'ok': True, 'handled': 'profile_field'}


async def _process_deletion_confirm(user, text, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    expected = get_message('delete_account_btn', language)
    if (text or '').strip() != expected:
        await send_func(get_message('invalid_confirmation_text', language))
        raw = max_state.get_raw_state(max_id)
        await send_func(
            get_message(
                'confirm_account_deletion',
                language,
                balance_warning=raw.get('balance_warning') or '',
            )
        )
        return {'ok': True, 'handled': 'delete_account_confirm', 'error': 'mismatch'}

    result = await anonymize_user_account(user)
    max_state.clear_fsm_state(max_id)
    if result.get('success'):
        await send_func(get_message('account_deletion_confirmed', language))
        return {'ok': True, 'handled': 'delete_account_confirm'}
    await send_func(get_message('account_deletion_error', language))
    return {'ok': True, 'handled': 'delete_account_confirm', 'error': True}


def is_wave6_profile_callback(payload: str) -> bool:
    if payload in {
        'user_profile',
        'view_psychology_profile',
        'view_transaction_history',
        'edit_profile',
        'edit_profile_name',
        'edit_profile_email',
        'edit_profile_dob',
        'edit_profile_hobbies',
        'edit_profile_life_facts',
        'delete_account',
        'confirm_account_deletion_final',
        'delete_account_cancel',
        'get_referral_link',
        'export_user_data',
    }:
        return True
    if payload.startswith('view_profile_field:'):
        return True
    if payload.startswith('merge_requester:'):
        return True
    return False


async def route_wave6_profile_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not is_wave6_profile_callback(payload):
        return None

    language = user.language or 'ru'

    if payload.startswith('merge_requester:'):
        return await _handle_merge_requester(user, payload, send_func, language=language)

    if payload == 'user_profile':
        max_state.clear_fsm_state(max_id)
        return await handle_user_profile(user, send_func)

    if payload == 'view_psychology_profile':
        view = await build_psychology_profile_view(user, language)
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'view_transaction_history':
        result = await get_user_transaction_history(user, language)
        await send_func(
            result.get('message') or get_message('error_generic', language),
            get_single_button_keyboard(language, 'user_profile', 'btn_back'),
        )
        return {'ok': True, 'handled': payload}

    if payload.startswith('view_profile_field:'):
        if not getattr(user, 'is_premium', False):
            await send_func(get_message('feature_requires_premium', language))
            return {'ok': True, 'handled': payload, 'mode': 'premium_required'}
        field_key = payload.split(':', 1)[1]
        field_result = await get_user_profile_field(user, field_key, language)
        if not field_result.get('success'):
            await send_func(field_result.get('text') or get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': True}
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_back_to_psychology', language),
                        callback_data='view_psychology_profile',
                    )
                ]
            ]
        )
        await send_func(field_result['text'], kb)
        return {'ok': True, 'handled': payload}

    if payload == 'edit_profile':
        max_state.clear_fsm_state(max_id)
        await _show_edit_menu(user, send_func)
        return {'ok': True, 'handled': payload}

    if payload in FIELD_EDIT_CALLBACKS:
        _field, state_obj, ask_key = FIELD_EDIT_CALLBACKS[payload]
        max_state.set_fsm_state(max_id, state_obj)
        await send_func(
            get_message(ask_key, language),
            get_single_button_keyboard(language, 'edit_profile', 'btn_back'),
        )
        return {'ok': True, 'handled': payload}

    if payload == 'edit_profile_hobbies':
        view = await build_list_field_edit_prompt(
            user=user, field_name='hobbies', language=language, max_length=MAX_INLINE_FIELD_LENGTH
        )
        if not view.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': True}
        max_state.set_fsm_state(max_id, SettingsStates.waiting_for_hobbies_input)
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'edit_profile_life_facts':
        view = await build_list_field_edit_prompt(
            user=user,
            field_name='life_facts',
            language=language,
            max_length=MAX_INLINE_FIELD_LENGTH,
        )
        if not view.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': True}
        max_state.set_fsm_state(max_id, SettingsStates.waiting_for_life_facts_input)
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'delete_account':
        view = build_account_deletion_menu_view(user, language)
        max_state.set_fsm_state(
            max_id,
            SettingsStates.in_account_deletion_menu,
            balance_warning=view.get('balance_warning'),
        )
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'confirm_account_deletion_final':
        raw = max_state.get_raw_state(max_id)
        await send_func(
            get_message(
                'confirm_account_deletion',
                language,
                balance_warning=raw.get('balance_warning') or '',
            ),
            get_account_deletion_confirmation_keyboard(language),
        )
        max_state.set_fsm_state(
            max_id,
            SettingsStates.waiting_for_deletion_confirmation_text,
            balance_warning=raw.get('balance_warning'),
        )
        return {'ok': True, 'handled': payload}

    if payload == 'delete_account_cancel':
        max_state.clear_fsm_state(max_id)
        await send_func(get_message('account_deletion_cancelled', language))
        from bot.handlers.max.commands import handle_main_menu

        return await handle_main_menu(user, send_func, max_id=max_id)

    if payload == 'get_referral_link':
        view = await build_referral_link_view(user, language)
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'export_user_data':
        if not getattr(user, 'is_premium', False):
            await send_func(get_message('feature_requires_premium', language))
            return {'ok': True, 'handled': payload, 'mode': 'premium_required'}
        await send_func(
            'ℹ️ Экспорт данных (.docx) в MAX пока недоступен. Используйте Telegram или Web.'
        )
        return {'ok': True, 'handled': payload, 'mode': 'deferred'}

    return {'ok': True, 'handled': 'profile_unhandled', 'payload': payload}


async def _handle_merge_requester(user, payload, send_func, *, language: str) -> dict:
    parts = payload.split(':')
    if len(parts) != 3:
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'merge_requester', 'error': True}
    action = parts[1]
    try:
        merge_request_id = int(parts[2])
    except ValueError:
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'merge_requester', 'error': True}

    if action == 'no':
        result = await EmailMergeService.acancel_merge_request_by_id(user, merge_request_id)
        view = build_requester_merge_result_view(result, delivery_result=None, language=language)
        await send_func(view.get('text') or view.get('alert_text') or get_message('error_generic', language))
        return {'ok': True, 'handled': 'merge_requester', 'mode': 'cancel'}

    if action != 'yes':
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'merge_requester', 'error': True}

    result = await EmailMergeService.aconfirm_merge_request_by_id(user, merge_request_id)
    delivery_result = None
    if result.status == 'pending_target_confirmation' and result.merge_request is not None:
        delivery_result = await dispatch_target_merge_confirmation(result.merge_request)
    view = build_requester_merge_result_view(result, delivery_result, language)
    await send_func(view.get('text') or view.get('alert_text') or get_message('error_generic', language))
    return {'ok': True, 'handled': 'merge_requester', 'mode': 'confirm'}
