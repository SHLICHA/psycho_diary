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
                text=get_button_text('btn_therapy_chat', language),
                callback_data="start_therapy_chat" # Новая callback_data
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
        traits_filled = bool(user.personality_traits and isinstance(user.personality_traits, dict) and user.personality_traits)
        facts_filled = bool(user.life_facts and isinstance(user.life_facts, list) and user.life_facts)
        if not traits_filled and not facts_filled:
            questionnaire_button_row = [
                InlineKeyboardButton(
                    text=get_button_text('btn_fill_questionnaire', language),
                    callback_data="start_questionnaire_from_menu"
                )
            ]
            buttons.insert(0, questionnaire_button_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
