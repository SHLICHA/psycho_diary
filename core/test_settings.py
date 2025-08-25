# core/test_settings.py
"""
Настройки Django для тестовой среды.
Переопределяет параметры из основных настроек для тестов.
"""

# Импортируем все настройки из основного файла settings.py
try:
    from .settings import *
except ImportError:
    raise ImportError(
        "Не удалось импортировать основные настройки. "
        "Убедитесь, что файл core/settings.py существует."
    )

import os
import sys

# Добавляем путь к проекту в sys.path для корректной работы импортов
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if os.path.join(PROJECT_ROOT, 'core') not in sys.path:
    sys.path.append(os.path.join(PROJECT_ROOT, 'core'))

# ======================
# ОСНОВНЫЕ НАСТРОЙКИ
# ======================

# Упрощенный SECRET_KEY для тестов
SECRET_KEY = 'test-secret-key-for-pytest-django-abcdefghijklmnopqrstuvwxyz1234567890!@#$%^&*()'

# ======================
# БАЗА ДАННЫХ
# ======================

# Используем in-memory SQLite для быстрых тестов
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# ======================
# КЕШИРОВАНИЕ
# ======================

# Используем локальный memory cache для тестов
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

# ======================
# ЛОГИРОВАНИЕ
# ======================

# Минимальная настройка логирования для тестов
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'WARNING',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ======================
# ПРОЧИЕ НАСТРОЙКИ
# ======================

# Отключаем миграции для ускорения создания тестовой БД
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Убедимся, что тесты не отправляют реальные email'ы
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Ускоряем хэширование паролей для тестов
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Устанавливаем переменную окружения для Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.test_settings')
