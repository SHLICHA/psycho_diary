from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date, timedelta

from messages import get_button_text


def get_progress_keyboard_with_weekly(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для прогресса с кнопкой недельного анализа."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_weekly_progress', language),
                callback_data="weekly_progress_list"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_progress_keyboard_without_weekly(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для прогресса без кнопки недельного анализа."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_weekly_analysis_keyboard(language: str, week_start_date: date) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для просмотра недельного анализа с кнопками навигации.
    """
    prev_week_start = week_start_date - timedelta(weeks=1)
    next_week_start = week_start_date + timedelta(weeks=1)
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_prev_week', language),
                callback_data=f"weekly_nav:{prev_week_start.isoformat()}"
            ),
            InlineKeyboardButton(
                text=get_button_text('btn_next_week', language),
                callback_data=f"weekly_nav:{next_week_start.isoformat()}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="progress"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_weekly_navigation_keyboard(language: str, week_start_date: date) -> InlineKeyboardMarkup:
    """Создает клавиатуру для навигации по недельным анализам."""
    prev_week_start = week_start_date - timedelta(weeks=1)
    next_week_start = week_start_date + timedelta(weeks=1)
    
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_prev_week', language),
                callback_data=f"weekly_nav:{prev_week_start.isoformat()}"
            ),
            InlineKeyboardButton(
                text=get_button_text('btn_next_week', language),
                callback_data=f"weekly_nav:{next_week_start.isoformat()}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="progress"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
