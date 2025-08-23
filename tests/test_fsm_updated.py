"""
Обновленные тесты для системы состояний (FSM)
"""

import pytest
import os

class TestFSMStructure:
    """Тесты структуры FSM"""
    
    def test_fsm_files_exist(self):
        """Проверка существования файлов FSM"""
        fsm_files = [
            'bot/states/__init__.py',
            'bot/states/diary_states.py',
            'bot/states/task_states.py',
            'bot/states/settings_states.py',  # Добавили settings_states.py
            'bot/utils/state_manager.py',
            'bot/utils/state_utils.py'
        ]
        
        for file_path in fsm_files:
            assert os.path.exists(file_path), f"FSM файл {file_path} должен существовать"
    
    def test_fsm_syntax(self):
        """Проверка синтаксиса файлов FSM"""
        fsm_files = [
            'bot/states/diary_states.py',
            'bot/states/task_states.py',
            'bot/states/settings_states.py',
            'bot/utils/state_manager.py',
            'bot/utils/state_utils.py'
        ]
        
        for file_path in fsm_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), file_path, 'exec')
            except SyntaxError as e:
                pytest.fail(f"Синтаксическая ошибка в {file_path}: {e}")

class TestFSMStates:
    """Тесты состояний FSM"""
    
    def test_diary_states_exist(self):
        """Проверка существования состояний дневника"""
        try:
            from bot.states.diary_states import DiaryStates
            
            # Проверяем, что класс существует
            assert DiaryStates is not None
            
            # Проверяем, что основные состояния определены
            assert hasattr(DiaryStates, 'waiting_for_text_entry')
            
        except ImportError as e:
            pytest.fail(f"Ошибка импорта DiaryStates: {e}")
    
    def test_task_states_exist(self):
        """Проверка существования состояний заданий"""
        try:
            from bot.states.task_states import TaskStates
            
            # Проверяем, что класс существует
            assert TaskStates is not None
            
            # Проверяем, что основные состояния определены
            assert hasattr(TaskStates, 'waiting_for_task_completion')
            assert hasattr(TaskStates, 'describing_feelings')
            
        except ImportError as e:
            pytest.fail(f"Ошибка импорта TaskStates: {e}")
    
    def test_settings_states_exist(self):
        """Проверка существования состояний настроек"""
        try:
            from bot.states.settings_states import SettingsStates
            
            # Проверяем, что класс существует
            assert SettingsStates is not None
            
            # Проверяем, что основные состояния определены
            assert hasattr(SettingsStates, 'changing_language')
            assert hasattr(SettingsStates, 'waiting_for_language_choice')
            assert hasattr(SettingsStates, 'in_settings_menu')
            
        except ImportError as e:
            pytest.fail(f"Ошибка импорта SettingsStates: {e}")

class TestStateManagerStructure:
    """Тесты структуры менеджера состояний"""
    
    def test_state_manager_import(self):
        """Проверка импорта менеджера состояний"""
        try:
            from bot.utils.state_manager import StateManager
            manager = StateManager()
            assert manager is not None
        except ImportError as e:
            pytest.fail(f"Ошибка импорта StateManager: {e}")
        except Exception as e:
            pytest.fail(f"Ошибка создания StateManager: {e}")

def test_fsm_basic():
    """Простой тест для проверки FSM"""
    assert True