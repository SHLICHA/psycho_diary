import pytest

from bot.middlewares.analytics_middleware import AnalyticsMiddleware


class _DummyEvent:
    pass


@pytest.mark.asyncio
async def test_analytics_middleware_records_success(mocker):
    middleware = AnalyticsMiddleware()
    handler = mocker.AsyncMock(return_value='ok')
    record_mock = mocker.AsyncMock()
    mocker.patch(
        'bot.middlewares.analytics_middleware.monitoring_service.record_transport_event',
        new=record_mock,
    )

    result = await middleware(handler, _DummyEvent(), {})

    assert result == 'ok'
    record_mock.assert_awaited_once()
    kwargs = record_mock.await_args.kwargs
    assert kwargs['success'] is True
    assert kwargs['transport_event'] == 'telegram._DummyEvent'


@pytest.mark.asyncio
async def test_analytics_middleware_records_failure_and_reraises(mocker):
    middleware = AnalyticsMiddleware()
    handler = mocker.AsyncMock(side_effect=RuntimeError('boom'))
    record_mock = mocker.AsyncMock()
    mocker.patch(
        'bot.middlewares.analytics_middleware.monitoring_service.record_transport_event',
        new=record_mock,
    )

    with pytest.raises(RuntimeError):
        await middleware(handler, _DummyEvent(), {})

    record_mock.assert_awaited_once()
    kwargs = record_mock.await_args.kwargs
    assert kwargs['success'] is False
    assert kwargs['metadata']['error'] == 'RuntimeError'
