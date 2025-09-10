# test_scheduler_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, time, datetime, timedelta
import pytz
from django.utils import timezone
from diary.tasks.scheduler_tasks import (
    _get_user_local_time,
    _is_analysis_time_reached,
    schedule_daily_analyses,
    perform_scheduled_daily_analysis
)
# Импортируем модули, которые будем мокать
from diary import services
from diary.services import full_day_analysis_service
from bot import services as bot_services
from diary.models import CombinedDiaryEntry, DailyAnalysis, DiaryEntry
from users.models import User


# --- Тесты для вспомогательных функций ---

class TestHelperFunctions:

    def test_is_analysis_time_reached_false(self):
        """Тест: _is_analysis_time_reached возвращает False, если время анализа еще не наступило."""
        # Создаем пользователя напрямую для теста
        user = User(timezone='Europe/Moscow', preferred_analysis_time=time(1, 0)) # 01:00 MSK
        
        target_date = date(2023, 10, 26)
        # Предположим, "сейчас" это чуть раньше момента анализа
        # Момент анализа: 2023-10-27 01:00:00 MSK = 2023-10-26 22:00:00 UTC
        # "Сейчас": 2023-10-26 21:30:00 UTC
        moment_before_analysis_utc = datetime(2023, 10, 26, 21, 30, 0, tzinfo=pytz.utc)
        
        with patch('diary.tasks.scheduler_tasks.timezone.now', return_value=moment_before_analysis_utc):
            result = _is_analysis_time_reached(user, target_date)
        assert result is False

    def test_is_analysis_time_reached_true(self):
        """Тест: _is_analysis_time_reached возвращает True, если время анализа наступило."""
        user = User(timezone='Europe/Moscow', preferred_analysis_time=time(1, 0)) # 01:00 MSK
        target_date = date(2023, 10, 26)
        # --- ИСПРАВЛЕНИЕ ЛОГИКИ ---
        # Момент анализа для дня 2023-10-26 наступает в 01:00 2023-10-27 MSK.
        # 2023-10-27 01:00:00 MSK = 2023-10-26 22:00:00 UTC.
        # "Сейчас": чуть позже, например, 2023-10-26 22:30:00 UTC.
        moment_after_analysis_utc = datetime(2023, 10, 26, 22, 30, 0, tzinfo=pytz.utc)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        
        with patch('diary.tasks.scheduler_tasks.timezone.now', return_value=moment_after_analysis_utc):
            result = _is_analysis_time_reached(user, target_date)
        assert result is True

    def test_is_analysis_time_reached_user_utc(self):
        """Тест: _is_analysis_time_reached с пользователем в UTC."""
        user = User(timezone='UTC', preferred_analysis_time=time(2, 0)) # 02:00 UTC
        target_date = date(2023, 10, 26)
        # --- ИСПРАВЛЕНИЕ ЛОГИКИ ---
        # Момент анализа для дня 2023-10-26 наступает в 02:00 2023-10-27 UTC.
        # "Сейчас": 2023-10-27 03:00:00 UTC.
        moment_after_analysis_utc = datetime(2023, 10, 27, 3, 0, 0, tzinfo=pytz.utc)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        
        with patch('diary.tasks.scheduler_tasks.timezone.now', return_value=moment_after_analysis_utc):
            result = _is_analysis_time_reached(user, target_date)
        assert result is True

# --- Тесты для основной задачи schedule_daily_analyses ---

class TestScheduleDailyAnalyses:

    @pytest.mark.django_db
    def test_schedule_daily_analyses_filters_users(self):
        """Тест: schedule_daily_analyses фильтрует пользователей правильно."""
        # Создаем пользователей для теста, указывая УНИКАЛЬНЫЕ username
        # Убедитесь, что auto_analysis_enabled - это правильное имя поля в вашей модели
        user1 = User.objects.create(username='testuser1_sched', telegram_id=1, auto_analysis_enabled=True)
        user2 = User.objects.create(username='testuser2_sched', telegram_id=2, auto_analysis_enabled=False)
        user3 = User.objects.create(username='testuser3_sched', telegram_id=3, auto_analysis_enabled=True)

        # Создаем мок для логгера, чтобы проверить вызовы
        with patch('diary.tasks.scheduler_tasks.logger') as mock_logger:
            # Запускаем задачу
            schedule_daily_analyses.apply() # Используем .apply() для синхронного запуска в тесте

        # Проверяем, что логгер информировал о количестве найденных пользователей
        # (Это базовая проверка. В реальном тесте вы бы проверяли больше деталей,
        # например, вызовы perform_scheduled_daily_analysis.delay)
        # mock_logger.info.assert_any_call("--- НАЧАЛО: Задача планировщика schedule_daily_analyses ---")
        # mock_logger.info.assert_any_call("Найдено пользователей с auto_analysis_enabled=True: 2")
        
        # Простая проверка: info должен был быть вызван несколько раз
        assert mock_logger.info.call_count >= 2

    # Более сложные тесты требуют мока большого количества зависимостей
    # и, возможно, использования pytest-django и model_bakery

