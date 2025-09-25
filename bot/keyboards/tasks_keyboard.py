"""
Клавиатуры для работы с заданиями
"""

import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

from messages import get_button_text

logger = logging.getLogger(__name__)

def get_task_main_menu_keyboard(language: str, show_history_button: bool = True) -> InlineKeyboardMarkup:
    """
    Главная клавиатура раздела "Задания".
    Кнопка "История заданий" отображается в зависимости от show_history_button.

    Args:
        language (str): Язык интерфейса.
        show_history_button (bool): Флаг, определяющий, показывать ли кнопку "История заданий".
                                    По умолчанию True для обратной совместимости.

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    buttons = []
    if show_history_button:
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_task_history', language),
                callback_data="task_history_main"
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_pagination_keyboard(task_id: int,
                                 current_index: int,
                                 total_tasks: int,
                                 language: str,
                                 show_history_button: bool = True
                                 ) -> InlineKeyboardMarkup:
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
                callback_data="tasks_empty"
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
        ]
    ]
    buttons.extend(action_buttons)
    navigation_buttons = []
    if show_history_button:
        navigation_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_task_history', language),
                callback_data="task_history_main"
            )
        ])
    navigation_buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    buttons.extend(navigation_buttons)
    
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

def get_confirm_delete_task_keyboard(task_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления задания"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('confirm_delete_entry_yes', language),
                callback_data=f"confirm_delete_task:{task_id}"
            ),
            InlineKeyboardButton(
                text=get_button_text('confirm_delete_entry_no', language),
                callback_data="cancel_delete_task"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_history_main_keyboard(language: str) -> InlineKeyboardMarkup:
    """Главная клавиатура истории заданий с кнопкой "Назад"."""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="tasks"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_history_list_keyboard(
    task_ids: List[int],
    current_index: int,
    current_task_status: str,
    language: str
) -> InlineKeyboardMarkup:
    """
    Клавиатура списка истории заданий с пагинацией (аналогично активным заданиям).

    Args:
        task_ids: Список ID заданий.
        current_index: Индекс текущего задания в списке.
        current_task_status: Статус текущего задания (например, 'completed', 'skipped').
        language: Язык интерфейса.

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    buttons = []
    total_tasks = len(task_ids)
    if total_tasks > 1:
        pagination_buttons = []
        if current_index > 0:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"task_history_paginate:{current_index - 1}"
                )
            )
        pagination_buttons.append(
            InlineKeyboardButton(
                text=f"{current_index + 1}/{total_tasks}",
                callback_data="task_history_empty"
            )
        )
        if current_index < total_tasks - 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"task_history_paginate:{current_index + 1}"
                )
            )
        if pagination_buttons:
            buttons.append(pagination_buttons)
    current_task_id = task_ids[current_index] if task_ids and 0 <= current_index < len(task_ids) else None
    action_buttons = []
    if current_task_id and current_task_status == 'completed':
        action_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_detailed_analysis', language),
                callback_data=f"view_detailed_task_analysis:{current_task_id}"
            )
        ])
    if current_task_id and current_task_status == 'skipped':
        action_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_restore_task', language),
                callback_data=f"task_history_restore:{current_task_id}"
            )
        ])
    action_buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="tasks"
        )
    ])
    buttons.extend(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_history_detail_keyboard(
    task_id: int, 
    task_status: str,
    current_index: int,
    language: str
) -> InlineKeyboardMarkup:
    """
    Клавиатура детального просмотра задания из истории.

    Args:
        task_id: ID задания.
        task_status: Статус задания ('completed', 'skipped', etc.).
        current_index: Индекс задания в списке для пагинации.
        language: Язык интерфейса.

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    buttons = []
    if task_status == 'skipped':
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_restore_task', language),
                callback_data=f"task_history_restore:{task_id}:{current_index}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"back_to_tasks"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)