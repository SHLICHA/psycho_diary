"""MAX Wave 1 dispatcher: normalize → merge | product handlers."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings

from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.commands import handle_start
from bot.handlers.max.messages import route_text_message
from bot.handlers.max.send_adapter import build_send_func
from bot.middlewares.user_middleware import resolve_referrer_user_from_payload
from bot.transports.max.client import MaxClient
from bot.transports.max.inbound import (
    MaxNormalizedEvent,
    normalize_update,
    parse_merge_target_callback,
)
from diary.services.user_service import award_referral_bonus, get_or_create_user_by_max_id
from users.models import User
from users.services.email_merge_service import EmailMergeService

logger = logging.getLogger(__name__)


def _process_merge_sync(event: MaxNormalizedEvent) -> dict[str, Any] | None:
    parsed = parse_merge_target_callback(event)
    if parsed is None:
        return None

    user_id, action, merge_request_id = parsed
    try:
        target_user = User.objects.get(max_id=user_id)
    except User.DoesNotExist:
        return {'ok': True, 'ignored': True, 'reason': 'merge_target_missing'}
    except User.MultipleObjectsReturned:
        logger.error('[MAX merge] multiple users for max_id=%s', user_id)
        target_user = (
            User.objects.filter(max_id=user_id)
            .order_by('-last_activity', '-created_at', '-id')
            .first()
        )
        if target_user is None:
            return {'ok': True, 'ignored': True, 'reason': 'merge_target_missing'}

    result = EmailMergeService.confirm_target_transport_by_request_id(
        target_user=target_user,
        merge_request_id=merge_request_id,
        approve=(action == 'yes'),
    )
    language = target_user.language or 'ru'
    from users.services.email_merge_service import build_target_merge_result_view

    view = build_target_merge_result_view(result, language)
    return {
        'ok': True,
        'handled': 'merge_target',
        'status': result.status,
        'code': result.code,
        'view_text': view.get('text') or view.get('alert_text') or 'Готово',
        'view_success': bool(view.get('success')),
    }


def _build_max_client() -> MaxClient:
    return MaxClient(
        api_token=getattr(settings, 'MAX_BOT_TOKEN', ''),
        base_url=getattr(settings, 'MAX_API_BASE_URL', 'https://platform-api2.max.ru'),
        timeout_seconds=getattr(settings, 'MAX_API_TIMEOUT_SECONDS', 10),
        rate_limit_rps=getattr(settings, 'MAX_RATE_LIMIT_RPS', 10),
        rate_limit_burst=getattr(settings, 'MAX_RATE_LIMIT_BURST', 50),
        max_message_length=getattr(settings, 'MAX_MESSAGE_MAX_LENGTH', 3500),
    )


async def dispatch_max_update(
    update: dict[str, Any],
    *,
    max_client: MaxClient | None = None,
    callback_already_answered: bool = False,
) -> dict[str, Any]:
    """
    Async entry for webhook/polling.

    Важно: для message_callback единственный корректный способ снять ошибку
    на кнопке в клиенте MAX — POST /answers с полем message (правка исходного
    сообщения). Чистый notification «сжигает» callback, но UI ошибки может
    остаться. Поэтому ответ с message делает send_func при первом send.
    """
    event = normalize_update(update)
    if event is None:
        return {'ok': True, 'ignored': True, 'reason': 'unsupported_update'}

    logger.info(
        '[MAX dispatch] type=%s user_id=%s chat_id=%s payload=%s callback_id=%s',
        event.event_type,
        event.user_id,
        event.chat_id,
        (event.payload or '')[:80],
        (event.callback_id or '')[:40] or None,
    )

    merge_result = await sync_to_async(_process_merge_sync)(event)
    if merge_result is not None:
        if (
            event.callback_id
            and not callback_already_answered
            and getattr(settings, 'MAX_TRANSPORT_ENABLED', False)
        ):
            owned = max_client is None
            client = max_client or _build_max_client()
            try:
                message_text = merge_result.get('view_text') or 'Готово'
                await client.answer_callback(
                    callback_id=event.callback_id,
                    notification='✓' if merge_result.get('view_success', True) else '!',
                    message={'text': message_text},
                )
            finally:
                if owned:
                    await client.close()
        return merge_result

    if not event.user_id:
        logger.warning('[MAX dispatch] missing user_id for type=%s', event.event_type)
        return {'ok': True, 'ignored': True, 'reason': 'missing_user_id'}

    if not getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
        return {'ok': True, 'ignored': True, 'reason': 'transport_disabled'}

    owns_client = max_client is None
    client = max_client or _build_max_client()
    callback_answered = callback_already_answered
    try:
        referrer_user = None
        if event.event_type == 'bot_started' and event.payload:
            referrer_user = await resolve_referrer_user_from_payload(
                event.payload,
                current_max_id=event.user_id,
            )

        user, was_created, invited_set = await get_or_create_user_by_max_id(
            event.user_id,
            referrer_user=referrer_user,
        )
        if user is None:
            return {'ok': False, 'error': 'user_resolve_failed'}

        if was_created and invited_set and referrer_user is not None:
            bonus_ok = await award_referral_bonus(referrer_user, user)
            logger.info(
                '[MAX dispatch] referral bonus awarded=%s referrer=%s invitee_max=%s',
                bonus_ok,
                referrer_user.id,
                event.user_id,
            )

        send_func = build_send_func(
            client,
            max_id=event.user_id,
            chat_id=event.chat_id,
            callback_id=(
                event.callback_id
                if event.event_type == 'message_callback' and not callback_answered
                else None
            ),
        )

        result: dict[str, Any]
        if event.event_type == 'bot_started':
            # Deep-link start: payload уже обработан; показываем обычный /start.
            result = await handle_start(user, send_func, max_id=event.user_id)
            result = {**result, 'referral_applied': bool(invited_set)}
        elif event.event_type == 'message_created':
            result = await route_text_message(
                user,
                event.text or '',
                send_func,
                max_id=event.user_id,
                media=event.media,
                max_client=client,
            )
        elif event.event_type == 'message_callback':
            result = await route_callback(
                user,
                event.payload or '',
                send_func,
                max_id=event.user_id,
                max_client=client,
                callback_id=event.callback_id,
            )
            answered_via_send = False
            was_answered = getattr(send_func, 'was_callback_answered', None)
            if callable(was_answered):
                answered_via_send = bool(was_answered())
            callback_answered = callback_answered or answered_via_send

            # Если handler ничего не отправил — закрываем кнопку notification-only.
            if event.callback_id and not callback_answered:
                callback_answered = await client.answer_callback(
                    callback_id=event.callback_id,
                    notification='✓',
                )
            result = {**result, 'callback_answered': callback_answered}
        else:
            result = {'ok': True, 'ignored': True, 'reason': 'unhandled_event_type'}

        try:
            from diary.services.activity_service import record_max_dispatch_activity

            await record_max_dispatch_activity(
                user,
                result,
                event_type=event.event_type,
                payload=event.payload or event.text,
            )
        except Exception:
            logger.exception('[MAX dispatch] activity record failed')

        return result
    except Exception as exc:
        logger.error('[MAX dispatch] failed: %s', exc, exc_info=True)
        if event.callback_id and not callback_answered:
            try:
                await client.answer_callback(
                    callback_id=event.callback_id,
                    notification='Произошла ошибка, попробуйте ещё раз',
                )
            except Exception:
                logger.exception('[MAX dispatch] answer_callback after error failed')
        return {'ok': False, 'error': 'dispatch_exception', 'detail': str(exc)}
    finally:
        if owns_client:
            close_result = client.close()
            if hasattr(close_result, '__await__'):
                await close_result
