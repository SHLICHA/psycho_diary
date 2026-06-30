"""
Serializers для REST API Psycho Diary.
"""

from typing import Optional

from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from users.models import User, UserProfileHistory, TokenTransaction, Payment
from diary.models import DiaryEntry, CombinedDiaryEntry, WeeklyAnalysis, TherapyTask, UserActivity


class UserSerializer(serializers.ModelSerializer):
    """
    Сериализатор для базовой информации о пользователе.
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'language', 'timezone', 'is_premium', 'awareness_level',
            'created_at', 'token_balance'
        ]
        read_only_fields = ['id', 'created_at', 'token_balance']


class ProfileFullSerializer(serializers.ModelSerializer):
    """
    Сериализатор для полного профиля пользователя.
    Включает все профильные поля и сжатый/полный профили.
    """
    class Meta:
        model = User
        fields = [
            # Базовые данные
            'id', 'email', 'username', 'first_name', 'last_name', 'language',
            'timezone', 'is_premium', 'awareness_level', 'date_of_birth',
            'created_at', 'token_balance',
            
            # Профильные поля
            'personality_description',
            'personality_traits',
            'life_facts',
            'hobbies',
            'core_values',
            'triggers',
            'strengths',
            'areas_for_growth',
            'personality_insights',
            'practical_patterns',
            'aspirations',
            
            # Сгенерированные профили
            'compressed_psych_profile',
            'full_psych_profile',
        ]
        read_only_fields = fields


class ProfileCompactSerializer(serializers.ModelSerializer):
    """
    Сериализатор для компактного профиля (без sensitive данных).
    """
    full_psych_profile_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'language', 'is_premium', 'awareness_level',
            'full_psych_profile_summary', 'compressed_psych_profile'
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_full_psych_profile_summary(self, obj) -> str:
        """Возвращает summary из full_psych_profile."""
        full = obj.full_psych_profile or {}
        return full.get('summary', '')


class DiaryEntrySerializer(serializers.ModelSerializer):
    """
    Сериализатор для записей дневника.
    """
    entry_date = serializers.SerializerMethodField()
    
    class Meta:
        model = DiaryEntry
        fields = [
            'id', 'user', 'text', 'created_at', 'updated_at',
            'language', 'word_count', 'is_processed', 'entry_date',
            'is_primary', 'user_comment'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'word_count', 'is_processed', 'entry_date']

    @extend_schema_field(OpenApiTypes.DATE)
    def get_entry_date(self, obj) -> Optional[str]:
        """Return the entry date from the property."""
        entry_date = obj.entry_date
        return entry_date.isoformat() if entry_date else None
    
    def create(self, validated_data):
        """Create entry and calculate word_count from text."""
        text = validated_data.get('text', '')
        validated_data['word_count'] = len(text.split()) if text else 0
        return super().create(validated_data)


class CombinedDiaryEntrySerializer(serializers.ModelSerializer):
    """
    Сериализатор для объединённых записей дня.
    """
    entries_count = serializers.IntegerField(source='entry_count', read_only=True)
    average_mood = serializers.FloatField(source='average_mood_score', read_only=True)
    
    class Meta:
        model = CombinedDiaryEntry
        fields = [
            'id', 'user', 'date', 'text', 'entries_count',
            'average_mood', 'daily_mood_scores', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WeeklyAnalysisSerializer(serializers.ModelSerializer):
    """
    Сериализатор для еженедельных анализов.
    """
    class Meta:
        model = WeeklyAnalysis
        fields = [
            'id', 'user', 'week_start_date', 'summary_text',
            'progress_insights', 'statistics', 'comparison_with_previous',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class TherapyTaskSerializer(serializers.ModelSerializer):
    """
    Сериализатор для терапевтических заданий.
    """
    class Meta:
        model = TherapyTask
        fields = [
            'id', 'user', 'title', 'description', 'type',
            'status', 'assigned_at', 'completed_at', 'complexity'
        ]
        read_only_fields = ['id', 'user', 'assigned_at', 'completed_at']


class UserProfileHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории изменений профиля."""

    class Meta:
        model = UserProfileHistory
        fields = [
            'id',
            'created_at',
            'awareness_level',
            'personality_traits',
            'life_facts',
            'hobbies',
            'core_values',
            'triggers',
            'strengths',
            'areas_for_growth',
            'personality_insights',
            'practical_patterns',
            'aspirations',
            'personality_description',
        ]
        read_only_fields = fields


