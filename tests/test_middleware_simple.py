"""
Упрощенные тесты для middleware без раннего импорта Django
"""

import pytest
import os

class TestMiddlewareStructure:
    """Тесты структуры middleware"""
    
    def test_middleware_files_exist(self):
        """Проверка существования файлов middleware"""
        middleware_files = [
            'bot/middlewares/user_middleware.py',
            'bot/middlewares/language_middleware.py',
            'bot/middlewares/rate_limit_middleware.py',
            'bot/middlewares/analytics_middleware.py'
        ]
        
        for file_path in middleware_files:
            assert os.path.exists(file_path), f"File {file_path} should exist"
    
    def test_middleware_syntax(self):
        """Проверка синтаксиса файлов middleware"""
        middleware_files = [
            'bot/middlewares/user_middleware.py',
            'bot/middlewares/language_middleware.py',
            'bot/middlewares/rate_limit_middleware.py',
            'bot/middlewares/analytics_middleware.py'
        ]
        
        for file_path in middleware_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), file_path, 'exec')
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {file_path}: {e}")

def test_example():
    """Простой тест для проверки работы pytest"""
    assert 1 + 1 == 2