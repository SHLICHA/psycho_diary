# /home/shlicha/psycho_diary/bot/handlers/start.py
"""
Handler для команды /start (transport-only).
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from django.conf import settings

from messages import get_message
from bot.decorators.analytics_decorator import log_user_activity
from bot.keyboards import get_main_menu_keyboard
from bot.states.onboarding_states import OnboardingStates
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from diary.services.main_menu_service import build_main_menu_data
from diary.services.user_service import resolve_web_link_target, link_telegram_identity
from diary.services.onboarding_service import resolve_start_routing_use_case
from users.services.auth_token_service import (
    create_messenger_auth_token,
    validate_web_link_token,
)

router = Router()
logger = logging.getLogger(__name__)

WEB_LINK_PATTERN = "link_"


@router.message(Command("web"))
@log_user_activity('command', metadata_extra={'context': '/web'})
async def cmd_web(message: Message, user, language: str, **kwargs):
    """Генерирует магическую ссылку для входа в web-версию."""
    try:
        token = create_messenger_auth_token(user.id, platform='telegram')
        web_app_url = getattr(settings, 'WEB_APP_URL', 'http://127.0.0.1:8000').rstrip('/')
        auth_url = f"{web_app_url}/auth/telegram/?token={token}"
        web_link_msg = get_message('web_link_generated', language, auth_url=auth_url)
        await message.answer(web_link_msg)
        logger.info(f"Сгенерирована web-ссылка для пользователя {user.telegram_id}")
    except Exception as e:
        logger.error(f"[cmd_web] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.message(Command("start", magic=F.args.startswith(WEB_LINK_PATTERN)))
async def cmd_start_link(message: Message, user, language: str, state: FSMContext, **kwargs):
    """Обработчик /start link_XXX для привязки Telegram к web-аккаунту."""
    try:
        command_text = message.text or ""
        logger.debug(f"[cmd_start_link] Получена команда: {command_text}")

        if not command_text.startswith(f"/start {WEB_LINK_PATTERN}"):
            return

        token = command_text.replace(f"/start {WEB_LINK_PATTERN}", "", 1).strip()
        if not token:
            await message.answer(get_message('web_link_invalid', language))
            return

        web_user_id = validate_web_link_token(token)
        if not web_user_id:
            await message.answer(get_message('web_link_expired', language))
            return

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

        await link_telegram_identity(web_user, user.telegram_id)
        logger.info(f"[cmd_start_link] Telegram {user.telegram_id} привязан к web-аккаунту {web_user.id}")
        success_msg = get_message(
            'web_link_success', language, username=web_user.username or str(web_user.id)
        )
        await message.answer(success_msg)
    except Exception as e:
        logger.error(f"[cmd_start_link] Ошибка: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.message(Command("start", magic=F.args.is_(None)))
@log_user_activity('command', metadata_extra={'context': '/start'})
async def cmd_start(message: Message, user, language: str, state: FSMContext, data: dict = None, **kwargs):
    """Transport: resolve_start_routing_use_case → send/FSM."""
    try:
        current_state = await state_manager.get_current_state(state)
        was_reactivated = kwargs.get('was_blocked_and_reactivated', False)
        view = await resolve_start_routing_use_case(
            user=user,
            language=language,
            current_fsm_state=current_state,
            was_reactivated=was_reactivated,
        )
        if not view.get('success'):
            await message.answer(view.get('text') or get_message('error_generic', language))
            return

        if view.get('clear_state'):
            await state_manager.clear_state(state)
        if view.get('set_state') == 'waiting_for_agreement_1':
            await state_manager.set_state(state, OnboardingStates.waiting_for_agreement_1)

        if view.get('reactivation_text'):
            await message.answer(view['reactivation_text'])

        await message.answer(view['text'], reply_markup=view.get('reply_markup'))
        logger.debug(
            f"[cmd_start] mode={view.get('mode')} for user {user.telegram_id}, "
            f"fsm={current_state}"
        )
    except Exception as e:
        logger.error(f"[cmd_start] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))


@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Возврат в главное меню"""
    try:
        await state_manager.clear_state(state)
        menu_data = await build_main_menu_data(user=user, language=language)
        await safe_edit_message_text(
            message=callback.message,
            text=menu_data['message_text'],
            reply_markup=menu_data['keyboard'],
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[back_to_main_menu] Ошибка: {e}")
        try:
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('main_menu', language),
                reply_markup=await get_main_menu_keyboard(language, user),
            )
        except Exception as fallback_error:
            logger.error(f"[back_to_main_menu] Ошибка fallback: {fallback_error}")
        await safe_answer_callback(callback, get_message('error_generic', language))
