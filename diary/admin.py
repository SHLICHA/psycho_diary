# diary/admin.py
"""
Админка для приложения diary.
"""

import logging
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from diary.models import *

logger = logging.getLogger(__name__)

# === DiaryEntry Admin ===
@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    """
    Админка для записей дневника.
    """
    list_display = (
        'id', 'user_link', 'short_text', 'entry_date', 'word_count', 
        'is_processed', 'has_analysis', 'created_at'
    )
    list_filter = (
        'is_processed', 'language', 'created_at', 'updated_at',
        ('user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'user__username', 'user__telegram_id', 'text', 'id'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'entry_date', 'localized_created_at', 
        'combined_text_display', 'analysis_link', 'voice_to_text_link',
        'key_points_inline', 'assigned_tasks_inline'
    )
    # raw_id_fields = ('user', 'parent_entry') # Для быстрого поиска пользователей
    
    fieldsets = (
        (None, {
            'fields': ('user', 'text', 'language', 'word_count')
        }),
        (_('Даты и время'), {
            'fields': ('created_at', 'updated_at', 'entry_date', 'localized_created_at'),
            'classes': ('collapse',)
        }),
        (_('Статус обработки'), {
            'fields': ('is_processed', 'processing_error')
        }),
        (_('Группировка'), {
            'fields': ('is_primary', 'parent_entry'),
            'classes': ('collapse',)
        }),
        (_('Уточнения'), {
            'fields': ('clarification_questions_asked','clarification_answers'),
            'classes': ('collapse',)
        }),
        (_('Связанные данные'), {
            'fields': (
                'combined_text_display', 'analysis_link', 'voice_to_text_link',
                'key_points_inline', 'assigned_tasks_inline'
            )
        }),
    )
    
    # Оптимизация запросов
    list_select_related = ('user', 'analysis') # Оптимизирует JOIN с PsychoAnalysis
    list_prefetch_related = ('key_points', 'assigned_tasks') # Оптимизирует запросы к ключевым моментам и заданиям

    def user_link(self, obj):
        """Ссылка на пользователя в админке."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = _('Пользователь')
    user_link.admin_order_field = 'user__username'

    def short_text(self, obj):
        """Короткий текст записи."""
        if obj.text:
            return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
        return '-'
    short_text.short_description = _('Текст (короткий)')
    short_text.admin_order_field = 'text'

    def has_analysis(self, obj):
        """Есть ли анализ у записи."""
        return hasattr(obj, 'analysis')
    has_analysis.boolean = True
    has_analysis.short_description = _('Анализ')

    def combined_text_display(self, obj):
        """Отображение объединенного текста."""
        if obj.is_primary:
            combined_text = obj.combined_text
            if combined_text:
                return format_html('<pre>{}</pre>', combined_text[:1000] + "..." if len(combined_text) > 1000 else combined_text)
        return _('(Не основная запись)')
    combined_text_display.short_description = _('Объединенный текст дня')

    def analysis_link(self, obj):
        """Ссылка на анализ записи."""
        if hasattr(obj, 'analysis'):
            url = reverse('admin:diary_psychoanalysis_change', args=[obj.analysis.id])
            return format_html('<a href="{}">Анализ ID {}</a>', url, obj.analysis.id)
        return '-'
    analysis_link.short_description = _('Анализ')

    def voice_to_text_link(self, obj):
        """Ссылка на VoiceToText."""
        try:
            if hasattr(obj, 'voice_to_text'):
                url = reverse('admin:diary_voicetotext_change', args=[obj.voice_to_text.id])
                return format_html('<a href="{}">VoiceToText ID {}</a>', url, obj.voice_to_text.id)
        except Exception as e:
            logger.error(f"Ошибка при получении VoiceToText для записи {obj.id}: {e}")
        return '-'
    voice_to_text_link.short_description = _('Распознавание голоса')

    def key_points_inline(self, obj):
        """Инлайн отображение ключевых моментов."""
        if obj.key_points.exists():
            key_points_links = []
            for kp in obj.key_points.all()[:5]: # Показываем только первые 5
                url = reverse('admin:diary_keypoint_change', args=[kp.id])
                key_points_links.append(format_html('<a href="{}">{}</a>', url, kp.text[:30] + "..." if len(kp.text) > 30 else kp.text))
            more_count = obj.key_points.count() - 5
            if more_count > 0:
                key_points_links.append(format_html('<i>+ ещё {}...</i>', more_count))
            return format_html('<br>'.join(key_points_links))
        return '-'
    key_points_inline.short_description = _('Ключевые моменты')

    def assigned_tasks_inline(self, obj):
        """Инлайн отображение назначенных заданий."""
        if obj.assigned_tasks.exists():
            tasks_links = []
            for task in obj.assigned_tasks.all()[:3]: # Показываем только первые 3
                url = reverse('admin:diary_therapytask_change', args=[task.id])
                tasks_links.append(format_html('<a href="{}">{}</a>', url, task.title[:30] + "..." if len(task.title) > 30 else task.title))
            more_count = obj.assigned_tasks.count() - 3
            if more_count > 0:
                tasks_links.append(format_html('<i>+ ещё {}...</i>', more_count))
            return format_html('<br>'.join(tasks_links))
        return '-'
    assigned_tasks_inline.short_description = _('Назначенные задания')

# === PsychoAnalysis Admin ===
@admin.register(PsychoAnalysis)
class PsychoAnalysisAdmin(admin.ModelAdmin):
    """
    Админка для результатов психоанализа.
    """
    list_display = (
        'id', 'entry_link', 'mood_score', 'short_comment', 'short_recommendation', 
        'created_at'
    )
    list_filter = (
        'mood_score', 'created_at',
        ('entry__user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'entry__id', 'entry__user__username', 'comment', 'recommendation'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'entry_link', 'analysis_text_full', 
        'api_response_display'
    )
    
    fieldsets = (
        (None, {
            'fields': ('entry_link', 'mood_score', 'comment', 'recommendation')
        }),
        (_('Подробный анализ'), {
            'fields': ('analysis_text_full',),
            'classes': ('collapse',)
        }),
        (_('Метрики API'), {
            'fields': ('processing_time', 'insights_extracted', 'api_response_display'),
            'classes': ('collapse',)
        }),
        (_('Даты'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def entry_link(self, obj):
        """Ссылка на запись дневника."""
        if obj.entry:
            url = reverse('admin:diary_diaryentry_change', args=[obj.entry.id])
            return format_html('<a href="{}">Запись ID {}</a>', url, obj.entry.id)
        return '-'
    entry_link.short_description = _('Запись дневника')

    def short_comment(self, obj):
        """Короткий комментарий."""
        if obj.comment:
            return obj.comment[:50] + "..." if len(obj.comment) > 50 else obj.comment
        return '-'
    short_comment.short_description = _('Комментарий (короткий)')
    short_comment.admin_order_field = 'comment'

    def short_recommendation(self, obj):
        """Короткая рекомендация."""
        if obj.recommendation:
            return obj.recommendation[:50] + "..." if len(obj.recommendation) > 50 else obj.recommendation
        return '-'
    short_recommendation.short_description = _('Рекомендация (короткая)')
    short_recommendation.admin_order_field = 'recommendation'

    def analysis_text_full(self, obj):
        """Полный текст анализа."""
        if obj.analysis_text:
            return format_html('<pre>{}</pre>', obj.analysis_text)
        return '-'
    analysis_text_full.short_description = _('Полный текст анализа')

    def api_response_display(self, obj):
        """Отображение ответа API."""
        if obj.api_response:
            import json
            try:
                response_json = json.dumps(obj.api_response, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', response_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании api_response: {e}")
                return str(obj.api_response)
        return '-'
    api_response_display.short_description = _('Ответ API')

# === TherapyProgress Admin ===
@admin.register(TherapyProgress)
class TherapyProgressAdmin(admin.ModelAdmin):
    """
    Админка для прогресса терапии.
    """
    list_display = (
        'id', 'user_link', 'date', 'avg_mood', 'insights_count', 
        'tasks_completed', 'consistency_score'
    )
    list_filter = (
        'date', 'avg_mood',
        ('user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'user__username', 'user__telegram_id'
    )
    readonly_fields = ('user_link',)
    
    fieldsets = (
        (None, {
            'fields': ('user_link', 'date')
        }),
        (_('Метрики'), {
            'fields': (
                'avg_mood', 'insights_count', 'trigger_count', 
                'depth_score', 'tasks_completed', 'consistency_score'
            )
        }),
    )

    def user_link(self, obj):
        """Ссылка на пользователя."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = _('Пользователь')
    user_link.admin_order_field = 'user__username'

# === TherapyTask Admin ===
@admin.register(TherapyTask)
class TherapyTaskAdmin(admin.ModelAdmin):
    """
    Админка для терапевтических заданий.
    """
    list_display = (
        'id', 'user_link', 'short_title', 'type', 'priority', 'status', 
        'assigned_at', 'completed_at_display'
    )
    list_filter = (
        'type', 'priority', 'status', 'assigned_at', 'completed_at',
        ('user', admin.RelatedOnlyFieldListFilter),
        ('related_entry', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'user__username', 'user__telegram_id', 'title', 'description'
    )
    readonly_fields = (
        'assigned_at', 'completed_at', 'user_link', 'related_entry_link',
        'completion_link'
    )
    
    fieldsets = (
        (None, {
            'fields': ('user_link', 'title', 'description', 'type', 'priority', 'status')
        }),
        (_('Связи'), {
            'fields': ('related_entry_link', 'completion_link')
        }),
        (_('Даты'), {
            'fields': ('assigned_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        """Ссылка на пользователя."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = _('Пользователь')
    user_link.admin_order_field = 'user__username'

    def short_title(self, obj):
        """Короткое название задания."""
        if obj.title:
            return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title
        return '-'
    short_title.short_description = _('Название (короткое)')
    short_title.admin_order_field = 'title'

    def completed_at_display(self, obj):
        """Отображение даты завершения."""
        if obj.completed_at:
            return obj.completed_at.strftime('%d.%m.%Y %H:%M')
        return '-'
    completed_at_display.short_description = _('Завершено')
    completed_at_display.admin_order_field = 'completed_at'

    def related_entry_link(self, obj):
        """Ссылка на связанную запись дневника."""
        if obj.related_entry:
            url = reverse('admin:diary_diaryentry_change', args=[obj.related_entry.id])
            return format_html('<a href="{}">Запись ID {}</a>', url, obj.related_entry.id)
        return '-'
    related_entry_link.short_description = _('Связанная запись')

    def completion_link(self, obj):
        """Ссылка на выполнение задания."""
        try:
            if hasattr(obj, 'completion'):
                url = reverse('admin:diary_taskcompletion_change', args=[obj.completion.id])
                return format_html('<a href="{}">Выполнение ID {}</a>', url, obj.completion.id)
        except Exception as e:
            logger.error(f"Ошибка при получении Completion для задания {obj.id}: {e}")
        return '-'
    completion_link.short_description = _('Выполнение')

# === TaskCompletion Admin ===
@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    """
    Админка для выполнения заданий.
    """
    list_display = (
        'id', 'task_link', 'short_completion_text', 'created_at', 'time_spent'
    )
    list_filter = (
        'created_at', 'time_spent',
        ('task__user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'task__title', 'task__user__username', 'completion_text', 'feelings_text'
    )
    readonly_fields = (
        'created_at', 'task_link', 'completion_text_full', 'feelings_text_full',
        'analysis_link'
    )
    
    fieldsets = (
        (None, {
            'fields': ('task_link', 'time_spent')
        }),
        (_('Выполнение'), {
            'fields': ('completion_text_full',)
        }),
        (_('Ощущения'), {
            'fields': ('feelings_text_full',)
        }),
        (_('Анализ'), {
            'fields': ('analysis_link',),
            'classes': ('collapse',)
        }),
        (_('Дата'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def task_link(self, obj):
        """Ссылка на задание."""
        if obj.task:
            url = reverse('admin:diary_therapytask_change', args=[obj.task.id])
            return format_html('<a href="{}">Задание ID {}</a>', url, obj.task.id)
        return '-'
    task_link.short_description = _('Задание')

    def short_completion_text(self, obj):
        """Короткий текст выполнения."""
        if obj.completion_text:
            return obj.completion_text[:50] + "..." if len(obj.completion_text) > 50 else obj.completion_text
        return '-'
    short_completion_text.short_description = _('Выполнение (короткое)')

    def completion_text_full(self, obj):
        """Полный текст выполнения."""
        if obj.completion_text:
            return format_html('<pre>{}</pre>', obj.completion_text)
        return '-'
    completion_text_full.short_description = _('Полный текст выполнения')

    def feelings_text_full(self, obj):
        """Полный текст ощущений."""
        if obj.feelings_text:
            return format_html('<pre>{}</pre>', obj.feelings_text)
        return '-'
    feelings_text_full.short_description = _('Полный текст ощущений')

    def analysis_link(self, obj):
        """Ссылка на анализ выполнения."""
        try:
            if hasattr(obj, 'analysis'):
                url = reverse('admin:diary_taskanalysis_change', args=[obj.analysis.id])
                return format_html('<a href="{}">Анализ ID {}</a>', url, obj.analysis.id)
        except Exception as e:
            logger.error(f"Ошибка при получении Analysis для выполнения {obj.id}: {e}")
        return '-'
    analysis_link.short_description = _('Анализ выполнения')

# === UserActivity Admin ===
@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    """
    Админка для активности пользователей.
    """
    list_display = (
        'id', 'user_link', 'activity_type', 'timestamp', 'short_metadata'
    )
    list_filter = (
        'activity_type', 'timestamp',
        ('user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'user__username', 'user__telegram_id', 'activity_type'
    )
    readonly_fields = ('timestamp', 'user_link', 'metadata_display')
    
    fieldsets = (
        (None, {
            'fields': ('user_link', 'activity_type', 'timestamp')
        }),
        (_('Метаданные'), {
            'fields': ('metadata_display',),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        """Ссылка на пользователя."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = _('Пользователь')
    user_link.admin_order_field = 'user__username'

    def short_metadata(self, obj):
        """Короткие метаданные."""
        if obj.metadata:
            import json
            try:
                metadata_str = json.dumps(obj.metadata, ensure_ascii=False)
                return metadata_str[:50] + "..." if len(metadata_str) > 50 else metadata_str
            except Exception as e:
                logger.error(f"Ошибка при форматировании метаданных: {e}")
                return str(obj.metadata)[:50] + "..." if len(str(obj.metadata)) > 50 else str(obj.metadata)
        return '-'
    short_metadata.short_description = _('Метаданные (короткие)')

    def metadata_display(self, obj):
        """Отображение метаданных."""
        if obj.metadata:
            import json
            try:
                metadata_json = json.dumps(obj.metadata, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', metadata_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании метаданных: {e}")
                return str(obj.metadata)
        return '-'
    metadata_display.short_description = _('Метаданные')

# === CombinedDiaryEntry Admin ===
@admin.register(CombinedDiaryEntry)
class CombinedDiaryEntryAdmin(admin.ModelAdmin):
    """
    Админка для объединенных записей дня.
    """
    list_display = (
        'id', 'user_link', 'date', 'entry_count', 'is_analyzed', 
        'average_mood_score_display', 'created_at'
    )
    list_filter = (
        'date', 'is_analyzed', 'created_at', 'updated_at',
        ('user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'user__username', 'user__telegram_id', 'date'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'user_link', 'text_full', 
        'ai_state_data_display', 'analysis_result_display',
        'daily_mood_scores_display', 'average_mood_score_display',
        'daily_analysis_link',
    )
    
    fieldsets = (
        (None, {
            'fields': ('user_link', 'date', 'entry_count')
        }),
        (_('Текст и анализ'), {
            'fields': ('text_full', 'is_analyzed', 'ai_state_data_display', 'analysis_result_display')
        }),
        (_('Оценки настроения'), {
            'fields': ('daily_mood_scores_display', 'average_mood_score_display')
        }),
        (_('Связи'), {
            'fields': ('daily_analysis_link',)
        }),
        (_('Даты'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        """Ссылка на пользователя."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = _('Пользователь')
    user_link.admin_order_field = 'user__username'

    def text_full(self, obj):
        """Полный объединенный текст."""
        if obj.text:
            return format_html('<pre>{}</pre>', obj.text)
        return '-'
    text_full.short_description = _('Полный объединенный текст')

    def ai_state_data_display(self, obj):
        """Отображение состояния дня по версии ИИ."""
        if obj.ai_state_data:
            return format_html('<pre>{}</pre>', obj.ai_state_data)
        return '-'
    ai_state_data_display.short_description = _('Состояние дня по версии ИИ')

    def analysis_result_display(self, obj):
        """Отображение результата анализа."""
        if obj.analysis_result:
            import json
            try:
                result_json = json.dumps(obj.analysis_result, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', result_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании analysis_result: {e}")
                return str(obj.analysis_result)
        return '-'
    analysis_result_display.short_description = _('Результат анализа')

    def daily_mood_scores_display(self, obj):
        """Отображение списка оценок настроения за день."""
        if obj.daily_mood_scores:
            import json
            try:
                scores_json = json.dumps(obj.daily_mood_scores, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', scores_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании daily_mood_scores: {e}")
                return str(obj.daily_mood_scores)
        return '-'
    daily_mood_scores_display.short_description = _('Список оценок настроения за день')

    def average_mood_score_display(self, obj):
        """Отображение средней оценки настроения за день."""
        return f"{obj.average_mood_score:.2f}" if obj.average_mood_score else "-"
    average_mood_score_display.short_description = _('Средняя оценка настроения за день')

    def daily_analysis_link(self, obj):
        """Ссылка на глубокий анализ дня."""
        try:
            if hasattr(obj, 'daily_analysis'):
                url = reverse('admin:diary_dailyanalysis_change', args=[obj.daily_analysis.id])
                return format_html('<a href="{}">Анализ дня ID {}</a>', url, obj.daily_analysis.id)
        except Exception as e:
            logger.error(f"Ошибка при получении DailyAnalysis для CombinedDiaryEntry {obj.id}: {e}")
        return '-'
    daily_analysis_link.short_description = _('Глубокий анализ дня')

# === DailyAnalysis Admin ===
@admin.register(DailyAnalysis)
class DailyAnalysisAdmin(admin.ModelAdmin):
    """
    Админка для глубокого анализа дня.
    """
    list_display = (
        'id', 'combined_entry_link', 'mood_trend', 'created_at'
    )
    list_filter = (
        'mood_trend', 'created_at',
        ('combined_entry__user', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'combined_entry__user__username', 'combined_entry__date'
    )
    readonly_fields = (
        'created_at', 'combined_entry_link', 
        'key_themes_display', 'emotional_patterns_display',
        'insights_display', 'recommendations_display', 'overall_analysis_text'
    )
    
    fieldsets = (
        (None, {
            'fields': ('combined_entry_link', 'mood_trend')
        }),
        (_('Анализ'), {
            'fields': (
                'key_themes_display', 'emotional_patterns_display',
                'insights_display', 'recommendations_display', 'overall_analysis_text',
                'api_response'
            )
        }),
        (_('Дата'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def combined_entry_link(self, obj):
        """Ссылка на объединенную запись дня."""
        if obj.combined_entry:
            url = reverse('admin:diary_combineddiaryentry_change', args=[obj.combined_entry.id])
            return format_html('<a href="{}">Объединенная запись ID {}</a>', url, obj.combined_entry.id)
        return '-'
    combined_entry_link.short_description = _('Объединенная запись')

    def key_themes_display(self, obj):
        """Отображение ключевых тем."""
        if obj.key_themes:
            import json
            try:
                themes_json = json.dumps(obj.key_themes, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', themes_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании key_themes: {e}")
                return str(obj.key_themes)
        return '-'
    key_themes_display.short_description = _('Ключевые темы')

    def emotional_patterns_display(self, obj):
        """Отображение эмоциональных паттернов."""
        if obj.emotional_patterns:
            import json
            try:
                patterns_json = json.dumps(obj.emotional_patterns, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', patterns_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании emotional_patterns: {e}")
                return str(obj.emotional_patterns)
        return '-'
    emotional_patterns_display.short_description = _('Эмоциональные паттерны')

    def insights_display(self, obj):
        """Отображение инсайтов."""
        if obj.insights:
            import json
            try:
                insights_json = json.dumps(obj.insights, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', insights_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании insights: {e}")
                return str(obj.insights)
        return '-'
    insights_display.short_description = _('Инсайты')

    def recommendations_display(self, obj):
        """Отображение рекомендаций."""
        if obj.recommendations:
            import json
            try:
                recs_json = json.dumps(obj.recommendations, indent=2, ensure_ascii=False)
                return format_html('<pre>{}</pre>', recs_json)
            except Exception as e:
                logger.error(f"Ошибка при форматировании recommendations: {e}")
                return str(obj.recommendations)
        return '-'
    recommendations_display.short_description = _('Рекомендации')

@admin.register(TaskCompletionAnalysis)
class TaskCompletionAnalysisAdmin(admin.ModelAdmin):
    """Админка для анализа выполнения заданий."""
    list_display = (
        'id',
        'completion',
        'get_task_title',
        'get_user',
        'mood_impact_score',
        'analysis_performed_at',
    )
    list_filter = (
        'mood_impact_score',
        'analysis_performed_at',
    )
    search_fields = (
        'completion__task__title',
        'completion__task__user__username',
        'effect_description',
    )
    readonly_fields = (
        'analysis_performed_at',
        'api_response',
    )
    # Поля для отображения в форме редактирования
    fields = (
        'completion',
        'effect_description',
        'recommendation',
        'comment',
        'mood_impact_score',
        'analysis_performed_at',
        'detailed_analysis',
        'api_response', # Для дебага
    )
    # raw_id_fields = ('related_insights',) # Если инсайтов много, удобнее так

    def get_task_title(self, obj):
        """Отображение названия задания."""
        return obj.completion.task.title if obj.completion and obj.completion.task else "-"
    get_task_title.short_description = 'Задание'
    get_task_title.admin_order_field = 'completion__task__title'

    def get_user(self, obj):
        """Отображение имени пользователя."""
        return obj.completion.task.user.username if obj.completion and obj.completion.task and obj.completion.task.user else "-"
    get_user.short_description = 'Пользователь'
    get_user.admin_order_field = 'completion__task__user__username'

@admin.register(WeeklyAnalysis)
class WeeklyAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'week_start_date', 'created_at')
    list_filter = ('week_start_date', 'created_at', 'user')
    search_fields = ('user__username', 'user__telegram_id', 'summary_text')
    readonly_fields = ('created_at', 'api_response')
    # Можно добавить поля для отображения в списке или фильтрации по ним
    # raw_id_fields = ('user',) # Если пользователей много, удобнее использовать raw_id_fields

    fieldsets = (
        (None, {
            'fields': ('user', 'week_start_date', 'summary_text')
        }),
        ('Инсайты и Прогресс', {
            'fields': ('progress_insights', 'comparison_with_previous'),
            'classes': ('collapse',), # Сворачиваем для компактности
        }),
        ('Профиль и Статистика', {
            'fields': ('consolidated_user_profile', 'statistics'),
            'classes': ('collapse',),
        }),
        ('Техническая информация', {
            'fields': ('api_response', 'created_at'),
            'classes': ('collapse',),
        }),
    )

@admin.register(NextEntryPrompt)
class NextEntryPromptAdmin(admin.ModelAdmin):
    """
    Админка для модели NextEntryPrompt.
    """
    list_display = (
        'id',
        'user',
        'target_date',
        'is_used',
        'used_at',
        'created_at',
        'get_prompt_preview' # Добавим предпросмотр текста
    )
    list_filter = (
        'is_used',
        'created_at',
        'target_date',
        ('user', admin.RelatedOnlyFieldListFilter), # Удобный фильтр по пользователю
    )
    search_fields = (
        'user__username',
        'user__telegram_id',
        'prompt_text',
    )
    readonly_fields = (
        'id',
        'created_at',
        'used_at',
        'get_prompt_full' # Полный текст будет только для просмотра
    )
    date_hierarchy = 'target_date' # Навигация по датам

    # Оптимизация запросов к БД
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user') # Предзагрузка данных пользователя

    # Метод для предпросмотра текста подсказки в списке
    @admin.display(description="Текст подсказки (превью)")
    def get_prompt_preview(self, obj):
        if obj.prompt_text:
            # Возвращаем первые 100 символов
            return obj.prompt_text[:100] + "..." if len(obj.prompt_text) > 100 else obj.prompt_text
        return "-"

    # Метод для отображения полного текста в форме редактирования
    @admin.display(description="Полный текст подсказки")
    def get_prompt_full(self, obj):
        if obj.prompt_text:
            # Используем <pre> для сохранения форматирования
            return f"<pre>{obj.prompt_text}</pre>"
        return "-"
    get_prompt_full.allow_tags = True # Разрешить HTML (в Django 3.2+ используйте format_html)

    # Действия админки
    actions = ['mark_as_used', 'mark_as_unused']

    @admin.action(description="Пометить выбранные как использованные")
    def mark_as_used(self, request, queryset):
        updated_count = queryset.update(is_used=True)
        self.message_user(
            request,
            f"Успешно помечено как использованные: {updated_count} подсказок."
        )

    @admin.action(description="Пометить выбранные как НЕ использованные")
    def mark_as_unused(self, request, queryset):
        updated_count = queryset.update(is_used=False, used_at=None)
        self.message_user(
            request,
            f"Успешно помечено как НЕ использованные: {updated_count} подсказок."
        )
