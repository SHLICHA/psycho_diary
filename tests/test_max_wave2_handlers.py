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
    send_func = AsyncMock(return_value='status-mid')
    send_func.edit_or_send = AsyncMock(return_value='status-mid')
    send_func.pending_status_id = None
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
    send_func.assert_awaited_once()
    first_text = send_func.await_args.args[0]
    assert 'Обрабатываю' in first_text or 'Processing' in first_text
    send_func.edit_or_send.assert_awaited_once_with('status-mid', 'Сохранено', None)


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


@pytest.mark.asyncio
async def test_rate_analysis_callback_saves_rating(max_user, mocker):
    send_func = AsyncMock(return_value='mid')
    submit = mocker.patch(
        'bot.handlers.max.diary.diary_display_service.submit_analysis_rating_use_case',
        new=AsyncMock(return_value={'success': True, 'rating': 5}),
    )
    open_menu = mocker.patch(
        'bot.handlers.max.commands.handle_main_menu',
        new=AsyncMock(return_value={'ok': True, 'handled': 'main_menu'}),
    )

    result = await route_callback(
        max_user, 'rate_analysis:216:5', send_func, max_id=max_user.max_id
    )

    assert result['handled'] == 'rate_analysis'
    assert result.get('mode') == 'saved'
    submit.assert_awaited_once_with(216, max_user, 5)
    open_menu.assert_awaited_once_with(max_user, send_func, max_id=max_user.max_id)


@pytest.mark.asyncio
async def test_rate_analysis_callback_already_rated(max_user, mocker):
    send_func = AsyncMock(return_value='mid')
    mocker.patch(
        'bot.handlers.max.diary.diary_display_service.submit_analysis_rating_use_case',
        new=AsyncMock(return_value={'success': False, 'error': 'already_rated'}),
    )
    open_menu = mocker.patch(
        'bot.handlers.max.commands.handle_main_menu',
        new=AsyncMock(return_value={'ok': True, 'handled': 'main_menu'}),
    )

    result = await route_callback(
        max_user, 'rate_analysis:216:3', send_func, max_id=max_user.max_id
    )

    assert result['handled'] == 'rate_analysis'
    assert result.get('mode') == 'already_rated'
    open_menu.assert_not_awaited()
    send_func.assert_awaited()


@pytest.mark.asyncio
async def test_weekly_details_callback(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.diary.get_detailed_weekly_changes',
        new=AsyncMock(
            return_value={
                'success': True,
                'message': 'Подробный прогресс за неделю',
            }
        ),
    )
    result = await route_callback(
        max_user, 'weekly_details', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'weekly_details'
    assert result.get('error') is None
    send_func.assert_awaited()
    assert 'Подробный прогресс' in send_func.await_args.args[0]


@pytest.mark.asyncio
async def test_weekly_progress_list_callback(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    latest = MagicMock()
    latest.week_start_date = __import__('datetime').date(2026, 8, 4)
    mocker.patch(
        'bot.handlers.max.diary.get_latest_weekly_analysis',
        new=AsyncMock(return_value=latest),
    )
    mocker.patch(
        'bot.handlers.max.diary.build_weekly_analysis_page_view',
        new=AsyncMock(
            return_value={'text': 'Анализ недели', 'reply_markup': None}
        ),
    )
    result = await route_callback(
        max_user, 'weekly_progress_list', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'weekly_progress_list'
    assert result.get('error') is None
    send_func.assert_awaited_once_with('Анализ недели', None)


@pytest.mark.asyncio
async def test_mood_chart_requires_premium(max_user):
    send_func = AsyncMock(return_value=True)
    max_user.is_premium = False
    result = await route_callback(
        max_user, 'show_mood_chart_week', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'show_mood_chart_week'
    assert result.get('mode') == 'premium_required'
    send_func.assert_awaited()


@pytest.mark.asyncio
async def test_mood_chart_sends_image(max_user, mocker):
    import io

    send_func = AsyncMock(return_value='status-mid')
    send_func.edit_or_send = AsyncMock(return_value='status-mid')
    send_func.pending_status_id = None
    max_user.is_premium = True
    max_client = AsyncMock()
    max_client.send_image = AsyncMock(return_value=True)
    mocker.patch(
        'bot.utils.mood_chart.generate_mood_chart_image',
        new=AsyncMock(return_value=io.BytesIO(b'png-bytes')),
    )

    result = await route_callback(
        max_user,
        'show_mood_chart_week',
        send_func,
        max_id=max_user.max_id,
        max_client=max_client,
    )

    assert result['handled'] == 'show_mood_chart_week'
    assert result.get('error') is None
    max_client.send_image.assert_awaited_once()
    assert max_client.send_image.await_args.kwargs['filename'] == 'mood_chart.png'
