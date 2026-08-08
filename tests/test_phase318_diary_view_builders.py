"""Unit-тесты view/use-case builders для Phase 3.18 (без БД)."""
from datetime import date
from types import SimpleNamespace

import pytest

from bot.presenters.diary_presenter import (
    build_new_entry_outcome_view,
    build_delete_entire_day_confirm_view,
)
from bot.services.diary_service import DiaryService
from diary.services.diary_display_service import DiaryDisplayService
from core.service_response import ServiceResponse


@pytest.mark.asyncio
async def test_build_new_entry_outcome_view_failure(mocker):
    view = await build_new_entry_outcome_view(
        ServiceResponse(success=False, data={'validation_comment_ai': 'bad'}),
        user=object(),
        language='ru',
    )
    assert view['mode'] == 'failure'
    assert view['fsm_action'] == 'clear'
    assert 'не прошла валидацию' in view['text']


@pytest.mark.asyncio
async def test_build_new_entry_outcome_view_clarification(mocker):
    entry = SimpleNamespace(id=42)
    result = {
        'entry': entry,
        'analysis': SimpleNamespace(mood_score=5, comment='c', recommendation='r'),
        'needs_clarification': True,
        'clarification_questions': ['Q1?'],
        'suggested_task': None,
        'streak_bonus_info': {},
    }
    view = await build_new_entry_outcome_view(
        ServiceResponse(success=True, data=result),
        user=object(),
        language='ru',
    )
    assert view['mode'] == 'clarification'
    assert view['fsm_action'] == 'clarification'
    assert view['clarifying_entry_id'] == 42
    assert '1. Q1?' in view['text']


@pytest.mark.asyncio
async def test_build_new_entry_outcome_view_success(mocker):
    mocker.patch(
        'diary.services.diary_display_service.diary_display_service.build_entry_result_keyboard',
        new=mocker.AsyncMock(return_value='keyboard'),
    )
    entry = SimpleNamespace(id=7)
    result = {
        'entry': entry,
        'analysis': SimpleNamespace(mood_score=8, comment='ok', recommendation='go'),
        'needs_clarification': False,
        'clarification_questions': [],
        'suggested_task': None,
        'streak_bonus_info': {},
    }
    view = await build_new_entry_outcome_view(
        ServiceResponse(success=True, data=result),
        user=object(),
        language='ru',
    )
    assert view['mode'] == 'success'
    assert view['fsm_action'] == 'clear'
    assert view['should_trigger_prompt'] is True
    assert view['reply_markup'] == 'keyboard'


@pytest.mark.asyncio
async def test_start_add_comment_use_case_branches(mocker):
    service = DiaryService()
    user = SimpleNamespace(telegram_id=1)

    mocker.patch.object(service, 'get_user_entry_by_id', new=mocker.AsyncMock(return_value=None))
    assert (await service.start_add_comment_use_case(user, 1))['mode'] == 'not_found'

    mocker.patch.object(
        service,
        'get_user_entry_by_id',
        new=mocker.AsyncMock(return_value=SimpleNamespace(user_comment='exists')),
    )
    assert (await service.start_add_comment_use_case(user, 2))['mode'] == 'already_added'

    mocker.patch.object(
        service,
        'get_user_entry_by_id',
        new=mocker.AsyncMock(return_value=SimpleNamespace(user_comment=None)),
    )
    assert (await service.start_add_comment_use_case(user, 3))['mode'] == 'allow'


@pytest.mark.asyncio
async def test_build_day_first_entry_view_delegates(mocker):
    display_service = DiaryDisplayService()
    expected = {'success': True, 'mode': 'entries'}
    mock_build = mocker.patch.object(
        display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value=expected),
    )
    result = await display_service.build_day_first_entry_view(object(), date(2026, 8, 8), 'ru')
    assert result == expected
    mock_build.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_analysis_rating_use_case_bounds(mocker):
    display_service = DiaryDisplayService()
    submit_mock = mocker.patch.object(
        display_service,
        'submit_rating',
        new=mocker.AsyncMock(return_value={'success': True}),
    )

    invalid = await display_service.submit_analysis_rating_use_case(1, object(), 0)
    assert invalid['error'] == 'invalid_rating'
    submit_mock.assert_not_called()

    valid = await display_service.submit_analysis_rating_use_case(1, object(), 4)
    assert valid['success'] is True
    submit_mock.assert_awaited_once_with(1, mocker.ANY, 4)


