"""Inbound processing for MAX transport events and merge callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asgiref.sync import async_to_sync, sync_to_async

from users.models import User
from users.services.email_merge_service import EmailMergeService


SUPPORTED_CALLBACK_ACTIONS = {'yes', 'no'}
SUPPORTED_UPDATE_TYPES = {'message_created', 'bot_started', 'message_callback'}
MEDIA_KIND_PRIORITY = ('audio', 'image', 'file', 'video')


@dataclass(frozen=True)
class MaxMediaInfo:
    """Normalized inbound media attachment from MAX message."""

    kind: str  # audio | image | file | video
    url: str | None = None
    token: str | None = None
    file_id: str | None = None
    filename: str | None = None
    duration: int | None = None
    content_type: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class MaxNormalizedEvent:
    event_type: str
    raw_update_type: str
    user_id: int | None
    chat_id: int | None
    text: str | None
    payload: str | None
    update: dict[str, Any]
    media: MaxMediaInfo | None = None
    callback_id: str | None = None


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_media_kind(raw_type: str) -> str | None:
    kind = (raw_type or '').strip().lower()
    if kind in {'audio', 'voice'}:
        return 'audio'
    if kind in {'image', 'photo', 'picture'}:
        return 'image'
    if kind in {'file', 'document'}:
        return 'file'
    if kind == 'video':
        return 'video'
    return None


def extract_media_from_message(message: dict[str, Any] | None) -> MaxMediaInfo | None:
    """Pick the highest-priority media attachment from a MAX message body."""
    if not isinstance(message, dict):
        return None
    body = message.get('body') if isinstance(message.get('body'), dict) else message
    attachments = body.get('attachments') if isinstance(body, dict) else None
    if not isinstance(attachments, list) or not attachments:
        return None

    scored: list[tuple[int, MaxMediaInfo]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        kind = _normalize_media_kind(str(item.get('type') or ''))
        if kind is None:
            continue
        payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        url = payload.get('url') or item.get('url')
        token = payload.get('token') or item.get('token')
        file_id = (
            payload.get('id')
            or payload.get('file_id')
            or item.get('id')
            or item.get('file_id')
        )
        filename = payload.get('filename') or item.get('filename') or payload.get('name')
        duration = _to_int(payload.get('duration') or item.get('duration'))
        size = _to_int(payload.get('size') or item.get('size') or payload.get('file_size'))
        content_type = (
            payload.get('content_type')
            or item.get('content_type')
            or payload.get('mime_type')
        )
        if not url and not token:
            continue
        media = MaxMediaInfo(
            kind=kind,
            url=str(url) if url else None,
            token=str(token) if token else None,
            file_id=str(file_id) if file_id is not None else None,
            filename=str(filename) if filename else None,
            duration=duration,
            content_type=str(content_type) if content_type else None,
            size=size,
        )
        try:
            priority = MEDIA_KIND_PRIORITY.index(kind)
        except ValueError:
            priority = len(MEDIA_KIND_PRIORITY)
        scored.append((priority, media))

    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0])
    return scored[0][1]


def _extract_user_chat_text_payload(
    update: dict[str, Any],
) -> tuple[int | None, int | None, str | None, str | None, MaxMediaInfo | None, str | None]:
    callback = update.get('callback') or update.get('message_callback') or {}
    if not isinstance(callback, dict):
        callback = {}
    message = update.get('message') or {}
    if not isinstance(message, dict):
        message = {}
    source = update.get('source') or {}
    if not isinstance(source, dict):
        source = {}

    callback_user = callback.get('user') or callback.get('sender') or {}
    if not isinstance(callback_user, dict):
        callback_user = {}
    update_user = update.get('user') or source.get('user') or {}
    if not isinstance(update_user, dict):
        update_user = {}
    message_sender = message.get('sender') or {}
    if not isinstance(message_sender, dict):
        message_sender = {}
    recipient = message.get('recipient') or {}
    if not isinstance(recipient, dict):
        recipient = {}

    raw_update_type = (update.get('update_type') or update.get('type') or '').lower()
    is_callback = raw_update_type in {'message_callback', 'message_event'}

    if is_callback:
        # У callback message.sender часто сам бот (автор сообщения с кнопкой).
        # Берём пользователя, который нажал кнопку.
        user_id = (
            callback_user.get('user_id')
            or callback_user.get('id')
            or update_user.get('user_id')
            or update_user.get('id')
            or source.get('user_id')
            or update.get('user_id')
            or recipient.get('user_id')
            or recipient.get('id')
            or callback.get('user_id')
        )
    else:
        user_id = (
            update_user.get('user_id')
            or update_user.get('id')
            or message_sender.get('user_id')
            or message_sender.get('id')
            or source.get('user_id')
            or message.get('from_id')
            or message.get('user_id')
            or update.get('from_id')
            or update.get('user_id')
        )

    chat_id = (
        update.get('chat_id')
        or source.get('chat_id')
        or recipient.get('chat_id')
        or message.get('chat_id')
        or ((message.get('chat') or {}).get('chat_id') if isinstance(message.get('chat'), dict) else None)
        or ((message.get('chat') or {}).get('id') if isinstance(message.get('chat'), dict) else None)
    )

    text = (
        ((message.get('body') or {}).get('text') if isinstance(message.get('body'), dict) else None)
        or message.get('text')
        or ((update.get('body') or {}).get('text') if isinstance(update.get('body'), dict) else None)
    )

    payload = callback.get('payload')
    if payload is None:
        payload = callback.get('data')
    if payload is None:
        payload = update.get('payload')
    if payload is None and not is_callback:
        payload = text

    if isinstance(payload, dict):
        payload = payload.get('action') or payload.get('payload') or payload.get('data')

    if text is not None:
        text = str(text)
    if payload is not None:
        payload = str(payload)

    media = extract_media_from_message(message if isinstance(message, dict) else None)

    callback_id_raw = (
        callback.get('callback_id')
        or callback.get('id')
        or update.get('callback_id')
    )
    callback_id = str(callback_id_raw).strip() if callback_id_raw else None
    if callback_id == '':
        callback_id = None

    return _to_int(user_id), _to_int(chat_id), text, payload, media, callback_id


def extract_message_callback_payload(update: dict[str, Any]) -> tuple[int | None, str | None]:
    """Backward-compatible extractor returning only (user_id, payload)."""
    user_id, _chat_id, _text, payload, _media, _callback_id = _extract_user_chat_text_payload(update)
    return user_id, payload


def normalize_update(update: dict[str, Any]) -> MaxNormalizedEvent | None:
    """Normalize webhook/polling payload into unified internal event model."""
    raw_update_type = (update.get('update_type') or update.get('type') or '').lower()
    if raw_update_type not in SUPPORTED_UPDATE_TYPES:
        return None

    user_id, chat_id, text, payload, media, callback_id = _extract_user_chat_text_payload(update)

    return MaxNormalizedEvent(
        event_type=raw_update_type,
        raw_update_type=raw_update_type,
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        payload=payload,
        update=update,
        media=media,
        callback_id=callback_id,
    )


def parse_merge_target_callback(event_or_update: MaxNormalizedEvent | dict[str, Any]) -> tuple[int, str, int] | None:
    """Parse callback payload merge_target:yes|no:{request_id}."""
    event: MaxNormalizedEvent | None
    if isinstance(event_or_update, dict):
        event = normalize_update(event_or_update)
    else:
        event = event_or_update

    if event is None:
        return None

    if event.event_type != 'message_callback':
        return None

    if not event.user_id or not event.payload or not event.payload.startswith('merge_target:'):
        return None

    parts = event.payload.split(':', 2)
    if len(parts) != 3:
        return None

    action = parts[1]
    if action not in SUPPORTED_CALLBACK_ACTIONS:
        return None

    try:
        merge_request_id = int(parts[2])
    except (TypeError, ValueError):
        return None

    return event.user_id, action, merge_request_id


def process_max_update(update: dict[str, Any]) -> dict[str, Any]:
    """
    Sync entry (webhook view / legacy tests).
    Delegates to async Wave 1 dispatcher when transport is enabled.
    Merge-only path kept for environments without full dispatch.
    """
    from django.conf import settings

    # Prefer full async dispatcher (Wave 1+) when MAX transport is on.
    if getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
        from bot.handlers.max.dispatcher import dispatch_max_update

        return async_to_sync(dispatch_max_update)(update)

    # Legacy merge-only behavior (tests / transport off).
    event = normalize_update(update)
    if event is None:
        return {'ok': True, 'ignored': True}

    if event.event_type in {'message_created', 'bot_started'}:
        return {'ok': True, 'ignored': True}

    parsed = parse_merge_target_callback(event)
    if parsed is None:
        return {'ok': True, 'ignored': True}

    user_id, action, merge_request_id = parsed
    try:
        target_user = User.objects.get(max_id=user_id)
    except User.DoesNotExist:
        return {'ok': True, 'ignored': True}
    except User.MultipleObjectsReturned:
        target_user = (
            User.objects.filter(max_id=user_id)
            .order_by('-last_activity', '-created_at', '-id')
            .first()
        )
        if target_user is None:
            return {'ok': True, 'ignored': True}

    result = EmailMergeService.confirm_target_transport_by_request_id(
        target_user=target_user,
        merge_request_id=merge_request_id,
        approve=(action == 'yes'),
    )
    return {
        'ok': True,
        'status': result.status,
        'code': result.code,
    }


async def aprocess_max_update(
    update: dict[str, Any],
    *,
    max_client=None,
    callback_already_answered: bool = False,
) -> dict[str, Any]:
    """Async wrapper — always uses Wave 1 dispatcher when available."""
    from django.conf import settings

    if getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
        from bot.handlers.max.dispatcher import dispatch_max_update

        return await dispatch_max_update(
            update,
            max_client=max_client,
            callback_already_answered=callback_already_answered,
        )

    return await sync_to_async(process_max_update)(update)


# Backward-compatible aliases for existing call sites/tests.
process_merge_target_callback = process_max_update
aprocess_merge_target_callback = aprocess_max_update
