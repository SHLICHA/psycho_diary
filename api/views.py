"""
Views для REST API Psycho Diary.
"""

import logging
from datetime import date, timedelta, datetime
import asyncio
from typing import Literal

from django.db import models
from django.db.models import Avg
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from users.models import User, UserProfileHistory, TokenTransaction, Payment
from diary.models import (
    DiaryEntry,
    CombinedDiaryEntry,
    WeeklyAnalysis,
    TherapyTask,
    PsychoAnalysis,
    UserActivity,
    TaskCompletion,
)
from .serializers import (
    UserSerializer, ProfileFullSerializer, ProfileCompactSerializer,
    DiaryEntrySerializer, CombinedDiaryEntrySerializer,
    WeeklyAnalysisSerializer, TherapyTaskSerializer,
    UserStatisticsSerializer, MonitoringSnapshotSerializer,
    ComprehensiveStatsSerializer,
    UserProfileHistorySerializer,
    TokenTransactionSerializer,
    PaymentSerializer,
    ProgressSummarySerializer,
    ProgressStreakSerializer,
    MoodPointSerializer,
    UserActivitySerializer,
    MoodTimelineSerializer,
    UserActivityFeedSerializer,
    APIErrorSerializer,
)
from .error_utils import api_error_response
from .permissions import MonitoringAccessPermission
from .throttling import (
    AuthRateThrottle,
    EntryMutationRateThrottle,
    LinkGenerationRateThrottle,
    MonitoringHeavyRateThrottle,
    MonitoringRateThrottle,
    RefreshRateThrottle,
    TaskMutationRateThrottle,
)
from core.services.monitoring_service import monitoring_service
from core.services.prometheus_formatter import PrometheusFormatter
from core.services.stats_service import stats_service
from core.services.stats_dtos import StatsQuery

logger = logging.getLogger(__name__)


def _parse_bool_param(value):
    """Parse common boolean query parameter representations."""
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


