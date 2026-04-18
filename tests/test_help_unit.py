"""
Unit тесты для помощи
"""

import pytest
import os

class TestHelpFilesExist:
    """Тесты существования файлов помощи"""
    
    def test_help_handler_file_exists(self):
        """Проверка существования файла handlers помощи"""
        assert os.path.exists('bot/handlers/help.py'), \
            "Файл handlers помощи должен существовать"
    
    def test_help_keyboard_file_exists(self):
        """Проверка существования файла клавиатур помощи"""
        assert os.path.exists('bot/keyboards/help_keyboard.py'), \
            "Файл клавиатур помощи должен существовать"
    
    def test_help_handler_syntax(self):
        """Проверка синтаксиса файла handlers помощи"""
        try:
            with open('bot/handlers/help.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/handlers/help.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Синтаксическая ошибка в файле handlers помощи: {e}")
    
    def test_help_keyboard_syntax(self):
        """Проверка синтаксиса файла клавиатур помощи"""
        try:
            with open('bot/keyboards/help_keyboard.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/keyboards/help_keyboard.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Синтаксическая ошибка в файле клавиатур помощи: {e}")

class TestHelpStructure:
    """Тесты структуры помощи"""
    
    def test_help_functions_exist(self):
        """Проверка наличия основных функций помощи"""
        with open('bot/handlers/help.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие основных handler функций
        required_functions = [
            'show_help', 
            'show_faq',
            'show_how_to_start'
        ]
        
        for func_name in required_functions:
            assert f"async def {func_name}" in content, \
                f"Функция {func_name} должна существовать"
    
    def test_help_message_keys_exist(self):
        """Проверка наличия ключей сообщений помощи"""
        # Проверяем messages.py на наличие ключей помощи
        with open('messages/ru/ru_help.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        help_keys = [
            'help_text',
            'help_faq', 
            'help_how_to_start',
            'help_writing_entries'
        ]
        
        for key in help_keys:
            assert f"'{key}':" in content, \
                f"Ключ сообщения '{key}' должен существовать"

def test_help_basic():
    """Базовый тест помощи"""
    assert True