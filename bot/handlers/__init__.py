"""
Инициализация handlers
"""

# Импортируем роутеры из каждого модуля
from .calendar import router as calendar_router
from .start import router as start_router
from .diary import router as diary_router
from .tasks import router as tasks_router
from .settings import router as settings_router
from .progress import router as progress_router
from .profile import router as profile_router
from .help import router as help_router
from .onboarding import router as onboarding_router
from .feedback import router as feedback_router
from .database_handlers import router as database_router
from .therapy_chat_handlers import router as chat_router
from .payments import router as payment_router
from .admin import router as admin_router
from .fallback import router as fallback_router
from .diagnostic import router as diagnostic_router

# Присваиваем имена
admin_router.name = 'Admin_router'
calendar_router.name = "Calendar_router"
start_router.name = "Start_router"
diary_router.name = "Diary_router"
tasks_router.name = "Tasks_router"
settings_router.name = "Settings_router"
progress_router.name = "Progress_router"
help_router.name = "Help_router"
profile_router.name = "Profile_router"
onboarding_router.name = 'Onboarding_router'
feedback_router.name = "Feedback_router"
database_router.name = "Database_router"
chat_router.name = "Therapy_Chat_router"
payment_router.name = "Payment_router"
fallback_router.name = 'Fallback router'
diagnostic_router.name = 'Diagnostic_router'

# Создаем список всех роутеров
all_routers = [
    admin_router,
    diagnostic_router,  # Добавляем в начало для приоритета
    start_router,
    diary_router,
    tasks_router,
    settings_router,
    progress_router,
    profile_router,
    help_router,
    calendar_router,
    onboarding_router,
    feedback_router,
    database_router,
    chat_router,
    payment_router,
    fallback_router
]

__all__ = [
    'admin_router',
    'diagnostic_router',
    'start_router',
    'diary_router',
    'tasks_router',
    'settings_router',
    'progress_router',
    'profile_router',
    'help_router',
    'calendar_router',
    'all_routers',
    'onboarding_router',
    'feedback_router',
    'database_router',
    'chat_router',
    'payment_router',
    'fallback_router'
]