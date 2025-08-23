"""
Универсальные клавиатуры для общего использования
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

def get_cancel_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой "Отмена"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_cancel', language),
                callback_data="main_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_cancel_keyboard(language: str, confirm_callback: str = "confirm", cancel_callback: str = "main_menu") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения с кнопками "Подтвердить" и "Отмена"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=confirm_callback
            ),
            InlineKeyboardButton(
                text=get_button_text('btn_cancel', language),
                callback_data=cancel_callback
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_main_menu_keyboard(language: str) -> InlineKeyboardMarkup:
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
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)