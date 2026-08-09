import pytest
from pathlib import Path
from types import SimpleNamespace

from bot.transports.max.client import MaxClient
from bot.transports.max.preflight import collect_preflight_errors


@pytest.mark.asyncio
async def test_send_message_chunks_text_and_keeps_keyboard_on_last_chunk(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        max_message_length=100,
        ca_cert_paths=[],
    )

    calls = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None):
        calls.append(
            {
                'target_key': target_key,
                'target_value': target_value,
                'text': text,
                'attachments': attachments,
            }
        )
        return True, 200, {'ok': True}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)
    monkeypatch.setattr(
        client, '_serialize_inline_keyboard', lambda _: [[{'text': 'ok', 'payload': 'p'}]]
    )

    ok = await client.send_message(
        user_id=123,
        text=' '.join(['0123456789'] * 30),
        reply_markup=object(),
    )

    assert ok is True
    assert len(calls) >= 2
    assert calls[0]['attachments'] is None
    assert calls[-1]['attachments'] is not None


@pytest.mark.asyncio
async def test_send_message_fallbacks_from_chat_to_user(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    call_targets = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None):
        call_targets.append((target_key, target_value))
        if len(call_targets) == 1:
            return False, 404, {'error': 'chat not found'}
        return True, 200, {'ok': True}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)

    ok = await client.send_message(user_id=111, chat_id=222, text='hello')

    assert ok is True
    assert call_targets == [('chat_id', 222), ('user_id', 111)]


@pytest.mark.asyncio
async def test_send_message_retries_without_keyboard_on_payload_error(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        ca_cert_paths=[],
    )

    calls = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None):
        calls.append({'attachments': attachments})
        if len(calls) == 1:
            return False, 400, {'error': 'invalid keyboard payload'}
        return True, 200, {'ok': True}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)
    monkeypatch.setattr(
        client, '_serialize_inline_keyboard', lambda _: [[{'text': 'ok', 'payload': 'p'}]]
    )

    ok = await client.send_message(user_id=123, text='hello', reply_markup=object())

    assert ok is True
    assert calls[0]['attachments'] is not None


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
