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
            text=get_button_text('btn_view_transaction_history', language),
            callback_data="view_transaction_history"
        )
    ])
    
    buttons.append(
        [
            InlineKeyboardButton(
                text=get_button_text('btn_manage_subscription', language),
                callback_data="settings_premium"
            )
        ])
     
    buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_edit_profile', language),
                callback_data="edit_profile"
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_get_referral_link', language),
            callback_data="get_referral_link" # <-- Новый callback_data
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_export_data', language),  # <-- НОВАЯ КНОПКА
            callback_data="export_user_data"
        )
    ])
    buttons.append([
            InlineKeyboardButton(
                text=get_button_text('delete_account', language),
                callback_data="delete_account"
            )
        ])
    buttons.append(
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ])   
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_profile_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура редактирования профиля"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_edit_name', language),
                callback_data="edit_profile_name"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_edit_email', language),
                callback_data="edit_profile_email"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_edit_dob', language),
                callback_data="edit_profile_dob"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_edit_hobbies', language),
                callback_data="edit_profile_hobbies"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_edit_life_facts', language),
                callback_data="edit_profile_life_facts"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="user_profile"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_account_deletion_menu_keyboard(language: str, balance_info: str) -> InlineKeyboardMarkup:
    """Клавиатура меню удаления аккаунта"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_delete_account_and_funds', language),
                callback_data="confirm_account_deletion_final"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_cancel_deletion', language),
                callback_data="user_profile"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_account_deletion_confirmation_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления аккаунта"""
    # Убираем кнопку подтверждения, оставляем только отмену
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_cancel_deletion', language),
                callback_data="delete_account_cancel"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)