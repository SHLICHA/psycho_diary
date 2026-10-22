"""Доставка подтверждения web-password claim в Telegram/MAX."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings

from bot.transports.contracts import NormalizedButton, NormalizedOutput
from bot.transports.unified_send_port import UnifiedSendPort
from messages import get_message
from users.models import WebAccessClaimRequest

logger = logging.getLogger(__name__)


@sync_to_async
def _load_claim(claim_id: int) -> dict[str, Any] | None:
    claim = (
        WebAccessClaimRequest.objects.select_related('user')
        .filter(pk=claim_id)
        .first()
    )
    if claim is None:
        return None
    user = claim.user
    return {
        'claim_id': claim.id,
        'token': claim.confirmation_token,
        'platform': claim.target_platform,
        'telegram_id': user.telegram_id,
        'max_id': user.max_id,
        'language': user.language or 'ru',
    }


async def dispatch_web_access_claim_confirmation(claim: WebAccessClaimRequest) -> dict:
    context = await _load_claim(claim.id)
    if context is None:
        return {'ok': False, 'reason': 'claim_not_found'}

    language = context['language']
    text = get_message('web_access_claim_prompt', language)
    claim_id = context['claim_id']
    output = NormalizedOutput(
        text=text,
        buttons=[
            [
                NormalizedButton(
                    text=get_message('web_access_claim_btn_yes', language),
                    callback_data=f'webclaim:yes:{claim_id}',
                ),
                NormalizedButton(
                    text=get_message('web_access_claim_btn_no', language),
                    callback_data=f'webclaim:no:{claim_id}',
                ),
            ]
        ],
    )
    send_port = UnifiedSendPort()
    platform = context['platform']
    if platform == 'telegram':
        if not context['telegram_id']:
            return {'ok': False, 'reason': 'telegram_id_missing'}
        result = await send_port.send(
            platform='telegram',
            recipient_id=int(context['telegram_id']),
            output=output,
        )
        return {'ok': result.success, 'delivery': 'telegram', 'reason': result.reason}
    if platform == 'max':
        if not context['max_id']:
            return {'ok': False, 'reason': 'max_id_missing'}
        result = await send_port.send(
            platform='max',
            recipient_id=int(context['max_id']),
            output=output,
        )
        return {'ok': result.success, 'delivery': 'max', 'reason': result.reason}
    return {'ok': False, 'reason': 'unknown_platform'}


def build_set_password_url(token: str) -> str:
    base = getattr(settings, 'WEB_APP_URL', 'http://127.0.0.1:8000').rstrip('/')
    return f'{base}/auth/set-password/{token}/'
