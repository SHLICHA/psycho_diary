import asyncio
from unittest.mock import AsyncMock

import pytest

from bot.transports.max.runtime import MaxTransportCoordinator


@pytest.mark.asyncio
async def test_max_runtime_polling_mode_fetches_updates_and_processes(monkeypatch, settings):
    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_TRANSPORT_MODE = 'polling'
    settings.MAX_BOT_TOKEN = 'token'
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 10
    settings.MAX_POLLING_TIMEOUT_SECONDS = 1
    settings.MAX_POLLING_IDLE_SLEEP_SECONDS = 0

    stop_event = asyncio.Event()

    class FakeClient:
        def __init__(self):
            self.fetch_calls = 0
            self.closed = False
            self.last_update_types = None

        async def fetch_updates(self, *, marker=None, timeout_seconds=30, update_types=None):
            self.fetch_calls += 1
            self.last_update_types = update_types
            return [
                {
                    'update_type': 'message_callback',
                    'callback': {
                        'callback_id': 'cb_fast_1',
                        'user': {'user_id': 123},
                        'payload': 'onboarding_agree_1',
                    },
                }
            ], 'next'

        async def close(self):
            self.closed = True

    fake_client = FakeClient()
    async def _process_side_effect(update, **kwargs):
        stop_event.set()
        assert kwargs.get('max_client') is fake_client
        assert kwargs.get('callback_already_answered') is False
        return {'ok': True, 'ignored': True}

    mock_process = AsyncMock(side_effect=_process_side_effect)
    mock_metrics = AsyncMock()
    monkeypatch.setattr('bot.transports.max.runtime.aprocess_max_update', mock_process)
    monkeypatch.setattr('bot.transports.max.runtime.monitoring_service.record_transport_event', mock_metrics)

    coordinator = MaxTransportCoordinator(client=fake_client)
    await coordinator.run(stop_event)

    assert fake_client.fetch_calls >= 1
    assert fake_client.last_update_types == ['message_created', 'bot_started', 'message_callback']
    mock_process.assert_awaited_once()
    assert mock_metrics.await_count >= 2
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_max_runtime_webhook_mode_registers_when_url_present(monkeypatch, settings):
    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_TRANSPORT_MODE = 'webhook'
    settings.MAX_BOT_TOKEN = 'token'
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 10
    settings.MAX_WEBHOOK_URL = 'https://example.com/api/max/webhook/'

    stop_event = asyncio.Event()

    class FakeClient:
        def __init__(self):
            self.register_calls = []
            self.closed = False

        async def register_webhook(self, webhook_url, update_types=None):
            self.register_calls.append((webhook_url, update_types))
            stop_event.set()
            return True

        async def close(self):
            self.closed = True

    fake_client = FakeClient()
    mock_metrics = AsyncMock()
    monkeypatch.setattr('bot.transports.max.runtime.monitoring_service.record_transport_event', mock_metrics)
    coordinator = MaxTransportCoordinator(client=fake_client)

    await coordinator.run(stop_event)

    assert fake_client.register_calls == [
        ('https://example.com/api/max/webhook/', ['message_created', 'bot_started', 'message_callback'])
    ]
    assert mock_metrics.await_count >= 2
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_max_runtime_preflight_fails_when_token_missing(monkeypatch, settings):
    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_TRANSPORT_MODE = 'polling'
    settings.MAX_BOT_TOKEN = ''
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 10
    settings.MAX_POLLING_TIMEOUT_SECONDS = 1
    settings.MAX_POLLING_IDLE_SLEEP_SECONDS = 0

    stop_event = asyncio.Event()

    class FakeClient:
        def __init__(self):
            self.fetch_calls = 0
            self.closed = False

        async def fetch_updates(self, *, marker=None, timeout_seconds=30, update_types=None):
            self.fetch_calls += 1
            return [], marker

        async def close(self):
            self.closed = True

    fake_client = FakeClient()
    mock_metrics = AsyncMock()
    monkeypatch.setattr('bot.transports.max.runtime.monitoring_service.record_transport_event', mock_metrics)

    coordinator = MaxTransportCoordinator(client=fake_client)
    await coordinator.run(stop_event)

    assert fake_client.fetch_calls == 0
    assert fake_client.closed is False
    mock_metrics.assert_awaited_once()
    assert mock_metrics.await_args.kwargs['transport_event'] == 'max_runtime_preflight'
    assert mock_metrics.await_args.kwargs['success'] is False
