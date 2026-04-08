# /diary/services/main_menu_service.py
"""
Сервис для подготовки данных главного меню.
"""

import logging
import pytz
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.utils import timezone

from users.models import User
from messages import get_message
from bot.keyboards import get_main_menu_keyboard
from bot.utils.diary_utils import get_user_streaks, get_recoverable_gap_info

logger = logging.getLogger(__name__)

class MainMenuService:
    """Сервис для формирования данных главного меню."""

    @classmethod
    async def build_main_menu_data(cls, user: User, language: str) -> dict:
        """
        Асинхронно формирует данные для отображения главного меню.

        Args:
            user: Объект пользователя Django.
            language: Язык пользователя.

        Returns:
            dict: Словарь с данными для главного меню.
                - message_text (str): Текст сообщения.
                - keyboard (InlineKeyboardMarkup): Клавиатура.
        """
        try:
            # --- Получение данных профиля ---
            profile_data = await user.aget_profile_data()
            first_name = profile_data.get('first_name', get_message('user_default_name', language))
            awareness_level = profile_data.get('awareness_level', 1)
            entries_count = profile_data.get('entries_count', 0)
            token_balance = user.token_balance

            # --- Получение информации о премиуме ---
            is_user_premium_active = await sync_to_async(user.is_premium_active)()
            premium_info = ""
            if is_user_premium_active and user.premium_expires_at:
                user_timezone_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"[MainMenuService] Неизвестный часовой пояс у пользователя {user.telegram_id}: {user_timezone_str}. Используется UTC.")
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

            # --- Получение информации о серии (streak) ---
            current_streak, max_streak, has_entry_today = await get_user_streaks(user)
            dates_to_restore = await get_recoverable_gap_info(user)
            restore_available = dates_to_restore is not None

            # --- Формирование информации о стриках для передачи в шаблон ---
            streak_info_text = ""
            if has_entry_today:
                # Есть запись сегодня — показываем обычную серию
                if current_streak > 0:
                    streak_info_text = get_message('current_streak_info', language, current_streak=current_streak)
                    if current_streak == 1:
                         streak_info_text += " " + get_message('keep_going_1_day', language)
                    elif 2 <= current_streak <= 4:
                         streak_info_text += " " + get_message('keep_going_few_days', language)
                    elif current_streak >= 5:
                         streak_info_text += " " + get_message('keep_going_streak', language)
            else:
                # Нет записи сегодня
                if current_streak > 0:
                    # Серия есть, но оборвётся если не написать
                    streak_info_text = get_message('streak_at_risk', language, current_streak=current_streak)
                else:
                    streak_info_text = get_message('no_current_streak', language)

            max_streak_info_text = ""
            if max_streak > 0:
                max_streak_info_text = get_message('max_streak_info', language, max_streak=max_streak)
            # --- /Формирование информации о стриках ---

            # --- Формирование текста сообщения ---
            # Передаем оба параметра, как ожидал шаблон и как было в старом коде
            try:
                main_menu_msg = get_message('main_menu_welcome_back_with_premium', language,
                                           first_name=first_name,
                                           awareness_level=awareness_level,
                                           entries_count=entries_count,
                                           token_balance=token_balance,
                                           premium_info=premium_info,
                                           # --- ПЕРЕДАЁМ ОБА ПАРАМЕТРА О СТРИКАХ ---
                                           streak_info=streak_info_text,
                                           max_streak_info=max_streak_info_text
                                           # --- /ПЕРЕДАЁМ ---
                                           )
            except Exception as format_error:
                 logger.error(f"[MainMenuService] Ошибка форматирования основного сообщения меню для пользователя {user.telegram_id}: {format_error}")
                 main_menu_msg = get_message('main_menu', language) # fallback

            # --- Добавление подсказки о восстановлении серии ---
            if restore_available and dates_to_restore:
                 formatted_dates = [dt.strftime("%d.%m") for dt in dates_to_restore]
                 if len(formatted_dates) == 1:
                     restore_hint = get_message('streak_restore_hint_single_day', language, date=formatted_dates[0])
                 else:
                     dates_str = " и ".join(formatted_dates)
                     restore_hint = get_message('streak_restore_hint_two_days', language, dates=dates_str)
                 main_menu_msg += f"\n\n{restore_hint}"
            # --- /Добавление подсказки ---

            # --- Получение клавиатуры ---
            keyboard = await get_main_menu_keyboard(language, user)

            logger.debug(f"[MainMenuService] Данные главного меню сформированы для пользователя {user.telegram_id}")
            return {
                'message_text': main_menu_msg,
                'keyboard': keyboard
            }

        except Exception as e:
            logger.error(f"[MainMenuService] Ошибка при формировании данных главного меню для пользователя {user.telegram_id}: {e}", exc_info=True)
            # Возвращаем базовое сообщение в случае ошибки
            error_msg = get_message('error_generic', language)
            error_keyboard = await get_main_menu_keyboard(language, user) # Пытаемся получить клавиатуру
            return {
                'message_text': error_msg,
                'keyboard': error_keyboard
            }

# --- Удобные функции для импорта ---
async def build_main_menu_data(user: User, language: str) -> dict:
    """Удобная функция для формирования данных главного меню."""
    return await MainMenuService.build_main_menu_data(user, language)
