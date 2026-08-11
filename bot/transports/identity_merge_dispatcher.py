"""Доставка подтверждений merge между каналами Telegram/MAX."""

from __future__ import annotations

import logging
from typing import Any, Dict

from asgiref.sync import sync_to_async
from django.conf import settings

from bot.transports.contracts import NormalizedButton, NormalizedOutput
from bot.transports.unified_send_port import UnifiedSendPort
from messages import get_message
from users.models import EmailMergeRequest, User

logger = logging.getLogger(__name__)


@sync_to_async
def _load_merge_dispatch_context(merge_request_id: int) -> dict[str, Any] | None:
    """Синхронно подгружает merge_request + target/requester для async dispatch."""
    merge_request = (
        EmailMergeRequest.objects.select_related('target_user', 'requester_user')
        .filter(pk=merge_request_id)
        .first()
    )
    if merge_request is None:
        return None

    target_user: User = merge_request.target_user
    requester_user: User = merge_request.requester_user
    metadata = dict(merge_request.metadata or {})
    return {
        'merge_request_id': merge_request.id,
        'source_platform': merge_request.source_platform or 'unknown',
        'requester_user_id': merge_request.requester_user_id,
        'target_platform': metadata.get('target_platform'),
        'target_telegram_id': target_user.telegram_id,
        'target_max_id': target_user.max_id,
        'target_language': target_user.language or 'ru',
        'requester_name': requester_user.first_name or requester_user.username or 'user',
    }


async def dispatch_target_merge_confirmation(merge_request: EmailMergeRequest) -> Dict[str, Any]:
    """
    Доставляет запрос подтверждения merge во второй канал.

    ORM-доступ выполняется через sync_to_async (вызов из MAX/TG async handlers).
    """
    context = await _load_merge_dispatch_context(merge_request.id)
    if context is None:
        return {
            'success': False,
            'delivery': 'failed',
            'reason': 'merge_request_not_found',
        }

    target_platform = context['target_platform']
    if not target_platform:
        return {
            'success': True,
            'delivery': 'not_required',
            'reason': 'target_confirmation_not_required',
        }

    send_port = UnifiedSendPort()
    text = get_message(
        'merge_target_confirmation_prompt',
        context['target_language'],
        requester_platform=str(context['source_platform']).upper(),
        requester_name=context['requester_name'],
        requester_user_id=context['requester_user_id'],
    )
    output = _build_target_confirmation_output(
        merge_request_id=context['merge_request_id'],
        language=context['target_language'],
        text=text,
    )

    if target_platform == 'telegram':
        if not context['target_telegram_id']:
            return {
                'success': False,
                'delivery': 'failed',
                'reason': 'target_telegram_id_missing',
            }
        result = await send_port.send(
            platform='telegram',
            recipient_id=int(context['target_telegram_id']),
            output=output,
        )
        return {
            'success': result.success,
            'delivery': 'telegram',
            'reason': result.reason,
        }

    if target_platform == 'max':
        if not context['target_max_id']:
            return {
                'success': False,
                'delivery': 'failed',
                'reason': 'target_max_id_missing',
            }

        if not getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
            return {
                'success': False,
                'delivery': 'max_deferred',
                'reason': 'max_transport_disabled',
            }

        result = await send_port.send(
            platform='max',
            recipient_id=int(context['target_max_id']),
            output=output,
        )
        return {
            'success': result.success,
            'delivery': 'max',
            'reason': result.reason,
        }

    return {
        'success': False,
        'delivery': 'failed',
        'reason': f'unsupported_target_platform:{target_platform}',
    }


def _build_target_confirmation_output(merge_request_id: int, language: str, text: str) -> NormalizedOutput:
    yes_text = get_message('merge_btn_yes', language)
    no_text = get_message('merge_btn_no', language)
    return NormalizedOutput(
        text=text,
        buttons=[
            [
                NormalizedButton(text=yes_text, callback_data=f'merge_target:yes:{merge_request_id}'),
                NormalizedButton(text=no_text, callback_data=f'merge_target:no:{merge_request_id}'),
            ]
        ],
    )