@extend_schema_view(
    list=extend_schema(
        summary='Список пользователей (только текущий)',
        description='Возвращает только текущего аутентифицированного пользователя.',
        tags=['Users'],
    ),
    retrieve=extend_schema(summary='Детали пользователя', tags=['Users']),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с пользователями.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Пользователи видят только себя
        return User.objects.filter(id=self.request.user.id).order_by('id')
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Текущий пользователь',
        description='Возвращает профиль текущего пользователя (`/users/me/`).',
        tags=['Users'],
    )
    def me(self, request):
        """Получить текущего пользователя."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary='Профиль пользователя (compact)',
        description='Возвращает компактное представление профиля текущего пользователя.',
        tags=['Profile'],
    ),
    retrieve=extend_schema(summary='Полный профиль (retrieve)', tags=['Profile']),
)
class ProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с профилем пользователя.
    """
    queryset = User.objects.none()
    serializer_class = ProfileFullSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return User.objects.filter(id=self.request.user.id).order_by('id')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProfileCompactSerializer
        return ProfileFullSerializer
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Полный профиль',
        description='Возвращает полный профиль текущего пользователя.',
        tags=['Profile'],
    )
    def full(self, request):
        """Получить полный профиль пользователя."""
        user = request.user
        serializer = ProfileFullSerializer(user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Компактный профиль',
        description='Возвращает компактный профиль (без чувствительных полей).',
        tags=['Profile'],
    )
    def compact(self, request):
        """Получить компактный профиль."""
        user = request.user
        serializer = ProfileCompactSerializer(user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Статистика профиля',
        description='Агрегированная статистика: streak, mood, tasks, weekly analysis.',
        tags=['Profile'],
    )
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

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='История изменений профиля',
        description='История снимков психологического профиля пользователя.',
        tags=['Profile'],
    )
    def history(self, request):
        """История изменений профиля пользователя."""
        queryset = UserProfileHistory.objects.filter(user=request.user).order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserProfileHistorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = UserProfileHistorySerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Баланс токенов',
        description='Текущий баланс токенов и агрегаты по расходам/пополнениям.',
        tags=['Profile'],
    )
    def tokens(self, request):
        """Баланс токенов и агрегаты по транзакциям."""
        user = request.user
        tx_qs = TokenTransaction.objects.filter(user=user)

        total_earned = tx_qs.filter(amount__gt=0).aggregate(total=models.Sum('amount'))['total'] or 0
        total_spent = abs(tx_qs.filter(amount__lt=0).aggregate(total=models.Sum('amount'))['total'] or 0)

        return Response(
            {
                'token_balance': user.token_balance,
                'total_earned': int(total_earned),
                'total_spent': int(total_spent),
                'transactions_count': tx_qs.count(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='История транзакций',
        description='Список транзакций токенов и платежей пользователя.',
        tags=['Profile'],
    )
    def transactions(self, request):
        """История транзакций токенов и платежей."""
        token_tx = TokenTransaction.objects.filter(user=request.user).order_by('-created_at')[:50]
        payments = Payment.objects.filter(user=request.user).order_by('-created_at')[:50]

        return Response(
            {
                'token_transactions': TokenTransactionSerializer(token_tx, many=True).data,
                'payments': PaymentSerializer(payments, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(
        summary='Сводка прогресса',
        description='Ключевые метрики прогресса пользователя.',
        responses={200: ProgressSummarySerializer, 401: APIErrorSerializer},
        tags=['Progress'],
    )
)
class ProgressViewSet(viewsets.ViewSet):
    """ViewSet для прогресса и аналитики пользователя."""

    queryset = User.objects.none()
    serializer_class = ProgressSummarySerializer
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """Сводка прогресса пользователя."""
        user = request.user
        avg_mood = (
            PsychoAnalysis.objects.filter(entry__user=user).aggregate(avg=Avg('mood_score'))['avg']
            or 0.0
        )

        payload = {
            'total_entries': DiaryEntry.objects.filter(user=user).count(),
            'total_days_with_entries': CombinedDiaryEntry.objects.filter(user=user).count(),
            'total_tasks_completed': TaskCompletion.objects.filter(task__user=user).count(),
            'weekly_analyses_count': WeeklyAnalysis.objects.filter(user=user).count(),
            'avg_mood_score': round(float(avg_mood), 2),
        }
        return Response(ProgressSummarySerializer(payload).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Серия активности',
        description='Текущая серия, максимальная серия и активные дни за 30 дней.',
        responses={200: ProgressStreakSerializer, 401: APIErrorSerializer},
        tags=['Progress'],
    )
    def streak(self, request):
        """Серия активности на основе дат записей дневника."""
        user = request.user
        entry_dates = set(
            DiaryEntry.objects.filter(user=user).values_list('created_at__date', flat=True).distinct()
        )

        today = timezone.now().date()
        current_streak = 0
        probe = today
        while probe in entry_dates:
            current_streak += 1
            probe -= timedelta(days=1)

        max_streak = 0
        if entry_dates:
            sorted_dates = sorted(entry_dates)
            run = 1
            max_streak = 1
            for idx in range(1, len(sorted_dates)):
                if (sorted_dates[idx] - sorted_dates[idx - 1]).days == 1:
                    run += 1
                else:
                    run = 1
                if run > max_streak:
                    max_streak = run

        payload = {
            'current_streak': current_streak,
            'max_streak': max_streak,
            'active_days_last_30': DiaryEntry.objects.filter(
                user=user,
                created_at__date__gte=today - timedelta(days=30),
            ).values_list('created_at__date', flat=True).distinct().count(),
        }
        return Response(ProgressStreakSerializer(payload).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='mood/(?P<period>[^/.]+)')
    @extend_schema(
        summary='График настроения',
        description='Возвращает точки графика настроения по периодам: daily/weekly/monthly.',
        parameters=[
            OpenApiParameter(
                name='period',
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
                enum=['daily', 'weekly', 'monthly'],
                description='Период агрегации настроения.',
            ),
        ],
        responses={200: MoodTimelineSerializer, 400: APIErrorSerializer, 401: APIErrorSerializer},
        tags=['Progress'],
    )
    def mood(self, request, period: Literal['daily', 'weekly', 'monthly'] | None = None):
        """График настроения по периодам: daily, weekly, monthly."""
        if period not in {'daily', 'weekly', 'monthly'}:
            return api_error_response(
                code='invalid_period',
                message='Invalid period. Use daily, weekly or monthly.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        analyses = PsychoAnalysis.objects.filter(entry__user=request.user).select_related('entry')
        buckets = {}

        for item in analyses:
            if period == 'daily':
                bucket_key = item.created_at.date().isoformat()
            elif period == 'weekly':
                year, week, _ = item.created_at.date().isocalendar()
                bucket_key = f'{year}-W{week:02d}'
            else:
                bucket_key = item.created_at.strftime('%Y-%m')

            if bucket_key not in buckets:
                buckets[bucket_key] = {'sum': 0, 'count': 0}
            buckets[bucket_key]['sum'] += item.mood_score
            buckets[bucket_key]['count'] += 1

        points = []
        for key in sorted(buckets.keys()):
            points.append(
                {
                    'period': key,
                    'avg_mood_score': round(buckets[key]['sum'] / buckets[key]['count'], 2),
                    'entries_count': buckets[key]['count'],
                }
            )

        return Response(
            {
                'period': period,
                'points': MoodPointSerializer(points, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Недельные анализы прогресса',
        description='Возвращает список weekly analysis текущего пользователя.',
        responses={200: WeeklyAnalysisSerializer(many=True), 401: APIErrorSerializer},
        tags=['Progress'],
    )
    def weekly(self, request):
        """Недельные анализы пользователя."""
        queryset = WeeklyAnalysis.objects.filter(user=request.user).order_by('-week_start_date')
        serializer = WeeklyAnalysisSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='Активность пользователя',
        description='Сводка активности по типам и последние события.',
        responses={200: UserActivityFeedSerializer, 401: APIErrorSerializer},
        tags=['Progress'],
    )
    def activity(self, request):
        """Сводка и последние события активности пользователя."""
        queryset = UserActivity.objects.filter(user=request.user).order_by('-timestamp')

        summary = {}
        for row in queryset.values('activity_type').annotate(count=models.Count('id')):
            summary[row['activity_type']] = row['count']

        recent = queryset[:20]
        return Response(
            {
                'summary': summary,
                'recent': UserActivitySerializer(recent, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(
        summary='Список записей дневника',
        description='Список записей текущего пользователя с фильтрацией и сортировкой.',
        parameters=[
            OpenApiParameter('language', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Фильтр по языку (ru/en).'),
            OpenApiParameter('is_processed', OpenApiTypes.BOOL, OpenApiParameter.QUERY, description='Фильтр по статусу обработки.'),
            OpenApiParameter('is_primary', OpenApiTypes.BOOL, OpenApiParameter.QUERY, description='Только основные записи дня.'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата начала периода (YYYY-MM-DD).'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата конца периода (YYYY-MM-DD).'),
            OpenApiParameter('ordering', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Сортировка: created_at, -created_at, word_count, -word_count.'),
        ],
        tags=['Entries'],
    ),
    create=extend_schema(
        summary='Создать запись дневника',
        description='Создает запись дневника для текущего пользователя.',
        tags=['Entries'],
    ),
    retrieve=extend_schema(summary='Получить запись дневника', tags=['Entries']),
    update=extend_schema(summary='Обновить запись дневника', tags=['Entries']),
    partial_update=extend_schema(summary='Частично обновить запись дневника', tags=['Entries']),
    destroy=extend_schema(summary='Удалить запись дневника', tags=['Entries']),
)
class DiaryEntryViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с записями дневника.
    """
    queryset = DiaryEntry.objects.none()
    serializer_class = DiaryEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method not in SAFE_METHODS:
            return [EntryMutationRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        queryset = DiaryEntry.objects.filter(user=self.request.user)

        language = self.request.query_params.get('language')
        if language:
            queryset = queryset.filter(language=language)

        is_processed = _parse_bool_param(self.request.query_params.get('is_processed'))
        if is_processed is not None:
            queryset = queryset.filter(is_processed=is_processed)

        is_primary = _parse_bool_param(self.request.query_params.get('is_primary'))
        if is_primary is not None:
            queryset = queryset.filter(is_primary=is_primary)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        ordering = self.request.query_params.get('ordering', '-created_at')
        allowed_ordering = {'created_at', '-created_at', 'word_count', '-word_count'}
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')

        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='date/(?P<entry_date>[^/.]+)')
    @extend_schema(
        summary='Записи за дату',
        description='Возвращает записи текущего пользователя за конкретную дату.',
        parameters=[
            OpenApiParameter(
                name='entry_date',
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.DATE,
                description='Дата в формате YYYY-MM-DD.',
            )
        ],
        tags=['Entries'],
    )
    def by_date(self, request, entry_date: date | str | None = None):
        """Get current user's entries for a specific date (YYYY-MM-DD)."""
        try:
            if isinstance(entry_date, date):
                target_date = entry_date
            else:
                target_date = datetime.strptime(entry_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return api_error_response(
                code='invalid_date_format',
                message='Invalid date format. Use YYYY-MM-DD.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        queryset = DiaryEntry.objects.filter(
            user=request.user,
            created_at__date=target_date,
        ).order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    @extend_schema(
        summary='Анализ записи',
        description='Возвращает психоанализ для конкретной записи.',
        responses={
            200: OpenApiResponse(description='Анализ найден и возвращен.'),
            404: OpenApiResponse(description='Анализ не найден.'),
        },
        tags=['Entries'],
    )
    def analysis(self, request, pk: int | None = None):
        """Get psycho analysis details for a specific entry."""
        entry = self.get_object()

        try:
            analysis = entry.analysis
        except PsychoAnalysis.DoesNotExist:
            return api_error_response(
                code='analysis_not_found',
                message='Analysis not found for this entry.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                'entry_id': entry.id,
                'analysis_id': analysis.id,
                'mood_score': analysis.mood_score,
                'comment': analysis.comment,
                'recommendation': analysis.recommendation,
                'analysis_text': analysis.analysis_text,
                'processing_time': analysis.processing_time,
                'insights_extracted': analysis.insights_extracted,
                'created_at': analysis.created_at,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    @extend_schema(
        summary='Добавить комментарий к записи',
        description='Сохраняет `user_comment` для указанной записи.',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'user_comment': {
                        'type': 'string',
                        'description': 'Комментарий пользователя к записи.',
                    }
                },
                'required': ['user_comment'],
            }
        },
        responses={
            200: OpenApiResponse(description='Комментарий сохранен.'),
            400: OpenApiResponse(description='Некорректный запрос.'),
        },
        tags=['Entries'],
    )
    def comment(self, request, pk: int | None = None):
        """Save user comment for a specific entry."""
        entry = self.get_object()

        comment_text = (request.data.get('user_comment') or '').strip()
        if not comment_text:
            return api_error_response(
                code='user_comment_required',
                message='user_comment is required.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        entry.user_comment = comment_text
        entry.save(update_fields=['user_comment', 'updated_at'])

        serializer = self.get_serializer(entry)
        return Response(
            {
                'message': 'Comment saved.',
                'entry': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(
        summary='Список объединенных записей дня',
        description='Read-only endpoint с фильтрацией по диапазону дат.',
        parameters=[
            OpenApiParameter('date_from', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата начала.'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата окончания.'),
        ],
        tags=['Days'],
    ),
    retrieve=extend_schema(summary='Детали объединенной записи дня', tags=['Days']),
)
class CombinedDiaryEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с объединёнными записями дня (только чтение).
    """
    queryset = CombinedDiaryEntry.objects.none()
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


@extend_schema_view(
    list=extend_schema(summary='Список weekly analysis', tags=['Weekly']),
    retrieve=extend_schema(summary='Детали weekly analysis', tags=['Weekly']),
)
class WeeklyAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с еженедельными анализами (только чтение).
    """
    queryset = WeeklyAnalysis.objects.none()
    serializer_class = WeeklyAnalysisSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return WeeklyAnalysis.objects.filter(
            user=self.request.user
        ).order_by('-week_start_date')


@extend_schema_view(
    list=extend_schema(
        summary='Список задач',
        description='Список задач пользователя с фильтрацией и сортировкой.',
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Фильтр по статусу.'),
            OpenApiParameter('type', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Фильтр по типу задачи.'),
            OpenApiParameter('complexity', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Фильтр по сложности.'),
            OpenApiParameter('assigned_from', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата назначения от.'),
            OpenApiParameter('assigned_to', OpenApiTypes.DATE, OpenApiParameter.QUERY, description='Дата назначения до.'),
            OpenApiParameter('completed', OpenApiTypes.BOOL, OpenApiParameter.QUERY, description='Фильтр по завершенности.'),
            OpenApiParameter('ordering', OpenApiTypes.STR, OpenApiParameter.QUERY, description='assigned_at/-assigned_at/completed_at/-completed_at'),
        ],
        tags=['Tasks'],
    ),
    create=extend_schema(summary='Создать задачу', tags=['Tasks']),
    retrieve=extend_schema(summary='Получить задачу', tags=['Tasks']),
    update=extend_schema(summary='Обновить задачу', tags=['Tasks']),
    partial_update=extend_schema(summary='Частично обновить задачу', tags=['Tasks']),
    destroy=extend_schema(summary='Удалить задачу', tags=['Tasks']),
)
class TherapyTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с терапевтическими заданиями.
    """
    queryset = TherapyTask.objects.none()
    serializer_class = TherapyTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method not in SAFE_METHODS:
            return [TaskMutationRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        queryset = TherapyTask.objects.filter(user=self.request.user)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        task_type = self.request.query_params.get('type')
        if task_type:
            queryset = queryset.filter(type=task_type)

        complexity = self.request.query_params.get('complexity')
        if complexity:
            queryset = queryset.filter(complexity=complexity)

        assigned_from = self.request.query_params.get('assigned_from')
        if assigned_from:
            queryset = queryset.filter(assigned_at__date__gte=assigned_from)

        assigned_to = self.request.query_params.get('assigned_to')
        if assigned_to:
            queryset = queryset.filter(assigned_at__date__lte=assigned_to)

        completed = _parse_bool_param(self.request.query_params.get('completed'))
        if completed is True:
            queryset = queryset.filter(completed_at__isnull=False)
        if completed is False:
            queryset = queryset.filter(completed_at__isnull=True)

        ordering = self.request.query_params.get('ordering', '-assigned_at')
        allowed_ordering = {'assigned_at', '-assigned_at', 'completed_at', '-completed_at'}
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-assigned_at')

        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    @extend_schema(
        summary='Завершить задачу',
        description='Переводит задачу в статус completed и проставляет completed_at.',
        tags=['Tasks'],
    )
    def complete(self, request, pk: int | None = None):
        """Отметить задание как выполненное."""
        task = self.get_object()
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()
        return Response({'status': 'completed'})

    @action(detail=False, methods=['get'])
    @extend_schema(
        summary='История задач',
        description='Возвращает только задачи в статусах completed/skipped/expired.',
        tags=['Tasks'],
    )
    def history(self, request):
        """История завершенных/пропущенных/просроченных задач."""
        queryset = TherapyTask.objects.filter(
            user=request.user,
            status__in=['completed', 'skipped', 'expired'],
        ).order_by('-completed_at', '-assigned_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
    throttle_classes = [AuthRateThrottle]

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
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Авторизация Telegram-токеном',
        description='Выполняет авторизацию по токену из query param `token`.',
        request=None,
        parameters=[
            OpenApiParameter('token', OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: APIErrorSerializer, 404: APIErrorSerializer},
        tags=['Auth'],
    )
    def get(self, request):
        token = request.query_params.get('token')
        
        if not token:
            return api_error_response(
                code='token_required',
                message='Token is required',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Валидируем токен
        user_id = validate_telegram_auth_token(token)
        
        if not user_id:
            return api_error_response(
                code='invalid_token',
                message='Token is invalid or expired',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Получаем пользователя
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return api_error_response(
                code='user_not_found',
                message='User not found',
                status_code=status.HTTP_404_NOT_FOUND,
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
    serializer_class = CompleteRegistrationSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Завершение регистрации',
        description='Устанавливает email и пароль для telegram-пользователя.',
        request=CompleteRegistrationSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: APIErrorSerializer, 401: APIErrorSerializer},
        tags=['Auth'],
    )
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
    serializer_class = GenerateLinkSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [LinkGenerationRateThrottle]

    @extend_schema(
        summary='Сгенерировать ссылку привязки',
        description='Создает временную ссылку для связывания Telegram и web аккаунта.',
        request=None,
        responses={200: GenerateLinkSerializer, 401: APIErrorSerializer},
        tags=['Auth'],
    )
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
    throttle_classes = [AuthRateThrottle]
    
    @extend_schema(
        summary='Логин по email и паролю',
        description='Возвращает JWT access/refresh токены.',
        tags=['Auth'],
    )
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
                if hasattr(request.data, '_mutable'):
                    request.data._mutable = True
                    request.data['username'] = user.username
                else:
                    request._full_data = {**request.data, 'username': user.username}
            except User.DoesNotExist:
                pass
        return super().post(request, *args, **kwargs)


class MonitoringSnapshotView(APIView):
    """Read-only endpoint для snapshot системных метрик мониторинга."""
    serializer_class = MonitoringSnapshotSerializer
    permission_classes = [IsAuthenticated, MonitoringAccessPermission]
    throttle_classes = [MonitoringRateThrottle]

    @extend_schema(
        summary='Monitoring snapshot (JSON)',
        description='Возвращает JSON-снимок внутренних метрик мониторинга.',
        responses={200: MonitoringSnapshotSerializer, 401: APIErrorSerializer},
        tags=['Monitoring'],
    )
    def get(self, request):
        snapshot = monitoring_service.get_snapshot()
        serializer = MonitoringSnapshotSerializer(snapshot)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PrometheusMetricsView(APIView):
    """Prometheus exposition format endpoint для метрик мониторинга."""
    permission_classes = [IsAuthenticated, MonitoringAccessPermission]
    throttle_classes = [MonitoringHeavyRateThrottle]

    @extend_schema(
        summary='Monitoring snapshot (Prometheus)',
        description='Возвращает метрики в формате Prometheus exposition.',
        tags=['Monitoring'],
        responses={200: OpenApiResponse(description='text/plain Prometheus metrics')},
    )
    def get(self, request):
        snapshot = monitoring_service.get_snapshot()
        prometheus_text = PrometheusFormatter.format_snapshot(snapshot)
        return Response(
            prometheus_text,
            content_type="text/plain; version=0.0.4; charset=utf-8",
            status=status.HTTP_200_OK,
        )


class ComprehensiveStatsView(APIView):
    """Endpoint для получения комплексной статистики приложения."""
    serializer_class = ComprehensiveStatsSerializer
    permission_classes = [IsAuthenticated, MonitoringAccessPermission]
    throttle_classes = [MonitoringHeavyRateThrottle]

    @extend_schema(
        summary='Комплексная статистика',
        description='Агрегированная статистика приложения (AI, onboarding, retention, tasks, entries, engagement).',
        parameters=[
            OpenApiParameter('period', OpenApiTypes.STR, OpenApiParameter.QUERY, description='daily|weekly|monthly'),
            OpenApiParameter('days_back', OpenApiTypes.INT, OpenApiParameter.QUERY, description='Глубина периода в днях (1..365).'),
            OpenApiParameter('include_daily_snapshots', OpenApiTypes.BOOL, OpenApiParameter.QUERY, description='Включить ежедневные snapshot-ы.'),
        ],
        responses={
            200: ComprehensiveStatsSerializer,
            400: APIErrorSerializer,
            401: APIErrorSerializer,
            500: APIErrorSerializer,
        },
        tags=['Monitoring'],
    )
    def get(self, request):
        """
        Get comprehensive statistics.

        Query parameters:
        - period: "daily", "weekly", "monthly" (default: "daily")
        - days_back: number of days to look back (default: 7, max: 365)
        - include_daily_snapshots: "true"/"false" (default: false)
        """
        try:
            period = request.query_params.get('period', 'daily')
            days_back = int(request.query_params.get('days_back', 7))
            include_snapshots = request.query_params.get('include_daily_snapshots', 'false').lower() == 'true'

            query = StatsQuery(
                period=period,
                days_back=days_back,
                include_daily_snapshots=include_snapshots
            )

            if not query.validate():
                return api_error_response(
                    code='invalid_query_parameters',
                    message='Invalid query parameters',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            from asgiref.sync import async_to_sync
            stats_dto = async_to_sync(stats_service.get_comprehensive_stats)(query)

            serializer = ComprehensiveStatsSerializer(stats_dto.to_dict())
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.error(f"[ComprehensiveStatsView] Validation error: {e}")
            return api_error_response(
                code='validation_error',
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"[ComprehensiveStatsView] Error retrieving stats: {e}", exc_info=True)
            return api_error_response(
                code='stats_retrieval_failed',
                message='Failed to retrieve statistics',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RefreshView(TokenRefreshView):
    """JWT refresh endpoint with the same auth throttling policy."""

    permission_classes = []
    throttle_classes = [RefreshRateThrottle]
