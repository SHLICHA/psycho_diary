"""
Handlers для процесса онбординга (знакомства) нового пользователя.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from messages import get_message
from bot.services import deepseek_api_service
from bot.states.onboarding_states import OnboardingStates
from bot.keyboards import (
    get_instruction_keyboard,
    get_agreement_keyboard,
    get_skip_questionnaire_keyboard,
    get_main_menu_keyboard
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from prompts import get_prompt

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "onboarding_start")
async def start_onboarding(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Начинает процесс онбординга: показывает расширенное приветствие и соглашение.
    """
    try:
        # Получаем расширенное приветственное сообщение
        welcome_msg = get_message('onboarding_welcome_extended', language) # <-- Используем новый ключ

        # Устанавливаем состояние "показ соглашения", так как это следующий шаг после нового сообщения
        await state.set_state(OnboardingStates.showing_agreement)

        # Редактируем текущее сообщение (где была нажата кнопка "onboarding_start"),
        # добавляя новое приветствие и клавиатуру соглашения
        await safe_edit_message_text(
            message=callback.message,
            text=welcome_msg,
            reply_markup=get_agreement_keyboard(language) # <-- Используем клавиатуру соглашения
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при запуске онбординга для пользователя {user.telegram_id}: {e}", exc_info=True)
        # В случае ошибки, всё равно пытаемся отправить сообщение об ошибке и закрыть состояние
        await safe_answer_callback(callback, get_message('error_generic', language))
        await state.clear() # <-- Очищаем состояние, если что-то пошло не так

@router.callback_query(F.data == "onboarding_agree")
async def handle_agreement_accept(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает согласие пользователя."""
    try:
        @sync_to_async
        def update_user_agreement():
            user.has_agreed_to_terms = True
            user.save(update_fields=['has_agreed_to_terms'])
        await update_user_agreement()
        thank_you_msg = get_message('onboarding_thank_you', language)
        await safe_edit_message_text(
            message=callback.message,
            text=thank_you_msg
        )
        await safe_answer_callback(callback, "")
        await start_questionnaire(callback, state, user, language)
    except Exception as e:
        logger.error(f"Ошибка при обработке согласия пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_disagree")
async def handle_agreement_decline(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает отказ пользователя от согласия."""
    try:
        declined_msg = get_message('onboarding_disagreed', language)
        await state.clear()
        await safe_edit_message_text(
            message=callback.message,
            text=declined_msg
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при обработке отказа пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(OnboardingStates.collecting_profile_data)
async def process_questionnaire_answer(message: Message, state: FSMContext, user, language: str):
    """Обрабатывает ответ на вопрос анкеты."""
    try:
        answer_text = message.text.strip()
        if not answer_text:
            await message.answer(get_message('invalid_input', language))
            return
        state_data = await state_manager.get_state_data(state)
        current_q_num = state_data.get("current_question", 1)
        answers = state_data.get("answers", {})
        answers[current_q_num] = answer_text
        await state_manager.update_state_data(state, answers=answers)
        await state_manager.update_state_data(state, current_question=current_q_num + 1)
        await ask_next_question(message, state, user, language)
    except Exception as e:
        logger.error(f"Ошибка при обработке ответа на вопрос {message.text} от пользователя {user.telegram_id}: {e}")
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_skip_questionnaire")
async def skip_questionnaire(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пропускает анкетирование."""
    try:
        await state_manager.clear_state(state)
        skip_msg = get_message('onboarding_skip_questionnaire', language)
        await safe_edit_message_text(
            message=callback.message,
            text=skip_msg
        )
        await safe_answer_callback(callback, "")
        welcome_back_msg = get_message('welcome_back', language, username=user.first_name or "Пользователь")
        await callback.message.answer(welcome_back_msg, reply_markup=get_main_menu_keyboard(language))
    except Exception as e:
        logger.error(f"Ошибка при пропуске анкетирования пользователем {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

async def start_questionnaire(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начинает процесс анкетирования."""
    try:
        questionnaire_data = {
            "current_question": 1,
            "answers": {}
        }
        await state_manager.set_state(state, OnboardingStates.collecting_profile_data)
        await state_manager.update_state_data(state, **questionnaire_data)
        await ask_next_question(callback.message, state, user, language)
    except Exception as e:
        logger.error(f"Ошибка при запуске анкетирования для пользователя {user.telegram_id}: {e}")
        await callback.message.answer(get_message('error_generic', language))

async def ask_next_question(message, state: FSMContext, user, language: str):
    """Отправляет следующий вопрос анкеты."""
    try:
        state_data = await state_manager.get_state_data(state)
        current_q_num = state_data.get("current_question", 1)
        answers = state_data.get("answers", {})
        question_key = f'onboarding_question_{current_q_num}'
        if current_q_num > 7:
            await finish_questionnaire(message, state, user, language, answers)
            return
        question_text = get_message(question_key, language)
        if not question_text or question_text.startswith('onboarding_question_'):
             logger.warning(f"Вопрос с ключом '{question_key}' не найден для языка '{language}'. Завершаем анкету.")
             await finish_questionnaire(message, state, user, language, answers)
             return
        if current_q_num == 1:
            await message.answer(question_text, reply_markup=get_skip_questionnaire_keyboard(language))
        else:
            numbered_question = f"<b>Вопрос {current_q_num}/7:</b>\n\n{question_text}"
            await message.answer(numbered_question)      
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса {current_q_num} пользователю {user.telegram_id}: {e}")
        await message.answer(get_message('error_generic', language))

async def finish_questionnaire(message, state: FSMContext, user, language: str, answers: dict):
    """Завершает анкетирование и отправляет данные на анализ ИИ."""
    try:
        await state_manager.clear_state(state)
        processing_msg = await message.answer(get_message('processing', language))
        prompt = get_prompt(
            key='onboarding_questionnaire_analysis',
            language=language,
            q1_answer=answers.get(1, ""),
            q2_answer=answers.get(2, ""),
            q3_answer=answers.get(3, ""),
            q4_answer=answers.get(4, ""),
            q5_answer=answers.get(5, ""),
            q6_answer=answers.get(6, ""),
            q7_answer=answers.get(7, "")
        )
        api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language)
        if api_result.get('success'):
            parsed_result = api_result.get('result', {})
            profile_updates = parsed_result.get('user_profile_updates', {})
            @sync_to_async
            def save_profile_updates():
                try:
                    new_first_name = profile_updates.get('first_name')
                    if new_first_name and new_first_name != user.first_name and isinstance(new_first_name, str):
                        user.first_name = new_first_name.strip()
                    new_traits = profile_updates.get('personality_traits', {})
                    if new_traits and isinstance(new_traits, dict):
                        user.personality_traits = user.personality_traits or {}
                        user.personality_traits.update({k: v for k, v in new_traits.items() if isinstance(v, (int, float)) and 0 <= v <= 1})
                    list_fields = ['core_values', 'hobbies', 'triggers', 'life_facts', 'strengths', 'areas_for_growth']
                    for field_name in list_fields:
                        new_items = profile_updates.get(field_name, [])
                        if new_items and isinstance(new_items, list):
                            current_list = getattr(user, field_name, []) or []
                            if not isinstance(current_list, list):
                                current_list = []
                            current_set = set(item for item in current_list if isinstance(item, str))
                            new_set = set(item for item in new_items if isinstance(item, str))
                            updated_set = current_set.union(new_set)
                            setattr(user, field_name, list(updated_set))
                    update_fields_list = ['personality_traits', 'core_values', 'hobbies', 'triggers', 'life_facts', 'strengths', 'areas_for_growth']
                    if new_first_name and new_first_name != user.first_name and isinstance(new_first_name, str):
                        update_fields_list.append('first_name')
                    user.save(update_fields=update_fields_list)
                    logger.debug(f"Профиль пользователя {user.telegram_id} успешно обновлен на основе анкеты.")
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при сохранении обновлений профиля для пользователя {user.telegram_id}: {e}")
                    return False
            save_success = await save_profile_updates()
            if save_success:
                thank_you_msg = get_message('onboarding_thank_you_for_profile', language)
                await processing_msg.edit_text(thank_you_msg)
            else:
                error_msg = f"{get_message('error_processing', language)} Пока что ваши ответы сохранены локально."
                await processing_msg.edit_text(error_msg)
        else:
            error_detail = api_result.get('message', 'Неизвестная ошибка ИИ')
            logger.error(f"Ошибка анализа анкеты ИИ для пользователя {user.telegram_id}: {error_detail}")
            error_msg = f"{get_message('error_processing', language)} (Ошибка ИИ: {error_detail}). Пока что ваши ответы сохранены локально."
            await processing_msg.edit_text(error_msg)
    except Exception as e:
        logger.error(f"Критическая ошибка при завершении анкетирования для пользователя {user.telegram_id}: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(get_message('error_generic', language))
        except:
            try:
                await message.answer(get_message('error_generic', language))
            except:
                pass
    finally:
        try:
            welcome_back_msg = get_message('welcome_back', language, username=user.first_name or "Пользователь")
            await message.answer(welcome_back_msg, reply_markup=get_main_menu_keyboard(language))
        except Exception as menu_error:
            logger.error(f"Ошибка при переходе в главное меню после анкеты для пользователя {user.telegram_id}: {menu_error}")
