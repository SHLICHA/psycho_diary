# /home/shlicha/psycho_diary/bot/keyboards/onboarding_keyboards.py
"""
Клавиатуры для процесса онбординга.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages import get_button_text
# --- ИМПОРТ УНИВЕРСАЛЬНОЙ КЛАВИАТУРЫ ---
from bot.keyboards.common_keyboards import get_single_button_keyboard
# --- /ИМПОРТ ---

def get_start_onboarding_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для начала процесса онбординга.
    Используется, когда пользователь пытается получить доступ без согласия.
    (Остается для совместимости или устаревает в новом онбординге)
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
    (Остается для совместимости или устаревает в новом онбординге)
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
    (Остается для совместимости или устаревает в новом онбординге)
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
    """Клавиатура для соглашения в новом онбординге (соглашение -> первая запись). (Будет изменена или удалена)"""
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
    (Остается для совместимости или устаревает в новом онбординге)
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
    (Остается для совместимости или устаревает в новом онбординге)
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

# --- НОВЫЕ КЛАВИАТУРЫ ДЛЯ НОВОГО ОНБОРДИНГА (используют универсальную) ---

def get_next_after_welcome_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура после приветствия. Одна кнопка "Далее".
    Callback: onboarding_info_next
    """
    return get_single_button_keyboard(
        language=language,
        button_callback_data="onboarding_info_next",
        button_text="btn_next" # Используем существующий ключ 'btn_next'
    )

def get_next_after_info_keyboard(language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура после инструкции. Одна кнопка "Создать первую запись".
    Callback: onboarding_start_first_entry_new
    """
    return get_single_button_keyboard(
        language=language,
        button_callback_data="onboarding_ready_for_entry", # <-- Новый callback
        button_text="btn_ready_for_entry" # <-- Нужно добавить в messages
    )
