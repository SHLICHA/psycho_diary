"""
Handler для команды /start
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from bot.states.onboarding_states import OnboardingStates
from messages import get_message
from bot.keyboards import (
    get_main_menu_keyboard,
    get_instruction_keyboard
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message, user, language: str, state: FSMContext):
    """Обработчик команды /start"""
    try:
        if not getattr(user, 'has_agreed_to_terms', False):
            welcome_msg = get_message('onboarding_welcome', language)
            await message.answer(welcome_msg)
            instruction_msg = get_message('onboarding_instruction', language)
            await state.set_state(OnboardingStates.showing_instruction)
            await message.answer(instruction_msg, reply_markup=get_instruction_keyboard(language))         
        else:
            profile_data = await user.aget_profile_data()
            first_name = profile_data.get('first_name', get_message('user_default_name', language))
            awareness_level = profile_data.get('awareness_level', 1)
            entries_count = profile_data.get('entries_count', 0)
            token_balance = user.token_balance
            from bot.services.diary_service import get_user_streaks
            current_streak, max_streak = await sync_to_async(get_user_streaks)(user)
            streak_info = ""
            if current_streak > 0:
                streak_info = get_message('current_streak_info', language, current_streak=current_streak)
                if current_streak == 1:
                     streak_info += " " + get_message('keep_going_1_day', language)
                elif 2 <= current_streak <= 4:
                     streak_info += " " + get_message('keep_going_few_days', language)
                elif current_streak >= 5:
                     streak_info += " " + get_message('keep_going_streak', language)
            else:
                streak_info = get_message('no_current_streak', language)
            max_streak_info = ""
            if max_streak > 0:
                max_streak_info = get_message('max_streak_info', language, max_streak=max_streak)
            main_menu_msg = get_message('main_menu_welcome_back', language,
                                       first_name=first_name,
                                       awareness_level=awareness_level,
                                       entries_count=entries_count,
                                       token_balance=token_balance,
                                       streak_info=streak_info,
                                       max_streak_info=max_streak_info)
            await message.answer(
                main_menu_msg,
                reply_markup=get_main_menu_keyboard(language, user)
            )
    except Exception as e:
        logger.error(f"Ошибка в cmd_start для пользователя {user.id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Возврат в главное меню"""
    from bot.services.diary_service import get_user_streaks
    try:
        await state_manager.clear_state(state)
        profile_data = await user.aget_profile_data()
        first_name = profile_data.get('first_name', get_message('user_default_name', language))
        awareness_level = profile_data.get('awareness_level', 1)
        entries_count = profile_data.get('entries_count', 0)
        token_balance = user.token_balance
        
        current_streak, max_streak = await sync_to_async(get_user_streaks)(user)
        streak_info = ""
        if current_streak > 0:
            streak_info = get_message('current_streak_info', language, current_streak=current_streak)
            if current_streak == 1:
                 streak_info += " " + get_message('keep_going_1_day', language)
            elif 2 <= current_streak <= 4:
                 streak_info += " " + get_message('keep_going_few_days', language)
            elif current_streak >= 5:
                 streak_info += " " + get_message('keep_going_streak', language)
        else:
            streak_info = get_message('no_current_streak', language)
        max_streak_info = ""
        if max_streak > 0:
            max_streak_info = get_message('max_streak_info', language, max_streak=max_streak)
        main_menu_msg = get_message('main_menu_welcome_back', language,
                                   first_name=first_name,
                                   awareness_level=awareness_level,
                                   entries_count=entries_count,
                                   token_balance=token_balance,
                                   streak_info=streak_info,
                                   max_streak_info=max_streak_info)
        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=get_main_menu_keyboard(language, user)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при возврате в главное меню: {e}")
        try:
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('main_menu', language),
                reply_markup=get_main_menu_keyboard(language)
            )
        except Exception as fallback_error:
            logger.error(f"Ошибка при отправке fallback сообщения: {fallback_error}")
        await safe_answer_callback(callback, get_message('error_generic', language))
