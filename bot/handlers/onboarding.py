# /home/shlicha/psycho_diary/bot/handlers/onboarding.py
"""Онбординг handlers — transport-only."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext

from messages import get_message
from bot.states.onboarding_states import OnboardingStates
from bot.keyboards import get_single_button_keyboard
from bot.utils.message_utils import safe_edit_message_text, send_processing_message
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from bot.utils.audio_utils import process_voice_message
from bot.services.diary_service import diary_service
from bot.decorators.analytics_decorator import log_user_activity
from diary.services.onboarding_service import (
    build_onboarding_timezone_prompt_view,
    build_first_onboarding_entry_result_view,
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "onboarding_agree_1")
@log_user_activity('onboarding', metadata_extra={'context': 'Согласие с приветствием'})
async def onboarding_agree_1(callback: CallbackQuery, state: FSMContext, user, language: str):
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_agreement_1:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        info_msg = get_message('onboarding_project_info', language)
        keyboard = get_single_button_keyboard(
            language, button_callback_data="onboarding_agree_2", button_text='btn_next'
        )
        await safe_edit_message_text(message=callback.message, text=info_msg, reply_markup=keyboard)
        await state_manager.set_state(state, OnboardingStates.waiting_for_agreement_2)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[onboarding_agree_1] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)


@router.callback_query(F.data == "onboarding_agree_2")
@log_user_activity('onboarding', metadata_extra={'context': 'Согласие с инструкцией, переход к часовому поясу'})
async def onboarding_agree_2(callback: CallbackQuery, state: FSMContext, user, language: str):
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_agreement_2:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return

        view = await build_onboarding_timezone_prompt_view(
            user, language, include_info_prefix=True, show_back_button=False
        )
        if not view.get('success'):
            await safe_answer_callback(callback, get_message('error_generic', language))
            return

        if view.get('set_origin'):
            await state_manager.update_state_data(state, origin=view['set_origin'])
        await safe_edit_message_text(
            message=callback.message, text=view['text'], reply_markup=view['reply_markup']
        )
        await state_manager.set_state(state, OnboardingStates.waiting_for_timezone_confirmation)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[onboarding_agree_2] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)


@router.message(OnboardingStates.waiting_for_first_entry, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('entry_created', metadata_extra={'context': 'Первая запись онбординга (текст/голос) (новый порядок)'})
async def process_first_entry(message: Message, state: FSMContext, user, language: str):
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_first_entry:
            return

        entry_text = ""
        if message.content_type == ContentType.VOICE:
            status_msg = await send_processing_message(message.bot, message.chat.id, language)
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="OnboardingFirstEntry",
                language=language,
                status_msg=status_msg
            )
            if not success:
                await message.answer(
                    get_message('error_voice_recognition', language, error_message=error_message)
                )
                await state_manager.clear_state(state)
                return
            entry_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            entry_text = message.text
            status_msg = await send_processing_message(message.bot, message.chat.id, language)
        else:
            await message.answer(get_message('invalid_input', language))
            return

        if not entry_text.strip():
            await message.answer(get_message('entry_empty', language))
            return

        response = await diary_service.process_first_onboarding_entry_use_case(
            user=user,
            entry_text=entry_text,
            language=language,
            entry_datetime=None
        )
        view = build_first_onboarding_entry_result_view(response, language)

        if not view.get('success'):
            try:
                await status_msg.edit_text(text=view['text'], reply_markup=None)
            except Exception as edit_error:
                logger.error(f"Не удалось отредактировать сообщение 'Обработка...': {edit_error}")
                final_message_text = (
                    f"{view['text']}\n\n{get_message('onboarding_try_again_prompt', language)}"
                )
                await message.answer(
                    final_message_text,
                    reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel'),
                )
            return

        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language)
        await message.answer(text=view['text'], reply_markup=main_menu_keyboard)
        if view.get('clear_state'):
            await state_manager.clear_state(state)
    except Exception as e:
        logger.error(
            f"[process_first_entry] Ошибка обработки первой записи для {user.telegram_id}: {e}",
            exc_info=True,
        )
        try:
            await message.answer(get_message('error_generic', language))
        except Exception as msg_error:
            logger.error(f"[process_first_entry] Ошибка при отправке сообщения об ошибке: {msg_error}")
        await state_manager.clear_state(state)


@router.callback_query(F.data == "onboarding_ask_timezone")
@log_user_activity('onboarding', metadata_extra={'context': 'Запрос установки часового пояса'})
async def onboarding_ask_timezone(callback: CallbackQuery, state: FSMContext, user, language: str):
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_timezone_confirmation:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return

        view = await build_onboarding_timezone_prompt_view(
            user, language, include_info_prefix=True, show_back_button=False
        )
        if not view.get('success'):
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        if view.get('set_origin'):
            await state_manager.update_state_data(state, origin=view['set_origin'])
        await safe_edit_message_text(
            message=callback.message, text=view['text'], reply_markup=view['reply_markup']
        )
    except Exception as e:
        logger.error(
            f"[onboarding_ask_timezone] Ошибка для пользователя {user.telegram_id}: {e}",
            exc_info=True,
        )
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
