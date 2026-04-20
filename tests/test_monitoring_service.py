from core.services.monitoring_service import MonitoringService


import pytest


@pytest.mark.asyncio
async def test_monitoring_service_records_success_event():
    service = MonitoringService()

    await service.record_use_case_event(
        use_case='diary.process_new_entry',
        success=True,
        duration_ms=12.3,
        metadata={'source': 'telegram'},
    )

    snapshot = service.get_snapshot()
    bucket = snapshot['use_cases']['diary.process_new_entry']
    assert bucket['count'] == 1
    assert bucket['success'] == 1
    assert bucket['failure'] == 0
    assert bucket['last_duration_ms'] == 12.3
    assert bucket['last_metadata']['source'] == 'telegram'
    assert snapshot['totals']['success'] == 1
    assert snapshot['totals']['failure'] == 0


@pytest.mark.asyncio
async def test_monitoring_service_records_failure_event():
    service = MonitoringService()

    await service.record_use_case_event(
        use_case='diary.process_user_comment',
        success=False,
        duration_ms=1.5,
    )

    snapshot = service.get_snapshot()
    bucket = snapshot['use_cases']['diary.process_user_comment']
    assert bucket['count'] == 1
    assert bucket['success'] == 0
    assert bucket['failure'] == 1
    assert snapshot['totals']['success'] == 0
    assert snapshot['totals']['failure'] == 1


@pytest.mark.asyncio
async def test_monitoring_service_records_ai_call_event():
    service = MonitoringService()

    await service.record_ai_call_event(
        flow='diary.process_new_entry_logic',
        success=False,
        duration_ms=45.0,
        metadata={'error': 'timeout'},
    )

    snapshot = service.get_snapshot()
    bucket = snapshot['ai_calls']['diary.process_new_entry_logic']
    assert bucket['count'] == 1
    assert bucket['success'] == 0
    assert bucket['failure'] == 1
    assert bucket['last_metadata']['error'] == 'timeout'


@pytest.mark.asyncio
async def test_monitoring_service_records_transport_event():
    service = MonitoringService()

    await service.record_transport_event(
        transport_event='telegram.Message',
        success=True,
        duration_ms=4.2,
        metadata={'handler': 'x'},
    )

    snapshot = service.get_snapshot()
    bucket = snapshot['transport']['telegram.Message']
    assert bucket['count'] == 1
    assert bucket['success'] == 1
    assert bucket['failure'] == 0
    assert bucket['last_metadata']['handler'] == 'x'


@pytest.mark.asyncio
async def test_monitoring_service_reset_clears_counters():
    service = MonitoringService()

    await service.record_use_case_event('diary.any', True, 0.5)
    service.reset()

    snapshot = service.get_snapshot()
    assert snapshot['use_cases'] == {}
    assert snapshot['ai_calls'] == {}
    assert snapshot['transport'] == {}
    assert snapshot['totals'] == {'success': 0, 'failure': 0}
