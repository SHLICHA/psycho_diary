"""
Утилиты валидации данных бота
"""

import logging
import re
import html

from typing import Optional, Tuple
from aiogram.types import Message, ContentType

from core.constants import (
    TEXT_MESSAGE_MAX_LENGTH,
    TEXT_MESSAGE_MIN_LENGTH,
    VOICE_MESSAGE_MAX_DURATION,
    VOICE_MESSAGE_MIN_DURATION
)

logger = logging.getLogger(__name__)

class SecurityValidator:
    """Класс для проверки безопасности входных данных"""
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """Экранирование HTML тегов"""
        return html.escape(text)
    
    @staticmethod
    def sanitize_sql(text: str) -> str:
        """Базовая защита от SQL injection"""
        return re.sub(r'[;\'"\\]', '', text)
    
    @staticmethod
    def validate_telegram_id(user_id: int) -> bool:
        """Валидация Telegram ID"""
        return isinstance(user_id, int) and 1 <= user_id <= 2**63 - 1
    
    @staticmethod
    def validate_timezone(timezone: str) -> bool:
        """Валидация часового пояса"""
        try:
            import pytz
            pytz.timezone(timezone)
            return True
        except:
            return False

def validate_and_sanitize_text(
    text: str, 
    max_length: int = 10000,
    min_length: int = 10
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Валидация и санитизация текста
    
    Returns:
        Tuple[bool, Optional[str], Optional[str]]: 
        (is_valid, sanitized_text, error_code)
    """
    try:
        # Проверка длины
        if len(text) < min_length:
            return False, None, 'text_too_short'
        if len(text) > max_length:
            return False, None, 'text_too_long'
        
        # Санитизация
        sanitized = SecurityValidator.sanitize_html(text)
        sanitized = SecurityValidator.sanitize_sql(sanitized)
        
        # Проверка на запрещенные паттерны
        forbidden_patterns = [
            r'<script.*?>',
            r'javascript:',
            r'onload=',
            r'onerror=',
            r'vbscript:',
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                return False, None, 'invalid_content'
        return True, sanitized, None
    except Exception as e:
        logger.error(f"Ошибка при валидации текста: {e}")
        return False, None, 'validation_error'

def validate_text_entry(
    text: str,
    min_length: int = TEXT_MESSAGE_MIN_LENGTH,
    max_length: int = TEXT_MESSAGE_MAX_LENGTH
) -> Tuple[bool, Optional[str]]:
    """
    Валидация текстовой записи
    
    Args:
        text: Текст записи
        min_length: Минимальная длина
        max_length: Максимальная длина
        
    Returns:
        Tuple[bool, Optional[str]]: (валидность, сообщение об ошибке)
    """
    try:
        if len(text.strip()) < min_length:
            return False, "text_too_short" 
        if len(text) > max_length:
            return False, "text_too_long"
        if not text.strip():
            return False, "invalid_input"
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при валидации текстовой записи: {e}")
        return False, "validation_error_text"

def validate_voice_entry(
    duration: int,
    min_duration: int = VOICE_MESSAGE_MIN_DURATION,
    max_duration: int = VOICE_MESSAGE_MAX_DURATION
) -> Tuple[bool, Optional[str]]:
    """
    Валидация голосовой записи
    
    Args:
        duration: Длительность голосового сообщения (сек)
        min_duration: Минимальная длительность
        max_duration: Максимальная длительность
        
    Returns:
        Tuple[bool, Optional[str]]: (валидность, сообщение об ошибке)
    """
    try:
        if duration < min_duration:
            return False, "voice_too_short"
        if duration > max_duration:
            return False, "voice_too_long"
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при валидации голосовой записи: {e}")
        return False, "validation_error_voice"

def validate_incoming_message(message: Message) -> Tuple[bool, Optional[str]]:
    """
    Валидация входящего сообщения (текст или голос).
    
    Args:
        message: Входящее сообщение aiogram
        
    Returns:
        Tuple[bool, Optional[str]]: (валидность, код сообщения об ошибке)
    """
    try:
        if message.content_type == ContentType.TEXT:
            is_valid, error_code = validate_text_entry(message.text)
            return is_valid, error_code
        elif message.content_type == ContentType.VOICE:
            voice = message.voice
            if not voice:
                logger.warning("Получено сообщение типа VOICE, но объект voice отсутствует.")
                return False, "invalid_input"
            is_valid, error_code = validate_voice_entry(voice.duration)
            return is_valid, error_code
        else:
            logger.warning(f"Получен недопустимый тип сообщения: {message.content_type}")
            return False, "invalid_input_type"
    except Exception as e:
        logger.error(f"Ошибка при валидации входящего сообщения: {e}")
        return False, "validation_error_message"

def validate_user_input(
    input_text: str,
    allowed_chars: Optional[str] = None,
    forbidden_words: Optional[list] = None
) -> Tuple[bool, Optional[str]]:
    """
    Валидация пользовательского ввода
    
    Args:
        input_text: Текст ввода
        allowed_chars: Разрешенные символы (regex паттерн)
        forbidden_words: Запрещенные слова
        
    Returns:
        Tuple[bool, Optional[str]]: (валидность, сообщение об ошибке)
    """
    try:
        if allowed_chars:
            pattern = re.compile(allowed_chars)
            if not pattern.match(input_text):
                error_msg = "Ввод содержит недопустимые символы."
                logger.warning("Ввод содержит недопустимые символы")
                return False, error_msg
        if forbidden_words:
            input_lower = input_text.lower()
            for word in forbidden_words:
                if word.lower() in input_lower:
                    error_msg = f"Ввод содержит запрещенное слово: {word}"
                    logger.warning(f"Ввод содержит запрещенное слово: {word}")
                    return False, error_msg
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при валидации пользовательского ввода: {e}")
        return False, "Ошибка валидации пользовательского ввода."

def validate_date_range(
    year: int,
    month: int,
    day: int,
    min_year: int = 2020,
    max_year: int = 2030
) -> Tuple[bool, Optional[str]]:
    """
    Валидация диапазона дат
    
    Args:
        year: Год
        month: Месяц
        day: День
        min_year: Минимальный год
        max_year: Максимальный год
        
    Returns:
        Tuple[bool, Optional[str]]: (валидность, сообщение об ошибке)
    """
    try:
        if not (min_year <= year <= max_year):
            error_msg = f"Год должен быть в диапазоне {min_year}-{max_year}."
            logger.warning(f"Год вне диапазона: {year}")
            return False, error_msg
        if not (1 <= month <= 12):
            error_msg = "Месяц должен быть от 1 до 12."
            logger.warning(f"Месяц вне диапазона: {month}")
            return False, error_msg
        from calendar import monthrange
        try:
            days_in_month = monthrange(year, month)[1]
            if not (1 <= day <= days_in_month):
                error_msg = f"День должен быть от 1 до {days_in_month} для {month}.{year}."
                logger.warning(f"День вне диапазона: {day}")
                return False, error_msg
        except ValueError as date_error:
            error_msg = "Некорректная дата."
            logger.warning(f"Ошибка при проверке дней в месяце: {date_error}")
            return False, error_msg
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при валидации диапазона дат: {e}")
        return False, "Ошибка валидации диапазона дат."

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def sanitize_input_text(text: str) -> str:
    """
    Санитизация текста ввода
    
    Args:
        text: Текст ввода
        
    Returns:
        str: Санитизированный текст
    """
    try:
        sanitized_text = re.sub(r'\s+', ' ', text.strip())
        sanitized_text = re.sub(r'[<>"\']', '', sanitized_text)
        return sanitized_text
    except Exception as e:
        logger.error(f"Ошибка при санитизации текста: {e}")
        return text.strip()

def validate_language_code(language_code: str) -> bool:
    """
    Валидация кода языка
    
    Args:
        language_code: Код языка
        
    Returns:
        bool: Валидность кода языка
    """
    try:
        supported_languages = ['ru', 'en']
        is_valid = language_code and language_code[:2] in supported_languages
        logger.info(f"Код языка {'валиден' if is_valid else 'не валиден'}")
        return is_valid
    except Exception as e:
        logger.error(f"Ошибка при валидации кода языка: {e}")
        return False

def validate_telegram_id(telegram_id: int) -> bool:
    """
    Валидация Telegram ID
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        bool: Валидность Telegram ID
    """
    try:
        is_valid = isinstance(telegram_id, int) and telegram_id > 0
        logger.info(f"Telegram ID {'валиден' if is_valid else 'не валиден'}")
        return is_valid
    except Exception as e:
        logger.error(f"Ошибка при валидации Telegram ID: {e}")
        return False