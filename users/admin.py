from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import User, CityTimezone, UserProfileHistory

@admin.register(UserProfileHistory)
class UserProfileHistoryAdmin(admin.ModelAdmin):
    """Админка для истории профиля пользователя."""
    list_display = ('id', 'user_link', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__telegram_id', 'user__first_name')
    readonly_fields = ('created_at', 'user_link')
    # raw_id_fields = ('user',) # Полезно, если пользователей много

    # Настройка отображения полей в форме
    fieldsets = (
        (None, {
            'fields': ('user_link', 'created_at')
        }),
        ('Текстовое Описание', {
            'fields': ('personality_description',),
            'classes': ('collapse',), # Сворачиваем для компактности
        }),
        ('Структурированный Профиль', {
            'fields': (
                'awareness_level',
                'personality_traits',
                'life_facts',
                'hobbies',
                'core_values',
                'triggers',
                'strengths',
                'areas_for_growth',
                'personality_insights',
                'habits',
                'skills',
                'aspirations',
            ),
            'classes': ('collapse',),
        }),
    )

    def user_link(self, obj):
        """Создает ссылку на страницу редактирования пользователя в админке."""
        if obj.user:
            url = reverse("admin:users_user_change", args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user)
        return "-"
    user_link.short_description = "Пользователь"
    user_link.admin_order_field = 'user__username' # Позволяет сортировать по имени пользователя


class UserProfileHistoryInline(admin.TabularInline):
    """Встроенный список истории профиля на странице пользователя."""
    model = UserProfileHistory
    extra = 0 # Не показывать пустые формы для добавления
    fields = (
        'created_at', 'awareness_level', 
        # Можно добавить preview первых N символов из personality_description
        'get_description_preview'
    )
    readonly_fields = ('created_at', 'awareness_level', 'get_description_preview')
    can_delete = False # Запрещаем удалять через inline
    show_change_link = True # Показывать ссылку для перехода к полной записи истории

    def get_description_preview(self, obj):
        """Показывает короткий preview описания личности."""
        if obj.personality_description:
            return obj.personality_description[:50] + "..." if len(obj.personality_description) > 50 else obj.personality_description
        return "-"
    get_description_preview.short_description = "Описание (превью)"

    def has_add_permission(self, request, obj=None):
        """Запрещает добавление новых записей истории через inline."""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещает изменение записей истории через inline."""
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Админка для пользователя с расширенным психологическим профилем."""
    
    # Настройка отображения в списке пользователей
    list_display = (
        'username', 'telegram_id', 'first_name', 'last_name', 
        'awareness_level', 'is_premium', 'is_blocked', 'created_at'
    )
    list_filter = (
        'is_premium', 'is_blocked', 'language', 'created_at', 'last_activity',
        'auto_analysis_enabled', 'notifications_enabled'
    )
    search_fields = ('username', 'telegram_id', 'first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'last_entry', 'last_activity', 'deleted_at')

    # Определяем fieldsets, объединяя поля AbstractUser и наши новые поля
    fieldsets = (
        # Стандартные поля AbstractUser
        (None, {'fields': ('username', 'password')}),
        (('Персональная информация'), {'fields': ('first_name', 'last_name', 'email')}),
        (('Права доступа'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (('Важные даты'), {'fields': ('last_login', 'created_at', 'updated_at')}),
        
        # Новые поля для Telegram бота
        (('Telegram и Основное'), {
            'fields': (
                'telegram_id', 'language', 'timezone', 'has_agreed_to_terms',
                'is_premium', 'is_blocked', 'deletion_status', 'deleted_at'
            )
        }),
        (('Активность и Настройки'), {
            'fields': (
                'last_entry', 'last_activity', 'preferred_analysis_time',
                'current_calendar_year', 'current_calendar_month',
                'notifications_enabled', 'auto_analysis_enabled', 'max_ai_tasks_per_day'
            ),
            'classes': ('collapse',),
        }),
        
        # Психологический Профиль
        (('Психологический Профиль'), {
            'fields': (
                'awareness_level',
                ('personality_description',), # Отдельная строка для текстового описания
                'personality_traits',
                'life_facts',
                'hobbies',
                'core_values',
                'triggers',
                'strengths',
                'areas_for_growth',
                'personality_insights',
                'habits',
                'skills',
                'aspirations',
            ),
            'classes': ('collapse',),
        }),
        (('Персональные данные'), {
            'fields': ('date_of_birth',),
            'classes': ('collapse',),
        }),
    )
    
    # Настройка fieldsets для страницы создания пользователя
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'telegram_id', 'password1', 'password2'),
        }),
    )
    
    # Добавляем Inline для истории профиля
    inlines = [UserProfileHistoryInline]

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