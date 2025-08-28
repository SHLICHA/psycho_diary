"""
Клавиатуры для помощи
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

def get_help_keyboard(language: str) -> InlineKeyboardMarkup:
    """Основная клавиатура помощи"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('help_faq', language),
                callback_data="help_faq"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_how_to_start', language),
                callback_data="help_how_to_start"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_writing_entries', language),
                callback_data="help_writing_entries"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_tasks', language),
                callback_data="help_tasks"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_privacy', language),
                callback_data="help_privacy"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_contact', language),
                callback_data="help_contact"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_help_section_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для разделов помощи"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back_to_help', language),
                callback_data="help_back_to_main"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)