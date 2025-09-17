"""
Rate limiting для API и пользователей - УПРОЩЕННАЯ ВЕРСИЯ
"""

import logging
import time
from typing import Optional
from django.core.cache import cache

logger = logging.getLogger(__name__)

class RateLimiter:
    """Простой и надежный rate limiter"""
    
    def __init__(self):
        self.limits = {
            'user': (3, 60),  # 3 запроса в минуту для пользователей
            'api': (10, 60),  # 10 запросов в минуту для API
        }
    
    async def is_rate_limited(self, key: str, limit: int = 3, period: int = 60) -> bool:
        """Версия с подробным логированием"""
        try:
            from time import time
            current_time = int(time())
            window_key = f"ratelimit:{key}:{current_time // period}"
            
            current_count = cache.get(window_key, 0)
            logger.debug(f"Rate limit check: {window_key} = {current_count}/{limit}")
            
            if current_count >= limit:
                logger.info(f"Rate limit EXCEEDED: {key}")
                return True
                
            cache.set(window_key, current_count + 1, timeout=period)
            logger.debug(f"Rate limit incremented: {key}")
            return False
            
        except Exception as e:
            logger.error(f"Rate limiter error: {e}", exc_info=True)
            return False

rate_limiter = RateLimiter()