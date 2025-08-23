from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'telegram_id', 'language', 'awareness_level', 'is_premium', 'last_entry']
    list_filter = ['language', 'is_premium', 'awareness_level', 'is_staff', 'is_superuser']
    search_fields = ['username', 'telegram_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительная информация', {
            'fields': ('telegram_id', 'awareness_level', 'last_entry', 'is_premium', 'deleted_at')
        }),
        ('Настройки', {
            'fields': ('language', 'notifications_enabled', 'auto_analysis_enabled', 'timezone', 'current_calendar_year', 'current_calendar_month')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Дополнительная информация', {
            'fields': ('telegram_id', 'language')
        }),
    )