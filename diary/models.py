import uuid
import logging
import pytz

from datetime import datetime, date
from django.db import models
from users.models import User
from django.utils.translation import gettext_lazy as _

from core.constants import (
    KEYPOINT_TYPES, INSIGHT_CATEGORIES, TASK_STATUS, 
    TASK_TYPES, ACTIVITY_TYPES, MOOD_SCORES, LANGUAGES, TASK_PRIORITIES
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
        choices=LANGUAGES,  # из constants
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

    class Meta:
        verbose_name = _("Запись дневника")
        verbose_name_plural = _("Записи дневника")
        db_table = "diary_entry"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'day_group']),
            models.Index(fields=['created_at']),  # Для быстрого поиска по дате
        ]

    def __str__(self):
        return f"Запись {self.user.username} от {self.created_at.strftime('%d.%m.%Y')}"
    
    @property
    def localized_created_at(self) -> str:
        """Локализованное время создания записи"""
        try:
            # Используем метод модели User для получения локального времени
            user_local_dt = self.user.get_local_datetime()
            user_timezone_str = self.user.timezone if self.user else 'UTC'
            if not user_timezone_str:
                 user_timezone_str = 'UTC'
                 
            # Убедимся, что created_at это aware datetime
            created_at_for_conversion = self.created_at
            if created_at_for_conversion.tzinfo is None:
                created_at_for_conversion = pytz.utc.localize(created_at_for_conversion)
            
            # Вместо повторения логики get_local_datetime, просто конвертируем created_at
            # в часовой пояс пользователя
            user_tz = pytz.timezone(user_timezone_str)
            localized_time = created_at_for_conversion.astimezone(user_tz)
            
            return localized_time.strftime('%d.%m.%Y %H:%M')

        except Exception as e:
            logger.error(f"Ошибка при локализации времени для записи {self.id}: {e}")
            # Возвращаем время в UTC если не удалось
            if self.created_at.tzinfo:
                return self.created_at.strftime('%d.%m.%Y %H:%M UTC')
            else:
                return pytz.utc.localize(self.created_at).strftime('%d.%m.%Y %H:%M UTC')

    @property
    def entry_date(self) -> date:
        """Дата записи (без времени) с учетом часового пояса пользователя"""
        try:
            # Используем метод модели User для получения локального времени
            user_local_dt = self.user.get_local_datetime()
            user_timezone_str = self.user.timezone if self.user else 'UTC'
            if not user_timezone_str:
                 user_timezone_str = 'UTC'
                 
            # Убедимся, что created_at это aware datetime
            created_at_for_conversion = self.created_at
            if created_at_for_conversion.tzinfo is None:
                created_at_for_conversion = pytz.utc.localize(created_at_for_conversion)
            
            # Конвертируем created_at в часовой пояс пользователя и возвращаем дату
            user_tz = pytz.timezone(user_timezone_str)
            localized_time = created_at_for_conversion.astimezone(user_tz)
            
            return localized_time.date()

        except Exception as e:
            logger.error(f"Ошибка при получении даты записи {self.id}: {e}")
            # Возвращаем дату в UTC если не удалось
            if self.created_at.tzinfo:
                return self.created_at.date()
            else:
                return pytz.utc.localize(self.created_at).date()
    
    @property
    def combined_text(self) -> str:
        """Объединенный текст всех записей дня"""
        if self.is_primary:
            # Если это основная запись, объединяем все записи дня
            from django.db.models import Q
            entries = DiaryEntry.objects.filter(
                Q(user=self.user) & 
                Q(created_at__date=self.entry_date)
            ).order_by('created_at')
            
            texts = [entry.text for entry in entries]
            return "\n\n---\n\n".join(texts)  # Разделяем записями
        else:
            # Если не основная, возвращаем только свой текст
            return self.text
    
    async def acombined_text(self) -> str:
        """Асинхронный вариант объединенного текста"""
        if self.is_primary:
            # Если это основная запись, объединяем все записи дня
            from django.db.models import Q
            texts = []
            async for entry in DiaryEntry.objects.filter(
                Q(user=self.user) & 
                Q(created_at__date=self.entry_date)
            ).order_by('created_at'):
                texts.append(entry.text)
            
            return "\n\n---\n\n".join(texts)  # Разделяем записями
        else:
            # Если не основная, возвращаем только свой текст
            return self.text

class VoiceToText(models.Model):
    """Результат преобразования голоса в текст"""
    entry = models.OneToOneField(
        DiaryEntry, 
        on_delete=models.CASCADE, 
        verbose_name=_("Запись дневника")
    )
    original_duration = models.PositiveIntegerField(verbose_name=_("Длительность оригинала (сек)"))
    processed_text = models.TextField(verbose_name=_("Обработанный текст"))
    processing_time = models.FloatField(verbose_name=_("Время обработки (сек)"))
    speechkit_response = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ответ Yandex SpeechKit")
    )
    api_response = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ответ API постобработки (DeepSeek)") 
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Голос в текст")
        verbose_name_plural = _("Голос в текст")
        db_table = "diary_voice_to_text"
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['entry', 'created_at']),
        ]

    def __str__(self):
        return f"Распознавание для {self.entry}"

