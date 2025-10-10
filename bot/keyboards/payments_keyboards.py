# bot/keyboards/premium_keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text
from django.conf import settings

def get_purchase_options_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами покупки: подписка и токены."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"👑 Подписка (месяц) — {settings.PREMIUM_PRICE_MONTH}₽",
                callback_data="purchase_subscription:month"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"👑 Подписка (год) — {settings.PREMIUM_PRICE_YEAR}₽",
                callback_data="purchase_subscription:year"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_purchase_tokens', language),
                callback_data="purchase_tokens:start"
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

def get_manage_premium_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для управления активной подпиской."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔄 Продлить подписку",
                callback_data="purchase_subscription:month"  # или отдельный callback
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_purchase_tokens', language),
                callback_data="purchase_tokens:start"
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

def get_token_purchase_options_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами покупки токенов."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"💎 10 токенов — {settings.TOKEN_PACK_10}₽",
                callback_data="purchase_tokens:10"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"💎 100 токенов — {settings.TOKEN_PACK_100}₽",
                callback_data="purchase_tokens:100"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"💎 200 токенов — {settings.TOKEN_PACK_200}₽",
                callback_data="purchase_tokens:200"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"💎 500 токенов — {settings.TOKEN_PACK_500}₽",
                callback_data="purchase_tokens:500"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔢 Ввести количество",
                callback_data="purchase_tokens:custom"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="settings_premium"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_token_custom_amount_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Назад' для ввода произвольного количества токенов."""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="purchase_tokens:start"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_premium_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура премиум функций"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_subscribe', language),
                callback_data="premium_subscribe"
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