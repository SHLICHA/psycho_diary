import pytz
import logging

from datetime import datetime
from django.contrib.auth.models import AbstractUser
from django.db import models

logger = logging.getLogger(__name__)

class User(AbstractUser):
    """
    Расширенная модель пользователя для Telegram бота
    """
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    language = models.CharField(
        max_length=2, 
        choices=[('ru', 'Русский'), ('en', 'English')], 
        default='ru',
        verbose_name="Язык"
    )
    timezone = models.CharField(
        max_length=50, 
        default='UTC',
        verbose_name="Часовой пояс"
    )
    last_entry = models.DateTimeField(null=True, blank=True, verbose_name="Последняя запись")
    awareness_level = models.PositiveIntegerField(default=1, verbose_name="Уровень осознанности")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    is_premium = models.BooleanField(default=False, verbose_name="Премиум статус")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата удаления")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    preferred_analysis_time = models.TimeField(default='02:00', verbose_name="Время анализа")
    current_calendar_year = models.PositiveIntegerField(default=2025, verbose_name="Текущий год календаря")
    current_calendar_month = models.PositiveIntegerField(default=8, verbose_name="Текущий месяц календаря")
    # Добавляем настройки пользователя
    notifications_enabled = models.BooleanField(default=True, verbose_name="Уведомления включены")
    auto_analysis_enabled = models.BooleanField(default=True, verbose_name="Автоанализ включен")
    max_ai_tasks_per_day = models.PositiveIntegerField(
        default=1, 
        verbose_name="Максимум заданий от ИИ в день"
    )    
    
    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        db_table = "users_user"

    def __str__(self):
        return f"{self.username} ({self.telegram_id})"
    
    def get_profile_data(self):
        """
        Получение данных профиля пользователя для API.
        Возвращает синхронный словарь.
        """
        return {
            'username': self.username or f"user_{self.telegram_id}",
            'first_name': self.first_name or "",
            'language': self.language,
            'awareness_level': self.awareness_level,
        }

    def get_local_datetime(self):
        """
        Получение текущего времени в часовом поясе пользователя.
        Возвращает синхронный datetime.
        """
        try:
            user_tz_str = self.timezone if self.timezone else 'UTC'
            user_tz = pytz.timezone(user_tz_str)
            return datetime.now(user_tz)
        except Exception as e:
            logger.error(f"Ошибка при получении локального времени пользователя {self.telegram_id}: {e}")
            return datetime.now(pytz.utc)

    # Асинхронные версии (если потребуются напрямую в асинхронном контексте, 
    # хотя обычно достаточно синхронных)
    async def aget_profile_data(self) -> dict:
        # Убедись, что все поля — из текущего объекта, без ORM-запросов
        return {
            'first_name': self.first_name or self.username or f'Пользователь {self.telegram_id}',
            'awareness_level': self.awareness_level,
            'is_premium': self.is_premium,
            'entries_count': await self.diary_entries.acount(),
            'username': self.username,
            'language': self.language,
            'telegram_id': self.telegram_id
        }

    async def aget_local_datetime(self):
        """Асинхронная версия get_local_datetime."""
        # Аналогично, вызываем синхронный метод
        return self.get_local_datetime()