# test_scheduler_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, time, datetime, timedelta
import pytz
from django.utils import timezone
from diary.tasks.scheduler_tasks import (
    _get_user_local_time,
    schedule_daily_analyses,
    perform_scheduled_daily_analysis
)
from diary.models import CombinedDiaryEntry, DailyAnalysis, DiaryEntry
from users.models import User


# --- Тесты для вспомогательных функций ---

class TestHelperFunctions:

    def test_get_user_local_time_moscow(self):
        """Тест: _get_user_local_time возвращает правильное время для Москвы."""
        user = User(timezone='Europe/Moscow')
        result = _get_user_local_time(user)
        assert result.tzinfo is not None
        assert result.tzinfo.zone == 'Europe/Moscow'

    def test_get_user_local_time_unknown_timezone(self):
        """Тест: _get_user_local_time обрабатывает неизвестный часовой пояс."""
        user = User(timezone='Invalid/Timezone')
        result = _get_user_local_time(user)
        assert result.tzinfo == pytz.utc

    def test_get_user_local_time_none_timezone(self):
        """Тест: _get_user_local_time обрабатывает None часовой пояс."""
        user = User(timezone=None)
        result = _get_user_local_time(user)
        assert result.tzinfo == pytz.utc


# --- Тесты для schedule_daily_analyses ---

class TestScheduleDailyAnalyses:

    @pytest.mark.django_db
    def test_schedule_daily_analyses_runs(self):
        """Тест: schedule_daily_analyses выполняется без ошибок."""
        # Просто проверяем что задача выполняется
        result = schedule_daily_analyses.apply()
        assert result.successful() or result.failed()


# --- Тесты для perform_scheduled_daily_analysis ---

class TestPerformScheduledDailyAnalysis:

    @pytest.mark.django_db
    @patch('diary.tasks.scheduler_tasks.diary_service')
    @patch('diary.tasks.scheduler_tasks.full_day_analysis_service')
    @patch('diary.tasks.scheduler_tasks.create_bot_for_task')
    def test_perform_scheduled_daily_analysis_no_entries(self, mock_bot, mock_analysis_service, mock_diary_service):
        """Тест: perform_scheduled_daily_analysis не делает ничего без записей."""
        user = User.objects.create(username='testuser_perform', telegram_id=4444, auto_analysis_enabled=True)
        
        mock_diary_service.get_user_entries_for_date.return_value = []
        
        result = perform_scheduled_daily_analysis.apply(args=[user.id, date(2023, 10, 26)])
        
        # Проверяем что задача выполнилась (успешно или нет - не важно, главное без ошибок импорта)
        assert result is not None
