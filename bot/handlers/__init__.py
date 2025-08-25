"""
Инициализация handlers
"""

# Импортируем роутеры из каждого модуля
from .start import router as start_router
from .diary import router as diary_router
from .tasks import router as tasks_router
from .settings import router as settings_router
from .progress import router as progress_router
from .help import router as help_router

# Создаем список всех роутеров
all_routers = [
    start_router,
    diary_router,
    tasks_router,
    settings_router,
    progress_router,
    help_router
]

__all__ = [
    'start_router',
    'diary_router',
    'tasks_router',
    'settings_router',
    'progress_router',
    'help_router',
    'all_routers'
]