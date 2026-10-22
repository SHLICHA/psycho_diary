"""
Сервис для работы с токенами авторизации через Redis.
"""
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)

# TTL в секундах
TELEGRAM_AUTH_TOKEN_TTL = 300  # 5 минут
MESSENGER_AUTH_TOKEN_TTL = 300
WEB_LINK_TOKEN_TTL = 600       # 10 минут
PASSWORD_RESET_TOKEN_TTL = 1800  # 30 минут
WEB_ACCESS_CLAIM_TOKEN_TTL = 600
MERGE_EMAIL_OTP_TTL = 600

# Redis key prefixes
TELEGRAM_AUTH_KEY_PREFIX = "auth:telegram:"
MESSENGER_AUTH_KEY_PREFIX = "auth:messenger:"
WEB_LINK_KEY_PREFIX = "auth:weblink:"
MAX_LINK_KEY_PREFIX = "auth:maxlink:"
PASSWORD_RESET_KEY_PREFIX = "auth:pwreset:"
WEB_ACCESS_SET_PASSWORD_PREFIX = "auth:webclaim_pw:"
MERGE_EMAIL_OTP_PREFIX = "auth:merge_otp:"


def _generate_token() -> str:
    """Генерирует безопасный случайный токен."""
    return secrets.token_urlsafe(32)


def _generate_otp(length: int = 6) -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def create_telegram_auth_token(user_id: int, ttl: int = TELEGRAM_AUTH_TOKEN_TTL) -> str:
    """Создаёт токен для авторизации через Telegram (legacy prefix + messenger)."""
    return create_messenger_auth_token(user_id, platform='telegram', ttl=ttl)


def create_messenger_auth_token(
    user_id: int,
    platform: str = 'telegram',
    ttl: int = MESSENGER_AUTH_TOKEN_TTL,
) -> str:
    """
    Одноразовый токен handoff бот → web session/JWT.

    Пишет и legacy `auth:telegram:` (для старых клиентов), и `auth:messenger:`.
    """
    platform = (platform or 'telegram').lower()
    token = _generate_token()
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    value = json.dumps({
        'user_id': user_id,
        'platform': platform,
        'expires_at': expires_at,
    })
    cache.set(f'{MESSENGER_AUTH_KEY_PREFIX}{token}', value, timeout=ttl)
    # Backward-compatible key for TelegramAuthView / existing /web links
    if platform == 'telegram':
        cache.set(f'{TELEGRAM_AUTH_KEY_PREFIX}{token}', value, timeout=ttl)
    logger.info(
        'Создан messenger auth токен platform=%s user_id=%s TTL=%s',
        platform,
        user_id,
        ttl,
    )
    return token


def validate_telegram_auth_token(token: str) -> Optional[int]:
    """Валидирует токен Telegram/messenger; возвращает user_id."""
    user_id, _platform = validate_messenger_auth_token(token)
    return user_id


def validate_messenger_auth_token(token: str) -> Tuple[Optional[int], Optional[str]]:
    """Валидирует messenger auth token → (user_id, platform)."""
    if not token:
        return None, None
    for prefix in (MESSENGER_AUTH_KEY_PREFIX, TELEGRAM_AUTH_KEY_PREFIX):
        key = f'{prefix}{token}'
        value = cache.get(key)
        if not value:
            continue
        try:
            data = json.loads(value)
            user_id = data.get('user_id')
            expires_at = data.get('expires_at')
            platform = data.get('platform') or (
                'telegram' if prefix == TELEGRAM_AUTH_KEY_PREFIX else None
            )
            if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
                cache.delete(key)
                return None, None
            # One-time: delete both possible keys
            cache.delete(f'{MESSENGER_AUTH_KEY_PREFIX}{token}')
            cache.delete(f'{TELEGRAM_AUTH_KEY_PREFIX}{token}')
            logger.info('Messenger auth токен валиден user_id=%s platform=%s', user_id, platform)
            return user_id, platform
        except (json.JSONDecodeError, TypeError) as e:
            logger.error('Ошибка при парсинге messenger токена: %s', e)
            return None, None
    logger.debug('Messenger auth токен не найден: %s...', token[:8])
    return None, None


def create_web_link_token(user_id: int, ttl: int = WEB_LINK_TOKEN_TTL) -> str:
    """Токен привязки Telegram к web-аккаунту."""
    token = _generate_token()
    key = f'{WEB_LINK_KEY_PREFIX}{token}'
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    value = json.dumps({'user_id': user_id, 'expires_at': expires_at, 'platform': 'telegram'})
    cache.set(key, value, timeout=ttl)
    logger.info('Создан Web link токен для user_id=%s, TTL=%s сек', user_id, ttl)
    return token