def test_build_delete_entire_day_confirm_view(mocker):
    mocker.patch(
        'bot.presenters.diary_presenter.get_message',
        return_value='delete {date}?',
    )
    mocker.patch(
        'bot.presenters.diary_presenter.get_button_text',
        side_effect=lambda key, language=None: key,
    )
    target_date = date(2026, 8, 8)
    view = build_delete_entire_day_confirm_view(target_date, 'ru')
    assert '08.08.2026' in view['text']
    assert view['keyboard'].inline_keyboard[0][0].callback_data == 'confirm_delete_entire_day:2026-08-08'
    assert view['keyboard'].inline_keyboard[0][1].callback_data == 'archive'


@pytest.mark.asyncio
async def test_delete_entire_day_use_case_success(mocker):
    import importlib

    diary_service_module = importlib.import_module('bot.services.diary_service')

    service = DiaryService()
    user = object()
    target_date = date(2026, 8, 8)
    mocker.patch.object(service, 'delete_all_entries_for_day', new=mocker.AsyncMock(return_value=True))
    mocker.patch.object(
        diary_service_module,
        'get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_smart_calendar_keyboard',
        new=mocker.AsyncMock(return_value='calendar_kb'),
    )

    result = await service.delete_entire_day_use_case(user, target_date, 'ru')
    assert result['success'] is True
    assert result['alert_message'] == 'day_deleted_success'
    assert result['archive_view']['keyboard'] == 'calendar_kb'


@pytest.mark.asyncio
async def test_delete_entire_day_use_case_failure(mocker):
    import importlib

    diary_service_module = importlib.import_module('bot.services.diary_service')

    service = DiaryService()
    mocker.patch.object(service, 'delete_all_entries_for_day', new=mocker.AsyncMock(return_value=False))
    mocker.patch.object(
        diary_service_module,
        'get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.delete_entire_day_use_case(object(), date(2026, 8, 8), 'ru')
    assert result['success'] is False
    assert result['alert_message'] == 'error_processing'


@pytest.mark.asyncio
async def test_start_full_day_reanalysis_use_case_no_entries(mocker):
    import importlib

    diary_service_module = importlib.import_module('bot.services.diary_service')

    service = DiaryService()
    user = SimpleNamespace(telegram_id=1)
    mocker.patch.object(service, 'prepare_combined_entry_for_analysis', new=mocker.AsyncMock(return_value=None))
    mocker.patch.object(
        diary_service_module,
        'get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.start_full_day_reanalysis_use_case(user, date(2026, 8, 8), 'ru')
    assert result['mode'] == 'no_entries'
    assert result['text'] == 'no_entries_for_analysis'
    assert result['confirm_alert'] == 'day_analysis_confirmed'


@pytest.mark.asyncio
async def test_start_full_day_reanalysis_use_case_ready(mocker):
    import importlib

    diary_service_module = importlib.import_module('bot.services.diary_service')

    service = DiaryService()
    user = SimpleNamespace(telegram_id=2)
    mocker.patch.object(
        service,
        'prepare_combined_entry_for_analysis',
        new=mocker.AsyncMock(return_value=object()),
    )
    mocker.patch.object(
        diary_service_module,
        'get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.start_full_day_reanalysis_use_case(user, date(2026, 8, 8), 'ru')
    assert result['mode'] == 'ready'
    assert 'processing' in result['status_text']
    assert 'task_effect_analysis_started' in result['status_text']
    assert result['confirm_alert'] == 'day_analysis_confirmed'
