import pytest

from bot.transports.max.client import MaxClient


@pytest.mark.asyncio
async def test_send_message_chunks_text_and_keeps_keyboard_on_last_chunk(monkeypatch):
    client = MaxClient(
        api_token='token',
        base_url='https://platform-api2.max.ru',
        max_message_length=100,
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
    monkeypatch.setattr(client, '_serialize_inline_keyboard', lambda _: [[{'text': 'ok', 'payload': 'p'}]])

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
    client = MaxClient(api_token='token', base_url='https://platform-api2.max.ru')

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
    client = MaxClient(api_token='token', base_url='https://platform-api2.max.ru')

    calls = []

    async def fake_send_single_message(*, target_key, target_value, text, attachments=None):
        calls.append({'attachments': attachments})
        if len(calls) == 1:
            return False, 400, {'error': 'invalid keyboard payload'}
        return True, 200, {'ok': True}

    monkeypatch.setattr(client, '_send_single_message', fake_send_single_message)
    monkeypatch.setattr(client, '_serialize_inline_keyboard', lambda _: [[{'text': 'ok', 'payload': 'p'}]])

    ok = await client.send_message(user_id=123, text='hello', reply_markup=object())

    assert ok is True
    assert calls[0]['attachments'] is not None
    assert calls[1]['attachments'] is None
