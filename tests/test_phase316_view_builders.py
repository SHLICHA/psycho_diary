"""Unit-тесты Wave 3.16: therapy / settings / onboarding view builders."""
from types import SimpleNamespace

import pytest

from diary.services.therapy_chat_service import TherapyChatService
from diary.services.settings_service import SettingsService
from diary.services.onboarding_service import OnboardingService


def test_build_therapy_chat_welcome_view_premium(mocker):
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.common_keyboards.get_single_button_keyboard',
        return_value='kb',
    )
    user = mocker.Mock(is_premium=True)
    view = TherapyChatService.build_therapy_chat_welcome_view(user, 'ru')
    assert view['mode'] == 'premium'
    assert view['text'] == 'therapy_chat_welcome_premium'
    assert view['reply_markup'] == 'kb'


def test_build_therapy_chat_welcome_view_paid(mocker):
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.common_keyboards.get_single_button_keyboard',
        return_value='kb',
    )
    user = mocker.Mock(is_premium=False)
    view = TherapyChatService.build_therapy_chat_welcome_view(user, 'ru')
    assert view['mode'] == 'paid'
    assert view['text'] == 'therapy_chat_welcome_paid'


@pytest.mark.asyncio
async def test_build_therapy_chat_error_recovery_view(mocker):
    mocker.patch(
        'diary.services.main_menu_service.build_main_menu_data',
        new=mocker.AsyncMock(return_value={
            'message_text': 'menu',
            'keyboard': 'kb_main',
        }),
    )
    view = await TherapyChatService.build_therapy_chat_error_recovery_view(
        mocker.Mock(), 'ru'
    )
    assert view['mode'] == 'main_menu'
    assert view['text'] == 'menu'
    assert view['clear_state'] is True


@pytest.mark.asyncio
async def test_build_task_limit_update_view_limit_exceeded(mocker):
    mocker.patch.object(
        SettingsService,
        'update_task_limit',
        new=mocker.AsyncMock(return_value={
            'success': False,
            'error': 'limit_exceeded',
            'current_level': 3,
            'current_max_tasks': 1,
        }),
    )
    mocker.patch.object(
        SettingsService,
        'build_task_settings_view',
        new=mocker.AsyncMock(return_value={
            'success': True,
            'text': 'screen',
            'reply_markup': 'kb',
        }),
    )
    mocker.patch(
        'diary.services.settings_service.get_message',
        return_value='limit alert',
    )
    view = await SettingsService.build_task_limit_update_view(
        mocker.Mock(), 'ru', increment=1
    )
    assert view['mode'] == 'limit_exceeded'
    assert view['show_alert'] is True
    assert view['alert_text'] == 'limit alert'


def test_build_city_timezone_lookup_view_confirm(mocker):
    mocker.patch(
        'diary.services.settings_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_city_timezone_confirmation_keyboard',
        return_value='kb_confirm',
    )
    view = SettingsService.build_city_timezone_lookup_view(
        {
            'success': True,
            'source': 'cache',
            'timezone_data': {
                'city': 'Moscow',
                'country': 'RU',
                'timezone': 'Europe/Moscow',
            },
        },
        'ru',
        city_name='Moscow',
    )
    assert view['mode'] == 'confirm_single'
    assert view['reply_markup'] == 'kb_confirm'


def test_build_city_timezone_lookup_view_cancel(mocker):
    mocker.patch(
        'diary.services.settings_service.get_message',
        return_value='settings_menu',
    )
    view = SettingsService.build_city_timezone_lookup_view(
        {'success': False}, 'ru', city_name='назад'
    )
    assert view['mode'] == 'cancel'
    assert view['clear_state'] is True


@pytest.mark.asyncio
async def test_set_timezone_and_resolve_next_step_onboarding(mocker):
    mocker.patch.object(
        SettingsService,
        'update_user_timezone',
        new=mocker.AsyncMock(return_value={
            'success': True,
            'new_timezone': 'Europe/Moscow',
        }),
    )
    mocker.patch(
        'diary.services.settings_service.get_message',
        return_value='first entry prompt',
    )
    view = await SettingsService.set_timezone_and_resolve_next_step(
        mocker.Mock(), 'Europe/Moscow', 'ru', is_onboarding=True
    )
    assert view['next'] == 'onboarding_first_entry'
    assert view['set_state'] == 'waiting_for_first_entry'


def test_build_first_onboarding_entry_result_view_success(mocker):
    mocker.patch(
        'diary.services.onboarding_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'diary.services.onboarding_service.get_mood_text',
        return_value='ok',
    )
    response = SimpleNamespace(
        success=True,
        data={'mood_score': 7, 'comment': 'c', 'recommendation': 'r'},
    )
    view = OnboardingService.build_first_onboarding_entry_result_view(response, 'ru')
    assert view['mode'] == 'entry_saved'
    assert view['clear_state'] is True


@pytest.mark.asyncio
async def test_resolve_start_routing_start_onboarding(mocker):
    from bot.states.onboarding_states import OnboardingStates

    mocker.patch(
        'diary.services.onboarding_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_single_button_keyboard',
        return_value='kb',
    )
    user = mocker.Mock(is_onboarding_completed=False)
    view = await OnboardingService.resolve_start_routing_use_case(
        user, 'ru', current_fsm_state=None
    )
    assert view['mode'] == 'start_onboarding'
    assert view['set_state'] == 'waiting_for_agreement_1'
    assert OnboardingStates.waiting_for_agreement_1  # import used / sanity
