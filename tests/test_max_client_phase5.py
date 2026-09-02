from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.transports.max.client import MaxClient
from bot.transports.max.preflight import collect_preflight_errors


@pytest.mark.asyncio
async def test_answer_callback_posts_answers_endpoint(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    calls = []

    async def fake_request_json(*, method, path, params=None, payload=None):
        calls.append({'method': method, 'path': path, 'params': params, 'payload': payload})
        return 200, {'success': True}

    monkeypatch.setattr(client, '_request_json', fake_request_json)

    ok = await client.answer_callback(callback_id='cb_1', notification='ok')

    assert ok is True
    assert calls == [
        {
            'method': 'POST',
            'path': '/answers',
            'params': {'callback_id': 'cb_1'},
            'payload': {'notification': 'ok'},
        }
    ]

    calls.clear()
    ok_silent = await client.answer_callback(callback_id='cb_2')
    assert ok_silent is True
    assert calls == [
        {
            'method': 'POST',
            'path': '/answers',
            'params': {'callback_id': 'cb_2'},
            'payload': {'notification': '✓'},
        }
    ]

    calls.clear()

    async def fake_request_fail(*, method, path, params=None, payload=None):
        calls.append({'method': method, 'path': path, 'params': params, 'payload': payload})
        return 200, {'success': False, 'message': 'expired'}

    monkeypatch.setattr(client, '_request_json', fake_request_fail)
    assert await client.answer_callback(callback_id='cb_3') is False


@pytest.mark.asyncio
async def test_send_message_chunks_text_and_keeps_keyboard_on_last_chunk(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        max_message_length=100,
        ca_cert_paths=[],
    )

    calls = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None, text_format='html'):
        calls.append(
            {
                'target_key': target_key,
                'target_value': target_value,
                'text': text,
                'attachments': attachments,
                'text_format': text_format,
            }
        )
        return True, 200, {'ok': True}

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='ok', callback_data='p')]]
    )
    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)

    ok = await client.send_message(
        user_id=123,
        text=' '.join(['0123456789'] * 30),
        reply_markup=markup,
    )

    assert ok[0] is True
    assert len(calls) >= 2
    assert calls[0]['attachments'] is None
    assert calls[-1]['attachments'] is not None
    assert calls[-1]['attachments'][0]['type'] == 'inline_keyboard'
    assert 'payload' in calls[-1]['attachments'][0]
    assert 'buttons' in calls[-1]['attachments'][0]['payload']


@pytest.mark.asyncio
async def test_send_message_fallbacks_from_chat_to_user(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    call_targets = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None, text_format='html'):
        call_targets.append((target_key, target_value))
        if len(call_targets) == 1:
            return False, 404, {'error': 'chat not found'}
        return True, 200, {'ok': True}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)

    ok = await client.send_message(user_id=111, chat_id=222, text='hello')

    assert ok[0] is True
    # В личке сначала user_id, chat_id — только fallback.
    assert call_targets[0] == ('user_id', 111)


@pytest.mark.asyncio
async def test_send_message_tries_keyboard_variants_then_plain(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    calls = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None, text_format='html'):
        calls.append({'attachments': attachments, 'text_format': text_format})
        if attachments is not None:
            return False, 400, {'error': 'proto.payload invalid keyboard'}
        return True, 200, {'ok': True}

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='ok', callback_data='p')]]
    )
    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)

    ok = await client.send_message(user_id=123, text='hello', reply_markup=markup)

    assert ok[0] is True
    # 2 keyboard variants (string/legacy) + plain fallback
    assert len(calls) == 3
    assert calls[-1]['attachments'] is None
    assert all(c['attachments'] is not None for c in calls[:-1])
    first_btn = calls[0]['attachments'][0]['payload']['buttons'][0][0]
    assert first_btn['type'] == 'callback'
    assert first_btn['payload'] == 'p'
    second_btn = calls[1]['attachments'][0]['payload']['buttons'][0][0]
    assert 'type' not in second_btn
    assert second_btn['payload'] == 'p'


