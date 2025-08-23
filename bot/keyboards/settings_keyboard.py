"""
Клавиатуры для настроек
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text, get_status_text, get_message

def get_settings_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Основная клавиатура настроек"""
    
    # Определяем тексты для кнопок
    language_text = get_button_text('settings_language', language).format(
        language="Русский" if user.language == 'ru' else "English"
    )
    
    notifications_text = get_button_text('settings_notifications', language).format(
        status=get_status_text(user.notifications_enabled, language)
    )
    
    auto_analysis_text = get_button_text('settings_auto_analysis', language).format(
        status=get_status_text(user.auto_analysis_enabled, language)
    )
    
    premium_text = get_button_text('settings_premium', language).format(
        status=get_status_text(user.is_premium, language)
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
                text=premium_text,
                callback_data="settings_premium"
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

def get_premium_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура премиум функций"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text="💳 Подписаться",
                callback_data="premium_subscribe"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎁 Попробовать бесплатно",
                callback_data="premium_trial"
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
                text=get_button_text('btn_enter_custom_timezone', language),
                callback_data="timezone_enter_manually"
            )
        ],
        # Кнопка "Определить автоматически" может быть добавлена позже
        # [
        #     InlineKeyboardButton(
        #         text=get_button_text('btn_detect_timezone', language),
        #         callback_data="timezone_detect_auto"
        #     )
        # ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="settings"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_common_timezones_keyboard(language: str, current_timezone: str) -> InlineKeyboardMarkup:
    """Клавиатура с популярными часовыми поясами"""
    
    # Определяем кнопки для часовых поясов
    timezone_buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_timezone_utc', language),
                callback_data="set_timezone:UTC"
            )
        ],
        # Российские часовые пояса
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
                text=get_button_text('btn_timezone_magadan', language),
                callback_data="set_timezone:Asia/Magadan"
            )
        ],
        # Другие популярные пояса (можно расширить)
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