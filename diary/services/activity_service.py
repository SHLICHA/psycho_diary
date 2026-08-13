"""Единая фиксация UserActivity для Telegram / MAX / Web."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from django.utils import timezone

from core.constants import ACTIVITY_TYPES

logger = logging.getLogger(__name__)

VALID_PLATFORMS = frozenset({'telegram', 'max', 'web'})

# Значимые типы (см. ACTIVITY_TRACKING_PLAN.md). Вне списка — не пишем UserActivity.
ACTIVITY_ALLOWLIST = frozenset({
    'entry_created',
    'entry_comment',
    'entry_rate',
    'entry_edit',
    'entry_deleted',
    'day_entry_delete',
    'entry_viewed',
    'analysis_viewed',
    'archive_viewed',
    'task_completed',
    'task_skipped',
    'task_deleted',
    'settings_changed',
    'command',
    'chat',
    'onboarding',
    'show_profile',
    'profile_updated',
    'referral',
    'message_voice',
})

_ACTIVITY_TYPE_KEYS = frozenset(key for key, _ in ACTIVITY_TYPES)

# handled (MAX) → activity_type; None = не писать строку UserActivity.
# touch_only_handled: обновить только last_activity (навигация).
MAX_HANDLED_TO_ACTIVITY: dict[str, str] = {
    'start': 'command',
    'new_entry_process': 'entry_created',
    'first_entry': 'entry_created',
    'rate_analysis': 'entry_rate',
    'comment': 'entry_comment',
    'entry_edit_process': 'entry_edit',
    'confirm_delete_specific_entry': 'entry_deleted',
    'entry_page': 'entry_viewed',
    'entry_pagination': 'entry_viewed',
    'calendar_select_day': 'entry_viewed',
    'archive': 'archive_viewed',
    'calendar_nav': 'archive_viewed',
    'calendar_return_to_month': 'archive_viewed',
    'progress': 'archive_viewed',
    'task_feelings': 'task_completed',
    'skip_task': 'task_skipped',
    'confirm_delete_task': 'task_deleted',
    'set_language': 'settings_changed',
    'set_timezone': 'settings_changed',
    'confirm_timezone': 'onboarding',
    'therapy_message': 'chat',
    'user_profile': 'show_profile',
    'profile_field': 'profile_updated',
    'city_input': 'settings_changed',
}

MAX_TOUCH_ONLY_HANDLED = frozenset({
    'main_menu',
    'help',
    'settings',
    'tasks',
    'tasks_paginate',
    'view_task',
    'complete_task',
    'task_completion',
    'fallback',
    'new_entry',
    'premium',
    'purchase_subscription',
    'purchase_tokens_start',
    'purchase_tokens',
    'feedback_start',
})


def is_allowed_activity_type(activity_type: str) -> bool:
    return activity_type in ACTIVITY_ALLOWLIST and activity_type in _ACTIVITY_TYPE_KEYS


def resolve_max_activity(
    handled: Optional[str],
    *,
    error: Any = None,
    mode: Optional[str] = None,
    referral_applied: bool = False,
) -> tuple[Optional[str], bool]:
    """
    Возвращает (activity_type | None, touch_only).

    touch_only=True → обновить только last_activity без UserActivity.
    """
    if not handled or error:
        return None, False

    if handled == 'rate_analysis' and mode == 'already_rated':
        return None, False

    if handled == 'profile_field' and mode in {'cancel', 'merge_required'}:
        return None, True

    if handled == 'city_input' and mode == 'cancel':
        return None, True

    if handled == 'start' and referral_applied:
        return 'referral', False

    activity_type = MAX_HANDLED_TO_ACTIVITY.get(handled)
    if activity_type:
        return activity_type, False

    if handled in MAX_TOUCH_ONLY_HANDLED:
        return None, True

    return None, False


async def record_user_activity(
    user,
    activity_type: Optional[str] = None,
    *,
    platform: str,
    metadata: Optional[Mapping[str, Any]] = None,
    touch_last_activity: bool = True,
    touch_only: bool = False,
) -> bool:
    """
    Пишет UserActivity (если тип в allowlist) и/или обновляет last_activity.

    Ошибки глотаются — handler не роняется. Возвращает True, если что-то записали.
    """
    if user is None:
        return False

    platform_norm = (platform or '').strip().lower()
    if platform_norm not in VALID_PLATFORMS:
        logger.warning(
            '[activity] invalid platform=%r user_id=%s',
            platform,
            getattr(user, 'id', None),
        )
        platform_norm = 'telegram'

    wrote = False
    try:
        if touch_last_activity or touch_only:
            user.last_activity = timezone.now()
            await user.asave(update_fields=['last_activity'])
            wrote = True

        if touch_only:
            return wrote

        if not activity_type or not is_allowed_activity_type(activity_type):
            if activity_type:
                logger.debug(
                    '[activity] skip type=%s (not in allowlist) user_id=%s',
                    activity_type,
                    getattr(user, 'id', None),
                )
            return wrote

        meta: dict[str, Any] = {'platform': platform_norm}
        if metadata:
            meta.update(dict(metadata))
            meta['platform'] = platform_norm

        from diary.models import UserActivity

        await UserActivity.objects.acreate(
            user=user,
            activity_type=activity_type,
            metadata=meta,
        )
        wrote = True
        logger.debug(
            '[activity] recorded type=%s platform=%s user_id=%s',
            activity_type,
            platform_norm,
            getattr(user, 'id', None),
        )
    except Exception as exc:
        logger.error(
            '[activity] failed type=%s platform=%s user_id=%s: %s',
            activity_type,
            platform_norm,
            getattr(user, 'id', None),
            exc,
            exc_info=True,
        )
    return wrote


async def record_max_dispatch_activity(
    user,
    result: Mapping[str, Any],
    *,
    event_type: Optional[str] = None,
    payload: Optional[str] = None,
) -> bool:
    """Хук после успешного MAX routing: маппинг handled → allowlist."""
    if not result.get('ok', True):
        return False

    handled = result.get('handled')
    if not isinstance(handled, str):
        return False

    activity_type, touch_only = resolve_max_activity(
        handled,
        error=result.get('error'),
        mode=result.get('mode') if isinstance(result.get('mode'), str) else None,
        referral_applied=bool(result.get('referral_applied')),
    )

    if activity_type is None and not touch_only:
        return False

    meta: dict[str, Any] = {
        'handled': handled,
        'event_type': event_type,
    }
    if payload:
        meta['payload'] = payload[:80]
    if result.get('mode') is not None:
        meta['mode'] = result.get('mode')

    return await record_user_activity(
        user,
        activity_type,
        platform='max',
        metadata=meta,
        touch_last_activity=True,
        touch_only=touch_only,
    )
