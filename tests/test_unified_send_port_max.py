import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.transports.contracts import NormalizedOutput
from bot.transports.unified_send_port import UnifiedSendPort


pytestmark = pytest.mark.asyncio


async def test_send_max_maps_dialog_suspended_reason():
    port = UnifiedSendPort()
    client = MagicMock()
    client.send_message = AsyncMock(return_value=(False, None))
    client.last_failure_reason = 'dialog_suspended'
    client.close = AsyncMock()

    with patch('bot.transports.unified_send_port.MaxClient', return_value=client):
        result = await port.send(
            platform='max',
            recipient_id=159706904,
            output=NormalizedOutput(text='hello'),
        )

    assert result.success is False
    assert result.reason == 'max_dialog_suspended'
    client.close.assert_awaited_once()


async def test_send_max_closes_client_on_success():
    port = UnifiedSendPort()
    client = MagicMock()
    client.send_message = AsyncMock(return_value=(True, 'mid-1'))
    client.last_failure_reason = None
    client.close = AsyncMock()

    with patch('bot.transports.unified_send_port.MaxClient', return_value=client):
        result = await port.send(
            platform='max',
            recipient_id=159706904,
            output=NormalizedOutput(text='hello'),
        )

    assert result.success is True
    assert result.reason == 'sent'
    client.close.assert_awaited_once()
