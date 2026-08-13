"""Wave 1 MAX handlers: start / help / settings / onboarding routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.commands import handle_help, handle_main_menu, handle_settings, handle_start
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.dispatcher import dispatch_max_update
from bot.handlers.max.messages import route_text_message
from bot.states.onboarding_states import OnboardingStates
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def max_user(db):
    return User.objects.create_user(
        username='max_wave1',
        email='max_wave1@example.com',
        max_id=880001,
        language='ru',
        is_onboarding_completed=False,
    )


@pytest.mark.asyncio
async def test_handle_start_begins_onboarding(max_user):
    send_func = AsyncMock(return_value=True)
    result = await handle_start(max_user, send_func, max_id=max_user.max_id)
    assert result['ok'] is True
    assert result['mode'] == 'start_onboarding'
    assert max_state.matches_state(max_user.max_id, OnboardingStates.waiting_for_agreement_1)
    send_func.assert_awaited()
    text = send_func.await_args.args[0]
    assert text


@pytest.mark.asyncio
async def test_onboarding_agree_flow(max_user):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, OnboardingStates.waiting_for_agreement_1)

    r1 = await route_callback(max_user, 'onboarding_agree_1', send_func, max_id=max_user.max_id)
    assert r1['handled'] == 'onboarding_agree_1'
    assert max_state.matches_state(max_user.max_id, OnboardingStates.waiting_for_agreement_2)

    r2 = await route_callback(max_user, 'onboarding_agree_2', send_func, max_id=max_user.max_id)
    assert r2['handled'] == 'onboarding_agree_2'
    assert max_state.matches_state(max_user.max_id, OnboardingStates.waiting_for_timezone_confirmation)


@pytest.mark.asyncio
async def test_help_and_settings(max_user):
    max_user.is_onboarding_completed = True
    await max_user.asave(update_fields=['is_onboarding_completed'])
    send_func = AsyncMock(return_value=True)

    assert (await handle_help(max_user, send_func))['handled'] == 'help'
    assert (await handle_settings(max_user, send_func))['handled'] == 'settings'
    assert send_func.await_count == 2


@pytest.mark.asyncio
async def test_handle_main_menu_uses_message_text_with_stats(max_user, mocker):
    max_user.is_onboarding_completed = True
    max_user.first_name = 'Павел'
    await max_user.asave(update_fields=['is_onboarding_completed', 'first_name'])
    send_func = AsyncMock(return_value='mid')
    mocker.patch(
        'diary.services.main_menu_service.build_main_menu_data',
        new=AsyncMock(
            return_value={
                'message_text': '👋 Привет, Павел!\n📊 Уровень осознанности: 8\n💰 Токены: 72',
                'keyboard': None,
            }
        ),
    )

    result = await handle_main_menu(max_user, send_func, max_id=max_user.max_id)

    assert result['handled'] == 'main_menu'
    send_func.assert_awaited()
    text = send_func.await_args.args[0]
    assert 'Уровень осознанности' in text
    assert 'Токены' in text


@pytest.mark.asyncio
async def test_fallback_for_unknown_text(max_user):
    max_user.is_onboarding_completed = True
    await max_user.asave(update_fields=['is_onboarding_completed'])
    send_func = AsyncMock(return_value=True)
    result = await route_text_message(max_user, 'случайный текст', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'fallback'


@pytest.mark.asyncio
async def test_dispatch_start_message(settings, mocker):
    from asgiref.sync import sync_to_async

    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_BOT_TOKEN = 'test-token'

    mock_send = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.dispatcher.build_send_func',
        return_value=mock_send,
    )
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mocker.patch('bot.handlers.max.dispatcher.MaxClient', return_value=mock_client)

    update = {
        'update_type': 'message_created',
        'message': {
            'sender': {'user_id': 990011},
            'recipient': {'chat_id': 990011},
            'body': {'text': '/start'},
        },
    }
    result = await dispatch_max_update(update)
    assert result.get('ok') is True
    assert result.get('handled') == 'start'
    exists = await sync_to_async(User.objects.filter(max_id=990011).exists)()
    assert exists
    mock_send.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_merge_still_works(settings, mocker, max_user):
    settings.MAX_TRANSPORT_ENABLED = True
    mocker.patch(
        'bot.handlers.max.dispatcher.EmailMergeService.confirm_target_transport_by_request_id',
        return_value=MagicMock(status='confirmed', code=None),
    )
    update = {
        'update_type': 'message_callback',
        'callback': {
            'sender': {'user_id': max_user.max_id},
            'payload': 'merge_target:yes:12',
        },
    }
    result = await dispatch_max_update(update)
    assert result['handled'] == 'merge_target'
    assert result['status'] == 'confirmed'


@pytest.mark.asyncio
async def test_dispatch_callback_answers_via_message(settings, mocker, max_user):
    """Callback закрывается через /answers с message (правка исходного сообщения)."""
    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_BOT_TOKEN = 'test-token'

    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.answer_callback = AsyncMock(return_value=True)
    mock_client.send_message = AsyncMock(return_value=(True, 'mid-1'))
    mocker.patch('bot.handlers.max.dispatcher.MaxClient', return_value=mock_client)

    max_state.set_fsm_state(max_user.max_id, OnboardingStates.waiting_for_agreement_1)

    update = {
        'update_type': 'message_callback',
        'callback': {
            'callback_id': 'cb_dispatch_1',
            'payload': 'onboarding_agree_1',
            'user': {'user_id': max_user.max_id},
        },
    }
    result = await dispatch_max_update(update)
    assert result.get('ok') is True
    assert result.get('handled') == 'onboarding_agree_1'
    assert result.get('callback_answered') is True
    mock_client.answer_callback.assert_awaited()
    kwargs = mock_client.answer_callback.await_args.kwargs
    assert kwargs['callback_id'] == 'cb_dispatch_1'
    assert kwargs.get('text')
    assert kwargs.get('notification') == '✓'
    mock_client.send_message.assert_not_awaited()
