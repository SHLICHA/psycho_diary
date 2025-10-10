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
    get_instruction_keyboard,
    get_agreement_keyboard
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from bot.utils.diary_utils import get_user_streaks, get_recoverable_gap_info

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message, user, language: str, state: FSMContext):
    """Обработчик команды /start"""
    try:
        if not getattr(user, 'has_agreed_to_terms', False):
            # Пользователь не согласился. Показываем объединённое приветствие и соглашение, как в start_onboarding.
            welcome_msg = get_message('onboarding_welcome_extended', language) # <-- Используем новый ключ
            await state.set_state(OnboardingStates.showing_agreement) # <-- Устанавливаем состояние соглашения
            await message.answer(
                welcome_msg,
                reply_markup=get_agreement_keyboard(language) # <-- Клавиатура соглашения
            )
            return # <-- ВАЖНО: завершаем обработку, чтобы не показывать главное меню
        # Если пользователь согласился, показываем главное меню
        profile_data = await user.aget_profile_data()
        first_name = profile_data.get('first_name', get_message('user_default_name', language))
        awareness_level = profile_data.get('awareness_level', 1)
        entries_count = profile_data.get('entries_count', 0)
        token_balance = user.token_balance
        current_streak, max_streak = await get_user_streaks(user)
        dates_to_restore = await get_recoverable_gap_info(user)
        restore_available = dates_to_restore is not None
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
        if restore_available and dates_to_restore:
            # Форматируем даты для сообщения
            formatted_dates = [dt.strftime("%d.%m") for dt in dates_to_restore]
            # Можем использовать разные сообщения в зависимости от количества дней
            if len(formatted_dates) == 1:
                restore_hint = get_message('streak_restore_hint_single_day', language, date=formatted_dates[0])
            else: # len == 2
                # Объединяем даты, например, "07.10 и 08.10"
                dates_str = " и ".join(formatted_dates)
                restore_hint = get_message('streak_restore_hint_two_days', language, dates=dates_str)
            main_menu_msg += f"\n\n{restore_hint}"
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
    
    try:
        await state_manager.clear_state(state)
        profile_data = await user.aget_profile_data()
        first_name = profile_data.get('first_name', get_message('user_default_name', language))
        awareness_level = profile_data.get('awareness_level', 1)
        entries_count = profile_data.get('entries_count', 0)
        token_balance = user.token_balance
        
        current_streak, max_streak = await get_user_streaks(user)
        dates_to_restore = await get_recoverable_gap_info(user)
        restore_available = dates_to_restore is not None
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
        if restore_available and dates_to_restore:
             # Форматируем даты для сообщения
             formatted_dates = [dt.strftime("%d.%m") for dt in dates_to_restore]
             # Можем использовать разные сообщения в зависимости от количества дней
             if len(formatted_dates) == 1:
                 restore_hint = get_message('streak_restore_hint_single_day', language, date=formatted_dates[0])
             else: # len == 2
                 # Объединяем даты, например, "07.10 и 08.10"
                 dates_str = " и ".join(formatted_dates)
                 restore_hint = get_message('streak_restore_hint_two_days', language, dates=dates_str)
             main_menu_msg += f"\n\n{restore_hint}"
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
