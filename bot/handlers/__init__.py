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

# Присваиваем имена
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


# Создаем список всех роутеров
all_routers = [
    start_router,
    diary_router,
    tasks_router,
    settings_router,
    progress_router,
    profile_router,
    help_router,
    calendar_router,
    onboarding_router,
    feedback_router
]

__all__ = [
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
    'feedback_router'
]