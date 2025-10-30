"""
Клавиатуры главного меню и общие клавиатуры
"""

from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from diary.models import TherapyTask, DailyAnalysis
from messages import get_button_text


async def get_main_menu_keyboard(language: str, user=None) -> InlineKeyboardMarkup:
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
    ]
    if user:
        has_tasks = await sync_to_async(TherapyTask.objects.filter(user=user).exists)()
        if has_tasks:
            buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_tasks', language),
                    callback_data="tasks"
                )
            ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_therapy_chat', language),
            callback_data="start_therapy_chat" 
        )
    ])
    if user:
        has_daily_analysis = await sync_to_async(DailyAnalysis.objects.filter(combined_entry__user=user).exists)()
        if has_daily_analysis:
            buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_progress', language),
                    callback_data="progress"
                )
            ])
    buttons.extend([
        [
            InlineKeyboardButton(
                text=get_button_text('btn_user_profile', language),
                callback_data="user_profile"
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
    ])

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
