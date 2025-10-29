# /home/shlicha/psycho_diary/bot/handlers/start.py
"""
Handler для команды /start
"""

import logging
# import pytz # УБРАНО, так как логика работы с TZ перенесена в сервисы

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
# from asgiref.sync import sync_to_async # УБРАНО, так как сервисы сами обрабатывают асинхронность
# from django.utils import timezone # УБРАНО, так как логика работы с TZ перенесена в сервисы

from bot.states.onboarding_states import OnboardingStates
from messages import get_message
from bot.decorators.analytics_decorator import log_user_activity
from bot.keyboards import (
    get_main_menu_keyboard, # Может понадобиться напрямую, если сервис не возвращает её
    get_agreement_keyboard_for_first_entry
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
# from bot.utils.diary_utils import get_user_streaks, get_recoverable_gap_info # УБРАНО, логика перенесена в main_menu_service
# from diary.models import DiaryEntry # УБРАНО, логика проверки записей может остаться здесь или перейти в user_service

# ИМПОРТИРУЕМ НОВЫЕ СЕРВИСЫ
from diary.services.main_menu_service import build_main_menu_data
# from diary.services.user_service import ... # Если потребуются специфичные функции

router = Router()
logger = logging.getLogger(__name__)

# --- УБРАНО: async def build_main_menu_message(user, language: str): ---

@router.message(Command("start"))
@log_user_activity('command', metadata_extra={'context': '/start'})
async def cmd_start(message: Message, user, language: str, state: FSMContext, data: dict = None, **kwargs):
    """
    Обработчик команды /start
    Проверяет, был ли пользователь разблокирован при взаимодействии (через middleware).
    Если да - отправляет специальное приветствие.
    Затем показывает новый онбординг (соглашение -> первая запись -> часовой пояс -> главное меню) 
    или главное меню в зависимости от согласия.
    """
    try:
        await state_manager.clear_state(state)
        was_reactivated = kwargs.get('was_blocked_and_reactivated', False)
        logger.debug(f"[cmd_start] was_reactivated из kwargs: {was_reactivated}")

        # Если пользователь был разблокирован, отправляем специальное приветствие
        if was_reactivated:
            reactivation_msg = get_message(
                'welcome_back_reactivated',
                language,
                first_name=user.first_name or user.username or get_message('user_default_name', language)
            )
            await message.answer(reactivation_msg)

        # Проверка согласия с условиями
        if not getattr(user, 'has_agreed_to_terms', False):
            welcome_msg = get_message('onboarding_welcome_extended_first_entry', language)
            await state.set_state(OnboardingStates.show_agreement_for_first_entry)
            await message.answer(
                welcome_msg,
                reply_markup=get_agreement_keyboard_for_first_entry(language)
                )
            return 

        # Если согласие дано, показываем главное меню
        # --- ВЫЗОВ СЕРВИСА ДЛЯ ПОЛУЧЕНИЯ ДАННЫХ ГЛАВНОГО МЕНЮ ---
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        keyboard = menu_data['keyboard']
        # --- /ВЫЗОВ СЕРВИСА ---
        await message.answer(
            main_menu_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"[cmd_start] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.callback_query(F.data == "main_menu")
@log_user_activity('button', metadata_extra={'context': 'Главное меню'})
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Возврат в главное меню"""
    
    try:
        await state_manager.clear_state(state)

        # --- ВЫЗОВ СЕРВИСА ДЛЯ ПОЛУЧЕНИЯ ДАННЫХ ГЛАВНОГО МЕНЮ ---
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        keyboard = menu_data['keyboard']
        # --- /ВЫЗОВ СЕРВИСА ---

        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=keyboard
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[back_to_main_menu] Ошибка: {e}")
        try:
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('main_menu', language),
                reply_markup=await get_main_menu_keyboard(language, user) # fallback на прямой вызов клавиатуры
            )
        except Exception as fallback_error:
            logger.error(f"[back_to_main_menu] Ошибка fallback: {fallback_error}")
        await safe_answer_callback(callback, get_message('error_generic', language))
