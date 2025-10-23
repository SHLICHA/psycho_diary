"""
Handlers для процесса онбординга (знакомства) нового пользователя.
"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from messages import get_message
from bot.states.onboarding_states import OnboardingStates
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "onboarding_start_first_entry") # <-- Предположим, это callback_data для старта нового онбординга
async def start_agreement_and_first_entry_flow(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Начинает новый процесс онбординга: краткое приветствие -> соглашение -> согласие -> первая запись.
    """
    try:
        pass
    except Exception as e:
        logger.error(f"Ошибка при запуске нового онбординга для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

# --- НОВЫЙ ХЕНДЛЕР: Обработка согласия в новом онбординге ---
@router.callback_query(F.data == "onboarding_agree_and_start_first_entry", OnboardingStates.show_agreement_for_first_entry) # <-- Фильтр по состоянию
async def handle_agreement_for_first_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает согласие пользователя в новом онбординге и запускает первую запись."""
    try:
        # 1. Обновить профиль пользователя: has_agreed_to_terms = True
        @sync_to_async
        def update_user_agreement():
            user.has_agreed_to_terms = True
            user.save(update_fields=['has_agreed_to_terms'])
        await update_user_agreement()
        # 2. Отправить сообщение "спасибо за согласие"
        thank_you_msg = get_message('onboarding_thank_you_for_agreement_first_entry', language)
        await safe_edit_message_text(
            message=callback.message,
            text=thank_you_msg
        )
        await safe_answer_callback(callback, "")
        await state_manager.clear_state(state)

        from bot.handlers.diary import start_first_entry_flow
        await start_first_entry_flow(callback.message, state, user, language)
    except Exception as e:
        logger.error(f"Ошибка при обработке согласия для первой записи пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

# --- НОВЫЙ ХЕНДЛЕР: Обработка отказа в новом онбординге ---
@router.callback_query(F.data == "onboarding_disagree_and_exit", OnboardingStates.show_agreement_for_first_entry) # <-- Фильтр по состоянию
async def handle_agreement_decline_for_first_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает отказ пользователя от согласия в новом онбординге."""
    try:
        declined_msg = get_message('onboarding_disagreed', language) # <-- Используем старое сообщение или создадим новое
        await state_manager.clear_state(state)
        await safe_edit_message_text(
            message=callback.message,
            text=declined_msg
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при обработке отказа пользователя {user.telegram_id} в новом онбординге: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

