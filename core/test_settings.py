"""
Настройки для тестов
"""
import os
import sys

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .settings import *

# Используем in-memory базу данных для тестов
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Отключаем логирование для тестов
LOGGING = {}

# Отключаем кэширование для тестов (используем in-memory кэш)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Отключаем отправку email для тестов
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Ускоряем хэширование паролей для тестов
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Для тестов aiogram
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.test_settings')