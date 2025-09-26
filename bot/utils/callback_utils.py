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

async def get_callback_data_part(
    callback: CallbackQuery,
    index: int,
    default: Any = None,
    separator: str = ":"
) -> Any:
    """
    Получение части callback_data по индексу
    
    Args:
        callback: Callback запрос
        index: Индекс части
        default: Значение по умолчанию
        separator: Разделитель частей
        
    Returns:
        Any: Часть callback_data или значение по умолчанию
    """
    try:
        parts = await extract_callback_data_parts(callback, separator)
        if 0 <= index < len(parts):
            part = parts[index]
            return part
        else:
            logger.warning(f"Индекс {index} выходит за пределы callback_data")
            return default
    except Exception as e:
        logger.error(f"Ошибка при получении части callback_data: {e}")
        return default

async def parse_callback_data_with_types(
    callback: CallbackQuery,
    types_map: Dict[int, type],
    separator: str = ":"
) -> Dict[str, Any]:
    """
    Парсинг callback_data с преобразованием типов
    
    Args:
        callback: Callback запрос
        types_map: Карта типов для частей (индекс: тип)
        separator: Разделитель частей
        
    Returns:
        Dict[str, Any]: Словарь с преобразованными частями
    """
    try:
        parts = await extract_callback_data_parts(callback, separator)
        parsed_data = {}
        for index, target_type in types_map.items():
            if 0 <= index < len(parts):
                try:
                    value = target_type(parts[index])
                    parsed_data[f'part_{index}'] = value
                except (ValueError, TypeError) as convert_error:
                    logger.error(f"Ошибка преобразования части {index} в {target_type.__name__}: {convert_error}")
                    parsed_data[f'part_{index}'] = parts[index]
            else:
                logger.warning(f"Индекс {index} выходит за пределы callback_data")
                parsed_data[f'part_{index}'] = None
        return parsed_data
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге callback_data: {e}")
        return {}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def validate_callback_data_format(
    callback_data: str,
    expected_parts: int,
    separator: str = ":"
) -> bool:
    """
    Валидация формата callback_data
    
    Args:
        callback_data: Данные callback
        expected_parts: Ожидаемое количество частей
        separator: Разделитель частей
        
    Returns:
        bool: Валидность формата
    """  
    try:
        parts = callback_data.split(separator)
        is_valid = len(parts) == expected_parts
        return is_valid 
    except Exception as e:
        logger.error(f"Ошибка при валидации формата callback_data: {e}")
        return False

def sanitize_callback_data(
    callback_data: str,
    max_length: int = 64
) -> str:
    """
    Санитизация callback_data (ограничение длины)
    
    Args:
        callback_data: Данные callback
        max_length: Максимальная длина
        
    Returns:
        str: Санитизированные данные callback
    """
    try:
        if len(callback_data) > max_length:
            sanitized_data = callback_data[:max_length]
            return sanitized_data
        else:
            return callback_data
            
    except Exception as e:
        logger.error(f"Ошибка при санитизации callback_data: {e}")
        return callback_data[:max_length] if len(callback_data) > max_length else callback_data
    
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