class KeyPoint(models.Model):
    """Ключевой момент из записи"""
    
    entry = models.ForeignKey(
        DiaryEntry, 
        on_delete=models.CASCADE, 
        related_name='key_points',
        verbose_name=_("Запись дневника")
    )
    text = models.TextField(verbose_name=_("Текст ключевого момента"))
    type = models.CharField(
        max_length=10, 
        choices=KEYPOINT_TYPES,  # из constants
        verbose_name=_("Тип")
    )
    confidence = models.FloatField(default=1.0, verbose_name=_("Уверенность"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Ключевой момент")
        verbose_name_plural = _("Ключевые моменты")
        db_table = "diary_key_point"
        # === НОВЫЙ ИНДЕКС ===
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['entry', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_type_display()}: {self.text[:50]}..."

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
            models.Index(fields=['-created_at']), # Для сортировки по убыванию
        ]

    def __str__(self):
        return f"Анализ записи {self.entry.id} - {self.mood_score}/10"

class UserInsight(models.Model):
    """Инсайт пользователя"""
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='insights',
        verbose_name=_("Пользователь")
    )
    text = models.TextField(verbose_name=_("Текст инсайта"))
    weight = models.PositiveIntegerField(default=1, verbose_name=_("Вес"))
    last_mentioned = models.DateTimeField(verbose_name=_("Последнее упоминание"))
    category = models.CharField(
        max_length=50, 
        choices=INSIGHT_CATEGORIES,
        verbose_name=_("Категория")
    )
    first_mentioned = models.DateTimeField(auto_now_add=True, verbose_name=_("Первое упоминание"))
    source_entry = models.ForeignKey(
        'DiaryEntry', # Используем строковое имя для избежания циклических импортов
        on_delete=models.CASCADE, # Каскадное удаление: если DiaryEntry удаляется, UserInsight тоже удаляется
        related_name='generated_insights', # related_name для доступа из DiaryEntry: entry.generated_insights.all()
        verbose_name=_("Исходная запись дневника"),
        help_text=_("Запись дневника, из которой был извлечен этот инсайт."),
        null=True, # Разрешаем временно NULL, если инсайты создаются не только из записей
        blank=True # Разрешаем пустое поле в формах
    )

    class Meta:
        verbose_name = _("Инсайт пользователя")
        verbose_name_plural = _("Инсайты пользователя")
        db_table = "diary_user_insight"

    def __str__(self):
        return f"{self.user.username}: {self.text[:50]}..."

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
        on_delete=models.SET_NULL, # Или CASCADE, если удаление записи должно удалять задание
        null=True,
        blank=True,
        verbose_name="Связанная запись дневника",
        help_text="Запись дневника, которая привела к назначению этого задания.",
        related_name='assigned_tasks' # Позволяет получить задания из записи: entry.assigned_tasks.all()
    )
    status = models.CharField(
        max_length=11, 
        choices=TASK_STATUS,  # из constants
        verbose_name=_("Статус")
    )
    type = models.CharField(
        max_length=15, 
        choices=TASK_TYPES,  # из constants
        verbose_name=_("Тип")
    )

    priority = models.PositiveIntegerField(default=1, verbose_name=_("Сложность"))

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
    time_spent = models.PositiveIntegerField(verbose_name=_("Время выполнения (мин)"))

    class Meta:
        verbose_name = _("Выполнение задания")
        verbose_name_plural = _("Выполнения заданий")
        db_table = "diary_task_completion"

    def __str__(self):
        return f"Выполнение {self.task.title}"

