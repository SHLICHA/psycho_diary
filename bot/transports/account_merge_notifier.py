"""Notify both Telegram and MAX after successful account merge."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync

from users.models import User

logger = logging.getLogger(__name__)


def notify_accounts_merged(*, survivor_id: int, merge_request_id: int | None = None) -> dict:
    """Sync entry for transaction.on_commit — fan-out в оба канала."""
    try:
        return async_to_sync(_notify_accounts_merged_async)(survivor_id, merge_request_id)
    except Exception:
        logger.exception('notify_accounts_merged failed survivor_id=%s', survivor_id)
        return {'success': False}


async def _notify_accounts_merged_async(survivor_id: int, merge_request_id: int | None) -> dict:
    from bot.utils.message_utils import send_message_to_user_all_channels
    from messages import get_message

    try:
        user = await User.objects.aget(id=survivor_id)
    except User.DoesNotExist:
        return {'success': False, 'reason': 'user_not_found'}

    language = user.language or 'ru'
    text = get_message('merge_accounts_completed', language)
    # bot instance optional for dual-channel helper
    from bot.bot_instance import bot

    ok = await send_message_to_user_all_channels(bot, user, text)
    return {
        'success': ok,
        'survivor_id': survivor_id,
        'merge_request_id': merge_request_id,
    }
