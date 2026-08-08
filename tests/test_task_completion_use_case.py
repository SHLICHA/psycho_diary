import pytest

from diary.services.task_management_service import TaskManagementService
from diary.services.task_display_service import TaskDisplayService


@pytest.mark.asyncio
async def test_complete_task_with_feelings_use_case_empty_completion(mocker):
    user = mocker.Mock(telegram_id=1)
    response = await TaskManagementService.complete_task_with_feelings_use_case(
        user=user,
        task_id=10,
        completion_text='   ',
        feelings_text='feel',
        language='ru',
    )
    assert response.success is False
    assert response.error == 'empty_completion'


@pytest.mark.asyncio
async def test_complete_task_with_feelings_use_case_empty_feelings(mocker):
    user = mocker.Mock(telegram_id=1)
    response = await TaskManagementService.complete_task_with_feelings_use_case(
        user=user,
        task_id=10,
        completion_text='done',
        feelings_text='',
        language='ru',
    )
    assert response.success is False
    assert response.error == 'empty_feelings'


@pytest.mark.asyncio
async def test_complete_task_with_feelings_use_case_success(mocker):
    user = mocker.Mock(telegram_id=2)
    task_completion = mocker.Mock()
    mocker.patch.object(
        TaskManagementService,
        'complete_task',
        new=mocker.AsyncMock(return_value={
            'success': True,
            'task_completion': task_completion,
        }),
    )

    response = await TaskManagementService.complete_task_with_feelings_use_case(
        user=user,
        task_id=55,
        completion_text='done',
        feelings_text='better',
        language='ru',
    )

    assert response.success is True
    assert response.data['task_completion'] is task_completion
    assert response.metadata['task_id'] == 55


@pytest.mark.asyncio
async def test_complete_task_with_feelings_use_case_service_failure(mocker):
    user = mocker.Mock(telegram_id=3)
    mocker.patch.object(
        TaskManagementService,
        'complete_task',
        new=mocker.AsyncMock(return_value={'success': False, 'error': 'not found'}),
    )

    response = await TaskManagementService.complete_task_with_feelings_use_case(
        user=user,
        task_id=56,
        completion_text='done',
        feelings_text='ok',
        language='ru',
    )

    assert response.success is False
    assert response.error == 'task_completion_failed'


@pytest.mark.asyncio
async def test_analyze_completed_task_for_notification_use_case_success(mocker):
    user = mocker.Mock(telegram_id=4, language='ru')
    task = mocker.Mock(id=77)
    task_completion = mocker.Mock(task=task)
    analysis = mocker.Mock(id=1)
    notification = mocker.Mock(text='ok text', keyboard=object())

    mocker.patch.object(
        TaskManagementService,
        'analyze_task_completion_effect',
        new=mocker.AsyncMock(return_value=analysis),
    )
    mocker.patch(
        'diary.services.task_display_service.task_display_service.format_task_analysis_notification',
        new=mocker.AsyncMock(return_value=notification),
    )

    response = await TaskManagementService.analyze_completed_task_for_notification_use_case(
        task_completion=task_completion,
        user=user,
        language='ru',
    )

    assert response.success is True
    assert response.data['analysis'] is analysis
    assert response.data['notification_text'] == 'ok text'
    assert response.data['notification_keyboard'] is notification.keyboard


@pytest.mark.asyncio
async def test_analyze_completed_task_for_notification_use_case_failure(mocker):
    user = mocker.Mock(telegram_id=5, language='ru')
    task_completion = mocker.Mock(task=mocker.Mock(id=88))
    mocker.patch.object(
        TaskManagementService,
        'analyze_task_completion_effect',
        new=mocker.AsyncMock(side_effect=RuntimeError('boom')),
    )

    response = await TaskManagementService.analyze_completed_task_for_notification_use_case(
        task_completion=task_completion,
        user=user,
        language='ru',
    )

    assert response.success is False
    assert response.error == 'task_analysis_notification_failed'
    assert 'notification_text' in response.data
    assert 'notification_keyboard' in response.data


@pytest.mark.asyncio
async def test_build_active_tasks_view_empty(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=6)
    mocker.patch(
        'diary.services.task_management_service.get_user_active_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )

    view = await service.build_active_tasks_view(user, 'ru')

    assert view['success'] is True
    assert view['mode'] == 'empty'
    assert view['has_history'] is False
    assert view['keyboard'] is not None


@pytest.mark.asyncio
async def test_build_active_tasks_view_active(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=7)
    task = mocker.Mock(id=101, title='T', description='D')
    mocker.patch(
        'diary.services.task_management_service.get_user_active_tasks',
        new=mocker.AsyncMock(return_value=[task]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[object()]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )

    view = await service.build_active_tasks_view(user, 'ru')

    assert view['mode'] == 'active'
    assert view['has_history'] is True
    assert view['tasks'] == [task]


@pytest.mark.asyncio
async def test_build_task_history_view_empty(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=8)
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )

    view = await service.build_task_history_view(user, 'ru')

    assert view['mode'] == 'empty'
    assert view['task_ids'] == []


@pytest.mark.asyncio
async def test_build_task_history_view_list(mocker):
    service = TaskDisplayService()
    user = mocker.Mock(telegram_id=9)
    task = mocker.Mock(id=202, status='completed', completed_at=1, assigned_at=0)
    mocker.patch(
        'diary.services.task_management_service.get_user_completed_tasks',
        new=mocker.AsyncMock(return_value=[task]),
    )
    mocker.patch(
        'diary.services.task_management_service.get_user_skipped_tasks',
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch.object(
        service,
        'format_task_history_detail',
        new=mocker.AsyncMock(return_value=mocker.Mock(text='history text')),
    )

    view = await service.build_task_history_view(user, 'ru')

    assert view['mode'] == 'list'
    assert view['task_ids'] == [202]
    assert view['text'] == 'history text'
