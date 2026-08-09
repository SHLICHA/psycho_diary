"""Wave 5 MAX: admin stats / feedbacks / broadcast."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache
from django.test import override_settings

from bot.handlers.max import state as max_state
from bot.handlers.max.admin import (
    STATE_BROADCAST_MESSAGE,
    STATE_BROADCAST_TYPE,
    STATE_WAITING_FEEDBACK_REPLY,
)
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.messages import route_text_message
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
        username='max_wave5',
        email='max_wave5@example.com',
        max_id=880005,
        language='ru',
        is_onboarding_completed=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username='max_wave5_admin',
        email='max_wave5_admin@example.com',
        max_id=990005,
        language='ru',
        is_onboarding_completed=True,
        is_staff=True,
    )


@pytest.mark.asyncio
async def test_admin_forbidden_for_regular_user(max_user):
    send_func = AsyncMock(return_value=True)
    result = await route_text_message(max_user, '/admin', send_func, max_id=max_user.max_id)
    assert result['mode'] == 'forbidden'


@pytest.mark.asyncio
async def test_admin_menu_for_staff(admin_user):
    send_func = AsyncMock(return_value=True)
    result = await route_text_message(admin_user, '/admin', send_func, max_id=admin_user.max_id)
    assert result['handled'] == 'admin'
    assert 'stats' in send_func.await_args.args[0].lower() or 'Админ' in send_func.await_args.args[0]


@pytest.mark.asyncio
@override_settings(DEVELOPER_MAX_USER_ID='880005')
async def test_stats_via_developer_max_id(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.admin.admin_service.get_admin_stats',
        new=AsyncMock(return_value={'total_users': 1, 'active_users': 1}),
    )
    mocker.patch(
        'bot.handlers.max.admin.admin_service.build_admin_stats_report',
        return_value='STATS_OK',
    )
    result = await route_text_message(max_user, '/stats', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'stats'
    assert any('STATS_OK' in str(c.args[0]) for c in send_func.await_args_list)


@pytest.mark.asyncio
async def test_feedbacks_empty(admin_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.admin.feedback_service.get_unprocessed_feedbacks',
        new=AsyncMock(return_value=[]),
    )
    result = await route_text_message(
        admin_user, '/feedbacks', send_func, max_id=admin_user.max_id
    )
    assert result['handled'] == 'feedbacks'
    assert result['mode'] == 'empty'


@pytest.mark.asyncio
async def test_broadcast_flow(admin_user, mocker):
    send_func = AsyncMock(return_value=True)
    start = await route_text_message(
        admin_user, '/broadcast', send_func, max_id=admin_user.max_id
    )
    assert start['handled'] == 'broadcast_start'
    assert max_state.get_fsm_state(admin_user.max_id) == STATE_BROADCAST_TYPE

    typed = await route_callback(
        admin_user, 'broadcast_regular', send_func, max_id=admin_user.max_id
    )
    assert typed['handled'] == 'broadcast_regular'
    assert max_state.get_fsm_state(admin_user.max_id) == STATE_BROADCAST_MESSAGE

    mock_client = MagicMock()
    mock_client.send_message = AsyncMock(return_value=True)
    mock_client.close = MagicMock(return_value=None)
    mocker.patch('bot.handlers.max.admin._build_max_client', return_value=mock_client)
    mocker.patch(
        'bot.handlers.max.admin.admin_service.get_max_users_for_broadcast',
        new=AsyncMock(return_value=[(admin_user.max_id, 'ru')]),
    )
    mocker.patch(
        'bot.handlers.max.admin.admin_service.send_max_broadcast_message',
        new=AsyncMock(return_value={'success': 1, 'failed': 0}),
    )

    sent = await route_text_message(
        admin_user, 'Привет всем', send_func, max_id=admin_user.max_id
    )
    assert sent['handled'] == 'broadcast_send'
    assert max_state.get_fsm_state(admin_user.max_id) is None


@pytest.mark.asyncio
async def test_cancel_broadcast(admin_user):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(admin_user.max_id, STATE_BROADCAST_TYPE)
    result = await route_callback(
        admin_user, 'cancel_broadcast', send_func, max_id=admin_user.max_id
    )
    assert result['handled'] == 'cancel_broadcast'
    assert max_state.get_fsm_state(admin_user.max_id) is None


@pytest.mark.asyncio
async def test_reply_feedback_starts_fsm(admin_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.admin.feedback_service.build_admin_reply_prompt_view',
        new=AsyncMock(
            return_value={
                'success': True,
                'text': 'Введите ответ',
                'reply_markup': None,
            }
        ),
    )
    result = await route_callback(
        admin_user, 'reply_feedback_42', send_func, max_id=admin_user.max_id
    )
    assert result['handled'] == 'reply_feedback'
    assert max_state.get_fsm_state(admin_user.max_id) == STATE_WAITING_FEEDBACK_REPLY
    assert max_state.get_raw_state(admin_user.max_id).get('replying_to_feedback_id') == 42