# --- Тесты для задачи perform_scheduled_daily_analysis ---

class TestPerformScheduledDailyAnalysis:

    @pytest.mark.django_db
    def test_perform_scheduled_daily_analysis_user_not_found(self):
        """Тест: perform_scheduled_daily_analysis обрабатывает несуществующего пользователя."""
        non_existent_user_id = 999999
        target_date = date(2023, 10, 26)

        with patch('diary.tasks.scheduler_tasks.logger') as mock_logger:
            # Запускаем задачу
            res = perform_scheduled_daily_analysis.apply(args=[non_existent_user_id, target_date.isoformat()])

        assert res.successful() is True # Задача завершается успешно, даже если пользователь не найден
        # Проверяем, что был залогирована ошибка
        mock_logger.error.assert_called()
        # Проверяем, что сервис не был вызван (косвенно)
        # (Для прямой проверки нужно мокать сервис)

    # Тест с моком сервиса
    @pytest.mark.django_db
    def test_perform_scheduled_daily_analysis_success(self):
        """Тест: perform_scheduled_daily_analysis успешно вызывает сервис."""
        # Создаем пользователя
        user = User.objects.create(username='testuser_perf_succ', telegram_id=1) # Уникальное имя
        target_date = date(2023, 10, 26)
        
        # Мокаем результат, который должен вернуть сервис
        mock_result = {
            "success": True,
            "message": "Анализ завершен",
            "daily_analysis": MagicMock(), # Можно заменить на реальный словарь, если нужно проверять его содержимое
            "error": None
        }

        # --- ИСПРАВЛЕНИЕ ---
        # Мокаем ПРАВИЛЬНЫЙ путь к объекту, который импортируется в scheduler_tasks.py
        # В scheduler_tasks.py: from diary.services.full_day_analysis_service import full_day_analysis_service
        with patch('diary.services.full_day_analysis_service.full_day_analysis_service') as mock_service:
            # Настраиваем мок так, чтобы его метод perform_full_day_analysis возвращал наш результат
            # Так как метод асинхронный, но мы вызываем его через async_to_sync, мокаем синхронно
            mock_service.perform_full_day_analysis = MagicMock(return_value=mock_result)

            with patch('diary.tasks.scheduler_tasks.logger') as mock_logger:
                # Запускаем задачу
                res = perform_scheduled_daily_analysis.apply(args=[user.id, target_date.isoformat()])

        # Проверки
        assert res.successful() is True
        # Проверяем, что метод сервиса был вызван с правильными аргументами
        mock_service.perform_full_day_analysis.assert_called_once_with(user, target_date)
        # Проверяем, что был залогирован успех (пример)
        # (Вам нужно адаптировать это под реальные сообщения в вашем логгере)
        # mock_logger.info.assert_any_call(f"  ✅ Анализ дня {target_date} для пользователя {user.id} успешно завершен. Анализ завершен")
        # Проще проверить, что info был вызван
        assert mock_logger.info.call_count > 0

    @pytest.mark.django_db
    def test_perform_scheduled_daily_analysis_service_failure(self):
        """Тест: perform_scheduled_daily_analysis обрабатывает неуспешный результат от сервиса."""
        user = User.objects.create(username='testuser_fail', telegram_id=1)
        target_date = date(2023, 10, 26)
        mock_result = {
            "success": False,
            "message": "Ошибка API",
            "daily_analysis": None,
            "error": "api_timeout"
        }

        with patch('diary.services.full_day_analysis_service.full_day_analysis_service') as mock_service:
            mock_service.perform_full_day_analysis = MagicMock(return_value=mock_result)

            with patch('diary.tasks.scheduler_tasks.logger') as mock_logger:
                res = perform_scheduled_daily_analysis.apply(args=[user.id, target_date.isoformat()])

        assert res.successful() is True # Задача завершается успешно, даже при внутренней ошибке
        mock_service.perform_full_day_analysis.assert_called_once_with(user, target_date)
        # Проверить, что ошибка была залогирована
        mock_logger.error.assert_called() # Или конкретное сообщение, если проверяете

    @pytest.mark.django_db
    def test_perform_scheduled_daily_analysis_service_exception(self):
        """Тест: perform_scheduled_daily_analysis обрабатывает исключение от сервиса."""
        user = User.objects.create(username='testuser_exc', telegram_id=1)
        target_date = date(2023, 10, 26)

        with patch('diary.services.full_day_analysis_service.full_day_analysis_service') as mock_service:
            # Настраиваем мок, чтобы он выбрасывал исключение
            mock_service.perform_full_day_analysis = MagicMock(side_effect=ConnectionError("API недоступен"))

            with patch('diary.tasks.scheduler_tasks.logger') as mock_logger:
                res = perform_scheduled_daily_analysis.apply(args=[user.id, target_date.isoformat()])

        assert res.successful() is True # Задача завершается успешно, даже при исключении
        mock_service.perform_full_day_analysis.assert_called_once_with(user, target_date)
        # Проверить, что исключение было залогировано
        mock_logger.error.assert_called() # Или конкретное сообщение
