import uuid
import logging
import pytz

from asgiref.sync import sync_to_async
from datetime import datetime, date, timedelta
from django.db import models
from django.utils import timezone

from users.models import User
from django.utils.translation import gettext_lazy as _

from core.constants import (
    TASK_STATUS, 
    TASK_TYPES, ACTIVITY_TYPES, LANGUAGES
)

logger = logging.getLogger(__name__)

class DiaryEntry(models.Model):
    """Запись в дневнике"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"), related_name='diary_entries')
    text = models.TextField(verbose_name=_("Текст записи"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    language = models.CharField(
        max_length=2, 
        choices=LANGUAGES,
        verbose_name=_("Язык")
    )
    word_count = models.PositiveIntegerField(verbose_name=_("Количество слов"))
    is_processed = models.BooleanField(default=False, verbose_name=_("Обработана"))
    processing_error = models.TextField(blank=True, verbose_name=_("Ошибка обработки"))
    day_group = models.UUIDField(
        default=uuid.uuid4, 
        editable=False,
        verbose_name=_("Группа записей дня"),
        help_text=_("UUID для группировки записей одного дня")
    )
    clarification_questions_asked = models.JSONField(
        default=list, 
        blank=True, 
        verbose_name=_("Заданные уточняющие вопросы"),
        help_text=_("Список вопросов, заданных пользователю для уточнения по этой записи.")
    )
    clarification_answers = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ответы на уточнения"),
        help_text=_("Словарь ответов пользователя на уточняющие вопросы. Ключ - вопрос, значение - ответ.")
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("Основная запись дня"),
        help_text=_("Является ли эта запись основной для дня")
    )
    parent_entry = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Родительская запись"),
        help_text=_("Ссылка на основную запись дня")
    )
    clarification_asked_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_("Время запроса уточнений"),
        help_text=_("Время, когда ИИ запросил уточнения для этой записи.")
    )
    clarification_reminder_due_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Время, когда нужно отправить напоминание"),
        help_text=_("Предвычисленное время (в UTC) для отправки напоминания о неотвеченных уточнениях, с учетом часового пояса пользователя.")
    )
    clarification_force_process_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Время, когда нужно принудительно завершить анализ"),
        help_text=_("Предвычисленное время (в UTC) для принудительной обработки записи, с учетом часового пояса пользователя.")
    )
    last_reminder_sent_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_("Время последнего напоминания"),
        help_text=_("Время, когда было отправлено последнее напоминание о необходимости ответить на уточнения.")
    )
    analysis_processed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_("Время принудительной обработки анализа"),
        help_text=_("Время, когда был принудительно завершен анализ (например, из-за отсутствия ответов на уточнения).")
    )
    user_comment = models.TextField(
        blank=True,
        verbose_name=_("Комментарий пользователя"),
        help_text=_("Комментарий, добавленный пользователем после получения анализа.")
    )


    class Meta:
        verbose_name = _("Запись дневника")
        verbose_name_plural = _("Записи дневника")
        db_table = "diary_entry"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'day_group']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_processed']),
            models.Index(fields=['user', 'is_processed']),
        ]

    def __str__(self):
        return f"Запись {self.user.username} от {self.created_at.strftime('%d.%m.%Y')}"
    
    @property
    def entry_date(self) -> date:
        """Дата записи (без времени) с учетом часового пояса пользователя"""
        try:
            user_timezone_str = self.user.timezone if hasattr(self.user, 'timezone') and self.user.timezone else 'UTC'
            if not user_timezone_str:
                user_timezone_str = 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            created_at = self.created_at
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            localized_time = created_at.astimezone(user_tz)
            return localized_time.date()
        except Exception as e:
            logger.error(f"Ошибка при получении даты записи {self.id} в синхронном свойстве: {e}")
            # Фолбэк на UTC
            return self.created_at.date()

    # Убедимся, что асинхронная версия работает корректно
    async def aentry_date(self) -> date:
        """Асинхронная версия entry_date."""
        try:
            # Получаем пользователя асинхронно, если нужно
            # Но лучше использовать select_related в запросах
            user_obj = await sync_to_async(lambda: self.user)() if not hasattr(self, '_prefetched_user') else self.user
            user_timezone_str = user_obj.timezone if user_obj.timezone else 'UTC'
            if not user_timezone_str:
                user_timezone_str = 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            created_at = self.created_at
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            localized_time = created_at.astimezone(user_tz)
            return localized_time.date()
        except Exception as e:
            logger.error(f"Ошибка при получении даты записи {self.id} в асинхронном свойстве: {e}")
            # Фолбэк на UTC
            return self.created_at.date()

    @property
    def localized_created_at(self) -> str:
        """Локализованное время создания записи"""
        try:
            # Аналогично для localized_created_at
            user_timezone_str = self.user.timezone if hasattr(self.user, 'timezone') and self.user.timezone else 'UTC'
            if not user_timezone_str:
                user_timezone_str = 'UTC'
            created_at_for_conversion = self.created_at
            if created_at_for_conversion.tzinfo is None:
                created_at_for_conversion = pytz.utc.localize(created_at_for_conversion)
            user_tz = pytz.timezone(user_timezone_str)
            localized_time = created_at_for_conversion.astimezone(user_tz)
            return localized_time.strftime('%d.%m.%Y %H:%M')
        except Exception as e:
            logger.error(f"Ошибка при локализации времени для записи {self.id} в синхронном свойстве: {e}")
            if self.created_at.tzinfo:
                return self.created_at.strftime('%d.%m.%Y %H:%M UTC')
            else:
                return pytz.utc.localize(self.created_at).strftime('%d.%m.%Y %H:%M UTC')

    async def alocalized_created_at(self) -> str:
        """Асинхронная версия localized_created_at."""
        try:
            user_obj = await sync_to_async(lambda: self.user)() if not hasattr(self, '_prefetched_user') else self.user
            user_timezone_str = user_obj.timezone if user_obj.timezone else 'UTC'
            if not user_timezone_str:
                user_timezone_str = 'UTC'
            created_at_for_conversion = self.created_at
            if created_at_for_conversion.tzinfo is None:
                created_at_for_conversion = pytz.utc.localize(created_at_for_conversion)
            user_tz = pytz.timezone(user_timezone_str)
            localized_time = created_at_for_conversion.astimezone(user_tz)
            return localized_time.strftime('%d.%m.%Y %H:%M')
        except Exception as e:
            logger.error(f"Ошибка при локализации времени для записи {self.id} в асинхронном свойстве: {e}")
            if self.created_at.tzinfo:
                return self.created_at.strftime('%d.%m.%Y %H:%M UTC')
            else:
                return pytz.utc.localize(self.created_at).strftime('%d.%m.%Y %H:%M UTC')

    @property
    def combined_text(self) -> str:
        """Объединенный текст всех записей дня"""
        if self.is_primary:
            from django.db.models import Q
            entries = DiaryEntry.objects.filter(
                Q(user=self.user) & 
                Q(created_at__date=self.entry_date)
            ).order_by('created_at')
            texts = [entry.text for entry in entries]
            return "\n\n---\n\n".join(texts)
        else:
            return self.text
    
    async def acombined_text(self) -> str:
        """Асинхронный вариант объединенного текста"""
        if self.is_primary:
            from django.db.models import Q
            texts = []
            async for entry in DiaryEntry.objects.filter(
                Q(user=self.user) & 
                Q(created_at__date=self.entry_date)
            ).order_by('created_at'):
                texts.append(entry.text)
            return "\n\n---\n\n".join(texts)
        else:
            return self.text

class PsychoAnalysis(models.Model):
    """Результат психоанализа записи"""
    entry = models.OneToOneField(
        DiaryEntry, 
        on_delete=models.CASCADE, 
        related_name='analysis',
        verbose_name=_("Запись дневника")
    )
    mood_score = models.PositiveIntegerField(verbose_name=_("Оценка настроения (1-10)"))
    comment = models.TextField(verbose_name=_("Комментарий"))
    recommendation = models.TextField(verbose_name=_("Рекомендация"))
    processing_time = models.FloatField(verbose_name=_("Время обработки (сек)"))
    insights_extracted = models.PositiveIntegerField(verbose_name=_("Извлечено инсайтов"))
    analysis_text = models.TextField(verbose_name=_("Текст анализа"))
    api_response = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ответ API DeepSeek")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата последнего обновления"))

    class Meta:
        verbose_name = _("Психоанализ")
        verbose_name_plural = _("Психоанализы")
        db_table = "diary_psycho_analysis"
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['entry', 'created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['mood_score']),
        ]

    def __str__(self):
        return f"Анализ записи {self.entry.id} - {self.mood_score}/10"

class TherapyProgress(models.Model):
    """Прогресс терапии пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    date = models.DateField(verbose_name=_("Дата"))
    avg_mood = models.FloatField(verbose_name=_("Среднее настроение"))
    insights_count = models.PositiveIntegerField(verbose_name=_("Количество инсайтов"))
    trigger_count = models.PositiveIntegerField(verbose_name=_("Количество триггеров"))
    depth_score = models.PositiveIntegerField(verbose_name=_("Оценка глубины"))
    tasks_completed = models.PositiveIntegerField(verbose_name=_("Выполнено заданий"))
    consistency_score = models.FloatField(verbose_name=_("Оценка регулярности"))

    class Meta:
        verbose_name = _("Прогресс терапии")
        verbose_name_plural = _("Прогресс терапии")
        db_table = "diary_therapy_progress"
        unique_together = ['user', 'date']

    def __str__(self):
        return f"Прогресс {self.user.username} на {self.date}"

