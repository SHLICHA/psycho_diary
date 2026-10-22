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
    GenerateMaxLinkView, PasswordResetRequestView, PasswordResetConfirmView,
    WebAccessClaimStartView, WebAccessSetPasswordView,
    ConfirmEmailMergeOtpView,
    ConfirmEmailMergeView,
    GenerateLinkView, LoginView, LogoutView, MonitoringSnapshotView, PrometheusMetricsView,
    RefreshView,
    ComprehensiveStatsView,
    FeedbackView,
    RemindersView,
)
from .views_phase_a import (
    SettingsView,
    SettingsTaskLimitView,
    SettingsTimezoneLookupView,
    SettingsTimezoneConfirmView,
    OnboardingStatusView,
    OnboardingAcceptAgreementView,
    OnboardingTimezoneView,
    OnboardingFirstEntryView,
    TherapyChatWelcomeView,
    TherapyChatStartView,
    TherapyChatMessageView,
    TherapyChatEndView,
    DayByDateView,
    DayReanalyzeView,
    DayRatingView,
)
from .views_payments import (
    PaymentProductsView,
    PaymentCreateView,
    PaymentEmailView,
    PaymentDetailView,
    PaymentSyncView,
    PaymentWebhookView,
    PaymentListView,
)
from .views_admin import (
    AdminFeedbackListView,
    AdminFeedbackDetailView,
    AdminFeedbackReplyView,
    AdminExportView,
    AdminStatsView,
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
    # Phase A day-by-date routes (before router to avoid pk clash)
    path('days/date/<str:entry_date>/reanalyze/', DayReanalyzeView.as_view(), name='day-reanalyze'),
    path('days/date/<str:entry_date>/rating/', DayRatingView.as_view(), name='day-rating'),
    path('days/date/<str:entry_date>/', DayByDateView.as_view(), name='day-by-date'),

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
    path('generate-max-link/', GenerateMaxLinkView.as_view(), name='auth-generate-max-link'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('web-access/claim/', WebAccessClaimStartView.as_view(), name='auth-web-access-claim'),
    path('web-access/set-password/', WebAccessSetPasswordView.as_view(), name='auth-web-access-set-password'),
    path('confirm-email-merge-otp/', ConfirmEmailMergeOtpView.as_view(), name='auth-confirm-email-merge-otp'),
    path('monitoring/metrics/', MonitoringSnapshotView.as_view(), name='monitoring-metrics'),
    path('monitoring/prometheus/', PrometheusMetricsView.as_view(), name='monitoring-prometheus'),
    path('monitoring/stats/', ComprehensiveStatsView.as_view(), name='monitoring-stats'),
    path('feedback/', FeedbackView.as_view(), name='feedback'),
    path('reminders/', RemindersView.as_view(), name='reminders'),

    # Phase A — Settings / Onboarding / Therapy
    path('settings/', SettingsView.as_view(), name='settings'),
    path('settings/task-limit/', SettingsTaskLimitView.as_view(), name='settings-task-limit'),
    path('settings/timezone/lookup/', SettingsTimezoneLookupView.as_view(), name='settings-timezone-lookup'),
    path('settings/timezone/confirm/', SettingsTimezoneConfirmView.as_view(), name='settings-timezone-confirm'),
    path('onboarding/status/', OnboardingStatusView.as_view(), name='onboarding-status'),
    path('onboarding/accept-agreement/', OnboardingAcceptAgreementView.as_view(), name='onboarding-accept-agreement'),
    path('onboarding/timezone/', OnboardingTimezoneView.as_view(), name='onboarding-timezone'),
    path('onboarding/first-entry/', OnboardingFirstEntryView.as_view(), name='onboarding-first-entry'),
    path('therapy-chat/welcome/', TherapyChatWelcomeView.as_view(), name='therapy-chat-welcome'),
    path('therapy-chat/start/', TherapyChatStartView.as_view(), name='therapy-chat-start'),
    path('therapy-chat/message/', TherapyChatMessageView.as_view(), name='therapy-chat-message'),
    path('therapy-chat/end/', TherapyChatEndView.as_view(), name='therapy-chat-end'),

    # Phase B — Payments
    path('payments/products/', PaymentProductsView.as_view(), name='payments-products'),
    path('payments/create/', PaymentCreateView.as_view(), name='payments-create'),
    path('payments/email/', PaymentEmailView.as_view(), name='payments-email'),
    path('payments/webhook/', PaymentWebhookView.as_view(), name='payments-webhook'),
    path('payments/<int:payment_id>/sync/', PaymentSyncView.as_view(), name='payments-sync'),
    path('payments/<int:payment_id>/', PaymentDetailView.as_view(), name='payments-detail'),
    path('payments/', PaymentListView.as_view(), name='payments-list'),

    # Phase D — Admin
    path('admin/feedback/', AdminFeedbackListView.as_view(), name='admin-feedback-list'),
    path('admin/feedback/<int:feedback_id>/', AdminFeedbackDetailView.as_view(), name='admin-feedback-detail'),
    path('admin/feedback/<int:feedback_id>/reply/', AdminFeedbackReplyView.as_view(), name='admin-feedback-reply'),
    path('admin/export/', AdminExportView.as_view(), name='admin-export'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),

    path('schema/', SpectacularAPIView.as_view(permission_classes=[]), name='api-schema'),
    path('docs/', SpectacularRedocView.as_view(url_name='api-schema'), name='api-redoc'),
]