def test_build_ssl_connector_loads_repo_certs():
    root = Path(__file__).resolve().parents[1]
    sub = root / 'russian_trusted_sub_ca_2024_pem.crt'
    root_ca = root / 'russian_trusted_root_ca_pem.crt'
    assert sub.is_file() and root_ca.is_file()

    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[str(sub), str(root_ca)],
    )
    connector = client._build_ssl_connector()
    assert connector is not None


def test_preflight_errors_on_missing_ca_files():
    settings_obj = SimpleNamespace(
        MAX_TRANSPORT_MODE='polling',
        MAX_BOT_TOKEN='token',
        MAX_API_BASE_URL='https://platform-api2.max.ru',
        MAX_API_TIMEOUT_SECONDS=10,
        MAX_WEBHOOK_URL='',
        MAX_POLLING_TIMEOUT_SECONDS=30,
        MAX_POLLING_IDLE_SLEEP_SECONDS=1.5,
        MAX_API_CA_CERT_PATHS=['/tmp/missing_ca_cert_xyz.crt'],
        BASE_DIR=Path('/tmp'),
    )
    errors = collect_preflight_errors(settings_obj)
    assert any('MAX_API_CA_CERT_PATHS' in e for e in errors)


@pytest.mark.asyncio
async def test_fetch_updates_uses_long_poll_http_timeout(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        timeout_seconds=10,
        ca_cert_paths=[],
    )
    captured: dict = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return 200, {'updates': [], 'marker': '42'}

    monkeypatch.setattr(client, '_request_json', fake_request_json)
    updates, marker = await client.fetch_updates(timeout_seconds=30)

    assert updates == []
    assert marker == '42'
    assert captured['timeout_seconds'] == 40.0
    assert captured['params']['timeout'] == '30'


@pytest.mark.asyncio
async def test_send_message_includes_html_format_in_payload(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    captured: dict = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return 200, {'ok': True}

    monkeypatch.setattr(client, '_request_json', fake_request_json)
    ok = await client.send_message(user_id=7, text='<b>Привет</b>')

    assert ok[0] is True
    assert captured['payload']['text'] == '<b>Привет</b>'
    assert captured['payload']['format'] == 'html'


@pytest.mark.asyncio
async def test_send_message_sets_dialog_suspended_reason(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    async def fake_send_single_message(**kwargs):
        return False, 403, {
            'code': 'chat.denied',
            'message': 'Key: error.dialog.suspended, args: [159706904,].',
        }

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)
    ok, message_id = await client.send_message(user_id=159706904, text='hello')
    assert ok is False
    assert message_id is None
    assert client.last_failure_reason == 'dialog_suspended'


@pytest.mark.asyncio
async def test_send_message_returns_extracted_message_id(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    async def fake_send_single_message(**kwargs):
        return True, 200, {'message_id': 'mid-42', 'text': kwargs.get('text')}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)
    ok, message_id = await client.send_message(user_id=7, text='hello')
    assert ok is True
    assert message_id == 'mid-42'


@pytest.mark.asyncio
async def test_edit_message_puts_messages_endpoint(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    calls = []

    async def fake_request_json(*, method, path, params=None, payload=None, timeout_seconds=None):
        calls.append(
            {
                'method': method,
                'path': path,
                'params': params,
                'payload': payload,
            }
        )
        return 200, {'success': True}

    monkeypatch.setattr(client, '_request_json', fake_request_json)
    ok = await client.edit_message(message_id='mid-1', text='Готово')
    assert ok is True
    assert calls == [
        {
            'method': 'PUT',
            'path': '/messages',
            'params': {'message_id': 'mid-1'},
            'payload': {'text': 'Готово', 'format': 'html', 'attachments': []},
        }
    ]


def test_classify_send_failure_detects_dialog_suspended():
    body = {
        'code': 'chat.denied',
        'message': 'Key: error.dialog.suspended, args: [159706904,].',
    }
    assert MaxClient.classify_send_failure(403, body) == 'dialog_suspended'
    assert MaxClient.classify_send_failure(404, body) is None
    assert MaxClient.classify_send_failure(403, {'code': 'other'}) is None


def test_extract_message_id_from_known_shapes():
    assert MaxClient._extract_message_id({'message_id': 'a'}) == 'a'
    assert MaxClient._extract_message_id({'message': {'message_id': 'b'}}) == 'b'
    assert MaxClient._extract_message_id({'message': {'body': {'mid': 'c'}}}) == 'c'
    assert MaxClient._extract_message_id({'body': {'mid': 'd'}}) == 'd'
    assert MaxClient._extract_message_id({'ok': True}) is None


def test_keyboard_blank_button_text_is_sanitized():
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=' ', callback_data='calendar_empty'),
                InlineKeyboardButton(text='1', callback_data='calendar_select_day:2026:8:1'),
            ]
        ]
    )
    variants = client._build_keyboard_attachment_variants(markup)
    assert variants
    buttons = variants[0]['payload']['buttons'][0]
    assert buttons[0]['text'] == '·'
    assert buttons[0]['payload'] == 'calendar_empty'
    assert buttons[1]['text'] == '1'


