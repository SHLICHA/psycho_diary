"""Unit-тесты view/use-case builders для Phase 3.15 (без БД)."""
from datetime import date
from types import SimpleNamespace

import pytest

from diary.services.payment_service import PaymentService
from diary.services.progress_service import ProgressService
from diary.services.full_day_analysis_service import build_full_day_reanalysis_notification
from core.services.feedback_service import FeedbackService, FeedbackDisplayData


def test_build_payment_link_message_subscription():
    text = PaymentService.build_payment_link_message('https://pay.example/sub')
    assert 'подписки' in text
    assert 'https://pay.example/sub' in text


def test_build_payment_link_message_tokens():
    text = PaymentService.build_payment_link_message(
        'https://pay.example/tokens',
        payment_kind='tokens',
    )
    assert 'токенов' in text
    assert 'https://pay.example/tokens' in text


def test_build_payment_initiation_view_requires_email(mocker):
    mocker.patch('diary.services.payment_service.get_message', return_value='ask email')
    view = PaymentService.build_payment_initiation_view(
        {'success': True, 'requires_email': True, 'pending_payment_data': {'plan': 'month'}},
        language='ru',
    )
    assert view['success'] is True
    assert view['mode'] == 'requires_email'
    assert view['pending_payment_data']['plan'] == 'month'


def test_build_payment_initiation_view_payment_link(mocker):
    mocker.patch('diary.services.payment_service.get_message', return_value='err')
    view = PaymentService.build_payment_initiation_view(
        {'success': True, 'confirmation_url': 'https://pay.example/ok'},
        language='ru',
        payment_kind='subscription',
    )
    assert view['success'] is True
    assert view['mode'] == 'payment_link'
    assert view['confirmation_url'] == 'https://pay.example/ok'
    assert 'https://pay.example/ok' in view['text']


def test_build_payment_initiation_view_error(mocker):
    mocker.patch('diary.services.payment_service.get_message', return_value='generic error')
    view = PaymentService.build_payment_initiation_view(
        {'success': False, 'error': 'boom'},
        language='ru',
    )
    assert view['success'] is False
    assert view['mode'] == 'error'
    assert view['error'] == 'boom'


def test_build_premium_menu_view_active(mocker):
    mocker.patch(
        'diary.services.payment_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_manage_premium_keyboard',
        return_value='kb_manage',
    )
    user = mocker.Mock()
    user.is_premium_active.return_value = True
    user.premium_expires_at = SimpleNamespace(strftime=lambda fmt: '01.01.2030 12:00')

    view = PaymentService.build_premium_menu_view(user, 'ru')
    assert view['success'] is True
    assert view['mode'] == 'active'
    assert view['reply_markup'] == 'kb_manage'
    assert '01.01.2030 12:00' in view['text']


def test_build_premium_menu_view_purchase(mocker):
    mocker.patch(
        'diary.services.payment_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_purchase_options_keyboard',
        return_value='kb_purchase',
    )
    user = mocker.Mock()
    user.is_premium_active.return_value = False

    view = PaymentService.build_premium_menu_view(user, 'ru')
    assert view['mode'] == 'purchase'
    assert view['reply_markup'] == 'kb_purchase'


@pytest.mark.asyncio
async def test_build_full_day_reanalysis_notification_success(mocker):
    mocker.patch(
        'diary.services.full_day_analysis_service.perform_full_day_analysis',
        new=mocker.AsyncMock(return_value={
            'success': True,
            'daily_analysis': SimpleNamespace(overall_analysis_text='A' * 250),
        }),
    )
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    user = mocker.Mock(telegram_id=1)
    result = await build_full_day_reanalysis_notification(user, date(2026, 8, 8), 'ru')
    assert result['success'] is True
    assert result['reply_markup'] is not None
    assert 'analysis_recalculated' in result['text']
    assert '...' in result['text']


@pytest.mark.asyncio
async def test_build_full_day_reanalysis_notification_failure(mocker):
    mocker.patch(
        'diary.services.full_day_analysis_service.perform_full_day_analysis',
        new=mocker.AsyncMock(return_value={'success': False, 'message': 'no entries'}),
    )
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    user = mocker.Mock(telegram_id=2)
    result = await build_full_day_reanalysis_notification(user, date(2026, 8, 8), 'ru')
    assert result['success'] is False
    assert result['error'] == 'no entries'
    assert 'error_processing' in result['text']


@pytest.mark.asyncio
async def test_build_restore_streak_request_view_unavailable(mocker):
    mocker.patch.object(
        ProgressService,
        'check_restore_streak_availability',
        new=mocker.AsyncMock(return_value={'available': False, 'dates': []}),
    )
    view = await ProgressService.build_restore_streak_request_view(mocker.Mock(), 'ru')
    assert view['mode'] == 'unavailable'
    assert view['available'] is False


