import pytz
import logging
import json

from asgiref.sync import sync_to_async
from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction

from core.encrypted_fields import EncryptedCharField, EncryptedJSONField, EncryptedTextField, EncryptedEmailField

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
    has_agreed_to_terms = models.BooleanField(default=False, verbose_name="Согласие с условиями использования")
    timezone = models.CharField(max_length=50, default='UTC',verbose_name="Часовой пояс")
    last_entry = models.DateTimeField(null=True, blank=True, verbose_name="Последняя запись")
    awareness_level = models.PositiveIntegerField(default=1, verbose_name="Уровень осознанности")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    is_premium = models.BooleanField(default=False, verbose_name="Премиум статус")
    is_blocked = models.BooleanField(default=False, verbose_name="Бот заблокирован")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата удаления")
    deletion_status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Активен'),
            ('deleted', 'Удален'),
            ('anonymized', 'Обезличен'),
        ],
        default='active',
        verbose_name="Статус удаления"
    )
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    current_calendar_year = models.PositiveIntegerField(default=2025, verbose_name="Текущий год календаря")
    current_calendar_month = models.PositiveIntegerField(default=8, verbose_name="Текущий месяц календаря")
    notifications_enabled = models.BooleanField(default=True, verbose_name="Уведомления включены")
    auto_analysis_enabled = models.BooleanField(default=True, verbose_name="Автоанализ включен")
    max_ai_tasks_per_day = models.PositiveIntegerField(default=1, verbose_name="Максимум заданий от ИИ в день")
    personality_traits = EncryptedJSONField(default=dict, blank=True, verbose_name="Черты характера")
    life_facts = EncryptedJSONField(default=list, blank=True, verbose_name="Факты о жизни")
    hobbies = EncryptedJSONField(default=list, blank=True, verbose_name="Увлечения")
    core_values = EncryptedJSONField(default=list, blank=True, verbose_name="Ключевые ценности")
    triggers = EncryptedJSONField(default=list, blank=True, verbose_name="Триггеры")
    strengths = EncryptedJSONField(default=list, blank=True, verbose_name="Сильные стороны")
    areas_for_growth = EncryptedJSONField(default=list, blank=True, verbose_name="Зоны роста")
    personality_insights = EncryptedJSONField(default=dict, blank=True, verbose_name="Глубинные инсайты о личности")
    habits = EncryptedJSONField(default=list, blank=True, verbose_name="Привычки")
    skills = EncryptedJSONField(default=list, blank=True, verbose_name="Навыки")
    aspirations = EncryptedJSONField(default=list, blank=True, verbose_name="Стремления")
    personality_description = EncryptedTextField(blank=True, default="", verbose_name="Текстовое описание личности")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Дата рождения")
    email = EncryptedEmailField(blank=True, verbose_name="Email")
    token_balance = models.PositiveIntegerField(default=0, verbose_name="Баланс токенов")
    last_streak_reward_7 = models.PositiveIntegerField(
        default=0,
        verbose_name="Последняя награда за 7 дней подряд (токены)",
        help_text="Значение достигнутой серии, за которую была выдана последняя награда кратная 7."
    )
    last_streak_reward_30 = models.PositiveIntegerField(
        default=0,
        verbose_name="Последняя награда за 30 дней подряд (токены)",
        help_text="Значение достигнутой серии, за которую была выдана последняя награда кратная 30."
    )
    last_streak_reward_365 = models.PositiveIntegerField(
        default=0,
        verbose_name="Последняя награда за 365 дней под ряд (токены)",
        help_text="Значение достигнутой серии, за которую была выдана последняя награда кратная 365."
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
    
    async def aget_local_datetime_now(self):
        """
        Асинхронное получение текущего времени в часовом поясе пользователя.
        Возвращает datetime с правильным часовым поясом.
        """
        try:
            user_tz_str = self.timezone if self.timezone else 'UTC'
            user_tz = pytz.timezone(user_tz_str)
            utc_now = timezone.now()
            if utc_now.tzinfo is None:
                utc_now = pytz.utc.localize(utc_now)
            return utc_now.astimezone(user_tz)
        except Exception as e:
            logger.error(f"Ошибка при получении локального времени пользователя {self.telegram_id}: {e}")
            return timezone.now()

class UserProfileHistory(models.Model):
    """
    История изменений психологического профиля пользователя.
    Хранит снимки профиля в определенные моменты времени.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_history', verbose_name="Пользователь")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания слепка")
    awareness_level = models.PositiveIntegerField(verbose_name="Уровень осознанности")
    personality_traits = EncryptedJSONField(verbose_name="Черты характера")
    life_facts = EncryptedJSONField(verbose_name="Факты о жизни")
    hobbies = EncryptedJSONField(verbose_name="Увлечения")
    core_values = EncryptedJSONField(verbose_name="Ключевые ценности")
    triggers = EncryptedJSONField(verbose_name="Триггеры")
    strengths = EncryptedJSONField(verbose_name="Сильные стороны")
    areas_for_growth = EncryptedJSONField(null=True, verbose_name="Зоны роста")
    personality_insights = EncryptedJSONField(verbose_name="Глубинные инсайты о личности")
    habits = EncryptedJSONField(verbose_name="Привычки")
    skills = EncryptedJSONField(verbose_name="Навыки")
    aspirations = EncryptedJSONField(verbose_name="Стремления")
    personality_description = EncryptedJSONField(verbose_name="Текстовое описание личности")

    class Meta:
        verbose_name = "История профиля пользователя"
        verbose_name_plural = "Истории профилей пользователей"
        db_table = "users_profile_history"
        ordering = ['-created_at']

    def __str__(self):
        return f"Профиль {self.user.username} от {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        """Проверка и корректное сохранение JSON-полей при необходимости."""
        json_fields = [
            'personality_traits', 'life_facts', 'hobbies', 'core_values',
            'triggers', 'strengths', 'areas_for_growth', 'personality_insights',
            'habits', 'skills', 'aspirations'
        ]
        for field_name in json_fields:
            field_value = getattr(self, field_name)
            if not isinstance(field_value, (dict, list)):
                 if isinstance(field_value, str):
                     try:
                         setattr(self, field_name, json.loads(field_value))
                     except json.JSONDecodeError:
                         setattr(self, field_name, {} if 'traits' in field_name or 'insights' in field_name else [])
                 else:
                     setattr(self, field_name, {} if 'traits' in field_name or 'insights' in field_name else [])
        super().save(*args, **kwargs)

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

class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    message = models.TextField()
    is_voice = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    admin_response = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('new', 'Новое'),
            ('processed', 'Обработано'),
            ('replied', 'Ответ отправлен')
        ],
        default='new'
    )
    is_photo = models.BooleanField(default=False, verbose_name="Фото")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Обратная связь'
        verbose_name_plural = 'Обратные связи'

    def __str__(self):
        return f"Обращение от {self.user} ({self.created_at})"
    
    @classmethod
    async def aget_by_id(cls, feedback_id: int):
        """Асинхронное получение обращения"""
        return await sync_to_async(cls.objects.get)(id=feedback_id)
    
    async def asave_with_status(self, status: str, admin_response: str = None):
        """Асинхронное сохранение с обновлением статуса"""
        self.status = status
        if admin_response:
            self.admin_response = admin_response
        await sync_to_async(self.save)()

    @classmethod
    async def areply_to_feedback(cls, feedback_id: int, response_text: str):
        """Асинхронное обновление статуса обращения"""
        def update():
            feedback = cls.objects.get(id=feedback_id)
            feedback.admin_response = response_text
            feedback.status = 'replied'
            feedback.save()
            return feedback
        return await sync_to_async(update)()
    
    @classmethod
    async def aget_unprocessed(cls, limit=20):
        """Асинхронно получает необработанные обращения"""
        def get_feedbacks():
            return list(
                cls.objects.filter(status='new')
                .select_related('user')
                .order_by('-created_at')[:limit]
            )
        return await sync_to_async(get_feedbacks)()
    
class TokenTransaction(models.Model):
    """
    Модель для хранения транзакций внутренней валюты (токенов).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    amount = models.IntegerField(verbose_name="Количество токенов (может быть отрицательным)")
    transaction_type = models.CharField(
        max_length=20,
        choices=[
            ('task_completion', 'Выполнение задания'),
            ('purchase', 'Покупка'),
            ('bonus', 'Бонус'),
            ('refund', 'Возврат'),
            # Можно добавить другие типы в будущем
        ],
        verbose_name="Тип транзакции"
    )
    related_task_completion = models.ForeignKey(
        'diary.TaskCompletion', # Используем строку для избежания циклической зависимости
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Связанное выполнение задания"
    )
    description = models.TextField(blank=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Транзакция токенов"
        verbose_name_plural = "Транзакции токенов"
        db_table = "users_token_transaction"
        ordering = ['-created_at']

    def __str__(self):
        action = "получено" if self.amount > 0 else "потрачено"
        return f"{self.user.username} - {abs(self.amount)} токенов ({action}, {self.transaction_type})"
    
    @classmethod
    def create_and_update_balance(cls, user, amount, transaction_type, description="", related_task_completion=None):
        """
        Создает транзакцию и обновляет баланс пользователя в одной транзакции БД.
        """
        with transaction.atomic(): # <-- Гарантия атомарности
            # Создаем транзакцию
            transaction_obj = cls.objects.create(
                user=user,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                related_task_completion=related_task_completion
            )
            # Обновляем баланс пользователя
            # Используем F() выражение для избежания гонок
            from django.db.models import F
            user.token_balance = F('token_balance') + amount
            user.save(update_fields=['token_balance']) # <-- Обновляем только поле баланса
            logger.debug(f"[TokenTransaction] Транзакция ID {transaction_obj.id} создана, баланс пользователя {user.telegram_id} обновлен на {amount}. Новый баланс (в БД): {user.token_balance}")
            return transaction_obj

    # Асинхронный вариант метода, если он нужен в асинхронных контекстах
    @classmethod
    async def acreate_and_update_balance(cls, user, amount, transaction_type, description="", related_task_completion=None):
        """
        Асинхронный аналог create_and_update_balance.
        """
        # sync_to_async оборачивает весь метод или его часть
        return await sync_to_async(cls.create_and_update_balance)(
            user, amount, transaction_type, description, related_task_completion
        )