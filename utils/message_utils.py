"""
Утилиты для работы с сообщениями
"""

from typing import Dict, Any, Optional
from messages import get_message, get_button_text, get_mood_text

def format_message(template: str, **kwargs) -> str:
    """
    Форматирование сообщения с обработкой ошибок
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        # Логируем ошибку и возвращаем шаблон без форматирования
        print(f"Message formatting error: {e}")
        return template

def build_menu_buttons(buttons_config: list, language: str = 'ru') -> list:
    """
    Создание кнопок меню из конфигурации
    
    Args:
        buttons_config: Список кортежей (ключ_сообщения, callback_data)
        language: Язык
    
    Returns:
        Список кнопок для inline клавиатуры
    """
    from aiogram.types import InlineKeyboardButton
    
    buttons = []
    for button_key, callback_data in buttons_config:
        text = get_button_text(button_key, language)
        buttons.append(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    return buttons

def format_progress_message(
    awareness_level: int,
    entries_count: int,
    tasks_completed: int,
    streak_days: int,
    language: str = 'ru'
) -> str:
    """
    Форматирование сообщения о прогрессе
    """
    return get_message(
        'progress_title',
        language,
        awareness_level=awareness_level,
        entries_count=entries_count,
        tasks_completed=tasks_completed,
        streak_days=streak_days
    )

def format_entry_saved_message(
    score: int,
    comment: str,
    recommendation: str,
    language: str = 'ru'
) -> str:
    """
    Форматирование сообщения о сохраненной записи
    """
    mood_text = get_mood_text(score, language)
    return get_message(
        'entry_saved',
        language,
        score=score,
        mood=mood_text,
        comment=comment,
        recommendation=recommendation
    )