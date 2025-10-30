"""
Клавиатуры для настроек
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text, get_status_text, get_message

def get_settings_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Основная клавиатура настроек"""
    language_text = get_button_text('settings_language', language).format(
        language="Русский" if user.language == 'ru' else "English"
    )
    notifications_text = get_button_text('settings_notifications', language).format(
        status=get_status_text(user.notifications_enabled, language)
    )
    auto_analysis_text = get_button_text('settings_auto_analysis', language).format(
        status=get_status_text(user.auto_analysis_enabled, language)
    )
    tasks_limit_text = get_button_text('settings_tasks_limit', language).format(
        limit=user.max_ai_tasks_per_day
    )
    buttons = [
        [
            InlineKeyboardButton(
                text=language_text,
                callback_data="settings_change_language"
            )
        ],
        [
            InlineKeyboardButton(
                text=notifications_text,
                callback_data="settings_toggle_notifications"
            )
        ],
        [
            InlineKeyboardButton(
                text=auto_analysis_text,
                callback_data="settings_toggle_auto_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_message('settings_timezone', language, timezone=user.timezone),
                callback_data="settings_change_timezone"
            )
        ],
        [
            InlineKeyboardButton(
                text=tasks_limit_text,
                callback_data="settings_tasks"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_language_selection_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🇷🇺 Русский",
                callback_data="set_language:ru"
            )
        ],
        [
            InlineKeyboardButton(
                text="🇬🇧 English",
                callback_data="set_language:en"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="settings"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_timezone_selection_method_keyboard(language: str, current_timezone: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора способа установки часового пояса"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_select_common_timezones', language),
                callback_data="timezone_select_from_list"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_message('btn_enter_city', language),
                callback_data="timezone_enter_city"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="settings"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_city_timezone_confirmation_keyboard(language: str, timezone_data: dict) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения часового пояса по городу"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_confirm_changes', language),
                callback_data=f"confirm_timezone:{timezone_data['timezone']}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="timezone_enter_city"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_multiple_city_timezones_keyboard(language: str, options: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора из нескольких вариантов часовых поясов"""
    buttons = []
    
    for option in options:
        timezone_str = option['timezone']
        city = option.get('city', '')
        country = option.get('country', '')
        button_text = f"{city}, {country} ({timezone_str})"
        
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_timezone:{timezone_str}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="timezone_enter_city"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_common_timezones_keyboard(language: str, current_timezone: str) -> InlineKeyboardMarkup:
    """Клавиатура с популярными часовыми поясами"""
    timezone_buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_moscow', language),
                callback_data="set_timezone:Europe/Moscow"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_yekaterinburg', language),
                callback_data="set_timezone:Asia/Yekaterinburg"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_omsk', language),
                callback_data="set_timezone:Asia/Omsk"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_krasnoyarsk', language),
                callback_data="set_timezone:Asia/Krasnoyarsk"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_irkutsk', language),
                callback_data="set_timezone:Asia/Irkutsk"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_yakutsk', language),
                callback_data="set_timezone:Asia/Yakutsk"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_vladivostok', language),
                callback_data="set_timezone:Asia/Vladivostok"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_new_york', language),
                callback_data="set_timezone:America/New_York"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_london', language),
                callback_data="set_timezone:Europe/London"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_berlin', language),
                callback_data="set_timezone:Europe/Berlin"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_tokyo', language),
                callback_data="set_timezone:Asia/Tokyo"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="settings_change_timezone"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=timezone_buttons)

def get_account_deletion_confirmation_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления аккаунта"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_confirm_delete', language),
                callback_data="confirm_account_deletion_final"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_cancel_deletion', language),
                callback_data="delete_account_cancel"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_settings_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Клавиатура настроек заданий"""
    from aiogram.types import InlineKeyboardButton
    increase_btn = InlineKeyboardButton(
        text="➕",
        callback_data="settings_increase_tasks_limit"
    )
    decrease_btn = InlineKeyboardButton(
        text="➖",
        callback_data="settings_decrease_tasks_limit"
    )
    limit_text = f"{user.max_ai_tasks_per_day}"
    limit_btn = InlineKeyboardButton(
        text=limit_text,
        callback_data="settings_tasks_noop"
    )
    back_btn = InlineKeyboardButton(
        text=get_button_text('btn_back', language),
        callback_data="settings"
    )
    buttons = [
        [
            decrease_btn,
            limit_btn,
            increase_btn
        ],
        [
            back_btn
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
