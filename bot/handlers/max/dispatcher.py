"""MAX Wave 1 dispatcher: normalize → merge | product handlers."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings

from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.messages import route_text_message
from bot.handlers.max.send_adapter import build_send_func
from bot.transports.max.client import MaxClient
from bot.transports.max.inbound import (
    MaxNormalizedEvent,
    normalize_update,
    parse_merge_target_callback,
)
from diary.services.user_service import get_or_create_user_by_max_id
from users.models import User
from users.services.email_merge_service import EmailMergeService

logger = logging.getLogger(__name__)


def _process_merge_sync(event: MaxNormalizedEvent) -> dict[str, Any] | None:
    parsed = parse_merge_target_callback(event)
    if parsed is None:
        return None

    user_id, action, merge_request_id = parsed
    target_user = User.objects.filter(max_id=user_id).first()
    if target_user is None:
        return {'ok': True, 'ignored': True, 'reason': 'merge_target_missing'}

    result = EmailMergeService.confirm_target_transport_by_request_id(
        target_user=target_user,
        merge_request_id=merge_request_id,
        approve=(action == 'yes'),
    )
    return {
        'ok': True,
        'handled': 'merge_target',
        'status': result.status,
        'code': result.code,
    }


async def dispatch_max_update(update: dict[str, Any]) -> dict[str, Any]:
    """
    Async entry for webhook/polling.
    Merge callbacks stay first; otherwise Wave 1 product routing.
    """
    event = normalize_update(update)
    if event is None:
        return {'ok': True, 'ignored': True, 'reason': 'unsupported_update'}

    merge_result = await sync_to_async(_process_merge_sync)(event)
    if merge_result is not None:
        return merge_result

    if not event.user_id:
        return {'ok': True, 'ignored': True, 'reason': 'missing_user_id'}

    if not getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
        return {'ok': True, 'ignored': True, 'reason': 'transport_disabled'}

    max_client = MaxClient(
        api_token=getattr(settings, 'MAX_BOT_TOKEN', ''),
        base_url=getattr(settings, 'MAX_API_BASE_URL', 'https://platform-api2.max.ru'),
        timeout_seconds=getattr(settings, 'MAX_API_TIMEOUT_SECONDS', 10),
        rate_limit_rps=getattr(settings, 'MAX_RATE_LIMIT_RPS', 10),
        rate_limit_burst=getattr(settings, 'MAX_RATE_LIMIT_BURST', 50),
        max_message_length=getattr(settings, 'MAX_MESSAGE_MAX_LENGTH', 3500),
    )
    try:
        user, _created = await get_or_create_user_by_max_id(event.user_id)
        if user is None:
            return {'ok': False, 'error': 'user_resolve_failed'}

        send_func = build_send_func(
            max_client,
            max_id=event.user_id,
            chat_id=event.chat_id,
        )

        if event.event_type in {'message_created', 'bot_started'}:
            return await route_text_message(
                user,
                event.text or '',
                send_func,
                max_id=event.user_id,
                media=event.media,
                max_client=max_client,
            )

        if event.event_type == 'message_callback':
            return await route_callback(
                user,
                event.payload or '',
                send_func,
                max_id=event.user_id,
                max_client=max_client,
            )

        return {'ok': True, 'ignored': True, 'reason': 'unhandled_event_type'}
    except Exception as exc:
        logger.error('[MAX dispatch] failed: %s', exc, exc_info=True)
        return {'ok': False, 'error': 'dispatch_exception', 'detail': str(exc)}
    finally:
        close_result = max_client.close()
        if hasattr(close_result, '__await__'):
            await close_result