class TokenTransactionSerializer(serializers.ModelSerializer):
    """Сериализатор истории транзакций токенов."""

    class Meta:
        model = TokenTransaction
        fields = [
            'id',
            'amount',
            'transaction_type',
            'description',
            'created_at',
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    """Сериализатор платежей пользователя."""

    class Meta:
        model = Payment
        fields = [
            'id',
            'yookassa_payment_id',
            'amount_rub',
            'payment_type',
            'tokens_granted',
            'subscription_days_granted',
            'status',
            'created_at',
        ]
        read_only_fields = fields


class ProgressSummarySerializer(serializers.Serializer):
    """Сериализатор сводки прогресса пользователя."""

    total_entries = serializers.IntegerField()
    total_days_with_entries = serializers.IntegerField()
    total_tasks_completed = serializers.IntegerField()
    weekly_analyses_count = serializers.IntegerField()
    avg_mood_score = serializers.FloatField()


class ProgressStreakSerializer(serializers.Serializer):
    """Сериализатор серии активности пользователя."""

    current_streak = serializers.IntegerField()
    max_streak = serializers.IntegerField()
    active_days_last_30 = serializers.IntegerField()


class MoodPointSerializer(serializers.Serializer):
    """Точка графика настроения."""

    period = serializers.CharField()
    avg_mood_score = serializers.FloatField()
    entries_count = serializers.IntegerField()


class UserActivitySerializer(serializers.ModelSerializer):
    """Сериализатор пользовательской активности."""

    class Meta:
        model = UserActivity
        fields = ['id', 'activity_type', 'timestamp', 'metadata']
        read_only_fields = fields


class MoodTimelineSerializer(serializers.Serializer):
    """Сериализатор ответа графика настроения."""

    period = serializers.CharField()
    points = MoodPointSerializer(many=True)


class UserActivityFeedSerializer(serializers.Serializer):
    """Сериализатор ответа активности пользователя."""

    summary = serializers.DictField(child=serializers.IntegerField())
    recent = UserActivitySerializer(many=True)


class UserStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики пользователя.
    """
    total_entries = serializers.IntegerField()
    current_streak = serializers.IntegerField()
    max_streak = serializers.IntegerField()
    avg_mood_score = serializers.FloatField()
    total_tasks_completed = serializers.IntegerField()
    weekly_analyses_count = serializers.IntegerField()
    last_entry_date = serializers.DateField(allow_null=True)


class MonitoringSnapshotSerializer(serializers.Serializer):
    """Сериализатор snapshot метрик monitoring service."""
    use_cases = serializers.DictField(child=serializers.JSONField(), required=False)
    ai_calls = serializers.DictField(child=serializers.JSONField(), required=False)
    transport = serializers.DictField(child=serializers.JSONField(), required=False)
    totals = serializers.DictField(child=serializers.IntegerField(), required=False)


class AICallMetricsSerializer(serializers.Serializer):
    """Сериализатор для метрик AI вызовов."""
    total_calls = serializers.IntegerField()
    successful_calls = serializers.IntegerField()
    failed_calls = serializers.IntegerField()
    total_tokens_used = serializers.IntegerField()
    avg_latency_ms = serializers.FloatField()
    retry_count = serializers.IntegerField()
    error_rate = serializers.FloatField()


class OnboardingFunnelSerializer(serializers.Serializer):
    """Сериализатор для воронки онбординга."""
    started_count = serializers.IntegerField()
    registered_count = serializers.IntegerField()
    first_entry_count = serializers.IntegerField()
    completed_profile_count = serializers.IntegerField()
    register_conversion = serializers.FloatField()
    first_entry_conversion = serializers.FloatField()


class RetentionMetricsSerializer(serializers.Serializer):
    """Сериализатор для метрик удержания."""
    daily_active_users = serializers.IntegerField()
    weekly_active_users = serializers.IntegerField()
    monthly_active_users = serializers.IntegerField()
    users_with_active_streak = serializers.IntegerField()
    avg_streak_length = serializers.FloatField()
    max_streak_length = serializers.IntegerField()
    users_recovered_streak = serializers.IntegerField()
    churned_users_7d = serializers.IntegerField()
    returned_users_7d = serializers.IntegerField()


class TaskMetricsSerializer(serializers.Serializer):
    """Сериализатор для метрик задач."""
    total_tasks_created = serializers.IntegerField()
    total_tasks_completed = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    avg_completion_time_hours = serializers.FloatField()


class EntryMetricsSerializer(serializers.Serializer):
    """Сериализатор для метрик записей."""
    total_entries = serializers.IntegerField()
    processed_entries = serializers.IntegerField()
    failed_entries = serializers.IntegerField()
    avg_processing_time_ms = serializers.FloatField()
    entries_with_clarifications = serializers.IntegerField()
    avg_clarifications_per_entry = serializers.FloatField()
    user_comments_count = serializers.IntegerField()


class UserEngagementSerializer(serializers.Serializer):
    """Сериализатор для метрик вовлеченности."""
    avg_entries_per_user = serializers.FloatField()
    avg_tasks_per_user = serializers.FloatField()
    users_with_premium = serializers.IntegerField()
    premium_conversion_rate = serializers.FloatField()
    total_tokens_purchased = serializers.IntegerField()
    avg_tokens_per_user = serializers.FloatField()


class DailySnapshotSerializer(serializers.Serializer):
    """Сериализатор для ежедневного снимка."""
    date = serializers.CharField()
    dau = serializers.IntegerField()
    entries_created = serializers.IntegerField()
    entries_processed = serializers.IntegerField()
    tasks_completed = serializers.IntegerField()
    ai_calls = serializers.IntegerField()
    ai_tokens_used = serializers.IntegerField()
    ai_avg_latency_ms = serializers.FloatField()


class ComprehensiveStatsSerializer(serializers.Serializer):
    """Сериализатор для комплексной статистики."""
    timestamp = serializers.CharField()
    period = serializers.CharField()
    ai_metrics = AICallMetricsSerializer()
    onboarding = OnboardingFunnelSerializer()
    retention = RetentionMetricsSerializer()
    tasks = TaskMetricsSerializer()
    entries = EntryMetricsSerializer()
    engagement = UserEngagementSerializer()
    daily_snapshots = DailySnapshotSerializer(many=True)


class APIErrorDetailSerializer(serializers.Serializer):
    """Внутренняя структура единого payload ошибки API."""

    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(required=False)


class APIErrorSerializer(serializers.Serializer):
    """Единый контракт ошибки API: {"error": {code, message, details?}}."""

    error = APIErrorDetailSerializer()


# =====================================================
# Auth Serializers
# =====================================================

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from users.services.identity_policy_service import IdentityPolicyService


class RegisterSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации нового пользователя.
    """
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'password_confirm', 'username']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password': 'Passwords do not match'
            })
        
        # Единая policy проверки merge/conflict по email.
        if attrs.get('email'):
            resolution = IdentityPolicyService.resolve_email_claim(attrs['email'])
            if resolution.status == 'conflict':
                raise serializers.ValidationError({
                    'email': 'Email already exists'
                })
        
        return attrs

    def create(self, validated_data):
        # Убираем password_confirm
        validated_data.pop('password_confirm')
        
        # Создаём пользователя без telegram_id
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        
        return user


