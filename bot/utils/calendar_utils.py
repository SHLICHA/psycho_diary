"""
Утилиты для работы с календарем.
"""

import logging
from datetime import date
from typing import Optional

from aiogram.types import Message
from users.models import User
from bot.keyboards import get_month_calendar_with_navigation
from bot.utils.message_utils import safe_edit_message_text
from core.constants import MONTH_NAMES_RU, MONTH_NAMES_EN
from messages import get_message

logger = logging.getLogger(__name__)

async def update_calendar_display(
    message: Message,
    user: User,
    target_date: date,
    language: str,
    status_message: Optional[str] = None,
    force_full_update: bool = False
) -> bool:
    """
    Утилита для обновления отображения календаря в чате.

    Args:
        message: Сообщение Telegram для редактирования.
        user: Объект пользователя.
        target_date: Дата, для которой отображается календарь (определяет год/месяц).
        language: Язык интерфейса.
        status_message: Дополнительное сообщение, которое будет отображаться над календарем.
        force_full_update: Если True, всегда обновляет текст сообщения, даже если он не изменился.

    Returns:
        bool: True, если обновление прошло успешно, иначе False.
    """
    try:
        year = target_date.year
        month = target_date.month
        user_local_date = user.get_local_datetime().date()
        if user_local_date.year == year and user_local_date.month == month:
            current_day_to_highlight = user_local_date.day
        else:
            current_day_to_highlight = 1
        month_names = MONTH_NAMES_RU if language == 'ru' else MONTH_NAMES_EN
        month_name = month_names[month] if 1 <= month <= 12 else ""
        
        base_calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )    
        final_message_text = f"{status_message}\n{base_calendar_msg}" if status_message else base_calendar_msg
        calendar_keyboard = await get_month_calendar_with_navigation(
            user, year, month, current_day_to_highlight, language
        )
        if force_full_update or (hasattr(message, 'text') and message.text != final_message_text):
            success = await safe_edit_message_text(
                message=message,
                text=final_message_text,
                reply_markup=calendar_keyboard
            )
        else:
            try:
                await message.edit_reply_markup(reply_markup=calendar_keyboard)
                success = True
            except Exception as keyboard_error:
                logger.warning(f"Не удалось обновить только клавиатуру: {keyboard_error}. Обновляем всё сообщение.")
                success = await safe_edit_message_text(
                    message=message,
                    text=final_message_text,
                    reply_markup=calendar_keyboard
                )
        return success
    except Exception as e:
        logger.error(f"Ошибка при обновлении отображения календаря для {target_date}: {e}", exc_info=True)
        return False
