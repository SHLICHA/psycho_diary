"""
Утилиты для работы с callback бота
"""

import logging
from typing import Optional, Dict, Any
from aiogram.types import CallbackQuery
from messages import get_message

logger = logging.getLogger(__name__)

async def safe_answer_callback(
    callback: CallbackQuery,
    text: Optional[str] = None,
    show_alert: bool = False,
    cache_time: int = 0
) -> bool:
    """
    Безопасный ответ на callback запрос
    
    Args:
        callback: Callback запрос
        text: Текст ответа
        show_alert: Показывать ли alert
        cache_time: Время кэширования ответа
        
    Returns:
        bool: Успешность ответа
    """
    logger.info(f"Безопасный ответ на callback запрос от пользователя {callback.from_user.id}")
    logger.info(f"Текст ответа: {text[:50] if text else 'None'}...")
    logger.info(f"Show alert: {show_alert}, Cache time: {cache_time}")
    
    try:
        await callback.answer(
            text=text,
            show_alert=show_alert,
            cache_time=cache_time
        )
        logger.info("Callback запрос успешно обработан")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback запрос: {e}")
        return False

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
    logger.info(f"Извлечение частей callback_data от пользователя {callback.from_user.id}")
    logger.info(f"Callback data: {callback.data}")
    logger.info(f"Разделитель: {separator}")
    
    try:
        if callback.data:
            parts = callback.data.split(separator)
            logger.info(f"Извлечено {len(parts)} частей из callback_data")
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
    logger.info(f"Получение части callback_data[{index}] от пользователя {callback.from_user.id}")
    
    try:
        parts = await extract_callback_data_parts(callback, separator)
        if 0 <= index < len(parts):
            part = parts[index]
            logger.info(f"Получена часть callback_data: {part}")
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
    logger.info(f"Парсинг callback_data с преобразованием типов от пользователя {callback.from_user.id}")
    logger.info(f"Карта типов: {types_map}")
    
    try:
        parts = await extract_callback_data_parts(callback, separator)
        parsed_data = {}
        
        for index, target_type in types_map.items():
            if 0 <= index < len(parts):
                try:
                    value = target_type(parts[index])
                    parsed_data[f'part_{index}'] = value
                    logger.info(f"Часть {index} преобразована в {target_type.__name__}: {value}")
                except (ValueError, TypeError) as convert_error:
                    logger.error(f"Ошибка преобразования части {index} в {target_type.__name__}: {convert_error}")
                    parsed_data[f'part_{index}'] = parts[index]  # Оставляем как строку
            else:
                logger.warning(f"Индекс {index} выходит за пределы callback_data")
                parsed_data[f'part_{index}'] = None
        
        logger.info(f"Callback_data успешно распарсен: {parsed_data}")
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
    logger.info(f"Валидация формата callback_data длиной {len(callback_data)} символов")
    logger.info(f"Ожидаемое количество частей: {expected_parts}")
    
    try:
        parts = callback_data.split(separator)
        is_valid = len(parts) == expected_parts
        logger.info(f"Формат callback_data {'валиден' if is_valid else 'не валиден'}")
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
    logger.info(f"Санитизация callback_data длиной {len(callback_data)} символов")
    logger.info(f"Максимальная длина: {max_length}")
    
    try:
        if len(callback_data) > max_length:
            sanitized_data = callback_data[:max_length]
            logger.info(f"Callback_data санитизированы до {len(sanitized_data)} символов")
            return sanitized_data
        else:
            logger.info("Callback_data не требуют санитизации")
            return callback_data
            
    except Exception as e:
        logger.error(f"Ошибка при санитизации callback_data: {e}")
        return callback_data[:max_length] if len(callback_data) > max_length else callback_data