"""
Middleware для ограничения частоты запросов (rate limiting)
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from core.constants import MESSAGES_PER_MINUTE_LIMIT
from django.core.cache import cache

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware для ограничения частоты запросов
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        logger.info("Вызов RateLimitMiddleware")
        
        # Обрабатываем только сообщения
        if isinstance(event, Message):
            user = data.get('user')
            language = data.get('language', 'ru')
            
            if user:
                if await self._is_rate_limited(user.telegram_id):
                    # Отправляем сообщение о превышении лимита
                    await self._send_rate_limit_message(event, language)
                    logger.warning(f"Превышен лимит запросов для пользователя {user.telegram_id}")
                    return  # Не передаем управление дальше
                
                # Записываем запрос в историю
                await self._record_request(user.telegram_id)
                logger.info(f"Запрос записан в историю для пользователя {user.telegram_id}")
        
        logger.info("Вызов следующего middleware/handler")
        result = await handler(event, data)
        logger.info("Handler выполнен успешно")
        return result
    
    async def _is_rate_limited(self, telegram_id: int) -> bool:
        """
        Проверка, превышен ли лимит запросов
        """
        try:
            logger.info(f"Проверка лимита запросов для пользователя {telegram_id}")
            cache_key = f"rate_limit:{telegram_id}"
            request_times = cache.get(cache_key, [])
            
            # Фильтруем запросы за последнюю минуту
            current_time = time.time()
            recent_requests = [
                req_time for req_time in request_times 
                if current_time - req_time < 60  # 60 секунд = 1 минута
            ]
            
            # Проверяем лимит
            is_limited = len(recent_requests) >= MESSAGES_PER_MINUTE_LIMIT
            logger.info(f"Лимит запросов: {len(recent_requests)}/{MESSAGES_PER_MINUTE_LIMIT}")
            return is_limited
            
        except Exception as e:
            logger.error(f"Ошибка при проверке лимита запросов: {e}")
            return False  # В случае ошибки не блокируем пользователя
    
    async def _record_request(self, telegram_id: int):
        """
        Запись запроса в историю
        """
        try:
            logger.info(f"Запись запроса в историю для пользователя {telegram_id}")
            cache_key = f"rate_limit:{telegram_id}"
            request_times = cache.get(cache_key, [])
            
            # Добавляем текущее время
            current_time = time.time()
            request_times.append(current_time)
            
            # Оставляем только последние 10 минут (на всякий случай)
            filtered_times = [
                req_time for req_time in request_times 
                if current_time - req_time < 600
            ]
            
            # Сохраняем в кэш на 10 минут
            cache.set(cache_key, filtered_times, 600)
            logger.info(f"История запросов обновлена для пользователя {telegram_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при записи запроса: {e}")
    
    async def _send_rate_limit_message(self, message: Message, language: str):
        """
        Отправка сообщения о превышении лимита
        """
        from messages import get_message
        
        try:
            rate_limit_msg = get_message('rate_limit_exceeded', language)
            await message.answer(rate_limit_msg)
            logger.info(f"Сообщение о превышении лимита отправлено пользователю {message.from_user.id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о лимите: {e}")