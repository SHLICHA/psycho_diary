"""
Handler для команды /start
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from messages import get_message
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message, user, language: str):
    """Обработчик команды /start"""
    try:
        if user.first_name:
            welcome_msg = get_message('welcome_back', language, username=user.first_name)
        else:
            welcome_msg = get_message('welcome', language)
        await message.answer(
            welcome_msg,
            reply_markup=get_main_menu_keyboard(language)
        )
    except Exception as e:
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, language: str):
    """Возврат в главное меню"""
    try:
        main_menu_msg = get_message('main_menu', language)
        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=get_main_menu_keyboard(language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при возврате в главное меню: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))
