"""
Django settings for psycho_diary project.
"""
import os
from pathlib import Path
from datetime import timedelta
from decouple import config
from dotenv import load_dotenv
from celery.schedules import crontab


def _parse_int_csv(value: str) -> list[int]:
    """Parse comma-separated integers from env var into a clean list."""
    items: list[int] = []
    for raw in (value or '').split(','):
        raw = raw.strip()
        if not raw:
            continue
        try:
            items.append(int(raw))
        except ValueError:
            continue
    return items


load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# HTTPS за nginx: доверенные Origin для CSRF (админка/формы).
# Пример: https://psychodiary.ru,https://www.psychodiary.ru
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()],
)

# nginx терминирует TLS и передаёт X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users',
    'diary',
    'core',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'django_celery_beat',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': 0,  # ← отключить переиспользование соединений
        'OPTIONS': {
            'sslmode': 'require',
        },
        'NAME': config('DATABASE_NAME'),
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_PASSWORD'),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


CELERY_BEAT_SCHEDULE = {
    'run-daily-analysis-check': {
        'task': 'diary.tasks.scheduler_tasks.schedule_daily_analyses',
        'schedule': crontab(minute=1),
    },
    'send-timezone-reminder': {
        'task': 'diary.tasks.scheduler_tasks.send_timezone_reminder',
        'schedule': crontab(minute=58, hour=13),
    },
    'send-entry-reminders': {
        'task': 'diary.tasks.reminder_tasks.send_entry_reminders',
        'schedule': crontab(minute=0),
    },
    'schedule-weekly-analyses': {
        'task': 'diary.tasks.weekly_analisys_tasks.schedule_weekly_analyses_task',
        'schedule': crontab(minute=0),
        #'schedule': 120,
    },
    'run-profile-cleanup-daily': {
        'task': 'diary.tasks.profile_cleanup.run_profile_cleanup',
        'schedule': crontab(minute=15, hour=4),
    },
    'check-clarification-reminders': {
        'task': 'diary.tasks.reminder_ask_questions.check_clarification_reminders',
        'schedule': 600, # 300 секунд = 5 минут
    },
    'force-process-clarifications': { # Добавьте эту задачу
        'task': 'diary.tasks.reminder_ask_questions.force_process_clarifications', # Убедитесь в правильном пути
        'schedule': 60, # 5 минут, или 600 (10 мин), или 1800 (30 мин) - зависит от того, как часто вы хотите проверять
    },
    'send-morning-motivation-hourly': {
        'task': 'diary.tasks.morning_motivations.send_morning_motivation_task',
        'schedule': crontab(minute=0)
        #'schedule': 30,
    },
    'expire_task': { # Добавьте эту задачу
        'task': 'diary.tasks.task_expiration.expire_tasks', # Убедитесь в правильном пути
        'schedule': 60.0,
     },
    'run-garbage-collection-hourly': {
        'task': 'diary.tasks.garbage_collector_task.run_garbage_collection',
        'schedule': crontab(minute=30, hour='*'),  # Каждый час
        #'schedule': 30,
    },
    'purge-merged-users-daily': {
        'task': 'diary.tasks.account_merge_tasks.purge_merged_users_task',
        'schedule': crontab(minute=40, hour=4),
    },
       # 5 минут, или 600 (10 мин), или 1800 (30 мин) - зависит от того, как часто вы хотите проверять
    #'send-test-morning-motivation-every-minute-during-test': { # Имя задачи
    #     'task': 'diary.tasks.test_morning.send_entry_reminders',
    #     'schedule': 60.0, # Каждую минуту
    #},
}

CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Используем БД для хранения расписания Celery Beat
# Это предотвращает повторный запуск задач после перезапуска контейнера
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

AUTH_USER_MODEL = 'users.User'
YANDEX_SPEECHKIT_API_KEY = config('YANDEX_SPEECHKIT_API_KEY')
DEEPSEEK_API_KEY = config('DEEPSEEK_API_KEY')
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN')
AI_INACTIVITY_DAYS = config('AI_INACTIVITY_DAYS', default=30, cast=int)
DEVELOPER_CHAT_ID = os.getenv('DEVELOPER_CHAT_ID')
# MAX user id разработчика (для admin-команд без связанного telegram_id)
DEVELOPER_MAX_USER_ID = os.getenv('DEVELOPER_MAX_USER_ID', '')
CRYPTOGRAPHY_KEY = os.getenv('CRYPTOGRAPHY_KEY')

YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
BOT_USERNAME = os.getenv('BOT_USERNAME')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://app.com').rstrip('/')

# Transactional email (password reset, merge OTP for web-only targets)
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Psycho Diary <noreply@localhost>')
EMAIL_FAIL_SILENTLY = config('EMAIL_FAIL_SILENTLY', default=True, cast=bool)
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST
    else 'django.core.mail.backends.console.EmailBackend'
)

PREMIUM_PRICE_MONTH = int(os.getenv('PREMIUM_PRICE_MONTH', 199))
PREMIUM_PRICE_YEAR = int(os.getenv('PREMIUM_PRICE_YEAR', 1999))
TOKEN_PRICE_PER_UNIT = int(os.getenv('TOKEN_PRICE_PER_UNIT', 5))
TOKEN_PACK_10 = int(os.getenv('TOKEN_PACK_10', 50))
TOKEN_PACK_50 = int(os.getenv('TOKEN_PACK_50', 250))
TOKEN_PACK_100 = int(os.getenv('TOKEN_PACK_100', 450))
TOKEN_PACK_200 = int(os.getenv('TOKEN_PACK_200', 800))
TOKEN_PACK_500 = int(os.getenv('TOKEN_PACK_500', 2000))

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": CELERY_BROKER_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        }
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'colored': {
            '()': 'colorlog.ColoredFormatter',
            'format': '%(log_color)s%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d - %(funcName)s] %(message)s',
        },
        'file_formatter': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'colored',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'bot_debug.log',
            'formatter': 'file_formatter',
            'level': 'DEBUG',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'WARNING',  # Только предупреждения и ошибки
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['console'],
            'level': 'WARNING',  # Только предупреждения и ошибки
            'propagate': False,
        },
        'celery.redirected': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'bot': {
            'handlers': ['console', 'file'],
            'level': os.getenv('LOGGING_LEVEL'),
            'propagate': False,
        },
        'aiogram.event': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', # По умолчанию требовать аутентификацию
    ],
    'DEFAULT_THROTTLE_RATES': {
        'auth': '10/minute',
        'refresh': '20/minute',
        'link_generation': '6/hour',
        'monitoring': '30/minute',
        'monitoring_heavy': '10/minute',
        'entry_mutation': '30/minute',
        'task_mutation': '30/minute',
        'settings_mutation': '30/minute',
        'payment_mutation': '20/minute',
        'admin_mutation': '10/minute',
    },
    'EXCEPTION_HANDLER': 'api.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Psycho Diary API',
    'DESCRIPTION': 'REST API for Psycho Diary application',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'DISABLE_ERRORS_AND_WARNINGS': True,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# ============================================================
# Compressed Profile Feature Flags
# ============================================================
COMPRESSED_PROFILE_ENABLED = True  # Мастер-переключатель
USE_LITE_V2 = False                 # Использовать v2 промпты для LITE (пока False)

# ============================================================
# Monitoring Access Controls
# ============================================================
MONITORING_REQUIRE_PRIVILEGED = config('MONITORING_REQUIRE_PRIVILEGED', default=False, cast=bool)
MONITORING_PRIVILEGED_USER_IDS = _parse_int_csv(config('MONITORING_PRIVILEGED_USER_IDS', default=''))
MONITORING_ALLOW_LEGACY_TELEGRAM_ID = config('MONITORING_ALLOW_LEGACY_TELEGRAM_ID', default=True, cast=bool)

# ============================================================
# Identity merge / conflict flow
# ============================================================
EMAIL_MERGE_CONFIRMATION_ENABLED = config('EMAIL_MERGE_CONFIRMATION_ENABLED', default=False, cast=bool)
EMAIL_MERGE_WEB_CONFIRM_FALLBACK_ENABLED = config(
    'EMAIL_MERGE_WEB_CONFIRM_FALLBACK_ENABLED',
    default=False,
    cast=bool,
)
# После dual-confirm выполнять атомарный data-merge (дневник, ids, токены/премиум).
EMAIL_MERGE_EXECUTE_ENABLED = config('EMAIL_MERGE_EXECUTE_ENABLED', default=False, cast=bool)

