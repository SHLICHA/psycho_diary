"""
Django settings for psycho_diary project.
"""
import os
from pathlib import Path
from decouple import config
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

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
    'core'
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
        'schedule': crontab(minute=20),
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
    },
    'check-clarification-reminders': {
        'task': 'diary.tasks.reminder_ask_questions.check_clarification_reminders',
        'schedule': 300.0, # 300 секунд = 5 минут
    },
    'force-process-clarifications': { # Добавьте эту задачу
        'task': 'diary.tasks.reminder_ask_questions.force_process_clarifications', # Убедитесь в правильном пути
        'schedule': 300.0, # 5 минут, или 600 (10 мин), или 1800 (30 мин) - зависит от того, как часто вы хотите проверять
    },
    'send-morning-motivation-hourly': {
        'task': 'diary.tasks.morning_motivations.send_morning_motivation_task',
        'schedule': crontab(minute=0)
    },
    'expire_task': { # Добавьте эту задачу
        'task': 'diary.tasks.task_expiration.expire_tasks', # Убедитесь в правильном пути
        'schedule': 60.0,
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

AUTH_USER_MODEL = 'users.User'
YANDEX_SPEECHKIT_API_KEY = config('YANDEX_SPEECHKIT_API_KEY')
DEEPSEEK_API_KEY = config('DEEPSEEK_API_KEY')
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN')
DEVELOPER_CHAT_ID = os.getenv('DEVELOPER_CHAT_ID')
CRYPTOGRAPHY_KEY = os.getenv('CRYPTOGRAPHY_KEY')

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
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'colored',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'bot': {
            'handlers': ['console'],
            'level': os.getenv('LOGGING_LEVEL'),
            'propagate': False,
        },
    },
}