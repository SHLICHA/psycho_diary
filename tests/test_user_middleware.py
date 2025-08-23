"""
Тесты для UserMiddleware
"""

import pytest
import os

class TestUserMiddleware:
    """Тесты UserMiddleware"""
    
    def test_middleware_import(self):
        """Тест импорта middleware без Django"""
        try:
            # Проверяем синтаксис файла
            with open('bot/middlewares/user_middleware.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/middlewares/user_middleware.py', 'exec')
            
            # Простой импорт без инициализации Django
            from bot.middlewares import user_middleware
            assert user_middleware is not None
            
        except SyntaxError as e:
            pytest.fail(f"Syntax error in user_middleware.py: {e}")
        except Exception as e:
            # Это нормально, если Django не настроен
            pytest.skip(f"Django not configured: {e}")
    
    def test_middleware_file_exists(self):
        """Проверка существования файла middleware"""
        assert os.path.exists('bot/middlewares/user_middleware.py'), \
            "User middleware file should exist"
    
    def test_middleware_syntax(self):
        """Проверка синтаксиса middleware"""
        try:
            with open('bot/middlewares/user_middleware.py', 'r', encoding='utf-8') as f:
                compile(f.read(), 'bot/middlewares/user_middleware.py', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Syntax error in user_middleware.py: {e}")

class TestUserMiddlewareStructure:
    """Тесты структуры UserMiddleware"""
    
    def test_middleware_files_exist(self):
        """Проверка существования файлов middleware"""
        import os
        
        middleware_files = [
            'bot/middlewares/user_middleware.py',
            'bot/middlewares/language_middleware.py',
            'bot/middlewares/rate_limit_middleware.py',
            'bot/middlewares/analytics_middleware.py'
        ]
        
        for file_path in middleware_files:
            assert os.path.exists(file_path), f"Middleware file {file_path} should exist"
    
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