import pytest

from bot.services.diary_service import DiaryService


@pytest.mark.asyncio
async def test_call_deepseek_with_metrics_records_success(mocker):
    service = DiaryService()
    deepseek_mock = mocker.Mock(send_prompt_and_parse=mocker.AsyncMock(return_value={'success': True, 'result': {}}))
    metrics_mock = mocker.Mock(record_ai_call_event=mocker.AsyncMock())

    module_globals = service._call_deepseek_with_metrics.__globals__
    mocker.patch.object(module_globals['deepseek_api_service'], 'send_prompt_and_parse', new=deepseek_mock.send_prompt_and_parse)
    mocker.patch.object(module_globals['monitoring_service'], 'record_ai_call_event', new=metrics_mock.record_ai_call_event)

    result = await service._call_deepseek_with_metrics(
        flow='diary.test_flow',
        prompt='p',
        language='ru',
        metadata={'attempt': 'primary'},
    )

    assert result['success'] is True
    metrics_mock.record_ai_call_event.assert_awaited_once()
    kwargs = metrics_mock.record_ai_call_event.await_args.kwargs
    assert kwargs['flow'] == 'diary.test_flow'
    assert kwargs['success'] is True
    assert kwargs['metadata']['provider'] == 'deepseek'


@pytest.mark.asyncio
async def test_call_deepseek_with_metrics_records_failed_response(mocker):
    service = DiaryService()
    deepseek_mock = mocker.Mock(send_prompt_and_parse=mocker.AsyncMock(return_value={'success': False, 'error': 'timeout'}))
    metrics_mock = mocker.Mock(record_ai_call_event=mocker.AsyncMock())

    module_globals = service._call_deepseek_with_metrics.__globals__
    mocker.patch.object(module_globals['deepseek_api_service'], 'send_prompt_and_parse', new=deepseek_mock.send_prompt_and_parse)
    mocker.patch.object(module_globals['monitoring_service'], 'record_ai_call_event', new=metrics_mock.record_ai_call_event)

    result = await service._call_deepseek_with_metrics(
        flow='diary.test_flow',
        prompt='p',
        language='ru',
    )

    assert result['success'] is False
    metrics_mock.record_ai_call_event.assert_awaited_once()
    kwargs = metrics_mock.record_ai_call_event.await_args.kwargs
    assert kwargs['success'] is False
    assert kwargs['metadata']['error'] == 'timeout'


@pytest.mark.asyncio
async def test_call_deepseek_with_metrics_records_exception_and_reraises(mocker):
    service = DiaryService()
    deepseek_mock = mocker.Mock(send_prompt_and_parse=mocker.AsyncMock(side_effect=ValueError('bad provider')))
    metrics_mock = mocker.Mock(record_ai_call_event=mocker.AsyncMock())

    module_globals = service._call_deepseek_with_metrics.__globals__
    mocker.patch.object(module_globals['deepseek_api_service'], 'send_prompt_and_parse', new=deepseek_mock.send_prompt_and_parse)
    mocker.patch.object(module_globals['monitoring_service'], 'record_ai_call_event', new=metrics_mock.record_ai_call_event)

    with pytest.raises(ValueError):
        await service._call_deepseek_with_metrics(
            flow='diary.test_flow',
            prompt='p',
            language='ru',
        )

    metrics_mock.record_ai_call_event.assert_awaited_once()
    kwargs = metrics_mock.record_ai_call_event.await_args.kwargs
    assert kwargs['success'] is False
    assert kwargs['metadata']['error'] == 'ValueError'
