"""Unit-тесты Wave 3.19: transport-only view builders/use cases (без БД)."""
from datetime import date
from types import SimpleNamespace

import pytest

from core.services.calendar_service import CalendarService
from diary.services.payment_service import (
    PaymentService,
    is_payment_cancel_command,
)
from diary.services.progress_service import ProgressService
from diary.services.task_display_service import TaskDisplayService
from diary.services.task_management_service import TaskManagementService
from users.services.email_merge_service import (
    EmailMergeConfirmationResult,
    build_requester_merge_result_view,
    build_target_merge_result_view,
)


@pytest.mark.asyncio
async def test_build_active_tasks_page_view_pagination_next(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=1)
    tasks = [
        mocker.Mock(id=1, title='A', description='da'),
        mocker.Mock(id=2, title='B', description='db'),
    ]
    mocker.patch(
        'diary.services.task_management_service.get_user_active_tasks',
        new=mocker.AsyncMock(return_value=tasks),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_display_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_task_pagination_keyboard',
        return_value='kb_page',
    )

    view = await service.build_active_tasks_page_view(
        user, 'ru', index=0, direction='next'
    )

    assert view['mode'] == 'active'
    assert view['current_index'] == 1
    assert view['task'].id == 2
    assert view['keyboard'] == 'kb_page'


@pytest.mark.asyncio
async def test_build_active_tasks_page_view_empty_back_only(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=2)
    mocker.patch(
        'diary.services.task_management_service.get_user_active_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_display_service.get_message',
        return_value='no tasks',
    )
    mocker.patch(
        'bot.keyboards.get_single_button_keyboard',
        return_value='kb_back',
    )

    view = await service.build_active_tasks_page_view(
        user, 'ru', empty_reply_mode='back_only'
    )

    assert view['mode'] == 'empty'
    assert view['keyboard'] == 'kb_back'


