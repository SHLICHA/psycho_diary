"""Inbound processing for MAX transport events and merge callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

from users.models import User
from users.services.email_merge_service import EmailMergeService


SUPPORTED_CALLBACK_ACTIONS = {'yes', 'no'}
SUPPORTED_UPDATE_TYPES = {'message_created', 'bot_started', 'message_callback'}


@dataclass(frozen=True)
class MaxNormalizedEvent:
    event_type: str
    raw_update_type: str
    user_id: int | None
    chat_id: int | None
    text: str | None
    payload: str | None
    update: dict[str, Any]


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_user_chat_text_payload(update: dict[str, Any]) -> tuple[int | None, int | None, str | None, str | None]:
    callback = update.get('callback') or update.get('message_callback') or {}
    message = update.get('message') or {}
    source = update.get('source') or {}

    user_id = (
        ((callback.get('sender') or {}).get('user_id'))
        or ((message.get('sender') or {}).get('user_id'))
        or source.get('user_id')
        or message.get('from_id')
        or update.get('from_id')
    )

    chat_id = (
        ((message.get('recipient') or {}).get('chat_id'))
        or message.get('chat_id')
        or source.get('chat_id')
        or update.get('chat_id')
    )

    text = (
        ((message.get('body') or {}).get('text'))
        or message.get('text')
        or ((update.get('body') or {}).get('text'))
    )

    payload = callback.get('payload') or update.get('payload')
    if payload is None:
        payload = text

    if isinstance(payload, dict):
        payload = payload.get('action') or payload.get('payload')

    if text is not None:
        text = str(text)
    if payload is not None:
        payload = str(payload)

    return _to_int(user_id), _to_int(chat_id), text, payload


def extract_message_callback_payload(update: dict[str, Any]) -> tuple[int | None, str | None]:
    """Backward-compatible extractor returning only (user_id, payload)."""
    user_id, _chat_id, _text, payload = _extract_user_chat_text_payload(update)
    return user_id, payload


def normalize_update(update: dict[str, Any]) -> MaxNormalizedEvent | None:
    """Normalize webhook/polling payload into unified internal event model."""
    raw_update_type = (update.get('update_type') or update.get('type') or '').lower()
    if raw_update_type not in SUPPORTED_UPDATE_TYPES:
        return None

    user_id, chat_id, text, payload = _extract_user_chat_text_payload(update)

    return MaxNormalizedEvent(
        event_type=raw_update_type,
        raw_update_type=raw_update_type,
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        payload=payload,
        update=update,
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
    """Process normalized MAX update and apply supported handlers."""
    event = normalize_update(update)
    if event is None:
        return {'ok': True, 'ignored': True}

    if event.event_type in {'message_created', 'bot_started'}:
        return {'ok': True, 'ignored': True}

    parsed = parse_merge_target_callback(event)
    if parsed is None:
        return {'ok': True, 'ignored': True}

    user_id, action, merge_request_id = parsed
    target_user = User.objects.filter(max_id=user_id).first()
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


async def aprocess_max_update(update: dict[str, Any]) -> dict[str, Any]:
    """Async wrapper for process_max_update."""
    return await sync_to_async(process_max_update)(update)


# Backward-compatible aliases for existing call sites/tests.
process_merge_target_callback = process_max_update
aprocess_merge_target_callback = aprocess_max_update
