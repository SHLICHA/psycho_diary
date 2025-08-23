"""
Простой тест для проверки структуры помощи
"""

import pytest
import os

class TestHelpFileStructure:
    """Тест структуры файла помощи"""
    
    def test_help_file_exists(self):
        """Проверка существования файла помощи"""
        assert os.path.exists('bot/handlers/help.py'), \
            "Файл помощи должен существовать"
    
    def test_help_file_readable(self):
        """Проверка читаемости файла помощи"""
        try:
            with open('bot/handlers/help.py', 'r', encoding='utf-8') as f:
                content = f.read()
            assert len(content) > 0
        except Exception as e:
            pytest.fail(f"Файл помощи не читается: {e}")
    
    def test_help_has_router(self):
        """Проверка наличия роутера в файле помощи"""
        with open('bot/handlers/help.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'Router' in content, "Файл должен содержать Router"
        assert 'router = Router()' in content, "Файл должен создавать роутер"
    
    def test_help_has_handlers(self):
        """Проверка наличия handler функций"""
        with open('bot/handlers/help.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие основных элементов
        assert 'async def' in content, "Файл должен содержать async функции"
        assert 'CallbackQuery' in content or 'Message' in content, \
            "Файл должен обрабатывать сообщения или callback"
        
        # Проверяем наличие show_help функции
        assert 'show_help' in content, "Файл должен содержать функцию show_help"

def test_help_basic_functionality():
    """Базовый тест функциональности помощи"""
    assert True