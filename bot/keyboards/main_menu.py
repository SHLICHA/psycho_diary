"""
Клавиатуры главного меню и общие клавиатуры
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text


def get_main_menu_keyboard(language: str, user=None) -> InlineKeyboardMarkup:
    """Клавиатура главного меню"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_new_entry', language),
                callback_data="new_entry"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_archive', language),
                callback_data="archive"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_tasks', language),
                callback_data="tasks"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_progress', language),
                callback_data="progress"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_user_profile', language),
                callback_data="user_profile"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_settings', language),
                callback_data="settings"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_help', language),
                callback_data="help"
            )
        ]
    ]
    if user and hasattr(user, 'has_agreed_to_terms') and user.has_agreed_to_terms:
        # Определяем "заполненность" профиля.
        # Проверим несколько ключевых полей, которые должны быть заполнены после анкеты.
        # personality_traits и life_facts - хорошие кандидаты.
        # Если они пусты или содержат только стандартные/минимальные данные, считаем анкету непройденной.
        
        # Простая проверка: если оба поля пусты, значит, анкета точно не пройдена.
        # Более сложная логика может учитывать веса черт или количество фактов.
        traits_filled = bool(user.personality_traits and isinstance(user.personality_traits, dict) and user.personality_traits)
        facts_filled = bool(user.life_facts and isinstance(user.life_facts, list) and user.life_facts)

        if not traits_filled and not facts_filled:
            # Добавляем кнопку "Анкета" в начало меню
            questionnaire_button_row = [
                InlineKeyboardButton(
                    text=get_button_text('btn_fill_questionnaire', language), # Новое сообщение
                    callback_data="start_questionnaire_from_menu" # Новый callback
                )
            ]
            buttons.insert(0, questionnaire_button_row) # Вставляем в начало   
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# TODO Переделать по "В главное меню" и сделать общей для всех
def get_back_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой "Назад"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