@pytest.mark.asyncio
async def test_build_task_detail_view_not_found(mocker):
    service = TaskDisplayService()
    mocker.patch(
        'diary.services.task_management_service.get_user_task_by_id',
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch(
        'diary.services.task_display_service.get_message',
        return_value='not found',
    )

    view = await service.build_task_detail_view(mocker.Mock(), 99, 'ru')

    assert view['success'] is False
    assert view['mode'] == 'not_found'
    assert view['alert_text'] == 'not found'


@pytest.mark.asyncio
async def test_build_start_completion_view_success(mocker):
    service = TaskDisplayService()
    task = mocker.Mock(id=5, title='T', description='D')
    mocker.patch(
        'diary.services.task_management_service.get_user_task_by_id',
        new=mocker.AsyncMock(return_value=task),
    )
    mocker.patch(
        'diary.services.task_display_service.get_message',
        return_value='ask {title} {description}',
    )
    mocker.patch(
        'bot.keyboards.get_single_button_keyboard',
        return_value='kb_back',
    )
    from bot.states.task_states import TaskStates

    view = await service.build_start_completion_view(mocker.Mock(), 5, 'ru')

    assert view['success'] is True
    assert view['fsm_state'] == TaskStates.waiting_for_task_completion
    assert view['fsm_data']['completing_task_id'] == 5
    assert view['keyboard'] == 'kb_back'


@pytest.mark.asyncio
async def test_restore_skipped_task_use_case_success(mocker):
    mocker.patch.object(
        TaskManagementService,
        'restore_task',
        new=mocker.AsyncMock(return_value=True),
    )
    result = await TaskManagementService.restore_skipped_task_use_case(
        mocker.Mock(),
        task_id=10,
        task_history_ids=[10, 20],
    )
    assert result['success'] is True
    assert result['alert_text_key'] == 'task_restored'
    assert result['updated_task_history_ids'] == [20]
    assert result['refresh_active_tasks'] is True


@pytest.mark.asyncio
async def test_restore_skipped_task_use_case_failure(mocker):
    mocker.patch.object(
        TaskManagementService,
        'restore_task',
        new=mocker.AsyncMock(return_value=False),
    )
    result = await TaskManagementService.restore_skipped_task_use_case(
        mocker.Mock(),
        task_id=10,
        task_history_ids=[10],
    )
    assert result['success'] is False
    assert result['alert_text_key'] == 'task_not_found_or_not_skipped'
    assert result['updated_task_history_ids'] == [10]


def test_is_payment_cancel_command():
    assert is_payment_cancel_command('назад') is True
    assert is_payment_cancel_command('Cancel') is True
    assert is_payment_cancel_command('user@example.com') is False


def test_build_token_purchase_options_view(mocker):
    mocker.patch(
        'bot.keyboards.get_token_purchase_options_keyboard',
        return_value='kb_tokens',
    )
    view = PaymentService.build_token_purchase_options_view('ru')
    assert 'пакет токенов' in view['text']
    assert view['reply_markup'] == 'kb_tokens'


def test_build_email_payment_result_view_payment_ready(mocker):
    mocker.patch(
        'diary.services.payment_service.get_message',
        return_value='saved',
    )
    view = PaymentService.build_email_payment_result_view(
        {'success': True, 'confirmation_url': 'https://pay.example/x'},
        payment_kind='subscription',
        language='ru',
    )
    assert view['mode'] == 'payment_ready'
    assert view['clear_state'] is True
    assert len(view['messages']) == 2
    assert 'https://pay.example/x' in view['messages'][0]


def test_build_email_payment_result_view_merge_confirmation(mocker):
    mocker.patch(
        'diary.services.payment_service.get_message',
        return_value='merge prompt',
    )
    view = PaymentService.build_email_payment_result_view(
        {
            'success': False,
            'error_code': 'email_confirmation_required',
            'merge_request_id': 7,
        },
        payment_kind='tokens',
        language='ru',
    )
    assert view['mode'] == 'merge_confirmation'
    assert view['merge_request_id'] == 7
    assert view['clear_state'] is False


@pytest.mark.asyncio
async def test_confirm_streak_restoration_use_case_unavailable(mocker):
    mocker.patch.object(
        ProgressService,
        'check_restore_streak_availability',
        new=mocker.AsyncMock(return_value={'available': False, 'dates': []}),
    )
    mocker.patch(
        'diary.services.progress_service.get_message',
        return_value='unavailable',
    )
    result = await ProgressService.confirm_streak_restoration_use_case(
        mocker.Mock(), date(2026, 8, 6), 'ru'
    )
    assert result['ok'] is False
    assert result['alert_text'] == 'unavailable'
    assert result['notify_mode'] == 'message'


@pytest.mark.asyncio
async def test_confirm_streak_restoration_use_case_success(mocker):
    mocker.patch.object(
        ProgressService,
        'check_restore_streak_availability',
        new=mocker.AsyncMock(return_value={'available': True, 'dates': [date(2026, 8, 6)]}),
    )
    mocker.patch.object(
        ProgressService,
        'attempt_streak_restoration',
        new=mocker.AsyncMock(return_value={'success': True, 'message': 'restored'}),
    )
    result = await ProgressService.confirm_streak_restoration_use_case(
        mocker.Mock(), date(2026, 8, 6), 'ru'
    )
    assert result['ok'] is True
    assert result['alert_text'] == 'restored'
    assert result['notify_mode'] == 'alert'


def test_resolve_calendar_anchor_day_current_january():
    service = CalendarService()
    user_date = date(2026, 1, 15)
    assert service.resolve_calendar_anchor_day(user_date, 2026) == 15
    assert service.resolve_calendar_anchor_day(user_date, 2025) == 1
    assert service.resolve_calendar_anchor_day(date(2026, 3, 10), 2026) == 1


@pytest.mark.asyncio
async def test_build_year_selected_calendar_view(mocker):
    service = CalendarService()
    user = mocker.Mock()
    mocker.patch.object(service, 'get_user_local_date', return_value=date(2026, 1, 20))
    mocker.patch(
        'messages.get_message',
        return_value='archive',
    )
    mocker.patch(
        'bot.keyboards.get_month_calendar_with_navigation',
        new=mocker.AsyncMock(return_value='kb_cal'),
    )
    view = await service.build_year_selected_calendar_view(user, 2026, 'ru')
    assert view['success'] is True
    assert view['anchor_day'] == 20
    assert view['reply_markup'] == 'kb_cal'


def test_build_requester_merge_result_view_confirmed(mocker):
    mocker.patch(
        'messages.get_message',
        return_value='confirmed',
    )
    result = EmailMergeConfirmationResult(status='confirmed')
    view = build_requester_merge_result_view(result, None, 'ru')
    assert view['success'] is True
    assert view['mode'] == 'confirmed'


def test_build_requester_merge_result_view_max_deferred(mocker):
    mocker.patch(
        'messages.get_message',
        return_value='deferred',
    )
    result = EmailMergeConfirmationResult(
        status='pending_target_confirmation',
        merge_request=SimpleNamespace(id=1),
    )
    view = build_requester_merge_result_view(
        result,
        {'delivery': 'max_deferred'},
        'ru',
    )
    assert view['mode'] == 'max_deferred'


def test_build_target_merge_result_view_expired(mocker):
    mocker.patch(
        'messages.get_message',
        return_value='expired',
    )
    result = EmailMergeConfirmationResult(status='error', code='target_confirmation_expired')
    view = build_target_merge_result_view(result, 'ru')
    assert view['mode'] == 'expired'
