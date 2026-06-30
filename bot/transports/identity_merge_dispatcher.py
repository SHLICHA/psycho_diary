"""Доставка подтверждений merge между каналами Telegram/MAX."""

import logging
from typing import Dict, Any

from django.conf import settings

from bot.transports.contracts import NormalizedButton, NormalizedOutput
from bot.transports.unified_send_port import UnifiedSendPort
from messages import get_message
from users.models import EmailMergeRequest

logger = logging.getLogger(__name__)


async def dispatch_target_merge_confirmation(merge_request: EmailMergeRequest) -> Dict[str, Any]:
    """
    Доставляет запрос подтверждения merge во второй канал.

    На текущем этапе:
    - Telegram доставляется реальным сообщением с inline-кнопками.
    - MAX помечается как deferred до подключения полноценного MAX transport.
    """
    metadata = dict(merge_request.metadata or {})
    target_platform = metadata.get('target_platform')
    target_user = merge_request.target_user

    if not target_platform:
        return {
            'success': True,
            'delivery': 'not_required',
            'reason': 'target_confirmation_not_required',
        }

    send_port = UnifiedSendPort()

    if target_platform == 'telegram':
        if not target_user.telegram_id:
            return {
                'success': False,
                'delivery': 'failed',
                'reason': 'target_telegram_id_missing',
            }

        target_language = target_user.language or 'ru'
        requester_name = merge_request.requester_user.first_name or merge_request.requester_user.username or 'user'
        text = get_message(
            'merge_target_confirmation_prompt',
            target_language,
            requester_platform=(merge_request.source_platform or 'unknown').upper(),
            requester_name=requester_name,
            requester_user_id=merge_request.requester_user_id,
        )
        output = _build_target_confirmation_output(
            merge_request_id=merge_request.id,
            language=target_language,
            text=text,
        )
        result = await send_port.send(
            platform='telegram',
            recipient_id=int(target_user.telegram_id),
            output=output,
        )
        return {
            'success': result.success,
            'delivery': 'telegram',
            'reason': result.reason,
        }

    if target_platform == 'max':
        if not target_user.max_id:
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

        target_language = target_user.language or 'ru'
        requester_name = merge_request.requester_user.first_name or merge_request.requester_user.username or 'user'
        text = get_message(
            'merge_target_confirmation_prompt',
            target_language,
            requester_platform=(merge_request.source_platform or 'unknown').upper(),
            requester_name=requester_name,
            requester_user_id=merge_request.requester_user_id,
        )
        output = _build_target_confirmation_output(
            merge_request_id=merge_request.id,
            language=target_language,
            text=text,
        )
        result = await send_port.send(
            platform='max',
            recipient_id=int(target_user.max_id),
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
