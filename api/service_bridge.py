"""
Тонкий мост sync DRF views ↔ async use cases / сервисы.
Без доменной логики: только запуск, маппинг ошибок и очистка transport-полей.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from rest_framework import status
from rest_framework.response import Response

from api.error_utils import api_error_response
from core.service_response import ServiceResponse

logger = logging.getLogger(__name__)

TRANSPORT_KEYS = frozenset(
    {
        'reply_markup',
        'keyboard',
        'set_state',
        'clear_state',
        'fsm_state',
        'fsm_payload',
        'set_origin',
        'show_alert',
        'use_main_menu_keyboard',
        'refresh_screen',
        'notify_mode',
    }
)


def run_async(coro):
    """Run an async coroutine from a sync DRF view."""
    return asyncio.run(coro)


def strip_transport(payload: Any) -> Any:
    """Recursively drop Telegram/MAX transport-only keys from dict payloads."""
    if isinstance(payload, Mapping):
        cleaned: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in TRANSPORT_KEYS:
                continue
            cleaned[key] = strip_transport(value)
        return cleaned
    if isinstance(payload, list):
        return [strip_transport(item) for item in payload]
    return payload


def from_service_response(
    response: ServiceResponse,
    *,
    success_status: int = status.HTTP_200_OK,
    error_status: int = status.HTTP_400_BAD_REQUEST,
    data_transform=None,
) -> Response:
    """Map ServiceResponse to DRF Response / api_error_response."""
    if not response.success:
        return api_error_response(
            code=response.error or 'request_failed',
            message=response.message or 'Операция не выполнена.',
            status_code=error_status,
            details=strip_transport(response.data) if response.data is not None else None,
        )

    data = response.data
    if data_transform is not None:
        data = data_transform(data)
    payload = strip_transport(data) if data is not None else {}
    if isinstance(payload, dict):
        body = dict(payload)
        if response.message:
            body.setdefault('message', response.message)
        if response.metadata:
            body.setdefault('metadata', strip_transport(response.metadata))
        return Response(body, status=success_status)
    return Response({'result': payload, 'message': response.message}, status=success_status)


def from_service_dict(
    result: Mapping[str, Any],
    *,
    success_status: int = status.HTTP_200_OK,
    error_status: int = status.HTTP_400_BAD_REQUEST,
    error_code_key: str = 'error',
    default_error_code: str = 'request_failed',
) -> Response:
    """Map a plain service dict with success/error keys to DRF Response."""
    cleaned = strip_transport(dict(result))
    if cleaned.get('success') is False:
        return api_error_response(
            code=str(cleaned.get(error_code_key) or default_error_code),
            message=str(
                cleaned.get('message')
                or cleaned.get('alert_text')
                or cleaned.get('text')
                or 'Операция не выполнена.'
            ),
            status_code=error_status,
            details={k: v for k, v in cleaned.items() if k not in {'success', error_code_key}},
        )
    return Response(cleaned, status=success_status)


def ensure_tokens(user, cost: int = 1, *, feature_name: str = 'api_feature') -> Optional[Response]:
    """
    Mirror bot requires_tokens for sync API views.
    Premium users skip charge. Returns error Response or None if OK.
    """
    if getattr(user, 'is_premium', False):
        return None

    balance = getattr(user, 'token_balance', 0) or 0
    if balance < cost:
        return api_error_response(
            code='insufficient_tokens',
            message='Недостаточно токенов для выполнения операции.',
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details={'required': cost, 'balance': balance},
        )

    from users.models import TokenTransaction

    try:
        TokenTransaction.create_and_update_balance(
            user=user,
            amount=-cost,
            transaction_type='feature_usage',
            description=f'Использование платной функции: {feature_name}',
        )
    except Exception as exc:
        logger.error('Token charge failed for user %s: %s', user.pk, exc, exc_info=True)
        return api_error_response(
            code='token_charge_failed',
            message='Не удалось списать токены.',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return None


def refund_tokens(user, cost: int = 1, *, feature_name: str = 'api_feature') -> None:
    """Best-effort refund after a failed paid operation."""
    if getattr(user, 'is_premium', False) or cost <= 0:
        return
    from users.models import TokenTransaction

    try:
        TokenTransaction.create_and_update_balance(
            user=user,
            amount=cost,
            transaction_type='refund_on_error',
            description=f'Возврат токенов за ошибку в функции: {feature_name}',
        )
    except Exception as exc:
        logger.error('Token refund failed for user %s: %s', user.pk, exc, exc_info=True)


def serialize_entry_analysis(entry, analysis) -> Dict[str, Any]:
    """Build a compact entry+analysis payload for parity endpoints."""
    from api.serializers import DiaryEntrySerializer

    entry_data = DiaryEntrySerializer(entry).data if entry is not None else None
    analysis_data = None
    if analysis is not None:
        analysis_data = {
            'id': getattr(analysis, 'id', None),
            'mood_score': getattr(analysis, 'mood_score', None),
            'comment': getattr(analysis, 'comment', None),
            'recommendation': getattr(analysis, 'recommendation', None),
            'analysis_text': getattr(analysis, 'analysis_text', None),
        }
    return {'entry': entry_data, 'analysis': analysis_data}


def serialize_task_completion_analysis(analysis) -> Optional[Dict[str, Any]]:
    """Compact JSON-safe TaskCompletionAnalysis for API responses."""
    if analysis is None:
        return None
    if isinstance(analysis, Mapping):
        return dict(analysis)
    return {
        'id': getattr(analysis, 'id', None),
        'effect_description': getattr(analysis, 'effect_description', None),
        'mood_impact_score': getattr(analysis, 'mood_impact_score', None),
        'comment': getattr(analysis, 'comment', None),
        'recommendation': getattr(analysis, 'recommendation', None),
        'detailed_analysis': getattr(analysis, 'detailed_analysis', None),
        'tokens_awarded': getattr(analysis, 'tokens_awarded', 0),
        'analysis_performed_at': (
            analysis.analysis_performed_at.isoformat()
            if getattr(analysis, 'analysis_performed_at', None)
            else None
        ),
    }


def pick_keys(payload: Mapping[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    """Return subset of keys present in payload (after transport strip)."""
    cleaned = strip_transport(dict(payload))
    return {key: cleaned[key] for key in keys if key in cleaned}
