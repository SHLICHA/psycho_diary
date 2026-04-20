"""
Утилиты для работы с API
"""

import logging
import asyncio
import functools
from typing import Any, Callable, Dict, Awaitable, Tuple
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
            logger.debug(f"Начало retry механизма для функции {func.__name__}")
            logger.debug(f"Максимальное количество попыток: {max_attempts}")
            logger.debug(f"Задержка между попытками: {delay} секунд")
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    logger.debug(f"Попытка {attempt + 1}/{max_attempts}")
                    result = await func(*args, **kwargs)
                    logger.debug(f"Функция {func.__name__} выполнена успешно на попытке {attempt + 1}")
                    return result
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
                    if attempt < max_attempts - 1:
                        logger.debug(f"Ожидание {delay} секунд перед следующей попыткой...")
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
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"Функция {func.__name__} выполнена успешно")
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
    Безопасный вызов API функции с обработкой ошибок.
    
    Args:
        api_func: Функция API для вызова.
        *args: Аргументы функции.
        **kwargs: Именованные аргументы функции.
        
    Returns:
        Any: Результат вызова API функции или None в случае ошибки.
    """
    try:
        result = await api_func(*args, **kwargs)
        return result
    except asyncio.TimeoutError as timeout_error:
        logger.error(f"Таймаут API вызова в функции {api_func.__name__}: {timeout_error}")
        return {
            'success': False,
            'error': 'timeout',
            'message': 'Превышено время ожидания ответа от API',
            'result': None
        }
    except ConnectionError as connection_error:
        logger.error(f"Ошибка подключения к API в функции {api_func.__name__}: {connection_error}")
        return {
            'success': False,
            'error': 'connection_error',
            'message': 'Ошибка подключения к API',
            'result': None
        }
    except ValueError as value_error:
        logger.error(f"Ошибка значения в API вызове функции {api_func.__name__}: {value_error}")
        return {
            'success': False,
            'error': 'value_error',
            'message': 'Ошибка в данных API вызова',
            'result': None
        }
    except Exception as general_error:
        logger.error(f"Общая ошибка API вызова в функции {api_func.__name__}: {general_error}")
        return {
            'success': False,
            'error': 'general_error',
            'message': 'Произошла ошибка при вызове API',
            'result': None
        }

async def retry_api_call(
    api_func: Callable[..., Awaitable[Any]], 
    max_attempts: int = 3, 
    delay: float = 1.0,
    *args, 
    **kwargs
) -> Any:
    """
    Retry вызов API функции с использованием safe_api_call для обработки каждой попытки.
    
    Args:
        api_func: Функция API для вызова.
        max_attempts: Максимальное количество попыток.
        delay: Задержка между попытками (секунды).
        *args: Аргументы функции.
        **kwargs: Именованные аргументы функции.
        
    Returns:
        Any: Результат вызова API функции (успешный или последняя ошибка из safe_api_call).
    """
    logger.debug(f"Retry вызов API функции {api_func.__name__}")
    logger.debug(f"Максимальное количество попыток: {max_attempts}")
    logger.debug(f"Задержка между попытками: {delay} секунд")
    
    last_result = None
    
    for attempt in range(max_attempts):
        try:
            logger.debug(f"Попытка {attempt + 1}/{max_attempts}")
            result = await safe_api_call(api_func, *args, **kwargs)
            if isinstance(result, dict) and result.get('success') is False:
                last_result = result
                logger.warning(f"Попытка {attempt + 1} завершилась ошибкой API: {result.get('error')} - {result.get('message')}")
                if attempt < max_attempts - 1:
                    logger.debug(f"Ожидание {delay} секунд перед следующей попыткой...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Все {max_attempts} попыток неудачны. Возвращается последняя ошибка.")
                    return last_result 
            else:
                logger.debug(f"API функция {api_func.__name__} выполнена успешно на попытке {attempt + 1}")
                return result
        except Exception as e:
            last_result = e
            logger.warning(f"Попытка {attempt + 1} не удалась с неожиданной ошибкой: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
            else:
                logger.error(f"Все {max_attempts} попыток неудачны из-за неожиданных ошибок.")
                raise last_result
    if last_result:
        logger.error(f"Retry механизм исчерпан для API функции {api_func.__name__}")
        raise last_result if isinstance(last_result, Exception) else Exception(f"Retry failed, last result: {last_result}")

def get_api_error_message(error_code: str, language: str = 'ru') -> str:
    """
    Получение сообщения об ошибке API по коду
    
    Args:
        error_code: Код ошибки
        language: Язык сообщения
        
    Returns:
        str: Сообщение об ошибке
    """
    error_messages_ru = {
        'timeout': 'Превышено время ожидания ответа от API',
        'connection_error': 'Ошибка подключения к API',
        'value_error': 'Ошибка в данных API вызова',
        'general_error': 'Произошла ошибка при вызове API',
        'speechkit_error': 'Ошибка Yandex SpeechKit API',
        'deepseek_error': 'Ошибка DeepSeek API',
        'response_parse_failed': 'Не удалось обработать ответ AI',
        'upstream_unavailable': 'Внешний AI сервис временно недоступен',
        'context_length_exceeded': 'Контекст запроса превышает лимит модели',
        'request_failed': 'Не удалось выполнить запрос к AI сервису',
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
        'response_parse_failed': 'Failed to parse AI response',
        'upstream_unavailable': 'External AI service is temporarily unavailable',
        'context_length_exceeded': 'Request context exceeds model limit',
        'request_failed': 'Failed to complete AI service request',
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
    logger.debug(f"Сообщение об ошибке получено: {error_message}")
    return error_message

def format_api_error_for_analysis(
    analysis_result: Dict[str, Any], 
    language: str, 
    is_final: bool = False
) -> Tuple[str, str, str, str]:
    """
    Форматирует сообщения об ошибках API на основе результата анализа,
    специфичных для процесса анализа записей дневника.

    Args:
        analysis_result (Dict[str, Any]): Результат анализа от API сервиса.
        language (str): Код языка для локализации сообщений.
        is_final (bool): Флаг, указывающий, является ли это финальный анализ (после уточнений).

    Returns:
        Tuple[str, str, str, str]: Кортеж из 
            (comment, recommendation, analysis_text, log_message).
            - comment: Сообщение комментария для PsychoAnalysis.
            - recommendation: Рекомендация для PsychoAnalysis.
            - analysis_text: Текст анализа для PsychoAnalysis.
            - log_message: Сообщение для логирования.
    """
    try:
        default_comment = f'Анализ записан (ошибка {"финального " if is_final else ""}API)'
        default_recommendation = 'Попробуйте позже'
        default_analysis_text = f"{'Финальный ' if is_final else ''}Анализ не доступен из-за ошибки API"
        default_log_message = f"Ошибка {'финального ' if is_final else ''}анализа API"
        if not analysis_result:
            logger.warning("Пустой результат анализа передан в format_api_error_for_analysis.")
            return (
                default_comment,
                default_recommendation,
                default_analysis_text,
                default_log_message + ": Пустой результат"
            )
        success = analysis_result.get('success', False)
        if success:
            logger.warning("Функция format_api_error_for_analysis вызвана для успешного результата.")
            return (
                "Анализ записан",
                "Продолжайте вести дневник",
                "Текст проанализирован.",
                "Предупреждение: format_api_error_for_analysis вызван для успешного результата"
            )
        error_type = analysis_result.get('error', 'unknown')
        error_messages_ru = {
            'timeout': 'Превышено время ожидания ответа от API',
            'connection_error': 'Ошибка подключения к API',
            'value_error': 'Ошибка в данных API вызова',
            'general_error': 'Произошла ошибка при вызове API',
            'speechkit_error': 'Ошибка Yandex SpeechKit API',
            'deepseek_error': 'Ошибка DeepSeek API',
            'response_parse_failed': 'Не удалось обработать ответ AI',
            'upstream_unavailable': 'Внешний AI сервис временно недоступен',
            'context_length_exceeded': 'Контекст запроса превышает лимит модели',
            'request_failed': 'Не удалось выполнить запрос к AI сервису',
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
            'response_parse_failed': 'Failed to parse AI response',
            'upstream_unavailable': 'External AI service is temporarily unavailable',
            'context_length_exceeded': 'Request context exceeds model limit',
            'request_failed': 'Failed to complete AI service request',
            'unknown': 'Unknown API error',
            'api_key_missing': 'API key not configured',
            'api_key_invalid': 'Invalid API key',
            'rate_limit': 'API request limit exceeded',
            'invalid_request': 'Invalid API request',
            'server_error': 'API server error',
            'service_unavailable': 'API service unavailable'
        }
        error_messages = error_messages_ru if language == 'ru' else error_messages_en
        if error_type == 'timeout':
            comment = f'Анализ записан (превышено время ожидания {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за таймаута API."
        elif error_type == 'response_parse_failed':
            comment = f'Анализ записан (ошибка обработки ответа {"финального " if is_final else ""}AI)'
            analysis_text_suffix = " из-за ошибки обработки ответа AI."
        elif error_type in ('upstream_unavailable', 'connection_error'):
            comment = f'Анализ записан (внешний {"финальный " if is_final else ""}AI сервис недоступен)'
            analysis_text_suffix = ", так как внешний AI сервис временно недоступен."
        elif error_type == 'context_length_exceeded':
            comment = f'Анализ записан (превышен размер контекста {"финального " if is_final else ""}AI запроса)'
            analysis_text_suffix = " из-за слишком большого объема запроса к AI."
        elif error_type == 'request_failed':
            comment = f'Анализ записан (сбой запроса {"финального " if is_final else ""}AI)'
            analysis_text_suffix = " из-за сбоя запроса к AI сервису."
        elif error_type == 'value_error':
            comment = f'Анализ записан (ошибка данных {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за ошибки в данных, отправленных в API."
        elif error_type in ['speechkit_error', 'deepseek_error']:
            service_name = "Yandex SpeechKit" if error_type == 'speechkit_error' else "DeepSeek API"
            comment = f'Анализ записан (ошибка {service_name})'
            analysis_text_suffix = f" из-за ошибки {service_name}."
        elif error_type == 'rate_limit':
            comment = f'Анализ записан (превышен лимит запросов {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за превышения лимита запросов к API."
        elif error_type == 'invalid_request':
            comment = f'Анализ записан (некорректный запрос {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за некорректного запроса к API."
        elif error_type == 'server_error':
            comment = f'Анализ записан (ошибка сервера {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за внутренней ошибки сервера API."
        elif error_type == 'service_unavailable':
            comment = f'Анализ записан (сервис {"финального " if is_final else ""}API недоступен)'
            analysis_text_suffix = ", так как сервис API временно недоступен."
        else:
            comment = f'Анализ записан (неизвестная ошибка {"финального " if is_final else ""}API)'
            analysis_text_suffix = " из-за неизвестной ошибки API."
        recommendation = 'Попробуйте позже'
        analysis_text = f"{'Финальный ' if is_final else ''}Анализ не доступен{analysis_text_suffix}"
        specific_error_desc = analysis_result.get('message', error_messages.get(error_type, 'Неизвестная ошибка'))
        log_message = f"Ошибка {'финального ' if is_final else ''}API [{error_type}]: {specific_error_desc}"
        logger.error(log_message)
        return (comment, recommendation, analysis_text, log_message)
    except Exception as e:
        logger.error(f"Критическая ошибка в format_api_error_for_analysis: {e}", exc_info=True)
        return (
            default_comment,
            default_recommendation,
            default_analysis_text + " (критическая ошибка в обработчике ошибок)",
            default_log_message + f" (критическая ошибка в обработчике): {e}"
        )