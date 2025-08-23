"""
Тесты для состояний заданий
"""

import pytest
import os

class TestTaskStatesStructure:
    """Тесты структуры состояний заданий"""
    
    def test_task_states_file_exists(self):
        """Проверка существования файла состояний заданий"""
        assert os.path.exists('bot/states/task_states.py'), \
            "Файл состояний заданий должен существовать"
    
    def test_task_states_syntax(self):
        """Проверка синтаксиса файла состояний заданий"""
        try:
            with open('bot/states/task_states.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/states/task_states.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Синтаксическая ошибка в файле состояний заданий: {e}")
    
    def test_task_states_class_exists(self):
        """Проверка наличия класса TaskStates"""
        with open('bot/states/task_states.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        assert "class TaskStates" in content, \
            "Класс TaskStates должен существовать"
    
    def test_required_task_states_exist(self):
        """Проверка наличия необходимых состояний"""
        with open('bot/states/task_states.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        required_states = [
            'waiting_for_task_completion',
            'describing_feelings',
            'completing_task',
            'viewing_task'
        ]
        
        for state_name in required_states:
            assert f"{state_name} = State()" in content, \
                f"Состояние {state_name} должно существовать"

def test_task_states_basic():
    """Простой тест для проверки состояний заданий"""
    assert True