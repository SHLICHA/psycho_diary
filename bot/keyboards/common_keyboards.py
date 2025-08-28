"""
Универсальные клавиатуры для общего использования
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

# TODO Рассмотреть не возврат в главное меню, а другие варианты
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
