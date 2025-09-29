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


def get_add_foto_kb(
        language: str,
        callback_add_scrinshot: str = 'add_screenshot',
        callback_skip_foto: str = 'skip_photo',
):
    """
    Клавиатура с кнопками "Добавить скриншот" и "Отправить без фото".
    Args:
        callback_add_scrinshot (str): Callback data для кнопки добавления. По умолчанию "add_screenshot".
        callback_skip_foto (str): Callback data для кнопки пропуска. По умолчанию "skip_photo".
        text_add (str): Текст кнопки добавления. По умолчанию "📷 Добавить скриншот".
        text_skip (str): Текст кнопки пропуска. По умолчанию "➡️ Отправить без фото".
    """
    text_add = get_button_text('btn_add_screenshot', language)
    text_skip = get_button_text('btn_send_without_photo', language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text_add, callback_data=callback_add_scrinshot)],
            [InlineKeyboardButton(text=text_skip, callback_data=callback_skip_foto)]
        ])

def get_skip_kb(
        language: str,
        callback_data: str = 'skip_'):
    """
    Клавиатура с универсальной кнопкой "Пропустить".
    Args:
        callback_data (str): Callback data для кнопки. По умолчанию "skip_".
        text (str): Текст кнопки. По умолчанию "⏭ Пропустить".
    """
    text = get_button_text('btn_skip', language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data)]
        ]
    )