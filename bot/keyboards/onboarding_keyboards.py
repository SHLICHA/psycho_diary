# /home/shlicha/psycho_diary/bot/keyboards/onboarding_keyboards.py
"""
Клавиатуры для процесса онбординга.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text

def get_start_onboarding_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для начала процесса онбординга.
    Используется, когда пользователь пытается получить доступ без согласия.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_button_text('btn_start_onboarding', language),
                callback_data="onboarding_start"
            )
        ]
    ])
    return keyboard

def get_instruction_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для экрана с инструкцией.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_button_text('btn_next', language),
                callback_data="onboarding_next_to_agreement"
            )
        ]
    ])
    return keyboard

def get_agreement_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для экрана с соглашением.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_button_text('btn_agree', language),
                callback_data="onboarding_agree"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_disagree', language),
                callback_data="onboarding_disagree"
            )
        ]
    ])
    return keyboard

def get_agreement_keyboard_for_first_entry(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для соглашения в новом онбординге (соглашение -> первая запись)."""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_agree_and_start_first_entry', language),
                callback_data="onboarding_agree_and_start_first_entry" # <-- Новое callback_data
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_disagree_and_exit', language),
                callback_data="onboarding_disagree_and_exit" # <-- Новое callback_data
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_skip_questionnaire_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для пропуска анкетирования.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_button_text('btn_skip_questionnaire', language),
                callback_data="onboarding_skip_questionnaire"
            )
        ]
    ])
    return keyboard

def get_submit_answers_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для отправки ответов на анкету.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_button_text('btn_submit_answers', language),
                callback_data="onboarding_submit_questionnaire"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_button_text('btn_skip_questionnaire', language),
                callback_data="onboarding_skip_questionnaire"
            )
        ]
    ])
    return keyboard