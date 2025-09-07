"""
Универсальные клавиатуры для общего использования
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

def get_cancel_keyboard(language: str, cancel_callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Отмена".

    Args:
        language (str): Язык интерфейса.
        cancel_callback_data (str, optional): Callback data для кнопки "Отмена". 
                                               По умолчанию "main_menu".

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_cancel', language),
                callback_data=cancel_callback_data
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
