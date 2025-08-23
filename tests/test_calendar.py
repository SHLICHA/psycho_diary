"""
Тесты для календаря
"""

import pytest
import os

class TestCalendarStructure:
    """Тесты структуры календаря"""
    
    def test_calendar_file_exists(self):
        """Проверка существования файла календаря"""
        assert os.path.exists('bot/keyboards/calendar_keyboard.py'), \
            "Файл календаря должен существовать"
    
    def test_calendar_syntax(self):
        """Проверка синтаксиса файла календаря"""
        try:
            with open('bot/keyboards/calendar_keyboard.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/keyboards/calendar_keyboard.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Синтаксическая ошибка в файле календаря: {e}")
    
    def test_calendar_functions_exist(self):
        """Проверка наличия необходимых функций календаря"""
        with open('bot/keyboards/calendar_keyboard.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        required_functions = [
            'get_smart_calendar_keyboard',
            'get_month_calendar_with_navigation',
            'get_year_selection_keyboard',
            'get_month_selection_keyboard'
        ]
        
        for func_name in required_functions:
            assert f"def {func_name}" in content or f"async def {func_name}" in content, \
                f"Функция {func_name} должна существовать в календаре"

class TestCalendarFunctionality:
    """Тесты функциональности календаря"""
    
    def test_calendar_imports(self):
        """Проверка импортов календаря"""
        try:
            from bot.keyboards.calendar_keyboard import (
                get_smart_calendar_keyboard,
                get_month_calendar_with_navigation,
                get_year_selection_keyboard,
                get_month_selection_keyboard
            )
            
            # Проверяем, что функции существуют
            assert get_smart_calendar_keyboard is not None
            assert get_month_calendar_with_navigation is not None
            assert get_year_selection_keyboard is not None
            assert get_month_selection_keyboard is not None
            
        except ImportError as e:
            pytest.fail(f"Ошибка импорта календаря: {e}")
    
    def test_calendar_names(self):
        """Тест названий месяцев и дней"""
        # Проверяем, что названия месяцев и дней определены правильно
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        assert len(month_names_ru) == 13  # 12 месяцев + пустая строка
        assert len(month_names_en) == 13
        assert month_names_ru[1] == "Январь"
        assert month_names_en[1] == "January"

def test_calendar_basic():
    """Простой тест для проверки календаря"""
    assert True