# /home/shlicha/psycho_diary/bot/handlers/onboarding.py

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from messages import get_message, get_mood_text
from bot.states.onboarding_states import OnboardingStates
from bot.keyboards import get_single_button_keyboard, get_timezone_selection_method_keyboard
from bot.utils.message_utils import safe_edit_message_text, send_processing_message
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from bot.utils.audio_utils import process_voice_message
from bot.services import diary_service
from bot.decorators.analytics_decorator import log_user_activity

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "onboarding_agree_1")
@log_user_activity('onboarding', metadata_extra={'context': 'Согласие с приветствием'})
async def onboarding_agree_1(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обработка нажатия 'Далее' после приветственного сообщения."""
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_agreement_1:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        info_msg = get_message('onboarding_project_info', language)
        keyboard = get_single_button_keyboard(language, button_callback_data="onboarding_agree_2", button_text='btn_next')
        await safe_edit_message_text(message=callback.message, text=info_msg, reply_markup=keyboard)
        await state_manager.set_state(state, OnboardingStates.waiting_for_agreement_2)
        await safe_answer_callback(callback, "")
        logger.debug(f"[onboarding_agree_1] Пользователь {user.telegram_id} перешел к шагу 2 онбординга.")
    except Exception as e:
        logger.error(f"[onboarding_agree_1] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data == "onboarding_agree_2")
@log_user_activity('onboarding', metadata_extra={'context': 'Согласие с инструкцией'})
async def onboarding_agree_2(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обработка нажатия 'Далее' после сообщения с инструкцией."""
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_agreement_2:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        if not user.is_onboarding_completed:
            user.is_onboarding_completed = True
            await sync_to_async(user.save)(update_fields=['is_onboarding_completed'])
            logger.info(f"[onboarding_agree_2] Онбординг отмечен как завершён для пользователя {user.telegram_id} (после шага 2).")
        prompt_msg = get_message('onboarding_prompt_first_entry', language)
        await safe_edit_message_text(message=callback.message, text=prompt_msg, reply_markup=None)
        await state_manager.set_state(state, OnboardingStates.waiting_for_first_entry)
        await safe_answer_callback(callback, "")
        logger.debug(f"[onboarding_agree_2] Пользователь {user.telegram_id} перешел к шагу 3 (ожидание записи) онбординга.")
    except Exception as e:
        logger.error(f"[onboarding_agree_2] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.message(OnboardingStates.waiting_for_first_entry, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('entry_created', metadata_extra={'context': 'Первая запись онбординга (текст/голос)'})
async def process_first_entry(message: Message, state: FSMContext, user, language: str):
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_first_entry:
            logger.debug(f"Сообщение от {user.telegram_id} не обработано - не в состоянии ожидания записи.")
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
                logger.error(f"[process_first_entry] Ошибка распознавания голоса для {user.telegram_id}: {error_message}")
                await message.answer(get_message('error_voice_recognition', language, error_message=error_message))
                await state_manager.clear_state(state)
                return
            entry_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            entry_text = message.text
            status_msg = await send_processing_message(message.bot, message.chat.id, language)
        else:
            logger.debug(f"Получен неподдерживаемый тип контента от {user.telegram_id} в онбординге: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return

        if not entry_text.strip():
            await message.answer(get_message('entry_empty', language))
            return

        processing_result = await diary_service.process_first_onboarding_entry_logic(
            user=user,
            entry_text=entry_text,
            language=language,
            entry_datetime=None
        )

        if not processing_result.get('success'):
            logger.debug(f"Первая запись пользователя {user.telegram_id} не прошла валидацию ИИ.")
            formatted_message_ai = processing_result.get('formatted_message_ai')
            try:
                final_message_text = formatted_message_ai
                await status_msg.edit_text(text=final_message_text, reply_markup=None)
            except Exception as edit_error:
                logger.error(f"Не удалось отредактировать сообщение 'Обработка...' для ошибки валидации: {edit_error}")
                final_message_text = f"{formatted_message_ai}\n\n{get_message('onboarding_try_again_prompt', language)}"
                await message.answer(final_message_text, reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel'))
            return

        diary_entry = processing_result['entry']

        try:
            mood_score = processing_result.get('mood_score', 5)
            comment = processing_result.get('comment', get_message('no_comment', language))
            recommendation = processing_result.get('recommendation', get_message('no_recommendation', language))
        except KeyError as e:
            logger.error(f"Не все ожидаемые ключи найдены в processing_result: {e}")
            mood_score = 5
            comment = get_message('no_comment', language)
            recommendation = get_message('no_recommendation', language)

        mood_text = get_mood_text(mood_score, language)

        full_text_to_send = get_message('entry_saved', language,
                                        score=mood_score,
                                        mood=mood_text,
                                        comment=comment,
                                        recommendation=recommendation)
        keyboard_with_next = get_single_button_keyboard(language, button_callback_data="onboarding_ask_timezone", button_text='btn_next')
        try:
            await status_msg.edit_text(text=full_text_to_send, reply_markup=keyboard_with_next)
        except Exception as edit_error:
            logger.error(f"Не удалось отредактировать сообщение 'Обработка...' с результатом анализа: {edit_error}")
            await message.answer(text=full_text_to_send, reply_markup=keyboard_with_next)

        await state_manager.set_state(state, OnboardingStates.waiting_for_timezone_confirmation)
        logger.debug(f"[process_first_entry] Первая запись {diary_entry.id} обработана, показан результат, ожидаем установку часового пояса от {user.telegram_id}.")
    except Exception as e:
        logger.error(f"[process_first_entry] Ошибка обработки первой записи для {user.telegram_id}: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_generic', language))
        except Exception as msg_error:
            logger.error(f"[process_first_entry] Ошибка при отправке сообщения об ошибке: {msg_error}")
        await state_manager.clear_state(state)

@router.callback_query(F.data == "onboarding_ask_timezone")
@log_user_activity('onboarding', metadata_extra={'context': 'Запрос установки часового пояса'})
async def onboarding_ask_timezone(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает сообщение с просьбой указать часовой пояс."""
    try:
        current_state = await state_manager.get_current_state(state)
        if current_state != OnboardingStates.waiting_for_timezone_confirmation:
            logger.warning(f"Пользователь {user.telegram_id} пытается пропустить шаг онбординга.")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        timezone_info_msg = get_message('onboarding_timezone_info', language)
        await state_manager.update_state_data(state, origin='onboarding_timezone_setup')
        logger.debug(f"[onboarding_ask_timezone] Установлен origin='onboarding_timezone_setup' в state для {user.telegram_id}.")
        from diary.services.settings_service import get_timezone_info
        info_result = await get_timezone_info(user)
        if not info_result['success']:
            logger.error(f"Ошибка при получении информации о часовом поясе: {info_result.get('error')}")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        current_timezone = info_result['current_timezone']
        timezone_msg = get_message('ask_timezone_selection', language, current_timezone=current_timezone)
        reply_markup = get_timezone_selection_method_keyboard(language, current_timezone, show_back_button=False)
        await safe_edit_message_text(message=callback.message, text=timezone_info_msg + "\n\n" + timezone_msg, reply_markup=reply_markup)
        logger.debug(f"[onboarding_ask_timezone] Показан выбор часового пояса для {user.telegram_id} (origin установлен).")
    except Exception as e:
        logger.error(f"[onboarding_ask_timezone] Ошибка для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
