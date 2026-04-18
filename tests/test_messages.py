"""
Тесты для системы сообщений
"""

import pytest
from messages import get_message, get_button_text, get_mood_text


class TestMessages:
    """Тесты для системы сообщений"""
    
    def test_get_message_russian(self):
        """Тест получения русского сообщения"""
        msg = get_message('welcome', 'ru')
        assert 'психологический дневник' in msg
    
    def test_get_message_english(self):
        """Тест получения английского сообщения"""
        msg = get_message('welcome', 'en')
        assert 'psychological diary' in msg
    
    def test_get_message_fallback(self):
        """Тест fallback на русский язык"""
        msg = get_message('welcome', 'fr')  # несуществующий язык
        assert 'психологический дневник' in msg
    
    def test_get_message_with_params(self):
        """Тест сообщения с параметрами"""
        msg = get_message('entry_saved', 'ru', score=7, mood='хорошо', comment='Тест', recommendation='Продолжай')
        assert '7/10' in msg
        assert 'хорошо' in msg
    
    def test_get_button_text(self):
        """Тест получения текста кнопки"""
        btn_text = get_button_text('btn_new_entry', 'ru')
        assert btn_text == '📝 Новая запись'
        
        btn_text = get_button_text('btn_new_entry', 'en')
        assert btn_text == '📝 New entry'
    
    def test_get_mood_text(self):
        """Тест получения текста настроения"""
        mood = get_mood_text(7, 'ru')
        assert 'хорошо' in mood
        
        mood = get_mood_text(7, 'en')
        assert 'good' in mood
