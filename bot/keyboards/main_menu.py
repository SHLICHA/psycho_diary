"""
Клавиатуры главного меню и общие клавиатуры
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

"""
Клавиатуры главного меню
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

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

def get_entry_type_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа записи"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_text_entry', language),
                callback_data="text_entry"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_voice_entry', language),
                callback_data="voice_entry"
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

def get_entry_actions_keyboard(entry_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с записью"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_view_entry', language),
                callback_data=f"view_entry:{entry_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_delete_entry', language),
                callback_data=f"delete_entry:{entry_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_analyze_again', language),
                callback_data=f"reanalyze_entry:{entry_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="archive"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard(callback_data_yes: str, callback_data_no: str, language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Да",
                callback_data=callback_data_yes
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=callback_data_no
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)