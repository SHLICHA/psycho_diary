"""
Система шаблонов для сообщений
"""

from typing import Dict, Any, Optional
import re

class MessageTemplate:
    """
    Класс для работы с шаблонами сообщений
    """
    
    def __init__(self, template_string: str):
        self.template = template_string
        self.variables = self._extract_variables()
    
    def _extract_variables(self) -> set:
        """
        Извлечение переменных из шаблона
        """
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, self.template)
        return set(matches)
    
    def render(self, **kwargs) -> str:
        """
        Рендеринг шаблона с переданными параметрами
        """
        # Проверяем, все ли необходимые переменные переданы
        missing_vars = self.variables - set(kwargs.keys())
        if missing_vars:
            raise ValueError(f"Missing variables: {missing_vars}")
        
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Template rendering error: {e}")
    
    def get_variables(self) -> set:
        """
        Получение списка переменных в шаблоне
        """
        return self.variables.copy()

class TemplateManager:
    """
    Менеджер шаблонов сообщений
    """
    
    def __init__(self):
        self.templates = {}
    
    def register_template(self, template_name: str, template: str):
        """
        Регистрация шаблона
        """
        self.templates[template_name] = MessageTemplate(template)
    
    def render_template(self, template_name: str, **kwargs) -> str:
        """
        Рендеринг шаблона по имени
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        return self.templates[template_name].render(**kwargs)
    
    def get_template_variables(self, template_name: str) -> set:
        """
        Получение переменных шаблона
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        return self.templates[template_name].get_variables()

# Глобальный менеджер шаблонов
template_manager = TemplateManager()

# Регистрация основных шаблонов
def initialize_templates():
    """
    Инициализация основных шаблонов
    """
    from messages import MESSAGES
    
    # Регистрируем основные шаблоны
    for lang, messages in MESSAGES.items():
        for key, template in messages.items():
            template_manager.register_template(f"{lang}:{key}", template)

# Инициализация шаблонов при импорте
initialize_templates()