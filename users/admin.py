from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Определяем поля, которые будут отображаться в списке пользователей
    list_display = (
        'username', 
        'telegram_id', 
        'language', 
        'awareness_level', 
        'is_premium', 
        'is_staff', 
        'created_at'
    )
    
    # Поля для фильтрации
    list_filter = (
        'language', 
        'is_premium', 
        'is_staff', 
        'is_superuser', 
        'is_active',
        'created_at',
        'timezone'
    )
    
    # Поля для поиска
    search_fields = ('username', 'telegram_id', 'first_name', 'last_name')
    
    # Поля, отображаемые в форме редактирования пользователя
    fieldsets = BaseUserAdmin.fieldsets + (
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