class CompleteRegistrationSerializer(serializers.Serializer):
    """
    Сериализатор для завершения регистрации (установка email/пароля).
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password': 'Passwords do not match'
            })
        
        # Единая policy проверки merge/conflict по email.
        user = self.context.get('user')
        if attrs.get('email'):
            resolution = IdentityPolicyService.resolve_email_claim(attrs['email'], requester_user=user)
            if resolution.status == 'conflict':
                raise serializers.ValidationError({
                    'email': 'Email already exists'
                })
        
        return attrs

    def save(self):
        user = self.context['user']
        user.email = self.validated_data['email']
        user.set_password(self.validated_data['password'])
        user.save()
        return user


class GenerateLinkSerializer(serializers.Serializer):
    """
    Сериализатор для генерации ссылки привязки Telegram.
    """
    link = serializers.URLField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)


class ConfirmEmailMergeSerializer(serializers.Serializer):
    """Сериализатор подтверждения email merge-request."""

    confirmation_token = serializers.CharField(required=True, max_length=128)


import pytz as _pytz

class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для обновления профиля и настроек пользователя.
    Поддерживает PATCH /api/v1/profile/.
    Обновляемые поля: базовые данные, настройки, пользовательские поля профиля.
    """

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'date_of_birth',
            'language',
            'timezone',
            'notifications_enabled',
            'auto_analysis_enabled',
            'max_ai_tasks_per_day',
            'hobbies',
            'life_facts',
        ]

    def validate_language(self, value):
        allowed = {'ru', 'en'}
        if value not in allowed:
            raise serializers.ValidationError(f'Допустимые значения: {", ".join(sorted(allowed))}.')
        return value

    def validate_timezone(self, value):
        try:
            _pytz.timezone(value)
        except _pytz.UnknownTimeZoneError:
            raise serializers.ValidationError('Неверный часовой пояс.')
        return value

    def validate_max_ai_tasks_per_day(self, value):
        if value < 1 or value > 10:
            raise serializers.ValidationError('Допустимые значения: от 1 до 10.')
        return value


class FeedbackSerializer(serializers.Serializer):
    """Сериализатор для отправки обратной связи через API."""

    message = serializers.CharField(min_length=5, max_length=4000)

    def create(self, validated_data):
        from users.models import Feedback as FeedbackModel
        user = self.context['request'].user
        return FeedbackModel.objects.create(
            user=user,
            message=validated_data['message'],
        )