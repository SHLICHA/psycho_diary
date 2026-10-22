"""Telegram callbacks: подтверждение задания web-пароля."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from django.conf import settings

from bot.transports.web_access_claim_dispatcher import build_set_password_url
from messages import get_message
from users.services.web_access_claim_service import WebAccessClaimError, WebAccessClaimService

router = Router()
logger = logging.getLogger(__name__)


def _parse_claim_callback(data: str) -> tuple[str | None, int | None]:
    parts = (data or '').split(':')
    if len(parts) != 3 or parts[0] != 'webclaim':
        return None, None
    try:
        return parts[1], int(parts[2])
    except (TypeError, ValueError):
        return None, None


@router.callback_query(F.data.startswith('webclaim:'))
async def handle_web_access_claim(callback: CallbackQuery, user, language: str):
    action, claim_id = _parse_claim_callback(callback.data or '')
    if action is None or claim_id is None:
        await callback.answer(get_message('error_generic', language), show_alert=True)
        return
    try:
        result = await WebAccessClaimService.aconfirm_from_bot(
            actor_user=user,
            claim_id=claim_id,
            approve=(action == 'yes'),
        )
    except WebAccessClaimError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    except Exception:
        logger.exception('webclaim callback failed')
        await callback.answer(get_message('error_generic', language), show_alert=True)
        return

    if result.status == 'cancelled':
        text = get_message('web_access_claim_cancelled', language)
        await callback.message.edit_text(text)
        await callback.answer()
        return

    if result.status == 'confirmed' and result.set_password_token:
        url = build_set_password_url(result.set_password_token)
        text = get_message('web_access_claim_confirmed', language, set_password_url=url)
        await callback.message.edit_text(text)
        await callback.answer()
        return

    await callback.answer(get_message('error_generic', language), show_alert=True)
