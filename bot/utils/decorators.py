"""
Декораторы для обработки ошибок и логирования
"""

import logging
import asyncio
from typing import Any, Callable, Awaitable
from functools import wraps

logger = logging.getLogger(__name__)

def async_error_handler(logger_name: str = None):
    """
    Декоратор для обработки ошибок в асинхронных функциях.
    
    Args:
        logger_name: Имя логгера (если None, используется корневой логгер)
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            func_logger = logging.getLogger(logger_name) if logger_name else logger
            try:
                result = await func(*args, **kwargs)
                return result
                
            except asyncio.TimeoutError as e:
                func_logger.error(f"Таймаут в функции {func.__name__}: {e}")
                return {
                    'success': False,
                    'error': 'timeout',
                    'message': 'Превышено время ожидания'
                }
            except Exception as e:
                func_logger.error(
                    f"Ошибка в функции {func.__name__}: {e}", 
                    exc_info=True
                )
                return {
                    'success': False,
                    'error': 'internal_error',
                    'message': f'Внутренняя ошибка: {str(e)}'
                }
                
        return wrapper
    return decorator

def database_retry(max_retries: int = 3, delay: float = 0.1):
    """
    Декоратор для повторных попыток выполнения операций с БД.
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Попытка {attempt + 1}/{max_retries} не удалась "
                        f"в функции {func.__name__}: {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logger.error(
                            f"Все {max_retries} попыток не удались "
                            f"в функции {func.__name__}"
                        )
                        raise last_exception
            raise last_exception 
        return wrapper
    return decorator