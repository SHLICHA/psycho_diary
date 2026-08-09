"""Wave 2 MAX: diary / archive / progress handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.diary import handle_archive, handle_new_entry_prompt, handle_progress
from bot.handlers.max.messages import route_text_message
from bot.states.diary_states import DiaryStates
from core.service_response import ServiceResponse
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
        username='max_wave2',
        email='max_wave2@example.com',
        max_id=880002,
        language='ru',
        is_onboarding_completed=True,
    )


@pytest.mark.asyncio
async def test_new_entry_prompt_sets_fsm(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.diary.smart_prompt_manager.get_prompt_for_user',
        new=AsyncMock(return_value='Напишите запись'),
    )
    result = await handle_new_entry_prompt(max_user, send_func, max_id=max_user.max_id)
    assert result['handled'] == 'new_entry'
    assert max_state.matches_state(max_user.max_id, DiaryStates.waiting_for_text_entry)
    send_func.assert_awaited()


@pytest.mark.asyncio
async def test_process_new_entry_use_case(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, DiaryStates.waiting_for_text_entry)
    mocker.patch(
        'bot.handlers.max.diary.diary_service.process_new_entry_use_case',
        new=AsyncMock(return_value=ServiceResponse.ok(data={'entry': MagicMock(), 'analysis': None})),
    )
    mocker.patch(
        'bot.handlers.max.diary.build_new_entry_outcome_view',
        new=AsyncMock(
            return_value={
                'text': 'Сохранено',
                'reply_markup': None,
                'fsm_action': 'done',
                'mode': 'saved',
            }
        ),
    )
    result = await route_text_message(
        max_user, 'Сегодня хороший день', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'new_entry_process'
    assert max_state.get_fsm_state(max_user.max_id) is None


@pytest.mark.asyncio
async def test_progress_and_archive_callbacks(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.diary.build_progress_screen_view',
        new=AsyncMock(return_value={'text': 'Прогресс', 'reply_markup': None}),
    )
    mocker.patch(
        'bot.handlers.max.diary.get_smart_calendar_keyboard',
        new=AsyncMock(return_value=None),
    )

    progress = await route_callback(max_user, 'progress', send_func, max_id=max_user.max_id)
    assert progress['handled'] == 'progress'

    archive = await route_callback(max_user, 'archive', send_func, max_id=max_user.max_id)
    assert archive['handled'] == 'archive'


@pytest.mark.asyncio
async def test_progress_command(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.diary.build_progress_screen_view',
        new=AsyncMock(return_value={'text': 'Прогресс', 'reply_markup': None}),
    )
    result = await route_text_message(max_user, '/progress', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'progress'


@pytest.mark.asyncio
async def test_handle_progress_direct(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.diary.build_progress_screen_view',
        new=AsyncMock(return_value={'text': 'OK', 'reply_markup': None}),
    )
    assert (await handle_progress(max_user, send_func))['handled'] == 'progress'
    assert (await handle_archive(max_user, send_func, max_id=max_user.max_id))['handled'] == 'archive'