def validate_web_link_token(token: str) -> Optional[int]:
    """Валидирует токен привязки Telegram."""
    key = f'{WEB_LINK_KEY_PREFIX}{token}'
    value = cache.get(key)
    if not value:
        return None
    try:
        data = json.loads(value)
        user_id = data.get('user_id')
        expires_at = data.get('expires_at')
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            cache.delete(key)
            return None
        cache.delete(key)
        return user_id
    except (json.JSONDecodeError, TypeError) as e:
        logger.error('Ошибка при парсинге web link токена: %s', e)
        return None


def create_max_link_token(user_id: int, ttl: int = WEB_LINK_TOKEN_TTL) -> str:
    """Токен привязки MAX к web-аккаунту."""
    token = _generate_token()
    key = f'{MAX_LINK_KEY_PREFIX}{token}'
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    value = json.dumps({'user_id': user_id, 'expires_at': expires_at, 'platform': 'max'})
    cache.set(key, value, timeout=ttl)
    logger.info('Создан MAX link токен для user_id=%s', user_id)
    return token


def validate_max_link_token(token: str) -> Optional[int]:
    key = f'{MAX_LINK_KEY_PREFIX}{token}'
    value = cache.get(key)
    if not value:
        return None
    try:
        data = json.loads(value)
        user_id = data.get('user_id')
        expires_at = data.get('expires_at')
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            cache.delete(key)
            return None
        cache.delete(key)
        return user_id
    except (json.JSONDecodeError, TypeError) as e:
        logger.error('Ошибка при парсинге max link токена: %s', e)
        return None


def create_password_reset_token(user_id: int, ttl: int = PASSWORD_RESET_TOKEN_TTL) -> str:
    token = _generate_token()
    key = f'{PASSWORD_RESET_KEY_PREFIX}{token}'
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    cache.set(key, json.dumps({'user_id': user_id, 'expires_at': expires_at}), timeout=ttl)
    return token


def validate_password_reset_token(token: str) -> Optional[int]:
    key = f'{PASSWORD_RESET_KEY_PREFIX}{token}'
    value = cache.get(key)
    if not value:
        return None
    try:
        data = json.loads(value)
        user_id = data.get('user_id')
        expires_at = data.get('expires_at')
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            cache.delete(key)
            return None
        cache.delete(key)
        return user_id
    except (json.JSONDecodeError, TypeError):
        return None


def create_web_access_set_password_token(user_id: int, ttl: int = WEB_ACCESS_CLAIM_TOKEN_TTL) -> str:
    """После bot-confirm claim — одноразовый токен страницы задания пароля."""
    token = _generate_token()
    key = f'{WEB_ACCESS_SET_PASSWORD_PREFIX}{token}'
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    cache.set(key, json.dumps({'user_id': user_id, 'expires_at': expires_at}), timeout=ttl)
    return token


def validate_web_access_set_password_token(token: str, *, consume: bool = True) -> Optional[int]:
    key = f'{WEB_ACCESS_SET_PASSWORD_PREFIX}{token}'
    value = cache.get(key)
    if not value:
        return None
    try:
        data = json.loads(value)
        user_id = data.get('user_id')
        expires_at = data.get('expires_at')
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            cache.delete(key)
            return None
        if consume:
            cache.delete(key)
        return user_id
    except (json.JSONDecodeError, TypeError):
        return None


def create_merge_email_otp(merge_request_id: int, ttl: int = MERGE_EMAIL_OTP_TTL) -> str:
    code = _generate_otp(6)
    key = f'{MERGE_EMAIL_OTP_PREFIX}{merge_request_id}'
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    cache.set(key, json.dumps({'code': code, 'expires_at': expires_at}), timeout=ttl)
    return code


def validate_merge_email_otp(merge_request_id: int, code: str) -> bool:
    key = f'{MERGE_EMAIL_OTP_PREFIX}{merge_request_id}'
    value = cache.get(key)
    if not value:
        return False
    try:
        data = json.loads(value)
        expires_at = data.get('expires_at')
        if expires_at and datetime.now(timezone.utc).timestamp() > expires_at:
            cache.delete(key)
            return False
        if secrets.compare_digest(str(data.get('code') or ''), str(code or '').strip()):
            cache.delete(key)
            return True
        return False
    except (json.JSONDecodeError, TypeError):
        return False
