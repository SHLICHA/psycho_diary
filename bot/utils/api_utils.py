"""
Утилиты для работы с API
"""

import logging
import asyncio
import functools
from typing import Any, Callable, Awaitable
from functools import wraps

logger = logging.getLogger(__name__)

def api_retry(max_attempts: int = 3, delay: float = 1.0):
    """
    Декоратор для retry механизмов API вызовов
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками (секунды)
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            logger.info(f"Начало retry механизма для функции {func.__name__}")
            logger.info(f"Максимальное количество попыток: {max_attempts}")
            logger.info(f"Задержка между попытками: {delay} секунд")
            
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Попытка {attempt + 1}/{max_attempts}")
                    result = await func(*args, **kwargs)
                    logger.info(f"Функция {func.__name__} выполнена успешно на попытке {attempt + 1}")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
                    
                    if attempt < max_attempts - 1:
                        logger.info(f"Ожидание {delay} секунд перед следующей попыткой...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Все {max_attempts} попыток неудачны")
                        raise last_exception
            
            if last_exception:
                logger.error(f"Retry механизм исчерпан для функции {func.__name__}")
                raise last_exception
                
        return wrapper
    return decorator

def handle_api_error(func: Callable[..., Awaitable[Any]]):
    """
    Декоратор для обработки ошибок API вызовов
    
    Args:
        func: Функция для декорирования
        
    Returns:
        Callable[..., Awaitable[Any]]: Декорированная функция
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        logger.info(f"Начало обработки ошибок API для функции {func.__name__}")
        
        try:
            result = await func(*args, **kwargs)
            logger.info(f"Функция {func.__name__} выполнена успешно")
            return result
            
        except asyncio.TimeoutError as timeout_error:
            logger.error(f"Таймаут API вызова в функции {func.__name__}: {timeout_error}")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от API',
                'result': None
            }
            
        except ConnectionError as connection_error:
            logger.error(f"Ошибка подключения к API в функции {func.__name__}: {connection_error}")
            return {
                'success': False,
                'error': 'connection_error',
                'message': 'Ошибка подключения к API',
                'result': None
            }
            
        except ValueError as value_error:
            logger.error(f"Ошибка значения в API вызове функции {func.__name__}: {value_error}")
            return {
                'success': False,
                'error': 'value_error',
                'message': 'Ошибка в данных API вызова',
                'result': None
            }
            
        except Exception as general_error:
            logger.error(f"Общая ошибка API вызова в функции {func.__name__}: {general_error}")
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при вызове API',
                'result': None
            }
    
    return wrapper

class APIError(Exception):
    """Базовый класс для ошибок API"""
    
    def __init__(self, message: str, error_code: str = 'unknown'):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)
    
    def __str__(self):
        return f"API Error [{self.error_code}]: {self.message}"

class SpeechKitAPIError(APIError):
    """Ошибка Yandex SpeechKit API"""
    
    def __init__(self, message: str, error_code: str = 'speechkit_error'):
        super().__init__(message, error_code)

class DeepSeekAPIError(APIError):
    """Ошибка DeepSeek API"""
    
    def __init__(self, message: str, error_code: str = 'deepseek_error'):
        super().__init__(message, error_code)

async def safe_api_call(
    api_func: Callable[..., Awaitable[Any]], 
    *args, 
    **kwargs
) -> Any:
    """
    Безопасный вызов API функции с обработкой ошибок
    
    Args:
        api_func: Функция API для вызова
        *args: Аргументы функции
        **kwargs: Именованные аргументы функции
        
    Returns:
        Any: Результат вызова API функции
    """
    try:
        result = await api_func(*args, **kwargs)
        logger.info(f"API функция {api_func.__name__} выполнена успешно")
        return result
    except Exception as e:
        logger.error(f"Ошибка при безопасном вызове API функции {api_func.__name__}: {e}")
        return None

async def retry_api_call(
    api_func: Callable[..., Awaitable[Any]], 
    max_attempts: int = 3, 
    delay: float = 1.0,
    *args, 
    **kwargs
) -> Any:
    """
    Retry вызов API функции
    
    Args:
        api_func: Функция API для вызова
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками (секунды)
        *args: Аргументы функции
        **kwargs: Именованные аргументы функции
        
    Returns:
        Any: Результат вызова API функции
    """
    logger.info(f"Retry вызов API функции {api_func.__name__}")
    logger.info(f"Максимальное количество попыток: {max_attempts}")
    logger.info(f"Задержка между попытками: {delay} секунд")
    
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            logger.info(f"Попытка {attempt + 1}/{max_attempts}")
            result = await api_func(*args, **kwargs)
            logger.info(f"API функция {api_func.__name__} выполнена успешно на попытке {attempt + 1}")
            return result
            
        except Exception as e:
            last_exception = e
            logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
            
            if attempt < max_attempts - 1:
                logger.info(f"Ожидание {delay} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Все {max_attempts} попыток неудачны")
                raise last_exception
    
    # Если все попытки неудачны, выбрасываем последнее исключение
    if last_exception:
        logger.error(f"Retry механизм исчерпан для API функции {api_func.__name__}")
        raise last_exception

# Удобные функции для использования
def get_api_error_message(error_code: str, language: str = 'ru') -> str:
    """
    Получение сообщения об ошибке API по коду
    
    Args:
        error_code: Код ошибки
        language: Язык сообщения
        
    Returns:
        str: Сообщение об ошибке
    """
    logger.info(f"Получение сообщения об ошибке API: {error_code}")
    
    error_messages_ru = {
        'timeout': 'Превышено время ожидания ответа от API',
        'connection_error': 'Ошибка подключения к API',
        'value_error': 'Ошибка в данных API вызова',
        'general_error': 'Произошла ошибка при вызове API',
        'speechkit_error': 'Ошибка Yandex SpeechKit API',
        'deepseek_error': 'Ошибка DeepSeek API',
        'unknown': 'Неизвестная ошибка API',
        'api_key_missing': 'API ключ не настроен',
        'api_key_invalid': 'Неверный API ключ',
        'rate_limit': 'Превышен лимит запросов к API',
        'invalid_request': 'Неверный запрос к API',
        'server_error': 'Ошибка сервера API',
        'service_unavailable': 'Сервис API недоступен'
    }
    
    error_messages_en = {
        'timeout': 'API response timeout exceeded',
        'connection_error': 'API connection error',
        'value_error': 'API call data error',
        'general_error': 'An error occurred during API call',
        'speechkit_error': 'Yandex SpeechKit API error',
        'deepseek_error': 'DeepSeek API error',
        'unknown': 'Unknown API error',
        'api_key_missing': 'API key not configured',
        'api_key_invalid': 'Invalid API key',
        'rate_limit': 'API request limit exceeded',
        'invalid_request': 'Invalid API request',
        'server_error': 'API server error',
        'service_unavailable': 'API service unavailable'
    }
    
    error_messages = error_messages_ru if language == 'ru' else error_messages_en
    error_message = error_messages.get(error_code, error_messages['unknown'])
    
    logger.info(f"Сообщение об ошибке получено: {error_message}")
    return error_message