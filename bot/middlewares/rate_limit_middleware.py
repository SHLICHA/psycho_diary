"""
Middleware для ограничения частоты запросов (rate limiting)
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.fsm.context import FSMContext
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
        if isinstance(event, Message):
            user = data.get('user')
            language = data.get('language', 'ru')
            fsm_context: FSMContext = data.get('state')
            current_state = await fsm_context.get_state() if fsm_context else None
            if current_state and current_state.startswith('OnboardingStates:'):
                logger.debug(
                    f"Пропуск проверки лимита для пользователя {getattr(user, 'telegram_id', 'unknown')} в состоянии {current_state}"
                )
                result = await handler(event, data)
                return result
            if user:
                scope, limit, period = self._resolve_scope_and_limit(current_state)
                cache_key = self._build_cache_key(user.telegram_id, scope)

                if await self._is_rate_limited(cache_key, limit, period):
                    await self._send_rate_limit_message(event, language)
                    logger.warning(
                        f"Превышен лимит запросов для пользователя {user.telegram_id}: scope={scope}, limit={limit}, period={period}s"
                    )
                    return
                await self._record_request(cache_key, period)
        result = await handler(event, data)
        return result

    def _resolve_scope_and_limit(self, current_state: str | None) -> tuple[str, int, int]:
        """Return scope and limits for current handler state."""
        if current_state and current_state.endswith('waiting_for_text_entry'):
            return 'entries', 3, 60
        return 'default', MESSAGES_PER_MINUTE_LIMIT, 60

    def _build_cache_key(self, telegram_id: int, scope: str) -> str:
        return f"rate_limit:{scope}:{telegram_id}"
    
    async def _is_rate_limited(self, cache_key: str, limit: int, period: int) -> bool:
        """
        Проверка, превышен ли лимит запросов
        """
        try:
            request_times = cache.get(cache_key, [])
            current_time = time.time()
            recent_requests = [
                req_time for req_time in request_times 
                if current_time - req_time < period
            ]
            is_limited = len(recent_requests) >= limit
            logger.debug(f"Лимит запросов ({cache_key}): {len(recent_requests)}/{limit} за {period}s")
            return is_limited
        except Exception as e:
            logger.error(f"Ошибка при проверке лимита запросов: {e}")
            return False
        
    async def _record_request(self, cache_key: str, period: int):
        """
        Запись запроса в историю
        """
        try:
            request_times = cache.get(cache_key, [])
            current_time = time.time()
            request_times.append(current_time)
            filtered_times = [
                req_time for req_time in request_times 
                if current_time - req_time < period
            ]
            cache.set(cache_key, filtered_times, period)
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
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о лимите: {e}")