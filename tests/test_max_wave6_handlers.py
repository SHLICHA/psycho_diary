"""Wave 6 MAX: tasks / therapy / profile."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.messages import route_text_message
from bot.states.settings_states import SettingsStates
from bot.states.task_states import TaskStates
from bot.states.therapy_chat_states import TherapyChatStates
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
        username='max_wave6',
        email='max_wave6@example.com',
        max_id=880006,
        language='ru',
        is_onboarding_completed=True,
        token_balance=5,
    )


@pytest.mark.asyncio
async def test_tasks_callback(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.tasks.task_display_service.build_active_tasks_view',
        new=AsyncMock(return_value={'text': 'Tasks', 'keyboard': None}),
    )
    result = await route_callback(max_user, 'tasks', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'tasks'


@pytest.mark.asyncio
async def test_tasks_command(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.tasks.task_display_service.build_active_tasks_view',
        new=AsyncMock(return_value={'text': 'Tasks', 'keyboard': None}),
    )
    result = await route_text_message(max_user, '/tasks', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'tasks'


@pytest.mark.asyncio
async def test_complete_task_fsm(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.tasks.task_display_service.build_start_completion_view',
        new=AsyncMock(
            return_value={
                'success': True,
                'text': 'Опишите выполнение',
                'keyboard': None,
                'fsm_state': TaskStates.waiting_for_task_completion,
                'fsm_data': {'completing_task_id': 1, 'task_description': 't'},
            }
        ),
    )
    start = await route_callback(max_user, 'complete_task:1', send_func, max_id=max_user.max_id)
    assert start['handled'] == 'complete_task'
    assert max_state.matches_state(max_user.max_id, TaskStates.waiting_for_task_completion)

    done = await route_text_message(max_user, 'Сделал', send_func, max_id=max_user.max_id)
    assert done['handled'] == 'task_completion'
    assert max_state.matches_state(max_user.max_id, TaskStates.describing_feelings)


@pytest.mark.asyncio
async def test_task_feelings_awaits_analysis_notification(max_user, mocker):
    """Анализ должен выполняться в том же запросе (не create_task) — иначе webhook теряет его."""
    send_func = AsyncMock(return_value='status-mid')
    send_func.edit_or_send = AsyncMock(return_value='status-mid')
    send_func.pending_status_id = None

    max_state.set_fsm_state(
        max_user.max_id,
        TaskStates.describing_feelings,
        completing_task_id=42,
        completion_text='Сделал упражнение',
    )

    task_completion = MagicMock()
    completion_response = MagicMock()
    completion_response.success = True
    completion_response.data = {'task_completion': task_completion}
    completion_response.message = None

    mocker.patch(
        'bot.handlers.max.tasks.complete_task_with_feelings_use_case',
        new=AsyncMock(return_value=completion_response),
    )
    analyze_mock = mocker.patch(
        'bot.handlers.max.tasks.analyze_completed_task_for_notification_use_case',
        new=AsyncMock(
            return_value=MagicMock(
                data={
                    'notification_text': 'Анализ готов',
                    'notification_keyboard': None,
                }
            )
        ),
    )

    result = await route_text_message(
        max_user, 'Чувствую спокойствие', send_func, max_id=max_user.max_id
    )

    assert result['handled'] == 'task_feelings'
    assert result.get('error') is None
    analyze_mock.assert_awaited_once()
    send_func.edit_or_send.assert_awaited()
    edit_text = send_func.edit_or_send.await_args.args[1]
    assert edit_text == 'Анализ готов'
    assert not max_state.matches_state(max_user.max_id, TaskStates.describing_feelings)


@pytest.mark.asyncio
async def test_therapy_start_and_message(max_user, mocker):
    send_func = AsyncMock(return_value='status-mid')
    send_func.edit_or_send = AsyncMock(return_value='status-mid')
    send_func.pending_status_id = None
    mocker.patch(
        'bot.handlers.max.therapy.start_therapy_chat',
        new=AsyncMock(return_value={'success': True, 'initial_history': []}),
    )
    mocker.patch(
        'bot.handlers.max.therapy.build_therapy_chat_welcome_view',
        return_value={'text': 'Welcome', 'reply_markup': None},
    )
    start = await route_callback(
        max_user, 'start_therapy_chat', send_func, max_id=max_user.max_id
    )
    assert start['handled'] == 'start_therapy_chat'
    assert max_state.matches_state(max_user.max_id, TherapyChatStates.in_therapy_chat)

    mocker.patch(
        'bot.handlers.max.therapy._charge_tokens',
        new=AsyncMock(return_value={'ok': True, 'charged': False}),
    )
    mocker.patch(
        'bot.handlers.max.therapy.process_user_message_in_chat',
        new=AsyncMock(
            return_value={
                'success': True,
                'response_text': 'AI reply',
                'updated_history': [{'role': 'Пользователь', 'content': 'hi'}],
            }
        ),
    )

    msg = await route_text_message(max_user, 'Здравствуйте', send_func, max_id=max_user.max_id)
    assert msg['handled'] == 'therapy_message'
    send_func.edit_or_send.assert_awaited()
    edited_text = send_func.edit_or_send.await_args.args[1]
    assert edited_text == 'AI reply'


@pytest.mark.asyncio
async def test_profile_screen(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.profile.build_profile_screen_view',
        new=AsyncMock(return_value={'text': 'Profile', 'reply_markup': None}),
    )
    result = await route_callback(max_user, 'user_profile', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'user_profile'


@pytest.mark.asyncio
async def test_edit_name_flow(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    start = await route_callback(
        max_user, 'edit_profile_name', send_func, max_id=max_user.max_id
    )
    assert start['handled'] == 'edit_profile_name'
    assert max_state.matches_state(max_user.max_id, SettingsStates.waiting_for_name_input)

    mocker.patch(
        'bot.handlers.max.profile.process_profile_field_update',
        new=AsyncMock(return_value={'success': True}),
    )
    mocker.patch(
        'bot.handlers.max.profile.build_edit_profile_menu_view',
        new=AsyncMock(return_value={'text': 'Edit', 'reply_markup': None}),
    )
    result = await route_text_message(max_user, 'Иван', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'profile_field'
    assert max_state.get_fsm_state(max_user.max_id) is None


@pytest.mark.asyncio
async def test_merge_requester_cancel(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mock_result = MagicMock(status='cancelled')
    mocker.patch(
        'bot.handlers.max.profile.EmailMergeService.acancel_merge_request_by_id',
        new=AsyncMock(return_value=mock_result),
    )
    mocker.patch(
        'bot.handlers.max.profile.build_requester_merge_result_view',
        return_value={'success': True, 'text': 'Cancelled'},
    )
    result = await route_callback(
        max_user, 'merge_requester:no:99', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'merge_requester'
    assert result['mode'] == 'cancel'
