"""
Views для REST API Psycho Diary.
"""

import logging
from datetime import date, timedelta

from django.db import models
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from users.models import User
from diary.models import DiaryEntry, CombinedDiaryEntry, WeeklyAnalysis, TherapyTask
from .serializers import (
    UserSerializer, ProfileFullSerializer, ProfileCompactSerializer,
    DiaryEntrySerializer, CombinedDiaryEntrySerializer,
    WeeklyAnalysisSerializer, TherapyTaskSerializer,
    UserStatisticsSerializer
)

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с пользователями.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Пользователи видят только себя
        return User.objects.filter(id=self.request.user.id)
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Получить текущего пользователя."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class ProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с профилем пользователя.
    """
    serializer_class = ProfileFullSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return User.objects.filter(id=self.request.user.id)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProfileCompactSerializer
        return ProfileFullSerializer
    
    @action(detail=False, methods=['get'])
    def full(self, request):
        """Получить полный профиль пользователя."""
        user = request.user
        serializer = ProfileFullSerializer(user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def compact(self, request):
        """Получить компактный профиль."""
        user = request.user
        serializer = ProfileCompactSerializer(user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Получить статистику пользователя."""
        user = request.user
        
        # Подсчёт записей
        total_entries = DiaryEntry.objects.filter(user=user).count()
        
        # Подсчёт CombinedDiaryEntry (дней с записями)
        days_with_entries = CombinedDiaryEntry.objects.filter(user=user).count()
        
        # Подсчёт среднего настроения
        avg_mood = 0
        combined_entries = CombinedDiaryEntry.objects.filter(
            user=user, average_mood_score__gt=0
        )
        if combined_entries.exists():
            avg_mood = combined_entries.aggregate(
                avg=models.Avg('average_mood_score')
            )['avg'] or 0
        
        # Подсчёт текущей серии
        current_streak = 0
        check_date = date.today()
        while True:
            has_entry = CombinedDiaryEntry.objects.filter(
                user=user, date=check_date
            ).exists()
            if has_entry:
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        
        # Подсчёт максимальной серии (упрощённо)
        max_streak = current_streak  # TODO: полная логика
        
        # Подсчёт выполненных заданий
        from diary.models import TaskCompletion
        total_tasks_completed = TaskCompletion.objects.filter(
            task__user=user
        ).count()
        
        # Подсчёт weekly analyses
        weekly_count = WeeklyAnalysis.objects.filter(user=user).count()
        
        # Последняя запись
        last_entry = DiaryEntry.objects.filter(user=user).order_by('-created_at').first()
        last_entry_date = last_entry.entry_date if last_entry else None
        
        stats = {
            'total_entries': total_entries,
            'days_with_entries': days_with_entries,
            'current_streak': current_streak,
            'max_streak': max_streak,
            'avg_mood_score': round(avg_mood, 2),
            'total_tasks_completed': total_tasks_completed,
            'weekly_analyses_count': weekly_count,
            'last_entry_date': last_entry_date,
        }
        
        serializer = UserStatisticsSerializer(stats)
        return Response(serializer.data)


class DiaryEntryViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с записями дневника.
    """
    serializer_class = DiaryEntrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return DiaryEntry.objects.filter(user=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CombinedDiaryEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с объединёнными записями дня (только чтение).
    """
    serializer_class = CombinedDiaryEntrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = CombinedDiaryEntry.objects.filter(
            user=self.request.user
        ).order_by('-date')
        
        # Фильтрация по дате
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        
        return queryset


class WeeklyAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с еженедельными анализами (только чтение).
    """
    serializer_class = WeeklyAnalysisSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return WeeklyAnalysis.objects.filter(
            user=self.request.user
        ).order_by('-week_start_date')


class TherapyTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с терапевтическими заданиями.
    """
    serializer_class = TherapyTaskSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return TherapyTask.objects.filter(
            user=self.request.user
        ).order_by('-assigned_at')
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Отметить задание как выполненное."""
        task = self.get_object()
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()
        return Response({'status': 'completed'})


# =====================================================
# Auth Views
# =====================================================

from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings

from users.services.auth_token_service import (
    create_telegram_auth_token,
    validate_telegram_auth_token,
    create_web_link_token
)
from .serializers import (
    RegisterSerializer,
    CompleteRegistrationSerializer,
    GenerateLinkSerializer
)


class RegisterView(generics.CreateAPIView):
    """
    Регистрация нового пользователя через email + пароль.
    POST /api/auth/register/
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = []  # Разрешаем без аутентификации

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Генерируем токены
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class TelegramAuthView(APIView):
    """
    Авторизация через Telegram токен.
    GET /api/auth/telegram/?token=XXX
    """
    permission_classes = []  # Разрешаем без аутентификации

    def get(self, request):
        token = request.query_params.get('token')
        
        if not token:
            return Response(
                {'error': 'token_required', 'message': 'Token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Валидируем токен
        user_id = validate_telegram_auth_token(token)
        
        if not user_id:
            return Response(
                {'error': 'invalid_token', 'message': 'Token is invalid or expired'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем пользователя
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'user_not_found', 'message': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Генерируем JWT токены
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'telegram_id': user.telegram_id,
                'first_name': user.first_name,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


class CompleteRegistrationView(APIView):
    """
    Завершение регистрации (установка email/пароля для Telegram-пользователя).
    POST /api/auth/complete-registration/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CompleteRegistrationSerializer(
            data=request.data,
            context={'user': request.user}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Генерируем новые токены после установки пароля
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


class GenerateLinkView(APIView):
    """
    Генерация ссылки для привязки Telegram к web-аккаунту.
    POST /api/auth/generate-link/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Генерируем токен
        token = create_web_link_token(user.id)
        
        # Формируем ссылку
        bot_username = getattr(settings, 'BOT_USERNAME', 'your_bot')
        web_app_url = getattr(settings, 'WEB_APP_URL', 'https://app.com')
        
        # Используем web_app_url для формирования полной ссылки
        link_url = f"https://t.me/{bot_username}?start=link_{token}"
        
        return Response({
            'link': link_url,
            'expires_in': 600,  # 10 минут в секундах
        })


class LoginView(TokenObtainPairView):
    """
    Логин через email + пароль.
    POST /api/auth/login/
    Наследует стандартный JWT login из rest_framework_simplejwt.
    """
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        # Добавляем поддержку email вместо username
        email = request.data.get('email')
        if email:
            # DRF SimpleJWT ожидает username, но мы используем email
            # Находим пользователя по email_hash (для encrypted email)
            import hashlib
            from users.models import User
            email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
            try:
                user = User.objects.get(email_hash=email_hash)
                # Заменяем email на username для SimpleJWT
                request.data._mutable = True
                request.data['username'] = user.username
            except User.DoesNotExist:
                pass
        return super().post(request, *args, **kwargs)
