# /home/shlicha/psycho_diary/tests/test_weekly_analysis_tasks.py
"""
Тесты для Celery задач еженедельного анализа.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock

from diary.tasks import (
    perform_weekly_analysis_for_user_task,
    run_profile_cleanup,
    schedule_weekly_analyses_task,
)
from users.models import User
from model_bakery import baker


@pytest.mark.django_db(transaction=True)
class TestWeeklyAnalysisTasks:
    """Тесты для Celery задач."""

    @pytest.fixture
    def user_for_task(self, db):
        return baker.make(User, telegram_id=987654321, timezone='Europe/Moscow', is_blocked=False)

    def test_perform_weekly_analysis_for_user_task_success(self, user_for_task, mocker):
        """Тест успешного выполнения задачи для пользователя."""
        weekly_analysis = mocker.Mock(id=123)
        weekly_result = {'success': True, 'message': 'Completed', 'weekly_analysis': weekly_analysis}
        profile_result = {'success': True, 'message': 'Profile completed'}
        cleanup_result = {
            'success': True,
            'changed': True,
            'changed_fields': ['triggers', 'practical_patterns'],
            'changed_fields_count': 2,
            'removed_items': 2,
            'stale_items': 4,
            'compressed_profile_action': 'rebuilt',
        }
        change_result = {'success': True, 'message': 'Change completed'}

        mock_weekly = mocker.patch(
            'diary.tasks.weekly_analisys_tasks.weekly_analysis_service.perform_weekly_analysis',
            new=AsyncMock(return_value=weekly_result),
        )
        mock_profile = mocker.patch(
            'diary.tasks.weekly_analisys_tasks.user_profile_analysis_service.perform_user_profile_analysis',
            new=AsyncMock(return_value=profile_result),
        )
        mock_cleanup = mocker.patch(
            'diary.tasks.weekly_analisys_tasks.profile_cleanup_service.cleanup_user_profile',
            new=AsyncMock(return_value=cleanup_result),
        )
        mock_change = mocker.patch(
            'diary.tasks.weekly_analisys_tasks.perform_profile_change_analysis',
            new=AsyncMock(return_value=change_result),
        )
        
        result = perform_weekly_analysis_for_user_task(user_for_task.id)

        assert result['status'] == 'completed'
        assert result['weekly_result']['success'] is True
        assert result['profile_result']['success'] is True
        assert result['cleanup_result']['removed_items'] == 2
        assert result['cleanup_result']['changed_fields_count'] == 2
        assert result['profile_change_result']['success'] is True
        mock_weekly.assert_called_once_with(user_for_task)
        mock_profile.assert_called_once_with(user_for_task)
        mock_cleanup.assert_called_once_with(user_for_task)
        mock_change.assert_called_once_with(user_for_task, weekly_analysis, num_snapshots_to_compare=3)

    def test_perform_weekly_analysis_for_user_task_cleanup_error_does_not_stop_chain(self, user_for_task, mocker):
        weekly_analysis = mocker.Mock(id=456)
        mocker.patch(
            'diary.tasks.weekly_analisys_tasks.weekly_analysis_service.perform_weekly_analysis',
            new=AsyncMock(return_value={'success': True, 'weekly_analysis': weekly_analysis}),
        )
        mocker.patch(
            'diary.tasks.weekly_analisys_tasks.user_profile_analysis_service.perform_user_profile_analysis',
            new=AsyncMock(return_value={'success': True}),
        )
        mocker.patch(
            'diary.tasks.weekly_analisys_tasks.profile_cleanup_service.cleanup_user_profile',
            new=AsyncMock(return_value={'success': False, 'error': 'cleanup failed'}),
        )
        mock_change = mocker.patch(
            'diary.tasks.weekly_analisys_tasks.perform_profile_change_analysis',
            new=AsyncMock(return_value={'success': True}),
        )

        result = perform_weekly_analysis_for_user_task(user_for_task.id)

        assert result['status'] == 'completed'
        assert result['cleanup_result']['success'] is False
        mock_change.assert_called_once()


    def test_perform_weekly_analysis_for_user_task_user_not_found(self):
        """Тест задачи, когда пользователь не найден."""
        non_existent_user_id = 999999999
        
        result = perform_weekly_analysis_for_user_task(non_existent_user_id)
        
        assert result['status'] == 'failed'
        assert result['reason'] == 'user_not_found'


    def test_perform_weekly_analysis_for_user_task_user_blocked(self, db):
        """Тест задачи для заблокированного пользователя."""
        blocked_user = baker.make(User, is_blocked=True)
        
        result = perform_weekly_analysis_for_user_task(blocked_user.id)
        
        assert result['status'] == 'skipped'
        assert result['reason'] == 'user_blocked'


    @pytest.mark.parametrize("user_tz,should_schedule", [
        ('Europe/Moscow', True),   # 00:00 UTC = 03:00 MSK
        ('America/New_York', False), # 00:00 UTC = 20:00 EST (не 03:00)
        ('Asia/Tokyo', False),     # 00:00 UTC = 09:00 JST (не 03:00)
    ])
    def test_schedule_weekly_analyses_task_time_check(self, user_tz, should_schedule, mocker):
        """Тест проверки времени для планирования задач."""
        # Создаем пользователей
        user_in_tz = baker.make(User, timezone=user_tz, is_blocked=False)
        user_blocked = baker.make(User, timezone=user_tz, is_blocked=True)
        
        # Мокаем время UTC на 00:00
        with patch('diary.tasks.weekly_analisys_tasks.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2023, 10, 30, 0, 0, 0) # Понедельник 00:00 UTC
            
            # Мокаем delay задачи
            mock_delay = mocker.patch('diary.tasks.weekly_analisys_tasks.perform_weekly_analysis_for_user_task.delay')
            
            # Выполняем задачу планировщика
            result = schedule_weekly_analyses_task()
            
            if should_schedule:
                # Проверяем, что задача была запланирована для активного пользователя
                mock_delay.assert_called_once_with(user_in_tz.id)
                assert result['tasks_scheduled'] == 1
            else:
                # Проверяем, что задача не была запланирована
                mock_delay.assert_not_called()
                assert result['tasks_scheduled'] == 0


@pytest.mark.django_db(transaction=True)
class TestProfileCleanupTask:
    def test_run_profile_cleanup_aggregates_results(self, mocker):
        first_user = baker.make(User, telegram_id=500001, is_blocked=False)
        second_user = baker.make(User, telegram_id=500002, is_blocked=False)

        cleanup_mock = mocker.patch(
            'diary.tasks.profile_cleanup.profile_cleanup_service.cleanup_user_profile',
            new=AsyncMock(side_effect=[
                {
                    'success': True,
                    'changed': True,
                    'changed_fields_count': 2,
                    'removed_items': 3,
                    'stale_items': 4,
                    'compressed_profile_rebuilt': True,
                },
                {
                    'success': True,
                    'changed': False,
                    'changed_fields_count': 0,
                    'removed_items': 0,
                    'stale_items': 1,
                    'compressed_profile_rebuilt': False,
                },
            ]),
        )

        result = run_profile_cleanup(batch_size=1)

        assert result['status'] == 'completed'
        assert result['processed_users'] == 2
        assert result['changed_users'] == 1
        assert result['changed_fields'] == 2
        assert result['removed_items'] == 3
        assert result['stale_items'] == 5
        assert result['rebuilt_profiles'] == 1
        assert result['failed_users'] == 0
        assert cleanup_mock.await_count == 2

    def test_run_profile_cleanup_counts_failures(self, mocker):
        baker.make(User, telegram_id=500003, is_blocked=False)

        mocker.patch(
            'diary.tasks.profile_cleanup.profile_cleanup_service.cleanup_user_profile',
            new=AsyncMock(side_effect=RuntimeError('boom')),
        )

        result = run_profile_cleanup()

        assert result['status'] == 'completed'
        assert result['processed_users'] == 1
        assert result['failed_users'] == 1
