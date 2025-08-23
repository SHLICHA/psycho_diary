"""
Тесты для клавиатур
"""

import pytest
from aiogram.types import InlineKeyboardMarkup

class TestKeyboardStructure:
    """Тесты структуры клавиатур"""
    
    def test_keyboard_files_exist(self):
        """Проверка существования файлов клавиатур"""
        import os
        
        keyboard_files = [
            'bot/keyboards/__init__.py',
            'bot/keyboards/main_menu.py',
            'bot/keyboards/calendar_keyboard.py',
            'bot/keyboards/settings_keyboard.py',
            'bot/keyboards/tasks_keyboard.py'
        ]
        
        for file_path in keyboard_files:
            assert os.path.exists(file_path), f"Keyboard file {file_path} should exist"
    
    def test_keyboard_syntax(self):
        """Проверка синтаксиса файлов клавиатур"""
        keyboard_files = [
            'bot/keyboards/main_menu.py',
            'bot/keyboards/calendar_keyboard.py',
            'bot/keyboards/settings_keyboard.py',
            'bot/keyboards/tasks_keyboard.py'
        ]
        
        for file_path in keyboard_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), file_path, 'exec')
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {file_path}: {e}")

class TestKeyboardFunctionality:
    """Тесты функциональности клавиатур"""
    
    def test_main_menu_keyboard(self):
        """Тест главного меню"""
        from bot.keyboards.main_menu import get_main_menu_keyboard
        
        keyboard = get_main_menu_keyboard('ru')
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) > 0
        
        # Проверяем, что есть кнопки
        buttons_count = sum(len(row) for row in keyboard.inline_keyboard)
        assert buttons_count > 0
    
    def test_calendar_keyboard(self):
        """Тест календаря"""
        from bot.keyboards.calendar_keyboard import get_smart_calendar_keyboard
        from unittest.mock import Mock
        
        # Создаем mock пользователя
        user = Mock()
        user.telegram_id = 123456789
        
        keyboard = get_smart_calendar_keyboard(user, 'ru')
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) > 0
    
    def test_settings_keyboard(self):
        """Тест настроек"""
        from bot.keyboards.settings_keyboard import get_settings_keyboard
        from unittest.mock import Mock
        
        # Создаем mock пользователя
        user = Mock()
        user.language = 'ru'
        user.is_premium = False
        
        keyboard = get_settings_keyboard(user, 'ru')
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) > 0

# Простой тест для проверки
def test_keyboards_import():
    """Простой тест импортов клавиатур"""
    try:
        from bot.keyboards import get_main_menu_keyboard
        assert get_main_menu_keyboard is not None
    except ImportError as e:
        pytest.fail(f"Failed to import keyboards: {e}")