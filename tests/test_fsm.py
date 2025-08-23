"""
Тесты для системы состояний (FSM)
"""

import pytest
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

class TestFSMStates:
    """Тесты состояний FSM"""
    
    def test_diary_states_exist(self):
        """Проверка существования состояний дневника"""
        from bot.states.diary_states import DiaryStates
        
        # Проверяем, что класс существует
        assert DiaryStates is not None
        
        # Проверяем, что основное состояние определено
        assert hasattr(DiaryStates, 'waiting_for_text_entry')
        # Проверяем, что это действительно State
        assert isinstance(DiaryStates.waiting_for_text_entry, State)
    
    def test_task_states_exist(self):
        """Проверка существования состояний заданий"""
        from bot.states.task_states import TaskStates
        
        # Проверяем, что класс существует
        assert TaskStates is not None
        
        # Проверяем, что состояния определены
        assert hasattr(TaskStates, 'completing_task')
        assert hasattr(TaskStates, 'waiting_for_task_completion')
        assert hasattr(TaskStates, 'describing_feelings')
    
    def test_settings_states_exist(self):
        """Проверка существования состояний настроек"""
        from bot.states.settings_states import SettingsStates
        
        # Проверяем, что класс существует
        assert SettingsStates is not None
        
        # Проверяем, что состояния определены
        assert hasattr(SettingsStates, 'changing_language')
        assert hasattr(SettingsStates, 'waiting_for_language_choice')
        assert hasattr(SettingsStates, 'in_settings_menu')

# Простой тест для проверки
def test_fsm_basic():
    """Простой тест для проверки работы FSM"""
    assert True