"""Handlers для двустороннего подтверждения merge Telegram/MAX."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.transports.identity_merge_dispatcher import dispatch_target_merge_confirmation
from messages import get_message
from users.services.email_merge_service import EmailMergeService

router = Router()
logger = logging.getLogger(__name__)


def _extract_merge_request_id(callback_data: str) -> int | None:
    parts = callback_data.split(':')
    if len(parts) != 3:
        return None
    try:
        return int(parts[2])
    except (TypeError, ValueError):
        return None


@router.callback_query(F.data.startswith('merge_requester:'))
async def handle_requester_merge_confirmation(callback: CallbackQuery, user, language: str):
    """Подтверждение или отмена merge инициатором."""
    merge_request_id = _extract_merge_request_id(callback.data or '')
    if merge_request_id is None:
        await callback.answer(get_message('error_generic', language=language), show_alert=True)
        return

    action = (callback.data or '').split(':')[1]

    if action == 'no':
        result = await EmailMergeService.acancel_merge_request_by_id(user, merge_request_id)
        if result.status == 'cancelled':
            await callback.message.edit_text(get_message('merge_request_cancelled', language=language))
            await callback.answer()
            return
        await callback.answer(get_message('error_generic', language=language), show_alert=True)
        return

    if action != 'yes':
        await callback.answer(get_message('error_generic', language=language), show_alert=True)
        return

    result = await EmailMergeService.aconfirm_merge_request_by_id(user, merge_request_id)

    if result.status == 'confirmed':
        await callback.message.edit_text(get_message('merge_request_confirmed', language=language))
        await callback.answer()
        return

    if result.status == 'pending_target_confirmation' and result.merge_request is not None:
        delivery_result = await dispatch_target_merge_confirmation(result.merge_request)
        if delivery_result.get('success'):
            await callback.message.edit_text(get_message('merge_target_confirmation_sent', language=language))
            await callback.answer()
            return

        if delivery_result.get('delivery') == 'max_deferred':
            await callback.message.edit_text(get_message('merge_target_confirmation_deferred_max', language=language))
            await callback.answer()
            return

    await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.callback_query(F.data.startswith('merge_target:'))
async def handle_target_merge_confirmation(callback: CallbackQuery, user, language: str):
    """Подтверждение или отклонение merge во втором канале (Telegram)."""
    merge_request_id = _extract_merge_request_id(callback.data or '')
    if merge_request_id is None:
        await callback.answer(get_message('error_generic', language=language), show_alert=True)
        return

    action = (callback.data or '').split(':')[1]
    approve = action == 'yes'

    result = await EmailMergeService.aconfirm_target_transport_by_request_id(
        target_user=user,
        merge_request_id=merge_request_id,
        approve=approve,
    )

    if result.status == 'rejected':
        await callback.message.edit_text(get_message('merge_target_rejected', language=language))
        await callback.answer()
        return

    if result.status == 'pending_requester_confirmation':
        await callback.message.edit_text(get_message('merge_target_approved_wait_requester', language=language))
        await callback.answer()
        return

    if result.status == 'confirmed':
        await callback.message.edit_text(get_message('merge_request_confirmed', language=language))
        await callback.answer()
        return

    if result.code == 'target_confirmation_expired':
        await callback.message.edit_text(get_message('merge_request_expired', language=language))
        await callback.answer()
        return

    await callback.answer(get_message('error_generic', language=language), show_alert=True)
