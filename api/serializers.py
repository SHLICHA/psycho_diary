"""
Serializers для REST API Psycho Diary.
"""

from rest_framework import serializers
from users.models import User
from diary.models import DiaryEntry, CombinedDiaryEntry, WeeklyAnalysis, TherapyTask


class UserSerializer(serializers.ModelSerializer):
    """
    Сериализатор для базовой информации о пользователе.
    """
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name',
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
            'id', 'username', 'first_name', 'last_name', 'language',
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
            'habits',
            'skills',
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
    
    def get_full_psych_profile_summary(self, obj):
        """Возвращает summary из full_psych_profile."""
        full = obj.full_psych_profile or {}
        return full.get('summary', '')


class DiaryEntrySerializer(serializers.ModelSerializer):
    """
    Сериализатор для записей дневника.
    """
    entry_date = serializers.DateField(source='entry_date', read_only=True)
    
    class Meta:
        model = DiaryEntry
        fields = [
            'id', 'user', 'text', 'created_at', 'updated_at',
            'language', 'word_count', 'is_processed', 'entry_date',
            'is_primary', 'user_comment'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'word_count', 'is_processed']


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
            'id', 'user', 'title', 'description', 'task_type',
            'status', 'assigned_at', 'completed_at', 'effect_rating'
        ]
        read_only_fields = ['id', 'assigned_at']


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


# =====================================================
# Auth Serializers
# =====================================================

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError


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
        
        # Проверяем уникальность email через hash
        if attrs.get('email'):
            import hashlib
            email_hash = hashlib.sha256(attrs['email'].lower().encode()).hexdigest()
            if User.objects.filter(email_hash=email_hash).exists():
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
        
        # Проверяем, что email не занят другим пользователем (через hash)
        user = self.context.get('user')
        if attrs.get('email'):
            import hashlib
            email_hash = hashlib.sha256(attrs['email'].lower().encode()).hexdigest()
            if User.objects.exclude(id=user.id).filter(email_hash=email_hash).exists():
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