@pytest.mark.asyncio
async def test_build_restore_streak_request_view_select_date(mocker):
    dates = [date(2026, 8, 6), date(2026, 8, 7)]
    mocker.patch.object(
        ProgressService,
        'check_restore_streak_availability',
        new=mocker.AsyncMock(return_value={'available': True, 'dates': dates}),
    )
    mocker.patch(
        'diary.services.progress_service.get_message',
        return_value='restore info',
    )
    mocker.patch(
        'bot.keyboards.get_restore_date_selection_keyboard',
        return_value='kb_dates',
    )
    view = await ProgressService.build_restore_streak_request_view(mocker.Mock(), 'ru')
    assert view['success'] is True
    assert view['mode'] == 'select_date'
    assert view['reply_markup'] == 'kb_dates'
    assert view['dates'] == dates


@pytest.mark.asyncio
async def test_build_weekly_analysis_page_view_not_found(mocker):
    mocker.patch.object(
        ProgressService,
        'get_weekly_analysis_for_date',
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch(
        'diary.services.progress_service.get_message',
        return_value='not found',
    )
    mocker.patch(
        'bot.keyboards.get_weekly_navigation_keyboard',
        return_value='kb_nav',
    )
    view = await ProgressService.build_weekly_analysis_page_view(
        mocker.Mock(), date(2026, 8, 4), 'ru'
    )
    assert view['mode'] == 'not_found'
    assert view['text'] == 'not found'
    assert view['reply_markup'] == 'kb_nav'


@pytest.mark.asyncio
async def test_build_progress_screen_view(mocker):
    mocker.patch.object(
        ProgressService,
        'get_user_progress_statistics',
        new=mocker.AsyncMock(return_value={
            'entries_count': 3,
            'tasks_completed': 1,
            'tasks_assigned': 2,
            'tasks_completion_percentage': 50,
            'streak_days': 4,
            'streak_reset_warning': '',
        }),
    )
    mocker.patch.object(
        ProgressService,
        'get_latest_weekly_analysis',
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch.object(
        ProgressService,
        'get_has_weekly_analyses',
        new=mocker.AsyncMock(return_value=False),
    )
    mocker.patch.object(
        ProgressService,
        'check_restore_streak_availability',
        new=mocker.AsyncMock(return_value={'available': False, 'dates': []}),
    )
    mocker.patch(
        'diary.services.progress_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_progress_keyboard_without_weekly',
        return_value='kb_progress',
    )
    user = mocker.Mock(awareness_level=2)
    view = await ProgressService.build_progress_screen_view(user, 'ru')
    assert view['success'] is True
    assert view['has_analyses'] is False
    assert view['reply_markup'] == 'kb_progress'
    assert 'progress_title' in view['text']


def test_build_admin_feedback_list_keyboard_edges():
    service = FeedbackService()
    kb_first = service.build_admin_feedback_list_keyboard(feedback_id=10, index=0, total=3)
    first_row_callbacks = [btn.callback_data for btn in kb_first.inline_keyboard[0]]
    assert 'reply_feedback_10' in first_row_callbacks
    assert 'feedback_next' in first_row_callbacks
    assert 'feedback_prev' not in first_row_callbacks

    kb_last = service.build_admin_feedback_list_keyboard(feedback_id=12, index=2, total=3)
    last_row_callbacks = [btn.callback_data for btn in kb_last.inline_keyboard[0]]
    assert 'feedback_prev' in last_row_callbacks
    assert 'feedback_next' not in last_row_callbacks


@pytest.mark.asyncio
async def test_build_admin_feedback_item_view_not_found():
    service = FeedbackService()
    view = await service.build_admin_feedback_item_view([], 0)
    assert view['mode'] == 'not_found'
    assert view['clear_state'] is True


@pytest.mark.asyncio
async def test_build_admin_feedback_item_view_item(mocker):
    service = FeedbackService()
    feedback = mocker.Mock(id=5, is_photo=False, photo_file_id=None, message='hi')
    mocker.patch.object(
        service,
        'get_feedback_by_id',
        new=mocker.AsyncMock(return_value=feedback),
    )
    mocker.patch.object(
        service,
        'format_feedback_for_display',
        new=mocker.AsyncMock(return_value=FeedbackDisplayData(
            feedback_id=5,
            username='u',
            created_at='01.01.2026 10:00',
            is_voice=False,
            is_photo=False,
            message_preview='hi',
            full_message='hi',
            photo_file_id=None,
            status='new',
        )),
    )
    view = await service.build_admin_feedback_item_view([5], 0)
    assert view['success'] is True
    assert view['mode'] == 'item'
    assert view['has_photo'] is False
    assert 'Обращение #5' in view['text']


@pytest.mark.asyncio
async def test_build_admin_reply_prompt_view_not_found(mocker):
    service = FeedbackService()
    mocker.patch.object(
        service,
        'can_reply_to_feedback',
        new=mocker.AsyncMock(return_value=(False, None)),
    )
    view = await service.build_admin_reply_prompt_view(99, 'ru')
    assert view['success'] is False
    assert view['mode'] == 'not_found'
