from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import Feedback, User, CityTimezone, UserProfileHistory, TokenTransaction, Payment

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
        # Проверяем, является ли obj.user действительным объектом User
        if obj.user and hasattr(obj.user, 'pk') and hasattr(obj.user, '__str__'):
            try:
                # Пытаемся получить pk и строковое представление
                user_pk = obj.user.pk
                user_str = str(obj.user)
                url = reverse("admin:users_user_change", args=[user_pk])
                return format_html('<a href="{}">{}</a>', url, user_str)
            except (AttributeError, TypeError):
                # Если что-то пошло не так при получении pk или строкового представления
                return f"Ошибка: {obj.user}"
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
        # Проверяем, является ли obj.personality_description строкой
        if obj.personality_description and isinstance(obj.personality_description, str):
            desc_str = obj.personality_description
            return desc_str[:50] + "..." if len(desc_str) > 50 else desc_str
        # Если personality_description не строка или None/пустая строка
        elif obj.personality_description is not None:
            # Пытаемся получить строковое представление, если это не строка и не None
            try:
                desc_repr = str(obj.personality_description)
                return desc_repr[:50] + "..." if len(desc_repr) > 50 else desc_repr
            except (TypeError, AttributeError):
                # Если не удалось получить строку, возвращаем строковое представление типа
                return f"[{type(obj.personality_description).__name__}]"
        # Если personality_description пустое (None или "")
        return "-"
    get_description_preview.short_description = "Описание (превью)"

    def has_add_permission(self, request, obj=None):
        """Запрещает добавание новых записей истории через inline."""
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
        'awareness_level', 'is_premium', 'token_balance', 'is_blocked', 'created_at', 'is_onboarding_completed'
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
        (None, {'fields': ('username', 'password', 'email')}),
        (('Важные даты'), {'fields': ('last_login', 'created_at', 'updated_at', 'premium_expires_at', 'referral_link')}),
        
        # Новые поля для Telegram бота
        (('Telegram и Основное'), {
            'fields': (
                'telegram_id', 'language', 'timezone', 'is_onboarding_completed',
                'is_premium', 'is_blocked', 'deletion_status', 'deleted_at', 'token_balance',
                'last_streak_reward_7', 'last_streak_reward_30', 'last_streak_reward_365', 'invited_by',
            )
        }),
        (('Активность и Настройки'), {
            'fields': (
                'last_entry', 'last_activity',
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

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_link', 'short_message', 'feedback_type', 
                   'status_badge', 'created_at')
    list_filter = ('status', 'is_voice', 'is_photo', 'created_at')
    search_fields = ('message', 'user__username', 'admin_response')
    readonly_fields = ('created_at', 'user', 'message', 'is_voice', 'is_photo')
    list_per_page = 30
    date_hierarchy = 'created_at'
    actions = ['mark_as_processed', 'mark_as_replied']
    
    fieldsets = (
        (None, {
            'fields': ('user', 'message', 'is_voice', 'is_photo')
        }),
        ('Ответ администратора', {
            'fields': ('admin_response', 'status')
        }),
        ('Даты', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def user_link(self, obj):
        url = f"/admin/bot/user/{obj.user.id}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'Пользователь'
    
    def short_message(self, obj):
        return (obj.message[:50] + '...') if len(obj.message) > 50 else obj.message
    short_message.short_description = 'Сообщение'
    
    def feedback_type(self, obj):
        if obj.is_voice:
            return 'Голосовое'
        if obj.is_photo:
            return 'Фото'
        return 'Текст'
    feedback_type.short_description = 'Тип'
    
    def status_badge(self, obj):
        status_map = {
            'new': ('gray', 'Новое'),
            'processed': ('blue', 'Обработано'),
            'replied': ('green', 'Ответ отправлен')
        }
        color, text = status_map.get(obj.status, ('black', 'Unknown'))
        return format_html(
            '<span style="color: white; background-color: {}; '
            'padding: 3px 5px; border-radius: 3px;">{}</span>',
            color, text
        )
    status_badge.short_description = 'Статус'
    
    @admin.action(description='Пометить как обработанные')
    def mark_as_processed(self, request, queryset):
        updated = queryset.filter(status='new').update(status='processed')
        self.message_user(request, f"Помечено как обработанные: {updated} обращений")
    
    @admin.action(description='Пометить как отвеченные')
    def mark_as_replied(self, request, queryset):
        updated = queryset.filter(status__in=['new', 'processed']).update(status='replied')
        self.message_user(request, f"Помечено как отвеченные: {updated} обращений")

@admin.register(TokenTransaction)
class TokenTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'transaction_type', 'related_task_completion', 'created_at')
    list_filter = ('transaction_type', 'created_at', 'user')
    search_fields = ('user__username', 'user__telegram_id', 'description')
    readonly_fields = ('created_at',) # created_at не редактируется
    ordering = ('-created_at',)
    list_per_page = 25 # Удобно для просмотра списка

    def get_queryset(self, request):
        # Оптимизируем запрос, предзагрузив связанные объекты, если часто просматриваем через related_task_completion
        qs = super().get_queryset(request)
        return qs.select_related('user', 'related_task_completion')
    
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'yookassa_payment_id',
        'user_link',
        'amount_rub',
        'payment_type',
        'status',
        'tokens_granted',
        'subscription_days_granted',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'status',
        'payment_type',
        'created_at',
    )
    search_fields = (
        'yookassa_payment_id',
        'user__telegram_id',
        'user__username',
    )
    readonly_fields = (
        'yookassa_payment_id',
        'created_at',
        'updated_at',
    )
    ordering = ['-created_at']

    def user_link(self, obj):
        """Создаёт ссылку на пользователя в админке."""
        if obj.user:
            url = reverse("admin:users_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user)
        return "-"
    user_link.short_description = 'Пользователь'
    user_link.admin_order_field = 'user__username'

    # Опционально: можно добавить фильтр по пользователю
    def changelist_view(self, request, extra_context=None):
        # Позволяет фильтровать платежи по пользователю через URL
        # Например: /admin/users/payment/?user__id__exact=123
        if 'user__id__exact' in request.GET:
            user_id = request.GET.get('user__id__exact')
            # Добавим заголовок, чтобы было понятно, что фильтр активен
            user = User.objects.filter(id=user_id).first()
            if user:
                extra_context = extra_context or {}
                extra_context['subtitle'] = f"Платежи пользователя: {user}"
        return super().changelist_view(request, extra_context=extra_context)