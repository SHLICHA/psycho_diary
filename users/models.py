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
    timezone = models.CharField(max_length=50, default='UTC',verbose_name="Часовой пояс")
    last_entry = models.DateTimeField(null=True, blank=True, verbose_name="Последняя запись")
    awareness_level = models.PositiveIntegerField(default=1, verbose_name="Уровень осознанности")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    is_premium = models.BooleanField(default=False, verbose_name="Премиум статус")
    is_blocked = models.BooleanField(default=False, verbose_name="Бот заблокирован")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата удаления")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    preferred_analysis_time = models.TimeField(default='02:00', verbose_name="Время анализа")
    current_calendar_year = models.PositiveIntegerField(default=2025, verbose_name="Текущий год календаря")
    current_calendar_month = models.PositiveIntegerField(default=8, verbose_name="Текущий месяц календаря")
    notifications_enabled = models.BooleanField(default=True, verbose_name="Уведомления включены")
    auto_analysis_enabled = models.BooleanField(default=True, verbose_name="Автоанализ включен")
    max_ai_tasks_per_day = models.PositiveIntegerField(default=1, verbose_name="Максимум заданий от ИИ в день")    
    personality_traits = models.JSONField(default=dict, blank=True, verbose_name="Черты характера")
    life_facts = models.JSONField(default=list, blank=True, verbose_name="Факты о жизни")
    hobbies = models.JSONField(default=list, blank=True, verbose_name="Увлечения")
    core_values = models.JSONField(default=list, blank=True, verbose_name="Ключевые ценности")
    triggers = models.JSONField(default=list, blank=True, verbose_name="Триггеры")
    strengths = models.JSONField(default=list, blank=True, verbose_name="Сильные стороны")
    areas_for_growth = models.JSONField(default=list, blank=True, verbose_name="Зоны роста")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Дата рождения")
    email = models.EmailField(blank=True, verbose_name="Email")

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

    async def aget_profile_data(self) -> dict:
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
        return self.get_local_datetime()
    
class CityTimezone(models.Model):
    """
    Модель для хранения соответствия городов и часовых поясов
    """
    city_name = models.CharField(max_length=100, verbose_name="Название города")
    timezone = models.CharField(max_length=50, verbose_name="Часовой пояс")
    country = models.CharField(max_length=100, blank=True, verbose_name="Страна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Город и часовой пояс"
        verbose_name_plural = "Города и часовые пояса"
        db_table = "users_city_timezone"
        unique_together = ['city_name', 'country']

    def __str__(self):
        return f"{self.city_name}, {self.country} ({self.timezone})"

    def save(self, *args, **kwargs):
        """Проверка валидности часового пояса перед сохранением"""
        try:
            pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError:
            raise ValueError(f"Неверный часовой пояс: {self.timezone}")
        super().save(*args, **kwargs)