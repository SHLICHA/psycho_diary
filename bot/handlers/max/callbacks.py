"""Wave 1 MAX callback handlers (onboarding / help / settings)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from messages import get_message
from bot.handlers.max import state as max_state
from bot.keyboards import (
    get_common_timezones_keyboard,
    get_help_section_keyboard,
    get_language_selection_keyboard,
    get_settings_keyboard,
    get_single_button_keyboard,
    get_timezone_selection_method_keyboard,
)
from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.states.onboarding_states import OnboardingStates
from bot.states.settings_states import SettingsStates
from diary.services.onboarding_service import build_onboarding_timezone_prompt_view
from diary.services.settings_service import (
    build_task_limit_update_view,
    build_task_settings_view,
    confirm_timezone_by_city,
    get_timezone_info,
    set_timezone_and_resolve_next_step,
    toggle_user_auto_analysis,
    toggle_user_notifications,
    update_user_language,
    update_user_timezone,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)

HELP_SECTION_KEYS = {
    'help_faq': 'help_faq_text',
    'help_how_to_start': 'help_how_to_start_text',
    'help_writing_entries': 'help_writing_entries_text',
    'help_tasks': 'help_tasks_text',
    'help_privacy': 'help_privacy_text',
    'help_subscription_and_tokens': 'help_subscription_and_tokens_text',
    'help_referral_program': 'help_referral_program_text',
    'help_account_merge': 'help_account_merge_text',
}

HELP_GUIDE_KEYS = {
    'help_guide': 'help_guide_text',
    'help_guide_writing_entries': 'help_writing_entries_text',
    'help_guide_tasks': 'help_tasks_text',
    'help_guide_progress': 'help_progress_text',
    'help_guide_profile': 'help_profile_text',
    'help_guide_settings': 'help_settings_text',
    'help_guide_therapy_chat': 'help_therapy_chat_text',
}


async def route_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
    max_client=None,
    callback_id: str | None = None,
) -> dict:
    payload = (payload or '').strip()
    language = user.language or 'ru'

    from bot.handlers.max.diary import route_wave2_callback
    from bot.handlers.max.payments import route_wave3_callback
    from bot.handlers.max.feedback import route_wave4_callback
    from bot.handlers.max.admin import route_wave5_callback
    from bot.handlers.max.tasks import route_wave6_tasks_callback
    from bot.handlers.max.therapy import route_wave6_therapy_callback
    from bot.handlers.max.profile import route_wave6_profile_callback

    wave2 = await route_wave2_callback(
        user, payload, send_func, max_id=max_id, max_client=max_client
    )
    if wave2 is not None:
        return wave2

    wave3 = await route_wave3_callback(user, payload, send_func, max_id=max_id)
    if wave3 is not None:
        return wave3

    wave4 = await route_wave4_callback(user, payload, send_func, max_id=max_id)
    if wave4 is not None:
        return wave4

    wave5 = await route_wave5_callback(user, payload, send_func, max_id=max_id)
    if wave5 is not None:
        return wave5

    wave6_tasks = await route_wave6_tasks_callback(
        user, payload, send_func, max_id=max_id, max_client=max_client
    )
    if wave6_tasks is not None:
        return wave6_tasks

    wave6_therapy = await route_wave6_therapy_callback(user, payload, send_func, max_id=max_id)
    if wave6_therapy is not None:
        return wave6_therapy

    wave6_profile = await route_wave6_profile_callback(user, payload, send_func, max_id=max_id)
    if wave6_profile is not None:
        return wave6_profile

    if payload in {'onboarding_agree_1', 'onboarding_agree_2', 'onboarding_ask_timezone'}:
        return await _handle_onboarding_callback(
            user,
            payload,
            send_func,
            max_id=max_id,
            max_client=max_client,
            callback_id=callback_id,
        )

    if payload == 'help' or payload == 'help_back_to_main':
        from bot.handlers.max.commands import handle_help
        return await handle_help(user, send_func)

    if payload == 'help_support':
        from bot.handlers.max.feedback import handle_feedback_start
        return await handle_feedback_start(user, send_func, max_id=max_id)

    if payload in HELP_SECTION_KEYS:
        await send_func(
            get_message(HELP_SECTION_KEYS[payload], language=language),
            get_help_section_keyboard(language),
        )
        return {'ok': True, 'handled': payload}

    if payload in HELP_GUIDE_KEYS:
        keyboard = (
            get_help_guide_section_keyboard(language)
            if payload.startswith('help_guide')
            else get_help_section_keyboard(language)
        )
        await send_func(get_message(HELP_GUIDE_KEYS[payload], language=language), keyboard)
        return {'ok': True, 'handled': payload}

    if payload == 'settings':
        from bot.handlers.max.commands import handle_settings
        return await handle_settings(user, send_func)

    if payload == 'main_menu':
        from bot.handlers.max.commands import handle_main_menu
        return await handle_main_menu(user, send_func, max_id=max_id)

    if payload == 'settings_change_language':
        max_state.set_fsm_state(max_id, SettingsStates.waiting_for_language_choice)
        await send_func(
            get_message('settings_menu', language=language),
            get_language_selection_keyboard(language),
        )
        return {'ok': True, 'handled': payload}

    if payload.startswith('set_language:'):
        return await _set_language(user, payload, send_func, max_id=max_id)

    if payload == 'settings_toggle_notifications':
        result = await toggle_user_notifications(user)
        if result.get('success'):
            await send_func(
                get_message('settings_menu', language=language),
                get_settings_keyboard(user, language),
            )
        else:
            await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': payload}

    if payload == 'settings_toggle_auto_analysis':
        result = await toggle_user_auto_analysis(user)
        if result.get('success'):
            await send_func(
                get_message('settings_menu', language=language),
                get_settings_keyboard(user, language),
            )
        else:
            await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': payload}

    if payload == 'settings_tasks':
        view = await build_task_settings_view(user, language)
        await send_func(view.get('text') or get_message('error_generic', language), view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'settings_increase_tasks_limit':
        view = await build_task_limit_update_view(user, language, increment=1)
        if view.get('refresh_screen'):
            await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'settings_decrease_tasks_limit':
        view = await build_task_limit_update_view(user, language, increment=-1)
        if view.get('refresh_screen'):
            await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': payload}

    if payload == 'settings_change_timezone':
        info = await get_timezone_info(user)
        current_tz = info.get('current_timezone', user.timezone or 'UTC')
        await send_func(
            get_message('ask_timezone_selection', language, current_timezone=current_tz),
            get_timezone_selection_method_keyboard(language, current_tz, show_back_button=True),
        )
        return {'ok': True, 'handled': payload}

    if payload == 'timezone_select_from_list':
        info = await get_timezone_info(user)
        current_tz = info.get('current_timezone', user.timezone or 'UTC')
        await send_func(
            get_message('select_timezone_title', language, current_timezone=current_tz),
            get_common_timezones_keyboard(language, current_tz),
        )
        return {'ok': True, 'handled': payload}

    if payload == 'timezone_enter_city':
        max_state.set_fsm_state(max_id, SettingsStates.waiting_for_city_input)
        await send_func(
            get_message('enter_city', language),
            get_single_button_keyboard(language, 'settings', 'btn_back'),
        )
        return {'ok': True, 'handled': payload}

    if payload.startswith('set_timezone:'):
        return await _set_timezone(user, payload.split(':', 1)[1], send_func, max_id=max_id)

    if payload.startswith('select_timezone:'):
        return await _set_timezone(user, payload.split(':', 1)[1], send_func, max_id=max_id)

    if payload.startswith('confirm_timezone:'):
        tz_name = payload.split(':', 1)[1]
        result = await confirm_timezone_by_city(user, {'timezone': tz_name})
        if not result.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': True}
        return await _after_timezone_set(user, tz_name, send_func, max_id=max_id, language=language)

    # Unknown Wave 1 callback — soft fallback text
    logger.info('[MAX callbacks] unhandled payload=%s max_id=%s', payload, max_id)
    await send_func(
        get_message('unexpected_text_message', language),
        await get_main_menu_keyboard(language, user),
    )
    return {'ok': True, 'handled': 'unhandled_callback', 'payload': payload}


async def _handle_onboarding_callback(
    user,
    payload,
    send_func,
    *,
    max_id: int,
    max_client=None,
    callback_id: str | None = None,
) -> dict:
    language = user.language or 'ru'
    # callback_id / max_client: ack уже сделан в dispatcher через notification;
    # контент шлём новым сообщением (как wb_analyzer + docs POST /messages).

    if payload == 'onboarding_agree_1':
        if not max_state.matches_state(max_id, OnboardingStates.waiting_for_agreement_1):
            logger.warning(
                '[MAX onboarding] wrong_state agree_1 max_id=%s current=%s',
                max_id,
                max_state.get_fsm_state(max_id),
            )
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': 'wrong_state'}
        keyboard = get_single_button_keyboard(
            language, button_callback_data='onboarding_agree_2', button_text='btn_next'
        )
        await send_func(get_message('onboarding_project_info', language), keyboard)
        max_state.set_fsm_state(max_id, OnboardingStates.waiting_for_agreement_2)
        return {'ok': True, 'handled': payload}

    if payload in {'onboarding_agree_2', 'onboarding_ask_timezone'}:
        if payload == 'onboarding_agree_2' and not max_state.matches_state(
            max_id, OnboardingStates.waiting_for_agreement_2
        ):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': 'wrong_state'}
        view = await build_onboarding_timezone_prompt_view(
            user, language, include_info_prefix=True, show_back_button=False
        )
        if not view.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': payload, 'error': True}
        if view.get('set_origin'):
            max_state.update_state_data(max_id, origin=view['set_origin'])
        await send_func(view['text'], view.get('reply_markup'))
        max_state.set_fsm_state(max_id, OnboardingStates.waiting_for_timezone_confirmation)
        return {'ok': True, 'handled': payload}

    return {'ok': True, 'ignored': True}


async def _set_language(user, payload, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    new_language = payload.split(':', 1)[1]
    result = await update_user_language(user, new_language)
    if not result.get('success'):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'set_language', 'error': True}
    await user.arefresh_from_db()
    max_state.clear_fsm_state(max_id)
    await send_func(
        get_message('language_changed', language=new_language),
        get_settings_keyboard(user, new_language),
    )
    return {'ok': True, 'handled': 'set_language'}


async def _set_timezone(user, timezone_str: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    is_onboarding = max_state.matches_state(
        max_id, OnboardingStates.waiting_for_timezone_confirmation
    )
    view = await set_timezone_and_resolve_next_step(
        user=user,
        new_timezone_str=timezone_str,
        language=language,
        is_onboarding=is_onboarding,
    )
    if not view.get('success'):
        await send_func(view.get('alert_text') or get_message('error_generic', language))
        return {'ok': True, 'handled': 'set_timezone', 'error': True}

    await send_func(view['text'], view.get('reply_markup'))
    if view.get('next') == 'onboarding_first_entry':
        max_state.set_fsm_state(max_id, OnboardingStates.waiting_for_first_entry)
    elif view.get('clear_state'):
        max_state.clear_fsm_state(max_id)
    return {'ok': True, 'handled': 'set_timezone', 'mode': view.get('mode')}


async def _after_timezone_set(user, timezone_str, send_func, *, max_id: int, language: str) -> dict:
    is_onboarding = max_state.matches_state(
        max_id, OnboardingStates.waiting_for_timezone_confirmation
    ) or max_state.get_raw_state(max_id).get('origin') == 'onboarding_timezone_setup'
    if is_onboarding:
        return await _set_timezone(user, timezone_str, send_func, max_id=max_id)
    result = await update_user_timezone(user, timezone_str)
    if not result.get('success'):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'confirm_timezone', 'error': True}
    await send_func(
        get_message('timezone_changed', language, timezone=timezone_str),
        get_settings_keyboard(user, language),
    )
    max_state.clear_fsm_state(max_id)
    return {'ok': True, 'handled': 'confirm_timezone'}
