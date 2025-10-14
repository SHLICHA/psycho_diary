"""
Handler для команды /start
"""

import logging
import pytz

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from django.utils import timezone

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

# --- ВЫНЕСЕННАЯ АСИНХРОННАЯ ФУНКЦИЯ ---
async def build_main_menu_message(user, language: str):
    """
    Асинхронная функция для формирования сообщения главного меню.
    Возвращает строку сообщения и клавиатуру.
    """
    profile_data = await user.aget_profile_data()
    first_name = profile_data.get('first_name', get_message('user_default_name', language))
    awareness_level = profile_data.get('awareness_level', 1)
    entries_count = profile_data.get('entries_count', 0)
    token_balance = user.token_balance

    # --- НОВОЕ: Получение информации о подписке ---
    is_user_premium_active = await sync_to_async(user.is_premium_active)()
    premium_info = ""
    if is_user_premium_active and user.premium_expires_at:
        user_timezone_str = user.timezone if user.timezone else 'UTC'
        try:
            user_tz = pytz.timezone(user_timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Неизвестный часовой пояс у пользователя {user.telegram_id}: {user_timezone_str}. Используется UTC.")
            user_tz = pytz.UTC

        expires_local_dt = user.premium_expires_at.astimezone(user_tz)
        expires_local_date = expires_local_dt.date()
        user_local_date = await sync_to_async(lambda: timezone.now().astimezone(user_tz).date())()

        days_until_expiry = (expires_local_date - user_local_date).days
        if days_until_expiry >= 0:
            days_info = get_message('premium_days_remaining', language, days=days_until_expiry)
            premium_info = get_message('premium_active_info', language, days_info=days_info)
        else:
            premium_info = get_message('premium_expired', language)
    elif user.is_premium:
         premium_info = get_message('premium_expired', language)
    # --- КОНЕЦ НОВОГО ---

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

    main_menu_msg = get_message('main_menu_welcome_back_with_premium', language,
                               first_name=first_name,
                               awareness_level=awareness_level,
                               entries_count=entries_count,
                               token_balance=token_balance,
                               premium_info=premium_info,
                               streak_info=streak_info,
                               max_streak_info=max_streak_info)

    if restore_available and dates_to_restore:
         formatted_dates = [dt.strftime("%d.%m") for dt in dates_to_restore]
         if len(formatted_dates) == 1:
             restore_hint = get_message('streak_restore_hint_single_day', language, date=formatted_dates[0])
         else:
             dates_str = " и ".join(formatted_dates)
             restore_hint = get_message('streak_restore_hint_two_days', language, dates=dates_str)
         main_menu_msg += f"\n\n{restore_hint}"

    keyboard = get_main_menu_keyboard(language, user)
    return main_menu_msg, keyboard
# --- КОНЕЦ ВЫНЕСЕННОЙ ФУНКЦИИ ---


@router.message(Command("start"))
async def cmd_start(message: Message, user, language: str, state: FSMContext, data: dict = None, **kwargs):
    """
    Обработчик команды /start
    Проверяет, был ли пользователь разблокирован при взаимодействии (через middleware).
    Если да - отправляет специальное приветствие.
    Затем показывает онбординг или главное меню в зависимости от согласия.
    """
    try:
        await state_manager.clear_state(state)
        # --- ЧИТАЕМ ФЛАГ ИЗ kwargs, ТАК КАК data = None ---
        was_reactivated = kwargs.get('was_blocked_and_reactivated', False)
        # ---
        logger.debug(f"[cmd_start] was_reactivated из kwargs: {was_reactivated}")

        # Если пользователь был разблокирован, отправляем специальное приветствие
        if was_reactivated:
            reactivation_msg = get_message(
                'welcome_back_reactivated',
                language,
                first_name=user.first_name or user.username or get_message('user_default_name', language)
            )
            await message.answer(reactivation_msg)

        if not getattr(user, 'has_agreed_to_terms', False):
            # Пользователь не согласился. Показываем объединённое приветствие и соглашение, как в start_onboarding.
            welcome_msg = get_message('onboarding_welcome_extended', language)
            await state.set_state(OnboardingStates.showing_agreement)
            await message.answer(
                welcome_msg,
                reply_markup=get_agreement_keyboard(language)
            )
            return # <-- ВАЖНО: завершаем обработку, чтобы не показывать главное меню

        # --- ВЫЗОВ ВЫНЕСЕННОЙ ФУНКЦИИ ---
        main_menu_msg, keyboard = await build_main_menu_message(user, language)
        # ---

        await message.answer(
            main_menu_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка в cmd_start для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Возврат в главное меню"""
    
    try:
        await state_manager.clear_state(state)

        # --- ВЫЗОВ ВЫНЕСЕННОЙ ФУНКЦИИ ---
        main_menu_msg, keyboard = await build_main_menu_message(user, language)
        # ---

        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=keyboard
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