"""
Тесты для API авторизации (views и serializers)
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_with_email(db):
    """Пользователь с email и паролем (web-аккаунт)."""
    user = User.objects.create_user(
        username='webuser',
        email='web@example.com',
        password='testpass123',
        telegram_id=None
    )
    return user


@pytest.fixture
def user_with_telegram(db):
    """Пользователь с telegram_id (bot-аккаунт)."""
    user = User.objects.create_user(
        username='telegramuser',
        email='',
        telegram_id=123456789
    )
    return user


class TestRegisterSerializer:
    """Тесты для RegisterSerializer."""

    @pytest.mark.django_db
    def test_valid_registration_data(self):
        from api.serializers import RegisterSerializer
        data = {
            'email': 'new@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123',
            'username': 'newuser'
        }
        serializer = RegisterSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    @pytest.mark.django_db
    def test_password_mismatch(self):
        from api.serializers import RegisterSerializer
        data = {
            'email': 'new@example.com',
            'password': 'password1',
            'password_confirm': 'password2',
            'username': 'newuser'
        }
        serializer = RegisterSerializer(data=data)
        assert not serializer.is_valid()
        assert 'password' in serializer.errors

    @pytest.mark.django_db
    def test_duplicate_email(self, user_with_email):
        from api.serializers import RegisterSerializer
        data = {
            'email': 'web@example.com',  # уже существует
            'password': 'securepassword123',
            'password_confirm': 'securepassword123',
            'username': 'newuser'
        }
        serializer = RegisterSerializer(data=data)
        assert not serializer.is_valid()
        assert 'email' in serializer.errors


class TestCompleteRegistrationSerializer:
    """Тесты для CompleteRegistrationSerializer."""

    @pytest.mark.django_db
    def test_valid_data(self, user_with_telegram):
        from api.serializers import CompleteRegistrationSerializer
        data = {
            'email': 'new@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123'
        }
        serializer = CompleteRegistrationSerializer(
            data=data,
            context={'user': user_with_telegram}
        )
        assert serializer.is_valid(), serializer.errors

    @pytest.mark.django_db
    def test_duplicate_email_other_user(self, user_with_email, user_with_telegram):
        from api.serializers import CompleteRegistrationSerializer
        data = {
            'email': 'web@example.com',  # принадлежит другому пользователю
            'password': 'securepassword123',
            'password_confirm': 'securepassword123'
        }
        serializer = CompleteRegistrationSerializer(
            data=data,
            context={'user': user_with_telegram}
        )
        assert not serializer.is_valid()
        assert 'email' in serializer.errors


class TestRegisterView:
    """Тесты для регистрации через API."""

    @pytest.mark.django_db
    def test_register_success(self, api_client):
        response = api_client.post('/api/v1/auth/register/', {
            'email': 'new@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123',
            'username': 'newuser'
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == 'new@example.com'

    @pytest.mark.django_db
    def test_register_password_mismatch(self, api_client):
        response = api_client.post('/api/v1/auth/register/', {
            'email': 'new@example.com',
            'password': 'password1',
            'password_confirm': 'password2',
            'username': 'newuser'
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_register_duplicate_email(self, user_with_email, api_client):
        response = api_client.post('/api/v1/auth/register/', {
            'email': 'web@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123',
            'username': 'newuser'
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTelegramAuthView:
    """Тесты для авторизации через Telegram токен."""

    @pytest.mark.django_db
    @patch('api.views.validate_telegram_auth_token')
    def test_telegram_auth_valid_token(self, mock_validate, user_with_telegram, api_client):
        mock_validate.return_value = user_with_telegram.id
        
        response = api_client.get('/api/v1/auth/telegram/', {'token': 'valid_token_123'})
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert response.data['user']['id'] == user_with_telegram.id

    @pytest.mark.django_db
    @patch('api.views.validate_telegram_auth_token')
    def test_telegram_auth_invalid_token(self, mock_validate, api_client):
        mock_validate.return_value = None
        
        response = api_client.get('/api/v1/auth/telegram/', {'token': 'invalid_token'})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['error'] == 'invalid_token'

    @pytest.mark.django_db
    def test_telegram_auth_no_token(self, api_client):
        response = api_client.get('/api/v1/auth/telegram/')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['error'] == 'token_required'


class TestLoginView:
    """Тесты для логина через email + пароль."""

    @pytest.mark.django_db
    def test_login_success(self, user_with_email, api_client):
        response = api_client.post('/api/v1/auth/login/', {
            'email': 'web@example.com',
            'password': 'testpass123'
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    @pytest.mark.django_db
    def test_login_invalid_credentials(self, user_with_email, api_client):
        response = api_client.post('/api/v1/auth/login/', {
            'email': 'web@example.com',
            'password': 'wrongpassword'
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGenerateLinkView:
    """Тесты для генерации ссылки привязки Telegram."""

    @pytest.mark.django_db
    @patch('api.views.create_web_link_token')
    def test_generate_link_authenticated(self, mock_create_token, user_with_email, api_client):
        mock_create_token.return_value = 'test_token_123'
        
        # Логинимся
        api_client.force_authenticate(user=user_with_email)
        
        response = api_client.post('/api/v1/auth/generate-link/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'link' in response.data
        assert 'test_token_123' in response.data['link']
        assert response.data['expires_in'] == 600

    @pytest.mark.django_db
    def test_generate_link_unauthenticated(self, api_client):
        response = api_client.post('/api/v1/auth/generate-link/')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestCompleteRegistrationView:
    """Тесты для завершения регистрации."""

    @pytest.mark.django_db
    def test_complete_registration(self, user_with_telegram, api_client):
        api_client.force_authenticate(user=user_with_telegram)
        
        response = api_client.post('/api/v1/auth/complete-registration/', {
            'email': 'new@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123'
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        
        # Проверяем, что email установлен
        user_with_telegram.refresh_from_db()
        assert user_with_telegram.email == 'new@example.com'

    @pytest.mark.django_db
    def test_complete_registration_unauthenticated(self, api_client):
        response = api_client.post('/api/v1/auth/complete-registration/', {
            'email': 'new@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123'
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED