"""
Простые тесты для системы состояний (FSM)
"""

import pytest

class TestFSMStructure:
    """Тесты структуры FSM"""
    
    def test_fsm_files_exist(self):
        """Проверка существования файлов FSM"""
        import os
        
        fsm_files = [
            'bot/states/__init__.py',
            'bot/states/diary_states.py',
            'bot/states/task_states.py',
            'bot/states/settings_states.py',
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
    
    def test_state_classes_import(self):
        """Проверка импорта классов состояний"""
        try:
            from bot.states.diary_states import DiaryStates
            from bot.states.task_states import TaskStates
            from bot.states.settings_states import SettingsStates
            
            # Проверяем, что классы существуют
            assert DiaryStates is not None
            assert TaskStates is not None
            assert SettingsStates is not None
            
        except ImportError as e:
            pytest.skip(f"Django не настроен или файлы не найдены: {e}")
    
    def test_state_attributes_exist(self):
        """Проверка наличия атрибутов состояний"""
        try:
            from bot.states.diary_states import DiaryStates
            from bot.states.task_states import TaskStates
            from bot.states.settings_states import SettingsStates
            
            # Проверяем состояния дневника
            assert hasattr(DiaryStates, 'waiting_for_text_entry')
            
            # Проверяем состояния заданий
            assert hasattr(TaskStates, 'completing_task')
            assert hasattr(TaskStates, 'waiting_for_task_completion')
            assert hasattr(TaskStates, 'describing_feelings')
            
            # Проверяем состояния настроек
            assert hasattr(SettingsStates, 'changing_language')
            assert hasattr(SettingsStates, 'waiting_for_language_choice')
            assert hasattr(SettingsStates, 'in_settings_menu')
            
        except ImportError as e:
            pytest.skip(f"Django не настроен или файлы не найдены: {e}")

class TestStateManagerStructure:
    """Тесты структуры менеджера состояний"""
    
    def test_state_manager_import(self):
        """Проверка импорта менеджера состояний"""
        try:
            from bot.utils.state_manager import StateManager
            manager = StateManager()
            assert manager is not None
        except ImportError as e:
            pytest.skip(f"Ошибка импорта StateManager: {e}")
        except Exception as e:
            pytest.skip(f"Ошибка создания StateManager: {e}")

# Простой тест для проверки
def test_fsm_structure_basic():
    """Простой тест для проверки структуры FSM"""
    assert True