from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

def get_profile_keyboard(language: str, show_psychology_button: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру для экрана профиля."""
    buttons = []
    
    if show_psychology_button:
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_view_psychology_profile', language),
                callback_data="view_psychology_profile"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
