"""
Fallback handler для необработанных текстовых и голосовых сообщений.
Срабатывает только если сообщение не попало ни под один другой хендлер.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, ContentType

from messages import get_message
from bot.keyboards.main_menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="Fallback_router")

@router.message(F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def handle_unexpected_message(message: Message, user, language: str):
    """
    Ловит все текстовые и голосовые сообщения, которые приходят вне какого-либо FSM-состояния
    и не обрабатываются другими хендлерами.
    """
    logger.debug(f"Получено необработанное сообщение от пользователя {user.telegram_id}: {message.text[:50] if message.text else 'голосовое'}")

    if message.content_type == ContentType.VOICE:
        help_text = get_message('unexpected_voice_message', language)
    else:
        help_text = get_message('unexpected_text_message', language)

    await message.answer(
        help_text,
        reply_markup=await get_main_menu_keyboard(language, user)
    )