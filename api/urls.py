"""
URL configuration for REST API Psycho Diary.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from .views import (
    UserViewSet, ProfileViewSet,
    DiaryEntryViewSet, CombinedDiaryEntryViewSet,
    WeeklyAnalysisViewSet, TherapyTaskViewSet, ProgressViewSet,
    RegisterView, TelegramAuthView, CompleteRegistrationView,
    ConfirmEmailMergeView,
    GenerateLinkView, LoginView, LogoutView, MonitoringSnapshotView, PrometheusMetricsView,
    RefreshView,
    ComprehensiveStatsView,
    FeedbackView,
    RemindersView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'profile', ProfileViewSet, basename='profile')
router.register(r'entries', DiaryEntryViewSet, basename='entry')
router.register(r'days', CombinedDiaryEntryViewSet, basename='day')
router.register(r'weekly', WeeklyAnalysisViewSet, basename='weekly')
router.register(r'tasks', TherapyTaskViewSet, basename='task')
router.register(r'progress', ProgressViewSet, basename='progress')

urlpatterns = [
    path('', include(router.urls)),
    
    # Auth endpoints (under /api/v1/auth/)
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('telegram/', TelegramAuthView.as_view(), name='auth-telegram'),
    path('complete-registration/', CompleteRegistrationView.as_view(), name='auth-complete-registration'),
    path('confirm-email-merge/', ConfirmEmailMergeView.as_view(), name='auth-confirm-email-merge'),
    path('generate-link/', GenerateLinkView.as_view(), name='auth-generate-link'),
    path('link-telegram/', GenerateLinkView.as_view(), name='auth-link-telegram'),
    path('monitoring/metrics/', MonitoringSnapshotView.as_view(), name='monitoring-metrics'),
    path('monitoring/prometheus/', PrometheusMetricsView.as_view(), name='monitoring-prometheus'),
    path('monitoring/stats/', ComprehensiveStatsView.as_view(), name='monitoring-stats'),
    path('feedback/', FeedbackView.as_view(), name='feedback'),
    path('reminders/', RemindersView.as_view(), name='reminders'),
    path('schema/', SpectacularAPIView.as_view(permission_classes=[]), name='api-schema'),
    path('docs/', SpectacularRedocView.as_view(url_name='api-schema'), name='api-redoc'),
]