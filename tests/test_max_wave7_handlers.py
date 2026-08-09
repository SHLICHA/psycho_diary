"""Wave 7 MAX: inbound media + STT / feedback photo."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.messages import route_text_message
from bot.states.diary_states import DiaryStates
from bot.states.feedback_states import FeedbackStates
from bot.transports.max.inbound import MaxMediaInfo, extract_media_from_message, normalize_update
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
        username='max_wave7',
        email='max_wave7@example.com',
        max_id=880007,
        language='ru',
        is_onboarding_completed=True,
    )


def test_extract_audio_attachment_prefers_audio():
    message = {
        'body': {
            'text': '',
            'attachments': [
                {'type': 'inline_keyboard', 'buttons': []},
                {
                    'type': 'image',
                    'payload': {'url': 'https://cdn.example/a.jpg', 'id': 'img1'},
                },
                {
                    'type': 'audio',
                    'payload': {
                        'url': 'https://cdn.example/v.ogg',
                        'id': 'aud1',
                        'duration': 12,
                    },
                },
            ],
        }
    }
    media = extract_media_from_message(message)
    assert media is not None
    assert media.kind == 'audio'
    assert media.url.endswith('v.ogg')
    assert media.duration == 12


def test_normalize_update_includes_media():
    update = {
        'update_type': 'message_created',
        'message': {
            'sender': {'user_id': 42},
            'recipient': {'chat_id': 7},
            'body': {
                'text': '',
                'attachments': [
                    {
                        'type': 'image',
                        'payload': {'url': 'https://cdn.example/p.png', 'id': 'p1', 'size': 100},
                    }
                ],
            },
        },
    }
    event = normalize_update(update)
    assert event is not None
    assert event.media is not None
    assert event.media.kind == 'image'
    assert event.media.file_id == 'p1'


@pytest.mark.asyncio
async def test_diary_voice_stt_routes_to_text(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, DiaryStates.waiting_for_text_entry)
    media = MaxMediaInfo(kind='audio', url='https://cdn.example/v.ogg', duration=3)
    client = MagicMock()

    mocker.patch(
        'bot.handlers.max.media.recognize_max_voice',
        new=AsyncMock(return_value=(True, 'Голосовая запись дня', '')),
    )
    mocker.patch(
        'bot.handlers.max.diary.process_diary_text',
        new=AsyncMock(return_value={'ok': True, 'handled': 'new_entry_process'}),
    )

    result = await route_text_message(
        max_user,
        '',
        send_func,
        max_id=max_user.max_id,
        media=media,
        max_client=client,
    )
    assert result['handled'] == 'new_entry_process'


@pytest.mark.asyncio
async def test_feedback_photo_submit(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(
        max_user.max_id, FeedbackStates.waiting_photo, feedback_text='Проблема'
    )
    media = MaxMediaInfo(kind='image', url='https://cdn.example/p.png', file_id='f1', size=50)
    client = MagicMock()

    mocker.patch(
        'bot.handlers.max.media.download_media_bytes',
        new=AsyncMock(return_value=b'\xff\xd8\xff' + b'0' * 100),
    )
    mocker.patch(
        'bot.handlers.max.feedback.feedback_service.submit_user_feedback_use_case',
        new=AsyncMock(
            return_value={
                'success': True,
                'thanks_text': 'Спасибо!',
                'feedback': MagicMock(),
                'notify_payload': {'user': max_user, 'message_text': 'Проблема'},
                'clear_state': True,
            }
        ),
    )
    mocker.patch(
        'bot.utils.admin_utils.send_feedback_to_developer',
        new=AsyncMock(),
    )

    result = await route_text_message(
        max_user,
        '',
        send_func,
        max_id=max_user.max_id,
        media=media,
        max_client=client,
    )
    assert result['handled'] == 'feedback_photo'
    assert max_state.get_fsm_state(max_user.max_id) is None


@pytest.mark.asyncio
async def test_feedback_voice_stores_bytes(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, FeedbackStates.waiting_message)
    media = MaxMediaInfo(kind='audio', url='https://cdn.example/v.ogg')
    client = MagicMock()
    mocker.patch(
        'bot.handlers.max.media.download_media_bytes',
        new=AsyncMock(return_value=b'ogg-bytes'),
    )

    result = await route_text_message(
        max_user,
        '',
        send_func,
        max_id=max_user.max_id,
        media=media,
        max_client=client,
    )
    assert result['handled'] == 'feedback_voice'
    assert max_state.matches_state(max_user.max_id, FeedbackStates.waiting_photo)
    assert max_state.get_raw_state(max_user.max_id).get('voice_data_b64')
