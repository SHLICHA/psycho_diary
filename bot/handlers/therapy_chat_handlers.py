"""
Обработчики для чата с психологом ИИ.
Теперь содержат только логику взаимодействия с Telegram.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext

from bot.decorators.token_decorator import requires_tokens
from bot.decorators.analytics_decorator import log_user_activity
from bot.keyboards.common_keyboards import get_single_button_keyboard
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.states.therapy_chat_states import TherapyChatStates
from bot.utils.message_utils import (
    safe_edit_message_text,
    send_processing_message,
    safe_edit_message_reply_markup
)
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from bot.utils.audio_utils import process_voice_message
from bot.utils.diary_utils import get_user_streaks
from messages import get_message
from diary.services.therapy_chat_service import start_therapy_chat, process_user_message_in_chat, end_therapy_chat

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "start_therapy_chat")
@log_user_activity('chat')
async def start_therapy_chat_callback(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Обработчик нажатия кнопки "Поговорить с психологом".
    """
    try:
        init_result = await start_therapy_chat(user)
        if not init_result['success']:
            logger.error(f"Ошибка инициализации чата для {user.telegram_id}: {init_result.get('error')}")
            await callback.message.answer(get_message('error_generic', language))
            await safe_answer_callback(callback)
            return
        if user.is_premium:
            welcome_message = get_message('therapy_chat_welcome_premium', language)
        else:
            welcome_message = get_message('therapy_chat_welcome_paid', language)

        await callback.message.answer(
            welcome_message,
            reply_markup=get_single_button_keyboard(language, button_callback_data="main_menu", button_text='btn_end_chat')
        )
        await state_manager.set_state(state, TherapyChatStates.in_therapy_chat)
        initial_history = init_result.get('initial_history', [])
        await state_manager.update_state_data(state, therapy_history=initial_history)
        logger.debug(f"Состояние in_therapy_chat установлено для пользователя {user.telegram_id}. История инициализирована.")
        await safe_answer_callback(callback)
    except Exception as e:
        logger.error(f"Ошибка при запуске чата с психологом: {e}", exc_info=True)
        await callback.message.answer(get_message('error_generic', language))
        await safe_answer_callback(callback)

@router.message(TherapyChatStates.in_therapy_chat, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@requires_tokens(cost=1)
@log_user_activity('chat', metadata_extra={'context': 'Обработка сообщения'})
async def handle_therapy_message(message: Message, user, language: str, bot, state: FSMContext):
    """
    Обработчик текстовых и голосовых сообщений в состоянии in_therapy_chat.
    """
    processing_msg = None
    ai_response_msg = None
    user_message_text = ""
    try:
        if message.content_type == ContentType.VOICE:
            processing_msg = await send_processing_message(bot, message.chat.id, language)
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Therapy Chat",
                language=language,
                status_msg=processing_msg
            )
            if not success:
                error_text = f"{get_message('error_processing_voice', language)}: {error_message}"
                if processing_msg:
                    await processing_msg.edit_text(error_text)
                else:
                    await message.answer(error_text)
                return
            user_message_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            user_message_text = message.text
        else:
            logger.warning(f"[Therapy Chat] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        if not processing_msg:
             processing_msg = await send_processing_message(bot, message.chat.id, language)
        state_data = await state_manager.get_state_data(state)
        current_history_list = state_data.get('therapy_history', [])
        service_result = await process_user_message_in_chat(
            user=user,
            user_message_text=user_message_text,
            current_history=current_history_list
        )
        if not service_result['success']:
            logger.error(f"Ошибка в сервисе обработки сообщения чата: {service_result.get('error')}")
            ai_response_text = get_message('error_processing', language)
            updated_history = current_history_list
        else:
            ai_response_text = service_result['response_text']
            updated_history = service_result['updated_history']
        await state_manager.update_state_data(state, therapy_history=updated_history)
        edit_success = await safe_edit_message_text(processing_msg, ai_response_text)
        if not edit_success:
            logger.warning(f"[Therapy Chat] Не удалось отредактировать сообщение с ответом ИИ для user {user.telegram_id}")
        ai_response_msg = processing_msg
        back_to_menu_keyboard = get_single_button_keyboard(language, button_callback_data="main_menu", button_text='btn_end_chat')
        keyboard_update_success = await safe_edit_message_reply_markup(ai_response_msg, reply_markup=back_to_menu_keyboard)
        if not keyboard_update_success:
            logger.warning(f"[Therapy Chat] Не удалось прикрепить клавиатуру к сообщению с ответом ИИ для user {user.telegram_id}")
    except Exception as e:
        logger.error(f"Критическая ошибка в хендлере чата с психологом: {e}", exc_info=True)
        if processing_msg:
            try:
                await processing_msg.edit_text(get_message('error_processing', language))
                if ai_response_msg and ai_response_msg.message_id == processing_msg.message_id:
                    await safe_edit_message_reply_markup(ai_response_msg, reply_markup=None)
            except Exception as edit_error:
                logger.error(f"Ошибка при редактировании сообщения 'идет анализ' или 'ответ ИИ': {edit_error}")
                try:
                    await message.answer(get_message('error_processing', language))
                except Exception as send_error:
                    logger.error(f"Ошибка при отправке сообщения об ошибке пользователю {user.telegram_id}: {send_error}")
        try:
            profile_data = await user.aget_profile_data()
            first_name = profile_data.get('first_name', get_message('user_default_name', language))
            awareness_level = profile_data.get('awareness_level', 1)
            entries_count = profile_data.get('entries_count', 0)
            token_balance = user.token_balance
            current_streak, max_streak = await get_user_streaks(user)
            streak_info = ""
            if current_streak > 0:
                streak_info = get_message('current_streak_info', language, current_streak=current_streak)
                if current_streak == 1:
                     streak_info += " " + get_message('keep_going_1_day', language)
                elif 2 <= current_streak <= 4:
                     streak_info += " " + get_message('keep_going_few_days', language)
                elif current_streak >= 5:
                     streak_info += " " + get_message('keep_going_streak', language)
            else:
                streak_info = get_message('no_current_streak', language)
            max_streak_info = ""
            if max_streak > 0:
                max_streak_info = get_message('max_streak_info', language, max_streak=max_streak)
            main_menu_msg = get_message('main_menu_welcome_back', language,
                                       first_name=first_name,
                                       awareness_level=awareness_level,
                                       entries_count=entries_count,
                                       token_balance=token_balance,
                                       streak_info=streak_info,
                                       max_streak_info=max_streak_info)
            await message.answer(
                main_menu_msg,
                reply_markup=await get_main_menu_keyboard(language, user)
            )
            await state_manager.clear_state(state)
        except Exception as reset_error:
            logger.error(f"Ошибка при попытке вернуть пользователя в главное меню после ошибки: {reset_error}")
