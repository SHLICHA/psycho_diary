import pytest

from bot.services.diary_service import DiaryService
from core.service_response import ServiceResponse


@pytest.mark.asyncio
async def test_process_new_entry_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=101)
    monitor_mock = mocker.AsyncMock()
    mocker.patch.object(service, '_record_use_case_metric', new=monitor_mock)
    mocker.patch.object(
        service,
        'schedule_clarification_for_entry',
        new=mocker.AsyncMock(return_value=ServiceResponse.ok(data={})),
    )

    payload = {
        'success': True,
        'entry': object(),
        'analysis': object(),
        'needs_clarification': True,
        'clarification_questions': ['q1'],
        'suggested_task': object(),
    }

    mocker.patch.object(service, 'process_new_entry_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_new_entry_use_case(
        user=user,
        entry_text='test entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data == payload
    assert response.metadata['needs_clarification'] is True
    assert response.metadata['has_suggested_task'] is True
    assert response.metadata['clarification_scheduled'] is True
    service.schedule_clarification_for_entry.assert_awaited_once()
    monitor_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_new_entry_use_case_skips_schedule_without_clarification(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=1011)
    schedule_mock = mocker.AsyncMock()
    mocker.patch.object(service, '_record_use_case_metric', new=mocker.AsyncMock())
    mocker.patch.object(service, 'schedule_clarification_for_entry', new=schedule_mock)

    payload = {
        'success': True,
        'entry': object(),
        'analysis': object(),
        'needs_clarification': False,
        'clarification_questions': [],
        'suggested_task': None,
    }
    mocker.patch.object(service, 'process_new_entry_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_new_entry_use_case(
        user=user,
        entry_text='test entry',
        language='ru',
    )

    assert response.success is True
    assert response.metadata['clarification_scheduled'] is False
    schedule_mock.assert_not_awaited()


def test_build_clarification_answers_map_fills_missing_answers():
    result = DiaryService.build_clarification_answers_map(
        clarification_questions=['q1', 'q2', 'q3'],
        clarification_text='a1\n\na2',
    )

    assert result == {
        'q1': 'a1',
        'q2': 'a2',
        'q3': '[Ответ не получен]',
    }


@pytest.mark.asyncio
async def test_schedule_clarification_for_entry_success(mocker):
    service = DiaryService()
    entry = mocker.Mock(id=42)
    entry.asave = mocker.AsyncMock()
    mocker.patch.object(service, '_record_use_case_metric', new=mocker.AsyncMock())

    response = await service.schedule_clarification_for_entry(
        entry=entry,
        clarification_questions=['q1'],
        reminder_delay_minutes=10,
        force_process_delay_minutes=20,
    )

    assert response.success is True
    assert entry.clarification_questions_asked == ['q1']
    assert entry.clarification_asked_at is not None
    assert entry.clarification_reminder_due_at is not None
    assert entry.clarification_force_process_at is not None
    entry.asave.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_clarification_for_entry_failure(mocker):
    service = DiaryService()
    entry = mocker.Mock(id=43)
    entry.asave = mocker.AsyncMock(side_effect=RuntimeError('db down'))
    mocker.patch.object(service, '_record_use_case_metric', new=mocker.AsyncMock())

    response = await service.schedule_clarification_for_entry(
        entry=entry,
        clarification_questions=['q1'],
    )

    assert response.success is False
    assert response.error == 'clarification_schedule_failed'


@pytest.mark.asyncio
async def test_process_new_entry_use_case_wraps_validation_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=102)

    payload = {
        'success': False,
        'formatted_message_ai': '<b>validation failed</b>',
        'validation_comment_ai': 'Need more details',
    }

    mocker.patch.object(service, 'process_new_entry_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_new_entry_use_case(
        user=user,
        entry_text='bad',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'entry_validation_failed'
    assert response.data == payload
    assert response.message == 'Need more details'


@pytest.mark.asyncio
async def test_process_new_entry_use_case_wraps_exception(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=103)
    monitor_mock = mocker.AsyncMock()
    mocker.patch.object(service, '_record_use_case_metric', new=monitor_mock)

    mocker.patch.object(
        service,
        'process_new_entry_logic',
        new=mocker.AsyncMock(side_effect=RuntimeError('boom')),
    )

    response = await service.process_new_entry_use_case(
        user=user,
        entry_text='entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'entry_processing_exception'
    assert response.message is not None
    monitor_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_first_onboarding_entry_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=104, is_onboarding_completed=False)
    user.asave = mocker.AsyncMock()

    payload = {
        'success': True,
        'entry': object(),
        'analysis': object(),
        'mood_score': 7,
        'comment': 'ok',
        'recommendation': 'go on',
    }

    mocker.patch.object(service, 'process_first_onboarding_entry_logic', new=mocker.AsyncMock(return_value=payload))
    mocker.patch.object(service, '_record_use_case_metric', new=mocker.AsyncMock())

    response = await service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text='first entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data == payload
    assert response.metadata['onboarding_completed'] is True
    assert response.metadata['onboarding_just_completed'] is True
    assert user.is_onboarding_completed is True
    user.asave.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_first_onboarding_entry_use_case_skips_flag_when_already_completed(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=1041, is_onboarding_completed=True)
    user.asave = mocker.AsyncMock()
    payload = {'success': True, 'entry': object(), 'analysis': object()}
    mocker.patch.object(service, 'process_first_onboarding_entry_logic', new=mocker.AsyncMock(return_value=payload))
    mocker.patch.object(service, '_record_use_case_metric', new=mocker.AsyncMock())

    response = await service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text='first entry',
        language='ru',
    )

    assert response.success is True
    assert response.metadata['onboarding_completed'] is True
    assert response.metadata['onboarding_just_completed'] is False
    user.asave.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_first_onboarding_entry_use_case_wraps_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=105)

    payload = {
        'success': False,
        'formatted_message_ai': '<b>try again</b>',
    }

    mocker.patch.object(service, 'process_first_onboarding_entry_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text='bad first entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'onboarding_entry_validation_failed'
    assert response.data == payload
    assert response.message == '<b>try again</b>'


@pytest.mark.asyncio
async def test_process_first_onboarding_entry_use_case_wraps_exception(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=106)

    mocker.patch.object(
        service,
        'process_first_onboarding_entry_logic',
        new=mocker.AsyncMock(side_effect=RuntimeError('boom')),
    )

    response = await service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text='entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'onboarding_entry_processing_exception'
    assert response.message is not None


@pytest.mark.asyncio
async def test_process_clarification_answers_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=107)
    entry = mocker.Mock(id=501)

    payload = {
        'success': True,
        'entry': entry,
        'analysis': object(),
        'formatted_message_ai': 'done',
    }

    mocker.patch.object(service, 'process_clarification_answers_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_clarification_answers_use_case(
        user=user,
        diary_entry=entry,
        clarification_answers_dict={'q': 'a'},
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data == payload
    assert response.metadata['entry_id'] == 501


@pytest.mark.asyncio
async def test_process_clarification_answers_use_case_wraps_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=108)
    entry = mocker.Mock(id=502)

    payload = {
        'success': False,
        'error': 'clarification_failed',
        'message': 'bad clarification',
    }

    mocker.patch.object(service, 'process_clarification_answers_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_clarification_answers_use_case(
        user=user,
        diary_entry=entry,
        clarification_answers_dict={'q': 'a'},
        language='ru',
    )

    assert response.success is False
    assert response.error == 'clarification_failed'
    assert response.message == 'bad clarification'


