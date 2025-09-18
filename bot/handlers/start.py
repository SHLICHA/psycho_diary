"""
Handler для команды /start
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states.onboarding_states import OnboardingStates
from messages import get_message
from bot.keyboards import (
    get_main_menu_keyboard,
    get_instruction_keyboard
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message, user, language: str, state: FSMContext): # Добавлен state
    """Обработчик команды /start"""
    try:
        # --- НОВАЯ ЛОГИКА: Проверка согласия ---
        if not getattr(user, 'has_agreed_to_terms', False):
            logger.info(f"Пользователь {user.telegram_id} еще не дал согласие. Запуск онбординга.")
            
            # Отправляем приветствие
            welcome_msg = get_message('onboarding_welcome', language)
            await message.answer(welcome_msg)
            
            # Отправляем инструкцию и устанавливаем состояние
            instruction_msg = get_message('onboarding_instruction', language)
            await state.set_state(OnboardingStates.showing_instruction) # Устанавливаем состояние
            await message.answer(instruction_msg, reply_markup=get_instruction_keyboard(language))
            
        else:
            # Пользователь дал согласие, показываем обычное меню
            if user.first_name:
                welcome_msg = get_message('welcome_back', language, username=user.first_name)
            else:
                welcome_msg = get_message('welcome', language)
            await message.answer(
                welcome_msg,
                reply_markup=get_main_menu_keyboard(language, user)
            )
    except Exception as e:
        logger.error(f"Ошибка в cmd_start для пользователя {user.id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, language: str):
    """Возврат в главное меню"""
    logger.info("Обработчик main_menu вызван!")
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
