import pytest

from bot.services.diary_service import DiaryService
from core.service_response import ServiceResponse


@pytest.mark.asyncio
async def test_process_new_entry_use_case_wraps_success(mocker):
    service = DiaryService()
    user = mocker.Mock(telegram_id=101)
    monitor_mock = mocker.AsyncMock()
    mocker.patch.object(service, '_record_use_case_metric', new=monitor_mock)

    payload = {
        'success': True,
        'entry': object(),
        'analysis': object(),
        'needs_clarification': True,
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
    monitor_mock.assert_awaited_once()


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
    user = mocker.Mock(telegram_id=104)

    payload = {
        'success': True,
        'entry': object(),
        'analysis': object(),
        'mood_score': 7,
        'comment': 'ok',
        'recommendation': 'go on',
    }

    mocker.patch.object(service, 'process_first_onboarding_entry_logic', new=mocker.AsyncMock(return_value=payload))

    response = await service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text='first entry',
        language='ru',
    )

    assert isinstance(response, ServiceResponse)
    assert response.success is True
    assert response.data == payload
    assert response.metadata['onboarding_completed'] is False


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