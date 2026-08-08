"""Unit-тесты use-case для Phase 3.18 feedback (без БД)."""
from types import SimpleNamespace

import pytest

from core.services.feedback_service import FeedbackService, FeedbackDisplayData


@pytest.fixture
def service():
    return FeedbackService()


@pytest.fixture
def test_user():
    return SimpleNamespace(telegram_id=12345, username='tester')


@pytest.mark.asyncio
async def test_submit_user_feedback_use_case_success(mocker, service, test_user):
    feedback = SimpleNamespace(id=42)
    mocker.patch.object(
        service,
        'create_feedback',
        new=mocker.AsyncMock(return_value=feedback),
    )
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.submit_user_feedback_use_case(
        user=test_user,
        message_text='hello',
        language='ru',
        voice_data=b'voice',
    )

    assert result['success'] is True
    assert result['mode'] == 'success'
    assert result['feedback_id'] == 42
    assert result['feedback'] is feedback
    assert result['thanks_text'] == 'feedback_thanks'
    assert result['notify_payload']['user'] is test_user
    assert result['notify_payload']['message_text'] == 'hello'
    assert result['notify_payload']['voice_data'] == b'voice'
    assert result['clear_state'] is True


@pytest.mark.asyncio
async def test_submit_user_feedback_use_case_photo_too_large(mocker, service, test_user):
    mocker.patch.object(service, 'validate_photo_size', return_value=False)
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.submit_user_feedback_use_case(
        user=test_user,
        message_text='with photo',
        language='ru',
        photo_bytes=b'bytes',
        photo_file_id='file123',
        photo_file_size=30 * 1024 * 1024,
    )

    assert result['success'] is False
    assert result['mode'] == 'photo_too_large'
    assert result['thanks_text'] == 'photo_too_large'
    assert result['clear_state'] is False


@pytest.mark.asyncio
async def test_submit_user_feedback_use_case_no_user(mocker, service):
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.submit_user_feedback_use_case(
        user=None,
        message_text='hello',
        language='ru',
    )

    assert result['success'] is False
    assert result['mode'] == 'error'
    assert result['error'] == 'user_not_found'
    assert result['thanks_text'] == 'error_generic'


@pytest.mark.asyncio
async def test_submit_user_feedback_use_case_create_error(mocker, service, test_user):
    mocker.patch.object(
        service,
        'create_feedback',
        new=mocker.AsyncMock(side_effect=RuntimeError('db down')),
    )
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )

    result = await service.submit_user_feedback_use_case(
        user=test_user,
        message_text='hello',
        language='ru',
    )

    assert result['success'] is False
    assert result['mode'] == 'error'
    assert result['error'] == 'feedback_create_failed'


@pytest.mark.asyncio
async def test_process_admin_feedback_reply_use_case_success(mocker, service, test_user):
    feedback = SimpleNamespace(
        id=7,
        user=SimpleNamespace(telegram_id=999),
        message='help me',
    )
    mocker.patch.object(
        service,
        'can_reply_to_feedback',
        new=mocker.AsyncMock(return_value=(True, feedback)),
    )
    reply_mock = mocker.patch.object(
        service,
        'reply_to_feedback',
        new=mocker.AsyncMock(return_value=feedback),
    )
    mocker.patch.object(
        service,
        'format_feedback_for_display',
        new=mocker.AsyncMock(return_value=FeedbackDisplayData(
            feedback_id=7,
            username='alice',
            created_at='01.01.2026 10:00',
            is_voice=False,
            is_photo=False,
            message_preview='help me',
            full_message='help me',
            photo_file_id=None,
            status='new',
        )),
    )
    mocker.patch(
        'messages.get_message',
        side_effect=lambda key, language=None, **kwargs: f'{key}:{kwargs.get("feedback_id")}',
    )

    result = await service.process_admin_feedback_reply_use_case(
        admin_user=test_user,
        feedback_id=7,
        reply_text='We fixed it',
        language='ru',
    )

    assert result['success'] is True
    assert result['mode'] == 'ready_to_send'
    assert result['persist_reply'] is True
    assert result['notify_chat_id'] == 999
    assert result['notify_text'] == 'support_response:7'
    assert 'alice' in result['admin_ack_text']
    assert result['clear_state'] is True
    reply_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_admin_feedback_reply_use_case_not_found(mocker, service, test_user):
    mocker.patch.object(
        service,
        'can_reply_to_feedback',
        new=mocker.AsyncMock(return_value=(False, None)),
    )

    result = await service.process_admin_feedback_reply_use_case(
        admin_user=test_user,
        feedback_id=404,
        reply_text='nope',
        language='ru',
    )

    assert result['success'] is False
    assert result['mode'] == 'not_found'
    assert result['clear_state'] is True


@pytest.mark.asyncio
async def test_process_admin_feedback_reply_use_case_already_processed(mocker, service, test_user):
    feedback = SimpleNamespace(id=8, user=SimpleNamespace(telegram_id=1), message='x')
    mocker.patch.object(
        service,
        'can_reply_to_feedback',
        new=mocker.AsyncMock(return_value=(False, feedback)),
    )

    result = await service.process_admin_feedback_reply_use_case(
        admin_user=test_user,
        feedback_id=8,
        reply_text='late',
        language='ru',
    )

    assert result['success'] is False
    assert result['mode'] == 'already_processed'


def test_compute_admin_feedback_nav_index_next(service):
    ids = [1, 2, 3]
    nav = service.compute_admin_feedback_nav_index(ids, 0, 'next')
    assert nav['success'] is True
    assert nav['new_index'] == 1
    assert nav['at_bound'] is False

    nav_last = service.compute_admin_feedback_nav_index(ids, 2, 'next')
    assert nav_last['success'] is False
    assert nav_last['new_index'] == 2
    assert nav_last['at_bound'] is True
    assert 'Больше' in nav_last['alert_text']


def test_compute_admin_feedback_nav_index_prev(service):
    ids = [1, 2, 3]
    nav = service.compute_admin_feedback_nav_index(ids, 1, 'prev')
    assert nav['success'] is True
    assert nav['new_index'] == 0

    nav_first = service.compute_admin_feedback_nav_index(ids, 0, 'prev')
    assert nav_first['success'] is False
    assert nav_first['new_index'] == 0
    assert 'первое' in nav_first['alert_text']


def test_compute_admin_feedback_nav_index_invalid_direction(service):
    nav = service.compute_admin_feedback_nav_index([1], 0, 'jump')
    assert nav['success'] is False
    assert nav['at_bound'] is True
