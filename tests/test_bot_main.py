"""
Тесты для основного файла бота
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, Mock

class TestBotMain:
    """Тесты основного файла бота"""
    
    def test_main_file_exists(self):
        """Проверка существования основного файла бота"""
        assert os.path.exists('bot/main.py'), "Main bot file should exist"
    
    def test_handlers_structure(self):
        """Проверка структуры handlers"""
        handler_files = [
            'bot/handlers/__init__.py',
            'bot/handlers/start.py'
        ]
        
        for file_path in handler_files:
            assert os.path.exists(file_path), f"Handler file {file_path} should exist"
    
    def test_keyboards_structure(self):
        """Проверка структуры keyboards"""
        keyboard_files = [
            'bot/keyboards/__init__.py',
            'bot/keyboards/main_menu.py'
        ]
        
        for file_path in keyboard_files:
            assert os.path.exists(file_path), f"Keyboard file {file_path} should exist"
    
    def test_management_command_exists(self):
        """Проверка существования management команды"""
        assert os.path.exists('core/management/commands/runbot.py'), \
            "Management command file should exist"
    
    def test_main_file_syntax(self):
        """Проверка синтаксиса основного файла"""
        try:
            with open('bot/main.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/main.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Syntax error in main bot file: {e}")

class TestBotStructure:
    """Тесты структуры бота"""
    
    def test_bot_directory_structure(self):
        """Проверка структуры директории bot"""
        required_dirs = [
            'bot',
            'bot/handlers',
            'bot/middlewares',
            'bot/keyboards'
        ]
        
        for directory in required_dirs:
            assert os.path.exists(directory), f"Directory {directory} should exist"
    
    def test_required_files_exist(self):
        """Проверка наличия обязательных файлов"""
        required_files = [
            'bot/__init__.py',
            'bot/main.py',
            'bot/handlers/__init__.py',
            'bot/middlewares/__init__.py',
            'bot/keyboards/__init__.py'
        ]
        
        for file_path in required_files:
            assert os.path.exists(file_path), f"File {file_path} should exist"

# Простой тест для проверки
def test_example():
    """Простой тест для проверки работы pytest"""
    assert 1 + 1 == 2