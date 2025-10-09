# /home/shlicha/psycho_diary/bot/handlers/therapy_chat_handlers.py
"""
Обработчики для чата с психологом ИИ.
"""

import logging
from asgiref.sync import sync_to_async # Добавляем импорт
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext

from bot.decorators.token_decorator import requires_tokens
from bot.keyboards.common_keyboards import get_single_button_keyboard
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.therapy_chat_service import process_therapy_message
from bot.states.therapy_chat_states import TherapyChatStates
from bot.utils.message_utils import (
    safe_edit_message_text,
    send_processing_message,
    safe_edit_message_reply_markup # Импортируем новую утилиту
)
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from bot.utils.audio_utils import process_voice_message
from bot.services.diary_service import get_user_streaks
from messages import get_message, get_button_text

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "start_therapy_chat")
async def start_therapy_chat_callback(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Обработчик нажатия кнопки "Поговорить с психологом".
    """
    try:
        # Проверяем, является ли пользователь премиумом
        if user.is_premium:
            welcome_message = get_message('therapy_chat_welcome_premium', language)
        else:
            welcome_message = get_message('therapy_chat_welcome_paid', language)

        # Отправляем приветственное сообщение
        await callback.message.answer(
            welcome_message,
            reply_markup=get_single_button_keyboard(language, button_callback_data="main_menu", button_text='btn_end_chat')
            )

        # Устанавливаем состояние
        await state_manager.set_state(state, TherapyChatStates.in_therapy_chat)

        # Инициализируем пустую историю в состоянии FSM
        # Используем список для удобства форматирования, будем хранить пары (role, content)
        await state_manager.update_state_data(state, therapy_history=[])
        logger.debug(f"Состояние in_therapy_chat установлено для пользователя {user.telegram_id}. История инициализирована.")

        await safe_answer_callback(callback)

    except Exception as e:
        logger.error(f"Ошибка при запуске чата с психологом: {e}", exc_info=True)
        await callback.message.answer(get_message('error_generic', language))
        await safe_answer_callback(callback)


@router.message(TherapyChatStates.in_therapy_chat, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@requires_tokens(cost=1)
async def handle_therapy_message(message: Message, user, language: str, bot, state: FSMContext):
    """
    Обработчик текстовых и голосовых сообщений в состоянии in_therapy_chat.
    """
    processing_msg = None
    ai_response_msg = None # Теперь ai_response_msg - это processing_msg
    user_message_text = ""

    try:
        # --- Обработка голосового или текстового сообщения ---
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

        # --- Основная логика обработки текста ---
        if not processing_msg:
             processing_msg = await send_processing_message(bot, message.chat.id, language)

        state_data = await state_manager.get_state_data(state)
        current_history_list = state_data.get('therapy_history', [])
        history_str = "\n".join([f"{item['role']}: {item['content']}" for item in current_history_list])
        base_user_profile = await user.aget_profile_data()

        # Формируем расширенный контекст, как в другом хендлере
        extended_user_context = {
            "first_name": base_user_profile.get('first_name', 'Пользователь'),
            "awareness_level": base_user_profile.get('awareness_level', 1),
            "is_premium": base_user_profile.get('is_premium', False),
            "entries_count": base_user_profile.get('entries_count', 0),
            "personality_traits": user.personality_traits,
            "life_facts": user.life_facts,
            "hobbies": user.hobbies,
            "core_values": user.core_values,
            "triggers": user.triggers,
            "strengths": user.strengths,
            "areas_for_growth": user.areas_for_growth,
            "habits": user.habits,
            "skills": user.skills,
            "aspirations": user.aspirations
        }

        # Вызываем сервис для обработки сообщения, передавая расширенный контекст
        service_result = await process_therapy_message(
            user_profile=extended_user_context, # <-- Передаём extended_user_context
            history=history_str,
            user_message=user_message_text,
            language=language
        )

        is_valid = service_result.get('is_valid', False)
        ai_response_text = service_result.get('response_text', get_message('no_comment', language))

        new_pair = [
            {'role': 'Пользователь', 'content': user_message_text},
            {'role': 'ИИ', 'content': ai_response_text}
        ]
        updated_history = current_history_list + new_pair

        # --- Ограничение истории последними 10 парами (20 элементами) ---
        # Каждая пара состоит из 2 элементов: {'role': 'Пользователь', ...} и {'role': 'ИИ', ...}
        MAX_HISTORY_PAIRS = 10
        MAX_HISTORY_ITEMS = MAX_HISTORY_PAIRS * 2
        if len(updated_history) > MAX_HISTORY_ITEMS:
            # Сохраняем только последние MAX_HISTORY_ITEMS элементов
            updated_history = updated_history[-MAX_HISTORY_ITEMS:]
        # --- Конец ограничения ---

        await state_manager.update_state_data(state, therapy_history=updated_history)

        # Редактируем сообщение "идет анализ", заменяя его на ответ ИИ (пока без клавиатуры)
        # Используем safe_edit_message_text для безопасности
        edit_success = await safe_edit_message_text(processing_msg, ai_response_text)
        if not edit_success:
            logger.warning(f"[Therapy Chat] Не удалось отредактировать сообщение с ответом ИИ для user {user.telegram_id}")
            # Если не получилось отредактировать, возможно, сообщение устарело, но мы всё равно попробуем прикрепить клавиатуру к processing_msg
        # Сохраняем объект сообщения с ответом ИИ (это теперь processing_msg)
        ai_response_msg = processing_msg

        # Отправляем сообщение с кнопкой "В главное меню", прикрепленной к предыдущему сообщению (ответу ИИ)
        back_to_menu_keyboard = get_single_button_keyboard(language, button_callback_data="main_menu", button_text='btn_end_chat')
        # Обновляем reply_markup у сообщения с ответом ИИ с помощью безопасной утилиты
        keyboard_update_success = await safe_edit_message_reply_markup(ai_response_msg, reply_markup=back_to_menu_keyboard)
        if not keyboard_update_success:
            logger.warning(f"[Therapy Chat] Не удалось прикрепить клавиатуру к сообщению с ответом ИИ для user {user.telegram_id}")


    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения в чате с психологом: {e}", exc_info=True)
        # Пытаемся отредактировать сообщение "идет анализ" на сообщение об ошибке
        if processing_msg:
            try:
                await processing_msg.edit_text(get_message('error_processing', language))
                # Убираем клавиатуру в случае ошибки, если она была
                # ai_response_msg может быть тем же, что и processing_msg
                if ai_response_msg and ai_response_msg.message_id == processing_msg.message_id:
                    await safe_edit_message_reply_markup(ai_response_msg, reply_markup=None)
            except Exception as edit_error:
                logger.error(f"Ошибка при редактировании сообщения 'идет анализ' или 'ответ ИИ': {edit_error}")
                try:
                    await message.answer(get_message('error_processing', language))
                except Exception as send_error:
                    logger.error(f"Ошибка при отправке сообщения об ошибке пользователю {user.telegram_id}: {send_error}")

        # Возврат в главное меню в случае ошибки
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
                reply_markup=get_main_menu_keyboard(language, user)
            )
            await state_manager.clear_state(state)
        except Exception as reset_error:
            logger.error(f"Ошибка при попытке вернуть пользователя в главное меню после ошибки: {reset_error}")
