"""Wave 1 MAX command handlers (start / help / settings / fallback)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from messages import get_message
from bot.handlers.max import state as max_state
from bot.keyboards import get_help_keyboard, get_settings_keyboard
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.states.onboarding_states import OnboardingStates
from diary.services.onboarding_service import resolve_start_routing_use_case

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)


async def handle_web(user: 'User', send_func: 'SendFunc') -> dict:
    """Ссылка session-handoff на web (паритет Telegram /web)."""
    from django.conf import settings

    from users.services.auth_token_service import create_messenger_auth_token

    language = user.language or 'ru'
    token = create_messenger_auth_token(user.id, platform='max')
    web_app_url = getattr(settings, 'WEB_APP_URL', 'http://127.0.0.1:8000').rstrip('/')
    auth_url = f'{web_app_url}/auth/max/?token={token}'
    await send_func(get_message('web_link_generated', language, auth_url=auth_url))
    return {'ok': True, 'handled': 'web'}


async def handle_link_max_payload(user: 'User', send_func: 'SendFunc', *, max_id: int, payload: str) -> dict:
    """Привязка MAX к web по start payload link_<token>."""
    from diary.services.user_service import link_max_identity, resolve_max_web_link_target
    from users.services.auth_token_service import validate_max_link_token

    language = user.language or 'ru'
    token = payload.replace('link_', '', 1).strip()
    if not token:
        await send_func(get_message('web_link_invalid', language))
        return {'ok': True, 'handled': 'link_max', 'error': 'invalid'}
    web_user_id = validate_max_link_token(token)
    if not web_user_id:
        await send_func(get_message('web_link_expired', language))
        return {'ok': True, 'handled': 'link_max', 'error': 'expired'}
    web_user, link_error = await resolve_max_web_link_target(web_user_id, max_id)
    if link_error == 'web_user_not_found':
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'link_max', 'error': link_error}
    if link_error == 'max_already_linked':
        await send_func(get_message('web_link_max_already_linked', language))
        return {'ok': True, 'handled': 'link_max', 'error': link_error}
    if link_error == 'account_already_linked':
        await send_func(get_message('web_link_account_already_linked', language))
        return {'ok': True, 'handled': 'link_max', 'error': link_error}
    await link_max_identity(web_user, max_id)
    await send_func(
        get_message('web_link_max_success', language, username=web_user.username or str(web_user.id))
    )
    return {'ok': True, 'handled': 'link_max'}


async def handle_start(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    current = max_state.get_fsm_state(max_id)
    view = await resolve_start_routing_use_case(
        user=user,
        language=language,
        current_fsm_state=current,
        was_reactivated=False,
    )
    if not view.get('success'):
        await send_func(view.get('text') or get_message('error_generic', language))
        return {'ok': True, 'handled': 'start', 'mode': 'error'}

    if view.get('clear_state'):
        max_state.clear_fsm_state(max_id)
    if view.get('set_state') == 'waiting_for_agreement_1':
        max_state.set_fsm_state(max_id, OnboardingStates.waiting_for_agreement_1)
    elif view.get('set_state'):
        max_state.set_fsm_state(max_id, view['set_state'])

    if view.get('reactivation_text'):
        await send_func(view['reactivation_text'])

    markup = view.get('reply_markup')
    if view.get('use_main_menu_keyboard'):
        markup = await get_main_menu_keyboard(language, user)
    await send_func(view['text'], markup)
    return {'ok': True, 'handled': 'start', 'mode': view.get('mode')}


async def handle_help(user: 'User', send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    await send_func(get_message('help_main_text', language=language), get_help_keyboard(language))
    return {'ok': True, 'handled': 'help'}


async def handle_settings(user: 'User', send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    await send_func(
        get_message('settings_menu', language=language),
        get_settings_keyboard(user, language),
    )
    return {'ok': True, 'handled': 'settings'}


async def handle_main_menu(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    from diary.services.main_menu_service import build_main_menu_data

    language = user.language or 'ru'
    max_state.clear_fsm_state(max_id)
    menu = await build_main_menu_data(user=user, language=language)
    markup = menu.get('keyboard') or await get_main_menu_keyboard(language, user)
    await send_func(
        menu.get('message_text') or get_message('main_menu', language),
        markup,
    )
    return {'ok': True, 'handled': 'main_menu'}


async def handle_fallback(user: 'User', send_func: 'SendFunc', *, is_voice: bool = False) -> dict:
    language = user.language or 'ru'
    key = 'unexpected_voice_message' if is_voice else 'unexpected_text_message'
    await send_func(
        get_message(key, language),
        await get_main_menu_keyboard(language, user),
    )
    return {'ok': True, 'handled': 'fallback'}