class TherapyTask(models.Model):
    """Терапевтическое задание"""
    COMPLEXITY_CHOICES = [
        ('low', 'Легкий'),
        ('medium', 'Средний'),
        ('high', 'Сложный'),
    ]    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='tasks',
        verbose_name=_("Пользователь")
    )
    title = models.CharField(max_length=200, verbose_name=_("Название"))
    description = models.TextField(verbose_name=_("Описание"))
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Назначено"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Выполнено"))
    related_entry = models.ForeignKey(
        DiaryEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Связанная запись дневника",
        help_text="Запись дневника, которая привела к назначению этого задания.",
        related_name='assigned_tasks'
    )
    status = models.CharField(
        max_length=11, 
        choices=TASK_STATUS,
        verbose_name=_("Статус")
    )
    type = models.CharField(
        max_length=15, 
        choices=TASK_TYPES,
        verbose_name=_("Тип")
    )
    complexity = models.CharField(
        max_length=10,
        choices=COMPLEXITY_CHOICES,
        verbose_name=_("Сложность задания"),
        default='medium'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        default=timezone.now() + timedelta(days=7),
        verbose_name=_("Срок действия задания"),
        help_text=_("Дата и время, до которого задание считается активным. После этого времени статус изменится на 'expired'.")
    )

    class Meta:
        verbose_name = _("Терапевтическое задание")
        verbose_name_plural = _("Терапевтические задания")
        db_table = "diary_therapy_task"
        ordering = ['-assigned_at']

    def __str__(self):
        return f"Задание: {self.title} для {self.user.username}"

