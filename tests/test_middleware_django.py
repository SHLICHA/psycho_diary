"""
Django тесты для middleware
"""

import pytest
import os
import django
from django.conf import settings

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.test_settings')

# Инициализируем Django если еще не инициализирован
if not settings.configured:
    django.setup()

@pytest.mark.django_db
class TestUserMiddlewareDjango:
    """Django тесты UserMiddleware"""
    
    def test_user_middleware_import(self):
        """Тест импорта UserMiddleware с Django"""
        try:
            from bot.middlewares.user_middleware import UserMiddleware
            middleware = UserMiddleware()
            assert middleware is not None
        except Exception as e:
            pytest.fail(f"Failed to import UserMiddleware: {e}")
    
    def test_user_middleware_methods(self):
        """Тест методов UserMiddleware"""
        from bot.middlewares.user_middleware import UserMiddleware
        
        middleware = UserMiddleware()
        # Проверяем, что middleware имеет нужные методы
        assert hasattr(middleware, '__call__')
        assert callable(middleware.__call__)

@pytest.mark.django_db
class TestLanguageMiddlewareDjango:
    """Django тесты LanguageMiddleware"""
    
    def test_language_middleware_import(self):
        """Тест импорта LanguageMiddleware с Django"""
        try:
            from bot.middlewares.language_middleware import LanguageMiddleware
            middleware = LanguageMiddleware()
            assert middleware is not None
        except Exception as e:
            pytest.fail(f"Failed to import LanguageMiddleware: {e}")

@pytest.mark.django_db
class TestRateLimitMiddlewareDjango:
    """Django тесты RateLimitMiddleware"""
    
    def test_rate_limit_middleware_import(self):
        """Тест импорта RateLimitMiddleware с Django"""
        try:
            from bot.middlewares.rate_limit_middleware import RateLimitMiddleware
            middleware = RateLimitMiddleware()
            assert middleware is not None
        except Exception as e:
            pytest.fail(f"Failed to import RateLimitMiddleware: {e}")

@pytest.mark.django_db
class TestAnalyticsMiddlewareDjango:
    """Django тесты AnalyticsMiddleware"""
    
    def test_analytics_middleware_import(self):
        """Тест импорта AnalyticsMiddleware с Django"""
        try:
            from bot.middlewares.analytics_middleware import AnalyticsMiddleware
            middleware = AnalyticsMiddleware()
            assert middleware is not None
        except Exception as e:
            pytest.fail(f"Failed to import AnalyticsMiddleware: {e}")