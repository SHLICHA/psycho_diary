# /home/shlicha/psycho_diary/tests/test_weekly_analysis_tasks.py
"""
Тесты для Celery задач еженедельного анализа.
"""

import pytest
from datetime import datetime, time
from unittest.mock import patch, AsyncMock
import pytz

from diary.tasks import perform_weekly_analysis_for_user_task, schedule_weekly_analyses_task
from users.models import User
from model_bakery import baker


@pytest.mark.django_db
class TestWeeklyAnalysisTasks:
    """Тесты для Celery задач."""

    @pytest.fixture
    def user_for_task(self, db):
        return baker.make(User, telegram_id=987654321, timezone='Europe/Moscow', is_blocked=False)

    def test_perform_weekly_analysis_for_user_task_success(self, user_for_task, mocker):
        """Тест успешного выполнения задачи для пользователя."""
        # Мокаем сервис
        mock_result = {'success': True, 'message': 'Completed'}
        mock_service = mocker.patch('diary.tasks.weekly_analysis_service.perform_weekly_analysis', new=AsyncMock(return_value=mock_result))
        
        # Выполняем задачу
        result = perform_weekly_analysis_for_user_task(user_for_task.id)
        
        # Проверяем
        assert result['status'] == 'completed'
        assert result['result']['success'] is True
        mock_service.assert_called_once_with(user_for_task)


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
        with patch('diary.tasks.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2023, 10, 30, 0, 0, 0) # Понедельник 00:00 UTC
            
            # Мокаем delay задачи
            mock_delay = mocker.patch('diary.tasks.perform_weekly_analysis_for_user_task.delay')
            
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
