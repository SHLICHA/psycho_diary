"""
Утилиты для работы с callback бота
"""

import logging
from typing import Optional, Dict, Any
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest 

logger = logging.getLogger(__name__)

async def safe_answer_callback(
    callback: CallbackQuery,
    text: Optional[str] = None,
    show_alert: bool = False,
    cache_time: int = 0
) -> bool:
    """
    Безопасный ответ на callback запрос.
    
    Args:
        callback: Callback запрос.
        text: Текст ответа.
        show_alert: Показывать ли alert.
        cache_time: Время кэширования ответа.
        
    Returns:
        bool: Успешность ответа.
    """
    from bot.utils.message_utils import safe_telegram_call
    success, _, _ = await safe_telegram_call(
        callback.answer,
        text=text,
        show_alert=show_alert,
        cache_time=cache_time,
        operation_name=f"answer_callback (callback_id={callback.id})"
    )
    return success

async def extract_callback_data_parts(
    callback: CallbackQuery,
    separator: str = ":"
) -> list:
    """
    Извлечение частей callback_data
    
    Args:
        callback: Callback запрос
        separator: Разделитель частей
        
    Returns:
        list: Список частей callback_data
    """ 
    try:
        if callback.data:
            parts = callback.data.split(separator)
            return parts
        else:
            logger.warning("Callback data отсутствует")
            return []
    except Exception as e:
        logger.error(f"Ошибка при извлечении частей callback_data: {e}")
        return []

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
    
def is_message_not_modified_error(exception: Exception) -> bool:
    """
    Проверяет, является ли исключение ошибкой "message is not modified".

    Args:
        exception (Exception): Исключение для проверки.

    Returns:
        bool: True, если это ошибка "message is not modified", иначе False.
    """
    if isinstance(exception, TelegramBadRequest):
        error_message = str(exception).lower()
        return "message is not modified" in error_message or "message was not modified" in error_message
    return False