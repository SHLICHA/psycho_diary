"""Phase C: voice upload → STT → process_new_entry_use_case."""

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from core.service_response import ServiceResponse
from diary.models import DiaryEntry
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="voice_user",
        email="voice@example.com",
        password="testpass123",
        language="ru",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(auth_user).access_token)


def _auth(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")


def test_map_language_and_audio_format():
    from bot.utils.audio_utils import map_language_for_speechkit, resolve_audio_format

    assert map_language_for_speechkit('ru') == 'ru-RU'
    assert map_language_for_speechkit('en') == 'en-US'
    assert resolve_audio_format('note.ogg', 'audio/ogg') == 'oggopus'
    assert resolve_audio_format('note.mp3', 'audio/mpeg') == 'mp3'


def test_process_voice_bytes_short_path(mocker):
    from bot.utils.audio_utils import process_voice_bytes
    import asyncio

    mocker.patch.object(
        __import__('bot.services.yandex_speechkit', fromlist=['yandex_speechkit_service']).yandex_speechkit_service,
        'recognize_voice',
        new=AsyncMock(return_value={'success': True, 'result': 'привет мир'}),
    )
    mocker.patch(
        'bot.utils.audio_utils.deepseek_api_service.punctuate_and_format_text',
        new=AsyncMock(return_value={'success': True, 'result': 'Привет, мир!'}),
    )

    ok, text, err = asyncio.run(
        process_voice_bytes(
            b'x' * 2048,
            duration=5,
            language='ru',
            context_name='Test',
        )
    )
    assert ok is True
    assert text == 'Привет, мир!'
    assert err == ''


def test_voice_entry_endpoint(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)

    mocker.patch(
        'bot.utils.audio_utils.process_voice_bytes',
        new=AsyncMock(return_value=(True, 'Сегодня был хороший день.', '')),
    )

    entry = DiaryEntry.objects.create(
        user=auth_user,
        text='Сегодня был хороший день.',
        language='ru',
        word_count=4,
    )
    from bot.services.diary_service import diary_service

    mocker.patch.object(
        diary_service,
        'process_new_entry_use_case',
        new=AsyncMock(
            return_value=ServiceResponse.ok(
                data={
                    'entry': entry,
                    'analysis': None,
                    'needs_clarification': False,
                    'clarification_questions': [],
                }
            )
        ),
    )

    audio = SimpleUploadedFile(
        'voice.ogg',
        b'\x00' * 2048,
        content_type='audio/ogg',
    )
    resp = api_client.post(
        '/api/v1/entries/voice/',
        {'audio': audio, 'duration': '3'},
        format='multipart',
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data['recognized_text'] == 'Сегодня был хороший день.'
    assert 'entry' in resp.data


def test_voice_entry_requires_audio(api_client, auth_token):
    _auth(api_client, auth_token)
    resp = api_client.post('/api/v1/entries/voice/', {}, format='multipart')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data['error']['code'] == 'audio_required'


def test_voice_entry_stt_failure(api_client, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        'bot.utils.audio_utils.process_voice_bytes',
        new=AsyncMock(return_value=(False, '', 'STT down')),
    )
    audio = SimpleUploadedFile('voice.ogg', b'\x00' * 2048, content_type='audio/ogg')
    resp = api_client.post(
        '/api/v1/entries/voice/',
        {'audio': audio, 'duration': 2},
        format='multipart',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data['error']['code'] == 'speech_recognition_failed'
