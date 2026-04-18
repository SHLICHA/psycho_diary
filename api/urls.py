"""
URL configuration for REST API Psycho Diary.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    UserViewSet, ProfileViewSet,
    DiaryEntryViewSet, CombinedDiaryEntryViewSet,
    WeeklyAnalysisViewSet, TherapyTaskViewSet,
    RegisterView, TelegramAuthView, CompleteRegistrationView,
    GenerateLinkView, LoginView
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'profile', ProfileViewSet, basename='profile')
router.register(r'entries', DiaryEntryViewSet, basename='entry')
router.register(r'days', CombinedDiaryEntryViewSet, basename='day')
router.register(r'weekly', WeeklyAnalysisViewSet, basename='weekly')
router.register(r'tasks', TherapyTaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
    
    # Auth endpoints (under /api/v1/auth/)
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('telegram/', TelegramAuthView.as_view(), name='auth-telegram'),
    path('complete-registration/', CompleteRegistrationView.as_view(), name='auth-complete-registration'),
    path('generate-link/', GenerateLinkView.as_view(), name='auth-generate-link'),
]