# ============================================================
# Публичный домен (единый источник webhook URL для MAX и оплаты)
# ============================================================
# Пусто → локальная разработка (MAX polling, payment webhook выключен).
# Пример prod: https://www.psychodiary.ru
from core.public_domain import (
    MAX_WEBHOOK_PATH,
    PAYMENT_WEBHOOK_PATH,
    normalize_public_domain,
    resolve_max_transport_mode,
    resolve_max_webhook_url,
    resolve_payment_webhook_url,
)

BOT_PUBLIC_DOMAIN = normalize_public_domain(config('BOT_PUBLIC_DOMAIN', default=''))
PAYMENT_WEBHOOK_URL = resolve_payment_webhook_url(
    public_domain=BOT_PUBLIC_DOMAIN,
    explicit_webhook_url=config('PAYMENT_WEBHOOK_URL', default=''),
)
PAYMENT_WEBHOOK_ENABLED = bool(PAYMENT_WEBHOOK_URL)

# ============================================================
# MAX transport (поэтапное включение)
# ============================================================
MAX_TRANSPORT_ENABLED = config('MAX_TRANSPORT_ENABLED', default=False, cast=bool)
# Пустой MAX_TRANSPORT_MODE → auto: webhook при BOT_PUBLIC_DOMAIN / MAX_WEBHOOK_URL, иначе polling.
_MAX_TRANSPORT_MODE_RAW = config('MAX_TRANSPORT_MODE', default='').strip()
_MAX_WEBHOOK_URL_RAW = config('MAX_WEBHOOK_URL', default='')
MAX_WEBHOOK_URL = resolve_max_webhook_url(
    public_domain=BOT_PUBLIC_DOMAIN,
    explicit_webhook_url=_MAX_WEBHOOK_URL_RAW,
)
MAX_TRANSPORT_MODE = resolve_max_transport_mode(
    explicit_mode=_MAX_TRANSPORT_MODE_RAW,
    public_domain=BOT_PUBLIC_DOMAIN,
    explicit_webhook_url=_MAX_WEBHOOK_URL_RAW,
)
MAX_BOT_TOKEN = config('MAX_BOT_TOKEN', default='')
# Username бота в MAX (без @) для deep links: https://max.ru/<username>?start=...
MAX_BOT_USERNAME = config('MAX_BOT_USERNAME', default='').strip().lstrip('@')
MAX_API_BASE_URL = config('MAX_API_BASE_URL', default='https://platform-api2.max.ru')
MAX_API_TIMEOUT_SECONDS = config('MAX_API_TIMEOUT_SECONDS', default=10, cast=int)
MAX_WEBHOOK_SECRET = config('MAX_WEBHOOK_SECRET', default='')
MAX_POLLING_TIMEOUT_SECONDS = config('MAX_POLLING_TIMEOUT_SECONDS', default=30, cast=int)
MAX_POLLING_IDLE_SLEEP_SECONDS = config('MAX_POLLING_IDLE_SLEEP_SECONDS', default=0.0, cast=float)
MAX_RATE_LIMIT_RPS = config('MAX_RATE_LIMIT_RPS', default=10, cast=float)
MAX_RATE_LIMIT_BURST = config('MAX_RATE_LIMIT_BURST', default=50, cast=int)
MAX_MESSAGE_MAX_LENGTH = config('MAX_MESSAGE_MAX_LENGTH', default=3500, cast=int)
MAX_STATE_TTL_SECONDS = config('MAX_STATE_TTL_SECONDS', default=3600, cast=int)
# CA Минцифры для TLS к platform-api2.max.ru (через запятую).
# По умолчанию: intermediate + root из корня репозитория.
_default_max_api_ca_paths = ','.join(
    [
        str(BASE_DIR / 'russian_trusted_sub_ca_2024_pem.crt'),
        str(BASE_DIR / 'russian_trusted_root_ca_pem.crt'),
    ]
)
MAX_API_CA_CERT_PATHS = [
    path.strip()
    for path in config('MAX_API_CA_CERT_PATHS', default=_default_max_api_ca_paths).split(',')
    if path.strip()
]