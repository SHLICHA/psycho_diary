"""
Тесты для системы сообщений
"""

import pytest
from messages import get_message, get_button_text, get_mood_text
from utils.template_utils import MessageTemplate, template_manager

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

class TestMessageTemplate:
    """Тесты для шаблонов сообщений"""
    
    def test_template_rendering(self):
        """Тест рендеринга шаблона"""
        template = MessageTemplate("Привет, {name}! У тебя {count} записей.")
        result = template.render(name="Иван", count=5)
        assert "Иван" in result
        assert "5" in result
    
    def test_template_missing_variables(self):
        """Тест ошибки при отсутствии переменной"""
        template = MessageTemplate("Привет, {name}!")
        with pytest.raises(ValueError):
            template.render(age=25)  # отсутствует переменная name
    
    def test_template_variables_extraction(self):
        """Тест извлечения переменных из шаблона"""
        template = MessageTemplate("Привет, {name}! У тебя {count} записей.")
        variables = template.get_variables()
        assert 'name' in variables
        assert 'count' in variables
        assert len(variables) == 2

class TestTemplateManager:
    """Тесты для менеджера шаблонов"""
    
    def test_register_and_render_template(self):
        """Тест регистрации и рендеринга шаблона"""
        template_manager.register_template("test_template", "Привет, {name}!")
        result = template_manager.render_template("test_template", name="Мир")
        assert "Мир" in result
    
    def test_nonexistent_template(self):
        """Тест несуществующего шаблона"""
        with pytest.raises(ValueError):
            template_manager.render_template("nonexistent")