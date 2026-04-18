"""
Сервис для работы с токенами авторизации через Redis.
"""
import json
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)

# TTL в секундах
TELEGRAM_AUTH_TOKEN_TTL = 300  # 5 минут
WEB_LINK_TOKEN_TTL = 600       # 10 минут

# Redis key prefixes
TELEGRAM_AUTH_KEY_PREFIX = "auth:telegram:"
WEB_LINK_KEY_PREFIX = "auth:weblink:"


def _generate_token() -> str:
    """Генерирует безопасный случайный токен."""
    return secrets.token_urlsafe(32)


def _get_redis_client():
    """Получает Redis клиент из кэша Django."""
    return cache.client.get_client()


def create_telegram_auth_token(user_id: int, ttl: int = TELEGRAM_AUTH_TOKEN_TTL) -> str:
    """
    Создаёт токен для авторизации через Telegram.
    
    Args:
        user_id: ID пользователя
        ttl: Время жизни токена в секундах (по умолчанию 5 минут)
    
    Returns:
        Токен для авторизации
    """
    token = _generate_token()
    key = f"{TELEGRAM_AUTH_KEY_PREFIX}{token}"
    
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    value = json.dumps({
        "user_id": user_id,
        "expires_at": expires_at
    })
    
    cache.set(key, value, timeout=ttl)
    logger.info(f"Создан Telegram auth токен для user_id={user_id}, TTL={ttl} сек")
    
    return token


def validate_telegram_auth_token(token: str) -> Optional[int]:
    """
    Валидирует токен авторизации через Telegram.
    
    Args:
        token: Токен для валидации
    
    Returns:
        user_id если токен валиден, иначе None
    """
    key = f"{TELEGRAM_AUTH_KEY_PREFIX}{token}"
    value = cache.get(key)
    
    if not value:
        logger.debug(f"Telegram auth токен не найден или истёк: {token[:8]}...")
        return None
    
    try:
        data = json.loads(value)
        user_id = data.get("user_id")
        expires_at = data.get("expires_at")
        
        # Проверяем, не истёк ли токен
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            logger.debug(f"Telegram auth токен истёк: {token[:8]}...")
            cache.delete(key)  # Удаляем просроченный токен
            return None
        
        # Удаляем токен после использования (одноразовый)
        cache.delete(key)
        
        logger.info(f"Telegram auth токен валиден для user_id={user_id}")
        return user_id
        
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Ошибка при парсинге токена: {e}")
        return None


def create_web_link_token(user_id: int, ttl: int = WEB_LINK_TOKEN_TTL) -> str:
    """
    Создаёт токен для привязки Telegram к web-аккаунту.
    
    Args:
        user_id: ID пользователя (web-аккаунт)
        ttl: Время жизни токена в секундах (по умолчанию 10 минут)
    
    Returns:
        Токен для привязки
    """
    token = _generate_token()
    key = f"{WEB_LINK_KEY_PREFIX}{token}"
    
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    value = json.dumps({
        "user_id": user_id,
        "expires_at": expires_at
    })
    
    cache.set(key, value, timeout=ttl)
    logger.info(f"Создан Web link токен для user_id={user_id}, TTL={ttl} сек")
    
    return token


def validate_web_link_token(token: str) -> Optional[int]:
    """
    Валидирует токен для привязки Telegram.
    
    Args:
        token: Токен для валидации
    
    Returns:
        user_id если токен валиден, иначе None
    """
    key = f"{WEB_LINK_KEY_PREFIX}{token}"
    value = cache.get(key)
    
    if not value:
        logger.debug(f"Web link токен не найден или истёк: {token[:8]}...")
        return None
    
    try:
        data = json.loads(value)
        user_id = data.get("user_id")
        expires_at = data.get("expires_at")
        
        # Проверяем, не истёк ли токен
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            logger.debug(f"Web link токен истёк: {token[:8]}...")
            cache.delete(key)
            return None
        
        # Удаляем токен после использования
        cache.delete(key)
        
        logger.info(f"Web link токен валиден для user_id={user_id}")
        return user_id
        
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Ошибка при парсинге токена: {e}")
        return None