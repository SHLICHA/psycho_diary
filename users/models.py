import pytz
import logging
import json
import secrets

from asgiref.sync import sync_to_async
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction

from core.encrypted_fields import EncryptedCharField, EncryptedJSONField, EncryptedTextField, EncryptedEmailField

logger = logging.getLogger(__name__)

class User(AbstractUser):
    """
    Расширенная модель пользователя для Telegram бота и web-версии.
    """
    telegram_id = models.BigIntegerField(
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Telegram ID",
        help_text="Может быть NULL для web-only пользователей"
    )
    max_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name="MAX ID",
        help_text="Идентификатор пользователя в VK MAX (unique, nullable)"
    )
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
    is_onboarding_completed = models.BooleanField(default=False, verbose_name="Онбординг завершён")
    premium_expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Подписка действует до"
    )
    invited_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пригласивший пользователь",
        help_text="Пользователь, который пригласил этого пользователя по реферальной ссылке."
    )
    referral_link = models.CharField(
        max_length=255,
        unique=True, # Должна быть уникальной
        null=True,
        blank=True,
        verbose_name="Реферальная ссылка",
        help_text="Уникальная ссылка для приглашения других пользователей."
    )
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
    practical_patterns = EncryptedJSONField(default=list, blank=True, verbose_name="Привычки и навыки")
    aspirations = EncryptedJSONField(default=list, blank=True, verbose_name="Стремления")
    personality_description = EncryptedTextField(blank=True, default="", verbose_name="Текстовое описание личности")
    compressed_psych_profile = EncryptedJSONField(
        default=dict,
        blank=True,
        verbose_name="Сжатый психологический профиль",
        help_text=(
            "Сжатое представление профиля для LITE-анализов. "
            "Генерируется weekly analysis. Содержит: psych_summary, core_patterns, "
            "emotional_style, main_triggers, coping_style, current_focus."
        )
    )
    full_psych_profile = EncryptedJSONField(
        default=dict,
        blank=True,
        verbose_name="Полный психологический профиль",
        help_text=(
            "Полный психологический профиль для пользователя. "
            "Генерируется weekly analysis. Содержит: summary, traits, values, "
            "triggers, strengths, growth_areas, insights, practical_patterns, aspirations."
        )
    )
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Дата рождения")
    email = EncryptedEmailField(blank=True, verbose_name="Email")
    email_hash = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Email hash (для поиска)",
        help_text="SHA-256 от email в lower-case; NULL если email не задан",
    )
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
    def save(self, *args, **kwargs):
        # Генерируем hash email для поиска (deterministic). Пустой email → NULL (unique).
        if self.email and isinstance(self.email, str) and self.email.strip():
            import hashlib
            self.email_hash = hashlib.sha256(self.email.lower().encode()).hexdigest()
        else:
            if self.email is not None and not isinstance(self.email, str):
                self.email = ''
            self.email_hash = None
        
        if not self.referral_link:
            # Гибридная модель: единый transport-agnostic referral code.
            # Старые ссылки формата ref_<telegram_id>_<token> продолжают поддерживаться.
            for _ in range(5):
                candidate = f"ref_u_{secrets.token_urlsafe(8)}"
                if not User.objects.filter(referral_link=candidate).exists():
                    self.referral_link = candidate
                    break
            if not self.referral_link:
                self.referral_link = f"ref_u_{secrets.token_urlsafe(12)}"
        super().save(*args, **kwargs)

    def is_premium_active(self) -> bool:
        """Проверяет, активна ли подписка на текущий момент."""
        if not self.is_premium or not self.premium_expires_at:
            return False
        return self.premium_expires_at > timezone.now()
    
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

    async def ais_premium_active(self) -> bool:
        """
        Асинхронная версия is_premium_active.
        Проверяет, активна ли подписка на текущий момент.
        """
        if not self.is_premium or not self.premium_expires_at:
            return False
        return self.premium_expires_at > timezone.now()

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
        
    async def process_payment(self, payment: 'Payment'):
        """Активирует подписку или начисляет токены после успешной оплаты."""
        if payment.status != 'succeeded':
            return

        from django.utils import timezone
        update_fields = []

        # --- Подписка ---
        was_premium_before = self.is_premium # Сохраняем предыдущее состояние
        if payment.subscription_days_granted > 0:
            now = timezone.now()
            if self.premium_expires_at and self.premium_expires_at > now:
                new_expires = self.premium_expires_at + timedelta(days=payment.subscription_days_granted)
            else:
                new_expires = now + timedelta(days=payment.subscription_days_granted)
            self.premium_expires_at = new_expires
            self.is_premium = True
            if not was_premium_before:
                self.auto_analysis_enabled = True
                update_fields.append('auto_analysis_enabled')
                logger.info(f"[User.process_payment] Автоанализ включен для пользователя {self.telegram_id} после активации подписки.")
            update_fields.extend(['premium_expires_at', 'is_premium'])

        # --- Токены ---
        if payment.tokens_granted > 0:
            from users.models import TokenTransaction
            await TokenTransaction.acreate_and_update_balance(
                user=self,
                amount=payment.tokens_granted,
                transaction_type='purchase',
                description=f"Покупка токенов (платёж {payment.id})"
            )

        if update_fields:
            await self.asave(update_fields=update_fields)

    @classmethod
    async def mark_blocked(cls, telegram_id: int):
        """Отмечает пользователя как заблокировавшего бота (по telegram_id)."""
        await cls.objects.filter(telegram_id=telegram_id).aupdate(is_blocked=True)

    @classmethod
    async def mark_unblocked(cls, telegram_id: int):
        """Отмечает пользователя как разблокировавшего бота (по telegram_id)."""
        await cls.objects.filter(telegram_id=telegram_id).aupdate(is_blocked=False)

    @classmethod
    async def mark_user_blocked(cls, user: 'User'):
        """Отмечает пользователя как недоступного для исходящих сообщений (любой канал)."""
        if user and user.pk:
            await cls.objects.filter(pk=user.pk).aupdate(is_blocked=True)

    @classmethod
    async def mark_user_unblocked(cls, user: 'User'):
        """Снимает флаг блокировки у пользователя (по pk, работает и для MAX-only)."""
        if user and user.pk:
            await cls.objects.filter(pk=user.pk).aupdate(is_blocked=False)

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
    practical_patterns = EncryptedJSONField(default=list, blank=True, verbose_name="Привычки и навыки")
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
            'practical_patterns', 'aspirations'
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


