"""
Тесты для сервиса авторизации (auth_token_service.py)
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from users.services.auth_token_service import (
    create_telegram_auth_token,
    validate_telegram_auth_token,
    create_web_link_token,
    validate_web_link_token,
    TELEGRAM_AUTH_KEY_PREFIX,
    WEB_LINK_KEY_PREFIX,
    TELEGRAM_AUTH_TOKEN_TTL,
    WEB_LINK_TOKEN_TTL,
)


class TestCreateTelegramAuthToken:
    """Тесты для create_telegram_auth_token()."""

    @patch('users.services.auth_token_service.cache')
    def test_create_token_returns_string(self, mock_cache):
        """Токен должен быть строкой."""
        mock_cache.set.return_value = True
        token = create_telegram_auth_token(user_id=123)
        assert isinstance(token, str)
        assert len(token) > 20  # token_urlsafe(32) gives ~43 chars

    @patch('users.services.auth_token_service.cache')
    def test_create_token_stores_in_cache(self, mock_cache):
        """Токен должен сохраняться в кэш."""
        mock_cache.set.return_value = True
        token = create_telegram_auth_token(user_id=123, ttl=300)
        
        assert mock_cache.set.call_count >= 1
        keys = [c[0][0] for c in mock_cache.set.call_args_list]
        assert any(k.startswith(TELEGRAM_AUTH_KEY_PREFIX) and token in k for k in keys)

    @patch('users.services.auth_token_service.cache')
    def test_create_token_with_custom_ttl(self, mock_cache):
        """Токен должен использовать переданный TTL."""
        mock_cache.set.return_value = True
        create_telegram_auth_token(user_id=123, ttl=600)
        
        timeouts = [c[1].get('timeout') for c in mock_cache.set.call_args_list]
        assert 600 in timeouts


class TestValidateTelegramAuthToken:
    """Тесты для validate_telegram_auth_token()."""

    @patch('users.services.auth_token_service.cache')
    def test_validate_valid_token(self, mock_cache):
        """Валидный токен должен возвращать user_id."""
        future = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()
        mock_cache.get.return_value = json.dumps({
            'user_id': 123,
            'expires_at': future
        })
        
        user_id = validate_telegram_auth_token('valid_token_123')
        assert user_id == 123

    @patch('users.services.auth_token_service.cache')
    def test_validate_expired_token(self, mock_cache):
        """Просроченный токен должен возвращать None."""
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()
        mock_cache.get.return_value = json.dumps({
            'user_id': 123,
            'expires_at': past
        })
        
        user_id = validate_telegram_auth_token('expired_token')
        assert user_id is None

    @patch('users.services.auth_token_service.cache')
    def test_validate_nonexistent_token(self, mock_cache):
        """Несуществующий токен должен возвращать None."""
        mock_cache.get.return_value = None
        
        user_id = validate_telegram_auth_token('nonexistent_token')
        assert user_id is None

    @patch('users.services.auth_token_service.cache')
    def test_validate_invalid_json(self, mock_cache):
        """Невалидный JSON должен возвращать None."""
        mock_cache.get.return_value = 'not_json{'
        
        user_id = validate_telegram_auth_token('invalid_json_token')
        assert user_id is None


class TestCreateWebLinkToken:
    """Тесты для create_web_link_token()."""

    @patch('users.services.auth_token_service.cache')
    def test_create_weblink_token(self, mock_cache):
        """Токен для привязки должен создаваться."""
        mock_cache.set.return_value = True
        token = create_web_link_token(user_id=456)
        
        assert isinstance(token, str)
        call_args = mock_cache.set.call_args
        key = call_args[0][0]
        assert key.startswith(WEB_LINK_KEY_PREFIX)

    @patch('users.services.auth_token_service.cache')
    def test_weblink_default_ttl(self, mock_cache):
        """Web link токен должен иметь TTL по умолчанию 10 минут."""
        mock_cache.set.return_value = True
        create_web_link_token(user_id=456)
        
        call_args = mock_cache.set.call_args
        assert call_args[1]['timeout'] == WEB_LINK_TOKEN_TTL  # 600


class TestValidateWebLinkToken:
    """Тесты для validate_web_link_token()."""

    @patch('users.services.auth_token_service.cache')
    def test_validate_valid_weblink(self, mock_cache):
        """Валидный web link токен должен возвращать user_id."""
        future = (datetime.now(timezone.utc) + timedelta(seconds=600)).timestamp()
        mock_cache.get.return_value = json.dumps({
            'user_id': 456,
            'expires_at': future
        })
        
        user_id = validate_web_link_token('valid_weblink_token')
        assert user_id == 456

    @patch('users.services.auth_token_service.cache')
    def test_validate_expired_weblink(self, mock_cache):
        """Просроченный web link токен должен возвращать None."""
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()
        mock_cache.get.return_value = json.dumps({
            'user_id': 456,
            'expires_at': past
        })
        
        user_id = validate_web_link_token('expired_weblink')
        assert user_id is None


class TestTokenUniqueness:
    """Тесты для уникальности токенов."""

    @patch('users.services.auth_token_service.cache')
    def test_tokens_are_unique(self, mock_cache):
        """Каждый вызов должен генерировать уникальный токен."""
        mock_cache.set.return_value = True
        token1 = create_telegram_auth_token(user_id=1)
        token2 = create_telegram_auth_token(user_id=1)
        assert token1 != token2

    @patch('users.services.auth_token_service.cache')
    def test_different_users_get_different_tokens(self, mock_cache):
        """Токены для разных пользователей должны быть разными."""
        mock_cache.set.return_value = True
        token1 = create_telegram_auth_token(user_id=1)
        token2 = create_telegram_auth_token(user_id=2)
        assert token1 != token2