def test_keyboard_attachment_uses_payload_buttons_wrapper():
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='Далее', callback_data='next')]]
    )
    variants = client._build_keyboard_attachment_variants(markup)
    assert len(variants) == 2
    assert variants[0] == {
        'type': 'inline_keyboard',
        'payload': {
            'buttons': [
                [
                    {
                        'type': 'callback',
                        'text': 'Далее',
                        'payload': 'next',
                    }
                ]
            ]
        },
    }
    assert 'type' not in variants[1]['payload']['buttons'][0][0]
    assert variants[1]['payload']['buttons'][0][0]['payload'] == 'next'


@pytest.mark.asyncio
async def test_get_upload_url_uses_post(monkeypatch):
    """MAX docs: POST /uploads?type=image (GET returns method.not.found)."""
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )
    calls = []

    async def fake_request_json(*, method, path, params=None, payload=None, timeout_seconds=None):
        calls.append({'method': method, 'path': path, 'params': params})
        return 200, {'url': 'https://iu.oneme.ru/upload.do?x=1'}

    monkeypatch.setattr(client, '_request_json', fake_request_json)
    meta = await client.get_upload_url('image')
    assert meta == {'url': 'https://iu.oneme.ru/upload.do?x=1'}
    assert calls == [
        {'method': 'POST', 'path': '/uploads', 'params': {'type': 'image'}}
    ]


def test_resolve_upload_attachment_payload_photos_map():
    payload = MaxClient._resolve_upload_attachment_payload(
        {'photos': {'abc': {'token': 't1'}}},
        upload_type='image',
    )
    assert payload == {'photos': {'abc': {'token': 't1'}}}


def test_resolve_upload_attachment_payload_flat_token():
    payload = MaxClient._resolve_upload_attachment_payload(
        {'token': 'flat-token'},
        upload_type='image',
    )
    assert payload == {'token': 'flat-token'}


@pytest.mark.asyncio
async def test_upload_bytes_returns_photos_payload(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    async def fake_request_json(*, method, path, params=None, payload=None, timeout_seconds=None):
        return 200, {'url': 'https://iu.oneme.ru/upload.do?x=1'}

    class FakeResp:
        status = 200

        async def text(self):
            return '{"photos": {"p1": {"token": "tok"}}}'

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResp()

    async def fake_get_session():
        return FakeSession()

    monkeypatch.setattr(client, '_request_json', fake_request_json)
    monkeypatch.setattr(client, '_get_session', fake_get_session)
    monkeypatch.setattr(client._rate_limiter, 'acquire', AsyncMock())

    result = await client.upload_bytes(b'png', upload_type='image', filename='x.png')
    assert result == {'photos': {'p1': {'token': 'tok'}}}
