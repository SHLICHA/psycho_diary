from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, CityTimezone

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'telegram_id', 'language', 'timezone', 'awareness_level', 'is_premium', 'created_at', 'is_blocked', 'has_agreed_to_terms')
    list_filter = ('language', 'timezone', 'is_premium', 'notifications_enabled', 'auto_analysis_enabled')
    search_fields = ('username', 'telegram_id', 'first_name', 'last_name')
    readonly_fields = ('created_at', 'updated_at', 'last_entry', 'last_activity')
    
    # Поля, отображаемые в форме редактирования пользователя
    fieldsets = (
        ('Основная информация', {
            'fields': ('telegram_id', 'username', 'first_name', 'last_name', 'email', 'language', 'timezone', 'is_blocked', 'has_agreed_to_terms')
        }),
        ('Даты и время', {
            'fields': ('date_of_birth', 'created_at', 'updated_at', 'last_entry', 'last_activity', 'preferred_analysis_time')
        }),
        ('Настройки', {
            'fields': ('notifications_enabled', 'auto_analysis_enabled', 'is_premium')
        }),
        ('Психологический профиль', {
            'fields': ('awareness_level', 'personality_traits', 'life_facts', 'hobbies', 'core_values', 'triggers', 'strengths', 'areas_for_growth'),
            'classes': ('collapse',)  # Сворачиваем по умолчанию
        }),
        ('Календарь', {
            'fields': ('current_calendar_year', 'current_calendar_month'),
            'classes': ('collapse',)  # Сворачиваем по умолчанию
        }),
        ('Лимиты', {
            'fields': ('max_ai_tasks_per_day',),
            'classes': ('collapse',)  # Сворачиваем по умолчанию
        }),
    )
    
    # Поля, отображаемые в форме создания пользователя
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительная информация', {
            'fields': (
                'telegram_id',
                'language',
                'timezone',
                'awareness_level',
                'is_premium',
                'preferred_analysis_time',
                'notifications_enabled',
                'auto_analysis_enabled',
                'max_ai_tasks_per_day',
                # === ДОЛГОСРОЧНЫЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ ===
                'personality_traits',
                'life_facts',
                'hobbies',
                'core_values',
                'triggers',
                'strengths',
                'areas_for_growth',
            )
        }),
    )
    
    # Поля, доступные только для чтения в админке (опционально)
    readonly_fields = ('created_at', 'updated_at', 'last_entry', 'last_activity', 'deleted_at')

    # Сортировка по умолчанию
    ordering = ('-created_at',)

@admin.register(CityTimezone)
class CityTimezoneAdmin(admin.ModelAdmin):
    list_display = ('city_name', 'country', 'timezone', 'created_at')
    list_filter = ('country', 'timezone')
    search_fields = ('city_name', 'country', 'timezone')
    readonly_fields = ('created_at', 'updated_at')
    
    # Добавим валидацию часового пояса при сохранении из админки
    def save_model(self, request, obj, form, change):
        try:
            import pytz
            pytz.timezone(obj.timezone)
        except Exception:
            from django.contrib import messages
            messages.error(request, f"Неверный часовой пояс: {obj.timezone}")
            return
        super().save_model(request, obj, form, change)