class TaskAnalysis(models.Model):
    """Анализ выполнения задания"""
    completion = models.OneToOneField(
        TaskCompletion, 
        on_delete=models.CASCADE, 
        related_name='analysis',
        verbose_name=_("Выполнение")
    )
    bot_response = models.TextField(verbose_name=_("Ответ бота"))
    insights_updated = models.BooleanField(default=False, verbose_name=_("Инсайты обновлены"))
    quality_score = models.PositiveIntegerField(verbose_name=_("Оценка качества (1-10)"))
    feedback_given = models.BooleanField(default=False, verbose_name=_("Обратная связь дана"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Анализ задания")
        verbose_name_plural = _("Анализы заданий")
        db_table = "diary_task_analysis"
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['completion', 'created_at']),
        ]

    def __str__(self):
        return f"Анализ выполнения {self.completion.task.title}"

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
    related_insights = models.ManyToManyField(
        'UserInsight', 
        blank=True, 
        verbose_name=_("Связанные инсайты"),
        help_text=_("Инсайты пользователя, которые были выявлены или усилена в результате выполнения этого задания.")
    )
    # Ключевые моменты дня до выполнения задания (сохраненные для сравнения)
    key_points_before = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ключевые моменты дня до выполнения"),
        help_text=_("Ключевые моменты (эмоции, события и т.д.) из CombinedDiaryEntry на момент до выполнения задания.")
    )
    # Ключевые моменты дня после выполнения задания (сохраненные для сравнения)
    key_points_after = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_("Ключевые моменты дня после выполнения"),
        help_text=_("Ключевые моменты (эмоции, события и т.д.) из CombinedDiaryEntry на момент после выполнения задания (если анализ проводился позже).")
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
    # Храним ответ API для дебага/детализации
    api_response = models.JSONField(default=dict, blank=True, verbose_name=_("Ответ API DeepSeek"))

    class Meta:
        verbose_name = _("Анализ выполнения задания")
        verbose_name_plural = _("Анализы выполнения заданий")
        db_table = "diary_task_completion_analysis"

    def __str__(self):
        return f"Анализ выполнения {self.completion.task.title} ({self.completion.task.user.username})"

class UserActivity(models.Model):
    """Активность пользователя"""
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        verbose_name=_("Пользователь")
    )
    activity_type = models.CharField(
        max_length=20, 
        choices=ACTIVITY_TYPES,  # из constants
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
    # === ФЛАГ АНАЛИЗА ИИ ===
    ai_state_data = models.TextField(
        blank=True, 
        default="", 
        verbose_name=_("Состояние дня по версии ИИ"),
        help_text=_("Текстовый контекст или структурированные данные от ИИ, описывающие состояние дня.")
    )
    # === ФЛАГ АНАЛИЗА ИИ ===
    is_analyzed = models.BooleanField(
        default=False, 
        verbose_name=_("Проанализирован ИИ"),
        help_text=_("Указывает, был ли день проанализирован ИИ с учетом всех записей.")
    )
    # === РЕЗУЛЬТАТ АНАЛИЗА ===
    analysis_result = models.JSONField(
        blank=True, 
        default=dict, 
        verbose_name=_("Результат анализа (детали)"),
        help_text=_("Детальный результат финального анализа дня (например, JSON с итоговой оценкой, комментарием и т.д.).")
    )
    # Храним список всех mood_score за день для расчета среднего
    daily_mood_scores = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Список оценок настроения за день"),
        help_text=_("Список всех mood_score из PsychoAnalysis для записей этого дня.")
    )
    
    # Храним рассчитанное среднее значение настроения за день
    average_mood_score = models.FloatField(
        default=0.0,
        verbose_name=_("Средняя оценка настроения за день"),
        help_text=_("Среднее арифметическое всех mood_score записей за день.")
    )

    class Meta:
        verbose_name = _("Объединенная запись дня")
        verbose_name_plural = _("Объединенные записи дней")
        db_table = "diary_combined_entry"
        unique_together = ['user', 'date'] # Уникальность по пользователю и дате
        ordering = ['-date'] # Сортировка по убыванию даты

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
            # Создаем datetime для начала дня (00:00:00) в UTC, затем локализуем и переводим
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
        
        Args:
            new_score: Новая оценка настроения (1-10).
        """
        logger.info(f"Обновление оценок настроения для CombinedDiaryEntry ID {self.id}")
        if not isinstance(new_score, int) or not (1 <= new_score <= 10):
            logger.warning(f"Некорректная оценка {new_score} для CombinedDiaryEntry ID {self.id}")
            return

        # Добавляем новую оценку
        self.daily_mood_scores.append(new_score)
        logger.debug(f"Добавлена оценка {new_score}. Список: {self.daily_mood_scores}")

        # Пересчитываем среднее
        if self.daily_mood_scores:
            self.average_mood_score = sum(self.daily_mood_scores) / len(self.daily_mood_scores)
            logger.info(f"Средняя оценка пересчитана: {self.average_mood_score:.2f}")
        else:
            self.average_mood_score = 0.0
            logger.info("Список оценок пуст, средняя оценка установлена в 0.0")

        # Сохраняем изменения
        self.save(update_fields=['daily_mood_scores', 'average_mood_score'])
        logger.info(f"CombinedDiaryEntry ID {self.id} обновлен с новой оценкой и средним значением.")

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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Глубокий анализ дня")
        verbose_name_plural = _("Глубокие анализы дней")
        db_table = "diary_daily_analysis"

    def __str__(self):
        return f"Анализ дня {self.combined_entry.date} пользователя {self.combined_entry.user.username}"
