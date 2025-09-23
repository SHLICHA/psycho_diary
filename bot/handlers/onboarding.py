# /home/shlicha/psycho_diary/bot/handlers/onboarding.py
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
from prompts.get_prompt import get_prompt

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "onboarding_start")
async def start_onboarding(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начинает процесс онбординга: показывает приветствие."""
    try:
        welcome_msg = get_message('onboarding_welcome', language)
        # Отправляем новое сообщение, так как предыдущее могло быть заблокировано
        await callback.message.answer(welcome_msg)
        # Переходим к инструкции
        await show_onboarding_instruction(callback, state, user, language)
        # Подтверждаем callback
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при запуске онбординга для пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

async def show_onboarding_instruction(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает инструкцию."""
    try:
        instruction_msg = get_message('onboarding_instruction', language)
        await state.set_state(OnboardingStates.showing_instruction)
        # Редактируем сообщение приветствия или отправляем новое
        await safe_edit_message_text(
            message=callback.message,
            text=instruction_msg,
            reply_markup=get_instruction_keyboard(language)
        )
    except Exception as e:
        logger.error(f"Ошибка при показе инструкции для пользователя {user.telegram_id}: {e}")
        # Если не удалось отредактировать, отправляем новое
        try:
            await callback.message.answer(instruction_msg, reply_markup=get_instruction_keyboard(language))
        except Exception as send_error:
            logger.error(f"Не удалось отправить сообщение с инструкцией: {send_error}")

@router.callback_query(F.data == "onboarding_next_to_agreement")
async def show_onboarding_agreement(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает соглашение."""
    try:
        # Добавим логирование для отладки
        logger.info(f"Пользователь {user.telegram_id} нажал 'Далее' в инструкции.")
        
        agreement_msg = get_message('onboarding_agreement', language)
        # Меняем состояние на показ соглашения
        await state.set_state(OnboardingStates.showing_agreement)
        logger.debug(f"Состояние пользователя {user.telegram_id} изменено на showing_agreement.")
        
        # Редактируем сообщение с инструкцией на сообщение с соглашением
        await safe_edit_message_text(
            message=callback.message,
            text=agreement_msg,
            reply_markup=get_agreement_keyboard(language)
        )
        # Подтверждаем callback
        await safe_answer_callback(callback, "")
        logger.info(f"Пользователю {user.telegram_id} показано соглашение.")
    except Exception as e:
        logger.error(f"Ошибка при показе соглашения для пользователя {user.telegram_id}: {e}", exc_info=True)
        # Всегда подтверждаем callback, даже если ошибка
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data == "onboarding_agree")
async def handle_agreement_accept(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает согласие пользователя."""
    try:
        # Сохраняем согласие в базе данных
        @sync_to_async
        def update_user_agreement():
            user.has_agreed_to_terms = True
            user.save(update_fields=['has_agreed_to_terms'])
        
        await update_user_agreement()
        
        thank_you_msg = get_message('onboarding_thank_you', language)
        # Отправляем сообщение о согласии
        await safe_edit_message_text(
            message=callback.message,
            text=thank_you_msg
        )
        await safe_answer_callback(callback, "")
        
        # --- НОВОЕ: Запуск анкетирования ---
        # Начинаем анкету: задаем первый вопрос
        await start_questionnaire(callback, state, user, language)
        # --- КОНЕЦ НОВОГО ---
        
    except Exception as e:
        logger.error(f"Ошибка при обработке согласия пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_disagree")
async def handle_agreement_decline(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обрабатывает отказ пользователя от согласия."""
    try:
        declined_msg = get_message('onboarding_disagreed', language)
        # Очищаем состояние FSM
        await state.clear()
        # Отправляем сообщение об отказе
        await safe_edit_message_text(
            message=callback.message,
            text=declined_msg
            # reply_markup=None # Убираем клавиатуру
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при обработке отказа пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "start_questionnaire_from_menu")
async def start_questionnaire_from_main_menu(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Запускает анкетирование из главного меню по кнопке "Анкета".
    """
    try:
        logger.info(f"Пользователь {user.telegram_id} запустил анкетирование из главного меню.")
        
        # Проверяем, не находится ли пользователь уже в процессе анкетирования или другого FSM
        # Это важно, чтобы не "ломать" текущий процесс.
        current_state = await state.get_state()
        if current_state:
            # Если пользователь находится в каком-то другом состоянии FSM
            logger.info(f"Пользователь {user.telegram_id} уже в состоянии {current_state}. Предлагаем завершить текущее действие.")
            # Можно просто сообщить пользователю или сбросить состояние.
            # Для простоты сбросим состояние и запустим анкету.
            # В более сложной логике можно предложить "Продолжить" или "Отменить".
            await state.clear()
            # await callback.answer("Пожалуйста, завершите текущее действие или отмените его, прежде чем начать анкету.", show_alert=True)
            # return

        # Запускаем анкетирование
        # Используем существующую логику из handle_agreement_accept или создаем новую точку входа
        # Поскольку мы хотим запустить анкету с самого начала, вызовем start_questionnaire напрямую
        
        # Отправляем сообщение, чтобы инициировать новый диалог (вместо редактирования callback.message)
        # Это похоже на логику в cmd_start после согласия
        welcome_msg = get_message('onboarding_welcome', language)
        await callback.message.answer(welcome_msg)
        
        # Теперь запускаем анкету
        await start_questionnaire(callback, state, user, language)
        
        # Подтверждаем callback
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске анкетирования из главного меню для пользователя {user.telegram_id}: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language), show_alert=True)

@router.message(OnboardingStates.collecting_profile_data)
async def process_questionnaire_answer(message: Message, state: FSMContext, user, language: str):
    """Обрабатывает ответ на вопрос анкеты."""
    try:
        answer_text = message.text.strip()
        if not answer_text:
            await message.answer(get_message('invalid_input', language))
            # Повторно отправляем текущий вопрос?
            # state_data = await state_manager.get_state_data(state)
            # current_q_num = state_data.get("current_question", 1)
            # question_key = f'onboarding_question_{current_q_num}'
            # question_text = get_message(question_key, language)
            # await message.answer(question_text)
            return
            
        # Получаем текущее состояние
        state_data = await state_manager.get_state_data(state)
        current_q_num = state_data.get("current_question", 1)
        answers = state_data.get("answers", {})
        
        # Сохраняем ответ
        answers[current_q_num] = answer_text
        await state_manager.update_state_data(state, answers=answers)
        
        # Переходим к следующему вопросу
        await state_manager.update_state_data(state, current_question=current_q_num + 1)
        await ask_next_question(message, state, user, language)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке ответа на вопрос {message.text} от пользователя {user.telegram_id}: {e}")
        await message.answer(get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_skip_questionnaire")
async def skip_questionnaire(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пропускает анкетирование."""
    try:
        # Очищаем состояние
        await state_manager.clear_state(state)
        
        # Отправляем сообщение о пропуске
        skip_msg = get_message('onboarding_skip_questionnaire', language)
        await safe_edit_message_text(
            message=callback.message,
            text=skip_msg
        )
        await safe_answer_callback(callback, "")
        
        # Переходим в главное меню
        welcome_back_msg = get_message('welcome_back', language, username=user.first_name or "Пользователь")
        await callback.message.answer(welcome_back_msg, reply_markup=get_main_menu_keyboard(language))
        
    except Exception as e:
        logger.error(f"Ошибка при пропуске анкетирования пользователем {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

# --- Отложенные хендлеры для анкетирования ---
# @router.callback_query(F.data == "skip_questionnaire")
# async def skip_questionnaire(callback: CallbackQuery, state: FSMContext, user, language: str):
#     """Пропуск анкетирования."""
#     try:
#         # Переход в главное меню или другое действие
#         from bot.handlers.start import cmd_start
#         await cmd_start(callback.message, user, language)
#         await safe_answer_callback(callback, "")
#     except Exception as e:
#         logger.error(f"Ошибка при пропуске анкетирования для пользователя {user.telegram_id}: {e}")
#         await safe_answer_callback(callback, get_message('error_generic', language))

async def start_questionnaire(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начинает процесс анкетирования."""
    try:
        # Инициализируем данные анкеты в состоянии
        questionnaire_data = {
            "current_question": 1, # Начинаем с первого вопроса
            "answers": {} # Словарь для хранения ответов
        }
        await state_manager.set_state(state, OnboardingStates.collecting_profile_data)
        await state_manager.update_state_data(state, **questionnaire_data)
        
        # Отправляем первый вопрос
        await ask_next_question(callback.message, state, user, language)
        
    except Exception as e:
        logger.error(f"Ошибка при запуске анкетирования для пользователя {user.telegram_id}: {e}")
        # Отправляем сообщение об ошибке и переходим в главное меню
        await callback.message.answer(get_message('error_generic', language))
        # Здесь можно вызвать переход в главное меню

async def ask_next_question(message, state: FSMContext, user, language: str):
    """Отправляет следующий вопрос анкеты."""
    try:
        state_data = await state_manager.get_state_data(state)
        current_q_num = state_data.get("current_question", 1)
        answers = state_data.get("answers", {})
        
        # Формируем ключ для вопроса
        question_key = f'onboarding_question_{current_q_num}'
        
        # Проверяем, есть ли еще вопросы
        if current_q_num > 7: # У нас 7 вопросов
            # Анкета завершена, сохраняем ответы
            await finish_questionnaire(message, state, user, language, answers)
            return
            
        # Получаем текст вопроса
        question_text = get_message(question_key, language)
        if not question_text or question_text.startswith('onboarding_question_'): # Если ключ не найден
             logger.warning(f"Вопрос с ключом '{question_key}' не найден для языка '{language}'. Завершаем анкету.")
             await finish_questionnaire(message, state, user, language, answers)
             return
        
        # Отправляем вопрос
        # Если это первый вопрос, отправляем новое сообщение
        # Если нет, можно редактировать предыдущее, но проще отправить новое
        if current_q_num == 1:
            # Первый вопрос - отправляем новое сообщение с кнопкой пропуска
            await message.answer(question_text, reply_markup=get_skip_questionnaire_keyboard(language))
        else:
            # Последующие вопросы - отправляем новое сообщение
            # Можно добавить нумерацию вопросов
            numbered_question = f"<b>Вопрос {current_q_num}/7:</b>\n\n{question_text}"
            await message.answer(numbered_question)
            # Для последнего вопроса можно добавить кнопку "Отправить"
            # if current_q_num == 7:
            #     await message.answer("Это последний вопрос.", reply_markup=get_submit_answers_keyboard(language))
            
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса {current_q_num} пользователю {user.telegram_id}: {e}")
        await message.answer(get_message('error_generic', language))

async def finish_questionnaire(message, state: FSMContext, user, language: str, answers: dict):
    """Завершает анкетирование и отправляет данные на анализ ИИ."""
    try:
        # 1. Очищаем состояние FSM
        await state_manager.clear_state(state)
        
        # 2. Отправляем сообщение о начале обработки
        processing_msg = await message.answer(get_message('processing', language))
        
        # 3. Формируем промпт для ИИ на основе ответов
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
        
        # 4. Отправляем запрос к DeepSeek API
        api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language)
        
        # 5. Обрабатываем результат от ИИ
        if api_result.get('success'):
            parsed_result = api_result.get('result', {})
            profile_updates = parsed_result.get('user_profile_updates', {})
            
            # 6. Сохраняем обновленные данные профиля в БД
            @sync_to_async
            def save_profile_updates():
                try:
                    # Обновляем first_name, если он был предложен ИИ и отличается
                    new_first_name = profile_updates.get('first_name')
                    if new_first_name and new_first_name != user.first_name:
                        user.first_name = new_first_name
                    
                    # Обновляем personality_traits (словарь)
                    new_traits = profile_updates.get('personality_traits', {})
                    if new_traits and isinstance(new_traits, dict):
                        user.personality_traits = user.personality_traits or {}
                        user.personality_traits.update({k: v for k, v in new_traits.items() if isinstance(v, (int, float)) and 0 <= v <= 1})
                    
                    # Обновляем списки, избегая дубликатов
                    list_fields = ['core_values', 'hobbies', 'triggers', 'life_facts', 'strengths', 'areas_for_growth']
                    for field_name in list_fields:
                        new_items = profile_updates.get(field_name, [])
                        if new_items and isinstance(new_items, list):
                            current_list = getattr(user, field_name, []) or []
                            if not isinstance(current_list, list):
                                current_list = []
                            
                            current_set = set(item for item in current_list if isinstance(item, str))
                            new_set = set(item for item in new_items if isinstance(item, str))
                            
                            # Объединяем множества и сохраняем
                            updated_set = current_set.union(new_set)
                            setattr(user, field_name, list(updated_set))
                    
                    # Сохраняем изменения
                    user.save(update_fields=['first_name', 'personality_traits', 'core_values', 'hobbies', 'triggers', 'life_facts', 'strengths', 'areas_for_growth'])
                    logger.info(f"Профиль пользователя {user.telegram_id} успешно обновлен на основе анкеты.")
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при сохранении обновлений профиля для пользователя {user.telegram_id}: {e}")
                    return False
            
            save_success = await save_profile_updates()
            
            if save_success:
                # Редактируем сообщение обработки на сообщение об успехе
                thank_you_msg = get_message('onboarding_thank_you_for_profile', language)
                await processing_msg.edit_text(thank_you_msg)
            else:
                # Редактируем сообщение обработки на сообщение об ошибке
                error_msg = f"{get_message('error_processing', language)} Пока что ваши ответы сохранены локально."
                await processing_msg.edit_text(error_msg)
        else:
            # Если ИИ вернул ошибку
            error_detail = api_result.get('message', 'Неизвестная ошибка ИИ')
            logger.error(f"Ошибка анализа анкеты ИИ для пользователя {user.telegram_id}: {error_detail}")
            error_msg = f"{get_message('error_processing', language)} (Ошибка ИИ: {error_detail}). Пока что ваши ответы сохранены локально."
            await processing_msg.edit_text(error_msg)
            
    except Exception as e:
        logger.error(f"Критическая ошибка при завершении анкетирования для пользователя {user.telegram_id}: {e}", exc_info=True)
        # Отправляем сообщение об ошибке, если не удалось отредактировать processing_msg
        try:
            await processing_msg.edit_text(get_message('error_generic', language))
        except:
            try:
                await message.answer(get_message('error_generic', language))
            except:
                pass # Игнорируем ошибки отправки сообщений в этом блоке
    finally:
        # В любом случае, после обработки переходим в главное меню
        try:
            from bot.keyboards.main_menu import get_main_menu_keyboard
            welcome_back_msg = get_message('welcome_back', language, username=user.first_name or "Пользователь")
            await message.answer(welcome_back_msg, reply_markup=get_main_menu_keyboard(language))
        except Exception as menu_error:
            logger.error(f"Ошибка при переходе в главное меню после анкеты для пользователя {user.telegram_id}: {menu_error}")
