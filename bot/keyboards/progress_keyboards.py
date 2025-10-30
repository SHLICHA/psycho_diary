from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date, timedelta
from typing import List

from messages import get_button_text


def get_progress_keyboard_with_weekly(language: str, show_restore_button: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для прогресса с кнопкой недельного анализа и опционально кнопкой восстановления."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_weekly_progress', language),
                callback_data="weekly_progress_list"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_detailed_progress', language),
                callback_data="weekly_details"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_mood_chart', language),
                callback_data="show_mood_chart_week"
            )
        ],
    ]
    if show_restore_button:
        keyboard.insert(-1, [
            InlineKeyboardButton(
                text=get_button_text('btn_restore_streak', language),
                callback_data="restore_streak"
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_progress_keyboard_without_weekly(language: str, show_restore_button: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для прогресса без кнопки недельного анализа, с опциональной кнопкой восстановления."""
    keyboard = []
    if show_restore_button:
        keyboard.append([
            InlineKeyboardButton(
                text=get_button_text('btn_restore_streak', language),
                callback_data="restore_streak"
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
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

def get_restore_date_selection_keyboard(language: str, dates_to_restore: List[date]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора даты восстановления серии."""
    keyboard = []
    for dt in dates_to_restore:
        keyboard.append([
            InlineKeyboardButton(
                text=get_button_text('btn_restore_streak_for_date', language).format(date=dt.strftime("%d.%m.%Y")),
                callback_data=f"restore_streak_confirm:{dt.isoformat()}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="progress"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