class IdentityLinkEvent(models.Model):
    """Аудит-событие привязки/отвязки transport identity к аккаунту пользователя."""

    EVENT_TYPE_CHOICES = [
        ('link', 'Привязка'),
        ('unlink', 'Отвязка'),
    ]
    RESULT_CHOICES = [
        ('success', 'Успех'),
        ('rejected', 'Отклонено'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='identity_link_events',
        verbose_name="Пользователь",
    )
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_identity_link_events',
        verbose_name="Инициатор",
    )
    actor_telegram_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Telegram ID инициатора",
    )
    event_type = models.CharField(
        max_length=16,
        choices=EVENT_TYPE_CHOICES,
        verbose_name="Тип события",
    )
    result = models.CharField(
        max_length=16,
        choices=RESULT_CHOICES,
        verbose_name="Результат",
    )
    source_platform = models.CharField(
        max_length=32,
        default='telegram',
        verbose_name="Платформа-источник",
    )
    source_context = models.CharField(
        max_length=64,
        default='unknown',
        verbose_name="Контекст источника",
    )
    reason_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name="Код причины",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Метаданные",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Событие привязки identity"
        verbose_name_plural = "События привязки identity"
        db_table = "users_identity_link_event"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['event_type', 'result']),
            models.Index(fields=['source_platform', 'source_context']),
        ]

    def __str__(self):
        return f"{self.event_type}:{self.result} user={self.user_id} reason={self.reason_code}"


class EmailMergeRequest(models.Model):
    """Запрос подтверждения merge при конфликте email между аккаунтами."""

    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждено'),
        ('merged', 'Объединено'),
        ('merge_failed', 'Ошибка объединения'),
        ('expired', 'Истекло'),
        ('cancelled', 'Отменено'),
    ]

    requester_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_merge_requests',
        verbose_name='Пользователь-инициатор',
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_merge_targets',
        verbose_name='Целевой пользователь',
    )
    email_hash = models.CharField(max_length=64, verbose_name='Email hash')
    confirmation_token = models.CharField(max_length=128, unique=True, verbose_name='Токен подтверждения')
    source_platform = models.CharField(max_length=32, default='web', verbose_name='Платформа-источник')
    source_context = models.CharField(max_length=64, default='complete_registration', verbose_name='Контекст источника')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    expires_at = models.DateTimeField(verbose_name='Истекает в')
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Подтверждено в')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Метаданные')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = 'Запрос merge по email'
        verbose_name_plural = 'Запросы merge по email'
        db_table = 'users_email_merge_request'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['requester_user', 'status']),
            models.Index(fields=['target_user', 'status']),
            models.Index(fields=['email_hash', 'status']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return (
            f"merge_request requester={self.requester_user_id} "
            f"target={self.target_user_id} status={self.status}"
        )

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
    photo_file_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID файла фото в Telegram")
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
            ('analysis', 'Анализ дня'),
            ('recover_streak', 'Восстановление серии'),
        ],
        verbose_name="Тип транзакции"
    )
    related_task_completion = models.ForeignKey(
        'diary.TaskCompletion',
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
        with transaction.atomic():
            transaction_obj = cls.objects.create(
                user=user,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                related_task_completion=related_task_completion
            )
            from django.db.models import F
            user.token_balance = F('token_balance') + amount
            user.save(update_fields=['token_balance'])
            logger.debug(f"[TokenTransaction] Транзакция ID {transaction_obj.id} создана, баланс пользователя {user.telegram_id} обновлен на {amount}. Новый баланс (в БД): {user.token_balance}")
            return transaction_obj

    @classmethod
    async def acreate_and_update_balance(cls, user, amount, transaction_type, description="", related_task_completion=None):
        """
        Асинхронный аналог create_and_update_balance.
        """
        return await sync_to_async(cls.create_and_update_balance)(
            user, amount, transaction_type, description, related_task_completion
        )
    
class Payment(models.Model):
    PAYMENT_TYPES = [
        ('subscription_month', 'Подписка (месяц)'),
        ('subscription_year', 'Подписка (год)'),
        ('tokens_custom', 'Токены (произвольно)'),
        ('tokens_10', 'Токены (10 шт)'),
        ('tokens_50', 'Токены (50 шт)'),
        ('tokens_100', 'Токены (100 шт)'),
        ('tokens_200', 'Токены (200 шт)'),
        ('tokens_500', 'Токены (500 шт)'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('succeeded', 'Успешно'),
        ('canceled', 'Отменён'),
        ('failed', 'Ошибка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    yookassa_payment_id = models.CharField(max_length=100, unique=True, verbose_name="ID платежа в ЮKassa")
    amount_rub = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма (RUB)")
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    tokens_granted = models.PositiveIntegerField(default=0, verbose_name="Начислено токенов")
    subscription_days_granted = models.PositiveIntegerField(default=0, verbose_name="Дней подписки")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_payment"
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"Платёж {self.yookassa_payment_id} ({self.status}) для {self.user}"