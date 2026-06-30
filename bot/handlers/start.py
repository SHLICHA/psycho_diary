# /home/shlicha/psycho_diary/bot/handlers/start.py
"""
Handler для команды /start
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from django.conf import settings

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
from diary.services.user_service import resolve_web_link_target, link_telegram_identity
from diary.services.settings_service import get_timezone_info
from users.services.auth_token_service import create_telegram_auth_token, validate_web_link_token
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

# Паттерн для /start link_XXX
WEB_LINK_PATTERN = "link_"


@router.message(Command("web"))
@log_user_activity('command', metadata_extra={'context': '/web'})
async def cmd_web(message: Message, user, language: str, **kwargs):
    """
    Обработчик команды /web
    Генерирует магическую ссылку для входа в web-версию приложения.
    """
    try:
        # Генерируем токен для авторизации
        token = create_telegram_auth_token(user.id)
        
        # Формируем ссылку
        web_app_url = getattr(settings, 'WEB_APP_URL', 'https://app.com')
        auth_url = f"{web_app_url}/auth/telegram?token={token}"
        
        web_link_msg = get_message('web_link_generated', language, auth_url=auth_url)
        await message.answer(web_link_msg)
        
        logger.info(f"Сгенерирована web-ссылка для пользователя {user.telegram_id}")
        
    except Exception as e:
        logger.error(f"[cmd_web] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.message(Command("start", magic=F.args.startswith(WEB_LINK_PATTERN)))
async def cmd_start_link(message: Message, user, language: str, state: FSMContext, **kwargs):
    """
    Обработчик /start link_XXX для привязки Telegram к web-аккаунту.
    """
    try:
        # Получаем текст команды после /start
        command_text = message.text or ""
        logger.debug(f"[cmd_start_link] Получена команда: {command_text}")

        # Проверяем, начинается ли с "link_"
        if not command_text.startswith(f"/start {WEB_LINK_PATTERN}"):
            # Это обычный /start, не обработка ссылки
            return

        # Извлекаем токен
        token = command_text.replace(f"/start {WEB_LINK_PATTERN}", "", 1).strip()

        if not token:
            await message.answer(get_message('web_link_invalid', language))
            return

        # Валидируем токен
        web_user_id = validate_web_link_token(token)

        if not web_user_id:
            await message.answer(get_message('web_link_expired', language))
            return

        # Единая policy проверки identity-linking.
        web_user, link_error = await resolve_web_link_target(web_user_id, user.telegram_id)
        if link_error == 'web_user_not_found':
            await message.answer(get_message('error_generic', language))
            return

        if link_error == 'telegram_already_linked':
            await message.answer(get_message('web_link_telegram_already_linked', language))
            return

        if link_error == 'account_already_linked':
            await message.answer(get_message('web_link_account_already_linked', language))
            return

        # Привязываем telegram_id к web-аккаунту (idempotent).
        await link_telegram_identity(web_user, user.telegram_id)

        logger.info(f"[cmd_start_link] Telegram {user.telegram_id} привязан к web-аккаунту {web_user.id}")

        success_msg = get_message('web_link_success', language, username=web_user.username or str(web_user.id))
        await message.answer(success_msg)

    except Exception as e:
        logger.error(f"[cmd_start_link] Ошибка: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.message(Command("start", magic=F.args.is_(None)))
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
        menu_data = await build_main_menu_data(user=user, language=language)
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
        menu_data = await build_main_menu_data(user=user, language=language)
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