@pytest.mark.asyncio
async def test_process_user_comment_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=109)
    entry = mocker.Mock(id=503)

    payload = {
        'success': True,
        'entry': entry,
        'analysis': object(),
        'formatted_message_ai': 'comment analyzed',
    }

    mocker.patch.object(service, 'process_user_comment_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_user_comment_use_case(
        user=user,
        diary_entry=entry,
        user_comment_text='comment',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data == payload
    assert response.metadata['entry_id'] == 503


@pytest.mark.asyncio
async def test_process_user_comment_use_case_wraps_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=110)
    entry = mocker.Mock(id=504)

    payload = {
        'success': False,
        'error': 'comment_failed',
        'message': 'bad comment',
    }

    mocker.patch.object(service, 'process_user_comment_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_user_comment_use_case(
        user=user,
        diary_entry=entry,
        user_comment_text='comment',
        language='ru',
    )

    assert response.success is False
    assert response.error == 'comment_failed'
    assert response.message == 'bad comment'


@pytest.mark.asyncio
async def test_process_entry_edit_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=111)
    entry = mocker.Mock()
    entry.aentry_date = mocker.AsyncMock(return_value=None)
    day_view_payload = {'success': True, 'mode': 'empty', 'text': 'ok', 'keyboard': object()}

    mocker.patch.object(service, 'update_entry_text', new=mocker.AsyncMock(return_value=True))
    mocker.patch.object(service, 'get_user_entry_by_id', new=mocker.AsyncMock(return_value=entry))

    from diary.services.diary_display_service import diary_display_service
    mocker.patch.object(
        diary_display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value=day_view_payload),
    )

    response = await service.process_entry_edit_use_case(
        user=user,
        entry_id=7001,
        new_text='updated text',
        language='ru',
        target_date_iso='2026-06-30',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data['day_view'] == day_view_payload
    assert response.metadata['entry_id'] == 7001


@pytest.mark.asyncio
async def test_process_entry_edit_use_case_wraps_update_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=112)

    mocker.patch.object(service, 'update_entry_text', new=mocker.AsyncMock(return_value=False))

    response = await service.process_entry_edit_use_case(
        user=user,
        entry_id=7002,
        new_text='updated text',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'entry_update_failed'


@pytest.mark.asyncio
async def test_process_entry_edit_use_case_wraps_invalid_target_date(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=113)
    entry = mocker.Mock()

    mocker.patch.object(service, 'update_entry_text', new=mocker.AsyncMock(return_value=True))
    mocker.patch.object(service, 'get_user_entry_by_id', new=mocker.AsyncMock(return_value=entry))

    response = await service.process_entry_edit_use_case(
        user=user,
        entry_id=7003,
        new_text='updated text',
        language='ru',
        target_date_iso='invalid-date',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'invalid_target_date'


@pytest.mark.asyncio
async def test_process_delete_specific_entry_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=114)
    day_view_payload = {'success': True, 'mode': 'empty', 'text': 'ok', 'keyboard': object()}

    mocker.patch.object(service, 'delete_entry_and_update_combined', new=mocker.AsyncMock(return_value=True))

    from diary.services.diary_display_service import diary_display_service
    mocker.patch.object(
        diary_display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value=day_view_payload),
    )

    response = await service.process_delete_specific_entry_use_case(
        user=user,
        entry_id=8001,
        language='ru',
        target_date_iso='2026-06-30',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data['day_view'] == day_view_payload
    assert response.data['deleted'] is True
    assert response.metadata['entry_id'] == 8001


@pytest.mark.asyncio
async def test_process_delete_specific_entry_use_case_wraps_invalid_target_date(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=115)

    response = await service.process_delete_specific_entry_use_case(
        user=user,
        entry_id=8002,
        language='ru',
        target_date_iso='invalid-date',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'invalid_target_date'


@pytest.mark.asyncio
async def test_process_delete_specific_entry_use_case_wraps_day_view_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=116)

    mocker.patch.object(service, 'delete_entry_and_update_combined', new=mocker.AsyncMock(return_value=False))

    from diary.services.diary_display_service import diary_display_service
    mocker.patch.object(
        diary_display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value={'success': False}),
    )

    response = await service.process_delete_specific_entry_use_case(
        user=user,
        entry_id=8003,
        language='ru',
        target_date_iso='2026-06-30',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'day_view_build_failed'


@pytest.mark.asyncio
async def test_process_cancel_delete_specific_entry_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=117)
    day_view_payload = {'success': True, 'mode': 'entries', 'entry': object(), 'entries': [object()], 'total': 1}

    from diary.services.diary_display_service import diary_display_service
    mocker.patch.object(
        diary_display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value=day_view_payload),
    )

    response = await service.process_cancel_delete_specific_entry_use_case(
        user=user,
        language='ru',
        target_date_iso='2026-06-30',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data['day_view'] == day_view_payload


@pytest.mark.asyncio
async def test_process_cancel_delete_specific_entry_use_case_wraps_invalid_target_date(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=118)

    response = await service.process_cancel_delete_specific_entry_use_case(
        user=user,
        language='ru',
        target_date_iso='invalid-date',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'invalid_target_date'


@pytest.mark.asyncio
async def test_process_cancel_delete_specific_entry_use_case_wraps_day_view_failure(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=119)

    from diary.services.diary_display_service import diary_display_service
    mocker.patch.object(
        diary_display_service,
        'build_day_entries_view',
        new=mocker.AsyncMock(return_value={'success': False}),
    )

    response = await service.process_cancel_delete_specific_entry_use_case(
        user=user,
        language='ru',
        target_date_iso='2026-06-30',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is False
    assert response.error == 'day_view_build_failed'