class TaskCompletion(models.Model):
    """Выполнение задания"""
    task = models.OneToOneField(
        TherapyTask, 
        on_delete=models.CASCADE, 
        related_name='completion',
        verbose_name=_("Задание")
    )
    completion_text = models.TextField(verbose_name=_("Текст выполнения"))
    feelings_text = models.TextField(verbose_name=_("Ощущения при выполнении"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата выполнения"))

    class Meta:
        verbose_name = _("Выполнение задания")
        verbose_name_plural = _("Выполнения заданий")
        db_table = "diary_task_completion"

    def __str__(self):
        return f"Выполнение {self.task.title}"

class TaskCompletionAnalysis(models.Model):
    """
    Анализ выполнения терапевтического задания.
    Хранит результат анализа влияния выполнения задания на эмоциональное состояние и инсайты.
    """
    completion = models.OneToOneField(
        'TaskCompletion',
        on_delete=models.CASCADE,
        related_name='completion_analysis',
        verbose_name=_("Выполнение задания")
    )
    effect_description = models.TextField(
        verbose_name=_("Описание эффекта"),
        help_text=_("Текстовое описание влияния выполнения задания (например, 'Повышение настроения на X баллов').")
    )
    mood_impact_score = models.IntegerField(
        null=True, blank=True,
        verbose_name=_("Влияние на настроение"),
        help_text=_("Изменение оценки настроения дня после выполнения задания (может быть положительным или отрицательным).")
    )
    comment = models.TextField(
        blank=True,
        verbose_name=_("Комментарий ИИ"),
        help_text=_("Краткий комментарий от ИИ по результатам анализа выполнения.")
    )
    recommendation = models.TextField(
        blank=True,
        verbose_name=_("Рекомендация ИИ"),
        help_text=_("Персональная рекомендация от ИИ, вытекающая из анализа выполнения.")
    )
    analysis_performed_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата выполнения анализа"))
    api_response = models.JSONField(default=dict, blank=True, verbose_name=_("Ответ API DeepSeek"))
    detailed_analysis = models.TextField(
        blank=True,
        verbose_name=_("Развернутый анализ"),
        help_text=_("Подробный анализ влияния выполнения задания, включая сравнение дней и обоснование оценки.")
    )
    is_obsolete = models.BooleanField(
        default=False,
        verbose_name=_("Устаревший анализ"),
        help_text=_("Помечает анализ как устаревший, если задание было выполнено повторно.")
    )

    class Meta:
        verbose_name = _("Анализ выполнения задания")
        verbose_name_plural = _("Анализы выполнения заданий")
        db_table = "diary_task_completion_analysis"

    def __str__(self):
        base_str = f"Анализ выполнения {self.completion.task.title} ({self.completion.task.user.username})"
        if self.detailed_analysis:
            return f"{base_str}: {self.detailed_analysis[:50]}..."
        return base_str

class UserActivity(models.Model):
    """Активность пользователя"""
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        verbose_name=_("Пользователь")
    )
    activity_type = models.CharField(
        max_length=20, 
        choices=ACTIVITY_TYPES,
        verbose_name=_("Тип активности")
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Время"))
    metadata = models.JSONField(blank=True, default=dict, verbose_name=_("Метаданные"))

    class Meta:
        verbose_name = _("Активность пользователя")
        verbose_name_plural = _("Активности пользователей")
        db_table = "diary_user_activity"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()}"
    
class CombinedDiaryEntry(models.Model):
    """
    Объединенная запись дня для глубокого анализа ИИ.
    Хранит объединенный текст всех записей пользователя за конкретный день
    и промежуточное "состояние дня", определенное ИИ.
    """
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        verbose_name=_("Пользователь"),
        related_name='combined_entries'
    )
    date = models.DateField(verbose_name=_("Дата"))
    text = models.TextField(verbose_name=_("Объединенный текст всех записей дня"))
    entry_count = models.PositiveIntegerField(verbose_name=_("Количество записей в этот день"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата последнего обновления"))
    ai_state_data = models.TextField(
        blank=True, 
        default="", 
        verbose_name=_("Состояние дня по версии ИИ"),
        help_text=_("Текстовый контекст или структурированные данные от ИИ, описывающие состояние дня.")
    )
    is_analyzed = models.BooleanField(
        default=False, 
        verbose_name=_("Проанализирован ИИ"),
        help_text=_("Указывает, был ли день проанализирован ИИ с учетом всех записей.")
    )
    analysis_result = models.JSONField(
        blank=True, 
        default=dict, 
        verbose_name=_("Результат анализа (детали)"),
        help_text=_("Детальный результат финального анализа дня (например, JSON с итоговой оценкой, комментарием и т.д.).")
    )
    daily_mood_scores = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Список оценок настроения за день"),
        help_text=_("Список всех mood_score из PsychoAnalysis для записей этого дня.")
    )
    average_mood_score = models.FloatField(
        default=0.0,
        verbose_name=_("Средняя оценка настроения за день"),
        help_text=_("Среднее арифметическое всех mood_score записей за день.")
    )

    class Meta:
        verbose_name = _("Объединенная запись дня")
        verbose_name_plural = _("Объединенные записи дней")
        db_table = "diary_combined_entry"
        unique_together = ['user', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user', 'date']),
            models.Index(fields=['is_analyzed']),
        ]

    def __str__(self):
        return f"Объединенная запись {self.user.username} от {self.date}"
    
    def localized_date_at(self) -> datetime:
        """
        Возвращает datetime для начала этого дня в часовом поясе пользователя.
        Полезно для согласованности с DiaryEntry.localized_created_at.
        """
        try:
            user_timezone_str = self.user.timezone if self.user else 'UTC'
            if not user_timezone_str:
                 user_timezone_str = 'UTC'      
            user_tz = pytz.timezone(user_timezone_str)
            naive_datetime = datetime.combine(self.date, datetime.min.time())
            localized_datetime = user_tz.localize(naive_datetime)
            return localized_datetime
        except Exception as e:
            logger.error(f"Ошибка при локализации даты CombinedDiaryEntry: {e}")
            naive_datetime = datetime.combine(self.date, datetime.min.time())
            return pytz.utc.localize(naive_datetime)
        
    def update_mood_scores(self, new_score: int):
        """
        Обновляет список оценок и пересчитывает среднее.
        """
        try:
            if not isinstance(new_score, int) or not (1 <= new_score <= 10):
                logger.warning(f"Некорректная оценка {new_score}")
                return
            if not isinstance(self.daily_mood_scores, list):
                self.daily_mood_scores = []
            self.daily_mood_scores.append(new_score)
            if self.daily_mood_scores:
                self.average_mood_score = sum(self.daily_mood_scores) / len(self.daily_mood_scores)
            else:
                self.average_mood_score = 0.0
            self.save(update_fields=['daily_mood_scores', 'average_mood_score'])
        except Exception as e:
            logger.error(f"Ошибка обновления оценок настроения: {e}")

    def reset_analysis_flag(self):
        """
        Сбрасывает флаг анализа, указывая, что данные изменились и нужен пересчет.
        """
        self.is_analyzed = False

class DailyAnalysis(models.Model):
    """Глубокий анализ дня"""
    combined_entry = models.OneToOneField(
        CombinedDiaryEntry, 
        on_delete=models.CASCADE, 
        related_name='daily_analysis',
        verbose_name=_("Объединенная запись")
    )
    mood_trend = models.CharField(
        max_length=20,
        choices=[
            ('improving', _('Улучшается')),
            ('declining', _('Ухудшается')),
            ('stable', _('Стабильный')),
            ('volatile', _('Нестабильный')),
        ],
        verbose_name=_("Тренд настроения")
    )
    key_themes = models.JSONField(default=list, verbose_name=_("Ключевые темы"))
    emotional_patterns = models.JSONField(default=list, verbose_name=_("Эмоциональные паттерны"))
    insights = models.JSONField(default=list, verbose_name=_("Инсайты"))
    recommendations = models.JSONField(default=list, verbose_name=_("Рекомендации"))
    overall_analysis_text = models.TextField(
        blank=True,
        verbose_name=_("Общий текстовый анализ дня"),
        help_text=_("Полный текстовый анализ дня, сгенерированный ИИ.")
    )
    api_response = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ответ API DeepSeek"),
        help_text=_("Полный ответ API DeepSeek при анализе дня.")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Глубокий анализ дня")
        verbose_name_plural = _("Глубокие анализы дней")
        db_table = "diary_daily_analysis"

    def __str__(self):
        return f"Анализ дня {self.combined_entry.date} пользователя {self.combined_entry.user.username}"

class WeeklyAnalysis(models.Model):
    """
    Результат еженедельного анализа пользователя ИИ.
    Содержит сводку недели, инсайты, обновления профиля и статистику.
    Используется для отображения прогресса и как контекст для следующего анализа.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"), related_name='weekly_analyses')
    week_start_date = models.DateField(verbose_name=_("Дата начала недели (Понедельник)"))
    summary_text = models.TextField(verbose_name=_("Краткое резюме недели от ИИ"))
    progress_insights = models.JSONField(default=dict, blank=True, verbose_name=_("Ключевые инсайты и выводы по прогрессу"))
    consolidated_user_profile = models.JSONField(default=dict, blank=True, verbose_name=_("Обновленный/обобщенный психологический профиль"))
    statistics = models.JSONField(default=dict, blank=True, verbose_name=_("Агрегированная статистика недели"))
    comparison_with_previous = models.JSONField(default=dict, blank=True, verbose_name=_("Сравнение с предыдущей неделей"))
    api_response = models.JSONField(default=dict, blank=True, verbose_name=_("Полный ответ API DeepSeek"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Еженедельный анализ")
        verbose_name_plural = _("Еженедельные анализы")
        db_table = "diary_weekly_analysis"
        unique_together = ['user', 'week_start_date']
        ordering = ['-week_start_date']

    def __str__(self):
        return f"Анализ недели {self.week_start_date} для {self.user.username}"
    
class NextEntryPrompt(models.Model):
    """
    Модель для хранения персонализированных подсказок для следующей записи пользователя.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='next_entry_prompts', verbose_name="Пользователь")
    target_date = models.DateField(verbose_name="Дата, для которой предназначена подсказка")
    prompt_text = models.TextField(verbose_name="Текст подсказки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    is_used = models.BooleanField(default=False, verbose_name="Использовано")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата использования")

    class Meta:
        verbose_name = "Подсказка для следующей записи"
        verbose_name_plural = "Подсказки для следующих записей"
        db_table = "diary_next_entry_prompt"
        unique_together = ['user', 'target_date']
        indexes = [
            models.Index(fields=['user', 'is_used', '-created_at']),
            models.Index(fields=['user', 'target_date']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Подсказка для {self.user.username} на {self.target_date} (Использована: {self.is_used})"

    def mark_as_used(self):
        """Помечает подсказку как использованную."""
        from django.utils import timezone
        if not self.is_used:
            self.is_used = True
            self.used_at = timezone.now()
            self.save(update_fields=['is_used', 'used_at'])
            logger.debug(f"Подсказка ID {self.id} для пользователя {self.user.telegram_id} помечена как использованная.")

    @classmethod
    async def aget_latest_unused_prompt(cls, user):
        """
        Асинхронно получает последнюю непросмотренную подсказку для пользователя.
        """
        from asgiref.sync import sync_to_async
        try:
            @sync_to_async
            def _get_prompt_sync():
                return cls.objects.filter(user=user, is_used=False).order_by('-created_at').first()
            prompt = await _get_prompt_sync()
            if prompt:
                logger.debug(f"Найдена непросмотренная подсказка ID {prompt.id} для пользователя {user.telegram_id}")
                return prompt
            else:
                logger.debug(f"Непросмотренных подсказок для пользователя {user.telegram_id} не найдено.")
                return None
        except Exception as e:
            logger.error(f"Ошибка при асинхронном поиске последней непросмотренной подсказки для пользователя {user.telegram_id}: {e}")
            return None

class AnalysisRating(models.Model):
    """
    Модель для хранения оценок пользователя анализа записи (PsychoAnalysis).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    analysis = models.ForeignKey(PsychoAnalysis, on_delete=models.CASCADE, related_name='user_ratings', verbose_name=_("Анализ"))
    rating = models.PositiveSmallIntegerField(
        verbose_name=_("Оценка (1-5)"),
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    rated_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата оценки"))

    class Meta:
        verbose_name = _("Оценка анализа")
        verbose_name_plural = _("Оценки анализа")
        db_table = "diary_analysis_rating"
        unique_together = ['user', 'analysis']

    def __str__(self):
        return f"Оценка {self.rating} от {self.user.username} для анализа {self.analysis.id}"