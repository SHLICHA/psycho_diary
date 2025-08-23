"""
Инициализация состояний FSM
"""

from .diary_states import DiaryStates
from .task_states import TaskStates
from .settings_states import SettingsStates

# Экспорт всех состояний
__all__ = [
    'DiaryStates',
    'TaskStates', 
    'SettingsStates'
]

# Создание списка всех групп состояний для удобства
ALL_STATE_GROUPS = [
    DiaryStates,
    TaskStates,
    SettingsStates
]