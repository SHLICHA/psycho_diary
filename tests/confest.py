"""
Базовая конфигурация для тестов
"""
import os
import sys
import django

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.test_settings')

# Импортируем и настраиваем Django до импортов моделей
import django
from django.conf import settings

if not settings.configured:
    django.setup()

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Автоматически включает доступ к базе данных для всех тестов
    """
    pass

@pytest.fixture
def sample_user():
    """Фикстура для создания тестового пользователя"""
    user = User.objects.create_user(
        username='testuser',
        telegram_id=123456789,
        language='ru',
        password='testpass123'
    )
    return user

@pytest.fixture
def sample_user_en():
    """Фикстура для создания тестового пользователя с английским языком"""
    user = User.objects.create_user(
        username='testuser_en',
        telegram_id=987654321,
        language='en',
        password='testpass123'
    )
    return user

@pytest.fixture
def sample_diary_entry(sample_user):
    """Фикстура для создания тестовой записи в дневнике"""
    from diary.models import DiaryEntry
    
    entry = DiaryEntry.objects.create(
        user=sample_user,
        text='Тестовая запись о прекрасном дне',
        language='ru',
        word_count=5
    )
    return entry

# Фикстура для очистки кэша
@pytest.fixture(autouse=True)
def clear_cache():
    """Очистка кэша перед каждым тестом"""
    from django.core.cache import cache
    cache.clear()