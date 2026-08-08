"""psycho_diary URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from api.views import MaxWebhookView
from api.views_payments import PaymentWebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/max/webhook/', MaxWebhookView.as_view(), name='max-webhook'),
    # Alias без /v1 для кабинета ЮKassa (опционально)
    path('api/payments/webhook/', PaymentWebhookView.as_view(), name='payments-webhook-alias'),

    # REST API
    path('api/v1/auth/', include('api.urls')),
    path('api/v1/', include('api.urls')),

    # JWT Auth
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
