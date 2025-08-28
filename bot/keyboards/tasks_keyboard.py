"""
Клавиатуры для работы с заданиями
"""

import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

logger = logging.getLogger(__name__)

# TODO добавить постоянную кнопки с историей заданий (выполненные, пропущенные(можно взять в работу)). Там так же пагинация
def get_task_pagination_keyboard(task_id: int, current_index: int, total_tasks: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с заданием с пагинацией"""
    buttons = []
    if total_tasks > 1:
        pagination_buttons = [
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"tasks_paginate:prev:{current_index}"
            ),
            InlineKeyboardButton(
                text=f"{current_index + 1}/{total_tasks}",
                callback_data="tasks_empty"  # Не активная кнопка
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"tasks_paginate:next:{current_index}"
            )
        ]
        buttons.append(pagination_buttons)
    action_buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_complete_task', language),
                callback_data=f"complete_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_skip_task', language),
                callback_data=f"skip_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_delete_task', language),
                callback_data=f"delete_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    buttons.extend(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# TODO Переделать (вернуть в работу, удалить, пагинация). Возможно объединить с предыдущей
def get_task_detail_keyboard(task_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура просмотра деталей задания"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_complete_task', language),
                callback_data=f"complete_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_skip_task', language),
                callback_data=f"skip_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_delete_task', language),
                callback_data=f"delete_task:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="back_to_tasks"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_completion_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура выполнения задания"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="tasks"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# TODO Рассмотреть возможность единой клавиатуры подтверждения
def get_confirm_delete_task_keyboard(task_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления задания"""
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=f"confirm_delete_task:{task_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет, отмена",
                callback_data="cancel_delete_task"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# TODO рассмотреть возможность единой клавиатуры возврата назад
def get_task_back_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к заданиям"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="back_to_tasks"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
