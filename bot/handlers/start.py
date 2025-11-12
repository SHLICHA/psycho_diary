# /home/shlicha/psycho_diary/bot/handlers/start.py
"""
Handler для команды /start
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from messages import get_message
from bot.decorators.analytics_decorator import log_user_activity
from bot.keyboards import (
    get_main_menu_keyboard,
    get_single_button_keyboard,
    get_timezone_selection_method_keyboard
)
from bot.states.onboarding_states import OnboardingStates
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from diary.services.main_menu_service import build_main_menu_data
from diary.services.settings_service import get_timezone_info

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
@log_user_activity('command', metadata_extra={'context': '/start'})
async def cmd_start(message: Message, user, language: str, state: FSMContext, data: dict = None, **kwargs):
    """
    Обработчик команды /start
    Проверяет, был ли пользователь разблокирован при взаимодействии (через middleware).
    Если да - отправляет специальное приветствие.
    Затем показывает новый онбординг (соглашение -> часовой пояс -> первая запись -> главное меню)
    или главное меню в зависимости от согласия и состояния FSM.
    """
    try:
        current_state = await state_manager.get_current_state(state)
        logger.debug(f"[cmd_start] Пользователь {user.telegram_id} в состоянии FSM: {current_state}, onboarding_completed: {user.is_onboarding_completed}")
        if current_state in [
            OnboardingStates.waiting_for_agreement_1,
            OnboardingStates.waiting_for_agreement_2,
            OnboardingStates.waiting_for_timezone_confirmation
        ]:
            logger.info(f"[cmd_start] Пользователь {user.telegram_id} в состоянии обязательного онбординга {current_state}, перенаправляем.")
            if current_state == OnboardingStates.waiting_for_agreement_1:
                welcome_msg = get_message('onboarding_welcome_extended_first_entry', language)
                keyboard = get_single_button_keyboard(language, button_callback_data="onboarding_agree_1", button_text='btn_next')
                await message.answer(welcome_msg, reply_markup=keyboard)
            elif current_state == OnboardingStates.waiting_for_agreement_2:
                info_msg = get_message('onboarding_project_info', language)
                keyboard = get_single_button_keyboard(language, button_callback_data="onboarding_agree_2", button_text='btn_next')
                await message.answer(info_msg, reply_markup=keyboard)
            elif current_state == OnboardingStates.waiting_for_timezone_confirmation:
                timezone_info_msg = get_message('onboarding_timezone_info', language)
                info_result = await get_timezone_info(user)
                if not info_result['success']:
                    logger.error(f"Ошибка при получении информации о часовом поясе для перенаправления: {info_result.get('error')}")
                    await message.answer(get_message('error_generic', language))
                    return
                current_timezone = info_result['current_timezone']
                timezone_msg = get_message('ask_timezone_selection', language, current_timezone=current_timezone)
                reply_markup = get_timezone_selection_method_keyboard(language, current_timezone, show_back_button=False)
                await message.answer(text=timezone_info_msg + "\n\n" + timezone_msg, reply_markup=reply_markup)
            return
        if not user.is_onboarding_completed:
            if current_state in [OnboardingStates.waiting_for_first_entry]:
                 logger.info(f"[cmd_start] Пользователь {user.telegram_id} в состоянии онбординга {current_state} (не обязательное, но не завершено), перенаправляем.")
                 prompt_msg = get_message('onboarding_prompt_first_entry', language)
                 await message.answer(text=prompt_msg, reply_markup=None)
                 return
            await state_manager.clear_state(state)
            welcome_msg = get_message('onboarding_welcome_extended_first_entry', language)
            keyboard = get_single_button_keyboard(language, button_callback_data="onboarding_agree_1", button_text='btn_next')
            await message.answer(welcome_msg, reply_markup=keyboard)
            await state_manager.set_state(state, OnboardingStates.waiting_for_agreement_1)
            logger.info(f"[cmd_start] Начат онбординг для пользователя {user.telegram_id} (FSM была в необязательном состоянии или None)")
            return
        await state_manager.clear_state(state)
        was_reactivated = kwargs.get('was_blocked_and_reactivated', False)
        logger.debug(f"[cmd_start] was_reactivated из kwargs: {was_reactivated}")
        if was_reactivated:
            reactivation_msg = get_message(
                'welcome_back_reactivated',
                language,
                first_name=user.first_name or user.username or get_message('user_default_name', language)
            )
            await message.answer(reactivation_msg)
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        keyboard = menu_data['keyboard']
        await message.answer(
            main_menu_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"[cmd_start] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.callback_query(F.data == "main_menu")
@log_user_activity('button', metadata_extra={'context': 'Главное меню'})
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Возврат в главное меню"""
    
    try:
        await state_manager.clear_state(state)
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        keyboard = menu_data['keyboard']
        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=keyboard
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[back_to_main_menu] Ошибка: {e}")
        try:
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('main_menu', language),
                reply_markup=await get_main_menu_keyboard(language, user)
            )
        except Exception as fallback_error:
            logger.error(f"[back_to_main_menu] Ошибка fallback: {fallback_error}")
        await safe_answer_callback(callback, get_message('error_generic', language))
