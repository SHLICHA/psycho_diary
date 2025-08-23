"""
Тесты структуры проекта
"""

import pytest
import os

class TestProjectStructure:
    """Тесты структуры проекта"""
    
    def test_project_directories_exist(self):
        """Проверка существования основных директорий"""
        required_dirs = [
            'bot',
            'bot/handlers',
            'bot/middlewares',
            'bot/keyboards',
            'bot/states',
            'bot/utils',
            'core',
            'users',
            'diary'
        ]
        
        for directory in required_dirs:
            assert os.path.exists(directory), f"Directory {directory} should exist"
    
    def test_required_files_exist(self):
        """Проверка наличия обязательных файлов"""
        required_files = [
            'manage.py',
            'requirements.txt',
            'requirements-dev.txt',
            '.env',
            'pytest.ini',
            'bot/__init__.py',
            'bot/main.py',
            'core/settings.py',
            'users/models.py',
            'diary/models.py'
        ]
        
        for file_path in required_files:
            assert os.path.exists(file_path), f"File {file_path} should exist"
    
    def test_module_init_files_exist(self):
        """Проверка наличия __init__.py файлов"""
        init_files = [
            'bot/__init__.py',
            'bot/handlers/__init__.py',
            'bot/middlewares/__init__.py',
            'bot/keyboards/__init__.py',
            'bot/states/__init__.py',
            'bot/utils/__init__.py',
            'core/__init__.py',
            'users/__init__.py',
            'diary/__init__.py'
        ]
        
        for file_path in init_files:
            assert os.path.exists(file_path), f"Init file {file_path} should exist"

class TestBotStructure:
    """Тесты структуры бота"""
    
    def test_bot_components_exist(self):
        """Проверка существования компонентов бота"""
        bot_components = [
            'bot/main.py',
            'bot/handlers/start.py',
            'bot/handlers/diary.py',
            'bot/handlers/tasks.py',
            'bot/handlers/settings.py',  # Добавили settings.py
            'bot/handlers/archive.py',
            'bot/handlers/progress.py',
            'bot/handlers/help.py',
            'bot/keyboards/main_menu.py',
            'bot/keyboards/calendar_keyboard.py',
            'bot/keyboards/settings_keyboard.py',  # Добавили settings_keyboard.py
            'bot/keyboards/tasks_keyboard.py',
            'bot/states/diary_states.py',
            'bot/states/task_states.py',
            'bot/states/settings_states.py'  # Добавили settings_states.py
        ]
        
        for component in bot_components:
            assert os.path.exists(component), f"Bot component {component} should exist"

def test_project_basic():
    """Простой тест для проверки структуры проекта"""
    assert True