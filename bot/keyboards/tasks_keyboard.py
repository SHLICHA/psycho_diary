"""
Клавиатуры для работы с заданиями
"""

import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

logger = logging.getLogger(__name__)

'''def get_tasks_main_keyboard(language: str) -> InlineKeyboardMarkup:
    """Главная клавиатура заданий"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_view_task', language),
                callback_data="view_active_task"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_complete_task', language),
                callback_data="complete_task"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_skip_task', language),
                callback_data="skip_task"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_delete_task', language),
                callback_data="delete_task"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_task_history', language),
                callback_data="view_task_history"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)'''

def get_task_pagination_keyboard(task_id: int, current_index: int, total_tasks: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с заданием с пагинацией"""
    
    buttons = []
    
    # Кнопки пагинации (если больше одного задания)
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
    
    # Кнопки действий с заданием
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
                callback_data="back_to_tasks"  # Правильный callback для возврата к заданиям
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

def get_task_analysis_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура анализа выполнения задания"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_describe_feelings', language),
                callback_data="describe_feelings"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="tasks"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_history_keyboard(tasks: list, language: str) -> InlineKeyboardMarkup:
    """Клавиатура истории заданий"""
    
    buttons = []
    
    # Кнопки для каждого задания
    for task in tasks:
        buttons.append([
            InlineKeyboardButton(
                text=f"🎯 {task.title}",
                callback_data=f"view_completed_task:{task.id}"
            )
        ])
    
    # Кнопка "Назад"
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="tasks"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_back_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к заданиям"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="back_to_tasks"  # Правильный callback для возврата к заданиям
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)