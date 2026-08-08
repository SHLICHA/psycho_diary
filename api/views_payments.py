"""
Phase B API: payments / Premium / token packs via PaymentService.
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.error_utils import api_error_response
from api.serializers import APIErrorSerializer, PaymentSerializer
from api.service_bridge import run_async, strip_transport
from api.throttling import PaymentMutationRateThrottle

logger = logging.getLogger(__name__)

SUBSCRIPTION_SKUS = {
    'subscription_month': 'month',
    'subscription_year': 'year',
}
TOKEN_SKUS = {
    'tokens_10': 10,
    'tokens_50': 50,
    'tokens_100': 100,
    'tokens_200': 200,
    'tokens_500': 500,
}


def _payment_payload(result: dict) -> Response:
    cleaned = strip_transport(dict(result))
    payment = cleaned.pop('payment', None)
    if payment is not None and hasattr(payment, 'id'):
        cleaned['payment'] = PaymentSerializer(payment).data
    if cleaned.get('success') is False:
        return api_error_response(
            code=str(cleaned.get('error') or 'payment_failed'),
            message=str(cleaned.get('error') or 'Операция с платежом не выполнена.'),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={k: v for k, v in cleaned.items() if k not in {'success', 'error'}},
        )
    return Response(cleaned, status=status.HTTP_200_OK)


class PaymentProductsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Каталог продуктов оплаты',
        responses={200: OpenApiResponse(description='Подписки и пакеты токенов.'), 401: APIErrorSerializer},
        tags=['Payments'],
    )
    def get(self, request):
        from diary.services.payment_service import list_products

        return Response(list_products(), status=status.HTTP_200_OK)


class PaymentCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentMutationRateThrottle]

    @extend_schema(
        summary='Создать платёж (Premium / токены)',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'product': {
                        'type': 'string',
                        'description': 'sku: subscription_month|subscription_year|tokens_10|...',
                    },
                    'kind': {'type': 'string', 'enum': ['subscription', 'tokens']},
                    'plan': {'type': 'string', 'enum': ['month', 'year']},
                    'token_count': {'type': 'integer'},
                },
            }
        },
        responses={200: OpenApiResponse(description='Ссылка на оплату или requires_email.'), 400: APIErrorSerializer},
        tags=['Payments'],
    )
    def post(self, request):
        from diary.services.payment_service import (
            initiate_subscription_payment,
            initiate_token_payment,
        )

        product = (request.data.get('product') or '').strip()
        kind = (request.data.get('kind') or '').strip()
        plan = (request.data.get('plan') or '').strip()
        token_count = request.data.get('token_count')

        if product in SUBSCRIPTION_SKUS:
            plan = SUBSCRIPTION_SKUS[product]
            kind = 'subscription'
        elif product in TOKEN_SKUS:
            token_count = TOKEN_SKUS[product]
            kind = 'tokens'
        elif product and not kind:
            return api_error_response(
                code='invalid_product',
                message='Неизвестный product sku.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if kind == 'subscription':
            if plan not in ('month', 'year'):
                return api_error_response(
                    code='invalid_plan',
                    message='Поле plan должно быть month или year.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            result = run_async(initiate_subscription_payment(request.user, plan))
        elif kind == 'tokens':
            try:
                token_count = int(token_count)
            except (TypeError, ValueError):
                return api_error_response(
                    code='invalid_token_count',
                    message='Поле token_count обязательно и должно быть целым.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            result = run_async(initiate_token_payment(request.user, token_count))
        else:
            return api_error_response(
                code='product_required',
                message='Укажите product или kind=subscription|tokens.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        cleaned = strip_transport(result)
        if not cleaned.get('success'):
            return api_error_response(
                code='payment_init_failed',
                message=str(cleaned.get('error') or 'Не удалось создать платёж.'),
                status_code=status.HTTP_400_BAD_REQUEST,
                details=cleaned,
            )
        return Response(cleaned, status=status.HTTP_200_OK)


class PaymentEmailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentMutationRateThrottle]

    @extend_schema(
        summary='Указать email для чека и завершить создание платежа',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'email': {'type': 'string', 'format': 'email'},
                    'pending_payment_data': {'type': 'object'},
                },
                'required': ['email', 'pending_payment_data'],
            }
        },
        responses={200: OpenApiResponse(description='Ссылка на оплату.'), 400: APIErrorSerializer},
        tags=['Payments'],
    )
    def post(self, request):
        from diary.services.payment_service import process_user_email_for_pending_payment

        email = (request.data.get('email') or '').strip()
        pending = request.data.get('pending_payment_data')
        if not email:
            return api_error_response(
                code='email_required',
                message='Поле email обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(pending, dict) or not pending:
            return api_error_response(
                code='pending_payment_data_required',
                message='Поле pending_payment_data обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        result = run_async(
            process_user_email_for_pending_payment(request.user, email, pending)
        )
        cleaned = strip_transport(result)
        if not cleaned.get('success'):
            code = cleaned.get('error_code') or 'payment_email_failed'
            http_status = status.HTTP_400_BAD_REQUEST
            if cleaned.get('confirmation_required'):
                http_status = status.HTTP_409_CONFLICT
            return api_error_response(
                code=str(code),
                message=str(cleaned.get('error') or 'Не удалось создать платёж.'),
                status_code=http_status,
                details=cleaned,
            )
        return Response(cleaned, status=status.HTTP_200_OK)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Статус платежа',
        responses={200: PaymentSerializer, 404: APIErrorSerializer},
        tags=['Payments'],
    )
    def get(self, request, payment_id: int):
        from diary.services.payment_service import get_user_payment

        result = run_async(get_user_payment(request.user, payment_id))
        if not result.get('success'):
            return api_error_response(
                code=result.get('error') or 'payment_not_found',
                message='Платёж не найден.',
                status_code=status.HTTP_404_NOT_FOUND,
            )
        payment = result['payment']
        request.user.refresh_from_db()
        return Response(
            {
                'success': True,
                'payment': PaymentSerializer(payment).data,
                'user': {
                    'is_premium': request.user.is_premium,
                    'premium_expires_at': request.user.premium_expires_at,
                    'token_balance': request.user.token_balance,
                },
            },
            status=status.HTTP_200_OK,
        )


class PaymentSyncView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentMutationRateThrottle]

    @extend_schema(
        summary='Синхронизировать статус платежа с ЮKassa',
        responses={200: OpenApiResponse(description='Актуальный статус.'), 400: APIErrorSerializer},
        tags=['Payments'],
    )
    def post(self, request, payment_id: int):
        from diary.services.payment_service import sync_payment_status

        result = run_async(sync_payment_status(request.user, payment_id))
        return _payment_payload(result)


class PaymentWebhookView(APIView):
    """YooKassa notification webhook (no JWT)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='Webhook ЮKassa',
        responses={200: OpenApiResponse(description='Принято.'), 400: APIErrorSerializer},
        tags=['Payments'],
    )
    def post(self, request):
        from diary.services.payment_service import confirm_payment_by_yookassa_id

        payload = request.data or {}
        event_object = payload.get('object') or {}
        yookassa_id = (
            event_object.get('id')
            or payload.get('yookassa_payment_id')
            or payload.get('id')
        )
        provider_status = event_object.get('status') or payload.get('status')

        if not yookassa_id:
            return api_error_response(
                code='yookassa_payment_id_required',
                message='В webhook отсутствует id платежа ЮKassa.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        result = run_async(
            confirm_payment_by_yookassa_id(
                str(yookassa_id),
                provider_status=provider_status,
            )
        )
        if not result.get('success'):
            # Always 200 for unknown payments to avoid YooKassa retry storms on junk,
            # but return structured body for our monitoring.
            logger.warning(
                "[PaymentWebhook] confirm failed for %s: %s",
                yookassa_id,
                result.get('error'),
            )
            return Response(
                {
                    'success': False,
                    'error': result.get('error'),
                    'yookassa_payment_id': yookassa_id,
                },
                status=status.HTTP_200_OK,
            )

        payment = result.get('payment')
        return Response(
            {
                'success': True,
                'yookassa_payment_id': yookassa_id,
                'status': result.get('status'),
                'granted': result.get('granted', False),
                'payment_id': getattr(payment, 'id', None),
            },
            status=status.HTTP_200_OK,
        )


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='История платежей текущего пользователя',
        responses={200: PaymentSerializer(many=True), 401: APIErrorSerializer},
        tags=['Payments'],
    )
    def get(self, request):
        from users.models import Payment

        qs = Payment.objects.filter(user=request.user).order_by('-created_at')[:50]
        return Response(
            {'results': PaymentSerializer(qs, many=True).data},
            status=status.HTTP_200_OK,
        )
