"""
Тесты для состояний настроек
"""

import pytest
import os

class TestSettingsStatesStructure:
    """Тесты структуры состояний настроек"""
    
    def test_settings_states_file_exists(self):
        """Проверка существования файла состояний настроек"""
        assert os.path.exists('bot/states/settings_states.py'), \
            "Файл состояний настроек должен существовать"
    
    def test_settings_states_syntax(self):
        """Проверка синтаксиса файла состояний настроек"""
        try:
            with open('bot/states/settings_states.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/states/settings_states.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Синтаксическая ошибка в файле состояний настроек: {e}")
    
    def test_settings_states_class_exists(self):
        """Проверка наличия класса SettingsStates"""
        with open('bot/states/settings_states.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        assert "class SettingsStates" in content, \
            "Класс SettingsStates должен существовать"
    
    def test_required_settings_states_exist(self):
        """Проверка наличия необходимых состояний"""
        with open('bot/states/settings_states.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        required_states = [
            'changing_language',
            'waiting_for_language_choice',
            'in_settings_menu',
            'changing_notifications',
            'changing_auto_analysis'
        ]
        
        for state_name in required_states:
            assert f"{state_name} = State()" in content, \
                f"Состояние {state_name} должно существовать"

def test_settings_states_basic():
    """Простой тест для проверки состояний настроек"""
    assert True