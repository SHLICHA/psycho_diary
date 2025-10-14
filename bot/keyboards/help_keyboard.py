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
                text=get_button_text('help_how_to_start', language), # <-- Теперь первая
                callback_data="help_how_to_start"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_guide', language),
                callback_data="help_guide"  
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_subscription_and_tokens', language),
                callback_data="help_subscription_and_tokens"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_referral_program', language),
                callback_data="help_referral_program"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_faq', language),
                callback_data="help_faq"
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
        #[
        #    InlineKeyboardButton(
        #        text=get_button_text('help_contact', language),
        #        callback_data="help_contact"
        #    )
        #],
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
                callback_data="help_back_to_main" # <-- Возвращает к списку разделов
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

def get_help_guide_section_keyboard(language: str) -> InlineKeyboardMarkup: # <-- НОВАЯ КЛАВИАТУРА для подменю руководства
    """Клавиатура для подразделов руководства (возврат к меню руководства)"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('help_writing_entries', language), # Используем существующий ключ кнопки
                callback_data="help_guide_writing_entries"            # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_tasks', language),         # Используем существующий ключ кнопки
                callback_data="help_guide_tasks"                     # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_progress', language),      # Используем существующий ключ кнопки
                callback_data="help_guide_progress"                  # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_profile', language),       # Используем существующий ключ кнопки
                callback_data="help_guide_profile"                   # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_settings', language),      # Используем существующий ключ кнопки
                callback_data="help_guide_settings"                  # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('help_therapy_chat', language),  # Используем существующий ключ кнопки
                callback_data="help_guide_therapy_chat"              # Новый callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back_to_help', language),  # Возврат к общему списку помощи
                callback_data="help_back_to_main"                   # callback_data как у обычного раздела
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