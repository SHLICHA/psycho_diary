"""
Handlers для работы с терапевтическими заданиями
"""

import logging
import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext

from messages import get_message, get_button_text
from bot.states.task_states import TaskStates
from bot.keyboards import (
    get_back_keyboard,
    get_confirm_delete_task_keyboard,
    get_confirm_delete_task_keyboard,
    get_task_pagination_keyboard,
    get_task_detail_keyboard,
    get_single_button_keyboard,
    get_task_history_main_keyboard,
    get_task_history_list_keyboard,
    get_task_main_menu_keyboard
    )
from bot.decorators.analytics_decorator import log_user_activity
from bot.utils.audio_utils import process_voice_message
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from diary.models import TherapyTask, TaskCompletion, TaskCompletionAnalysis
from diary.services.task_management_service import (
    assign_task,
    get_user_active_tasks,
    get_user_completed_tasks,
    complete_task,
    skip_task,
    delete_task,
    get_user_skipped_tasks,
    restore_task,
    analyze_task_completion_effect
)
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "tasks")
@router.callback_query(F.data == "back_to_tasks")
@log_user_activity('task')
async def show_tasks(callback: CallbackQuery, user, language: str):
    """Показ текущих заданий с пагинацией"""
    try:
        active_tasks = await get_user_active_tasks(user)
        if active_tasks:
            first_task = active_tasks[0]
            task_msg = get_message(
                'task_assigned',
                language,
                title=first_task.title,
                description=first_task.description
            )
            completed_tasks_check = await get_user_completed_tasks(user, limit=1)
            skipped_tasks_check = await get_user_skipped_tasks(user, limit=1)
            has_completed_or_skipped = bool(completed_tasks_check or skipped_tasks_check)
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_task_pagination_keyboard(
                    task_id=first_task.id,
                    current_index=0,
                    total_tasks=len(active_tasks),
                    language=language,
                    show_history_button=has_completed_or_skipped
                )
            )
        else:
            completed_tasks_check = await get_user_completed_tasks(user, limit=1)
            skipped_tasks_check = await get_user_skipped_tasks(user, limit=1)
            has_completed_or_skipped = bool(completed_tasks_check or skipped_tasks_check)
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_task_main_menu_keyboard(
                    language=language,
                    show_history_button=has_completed_or_skipped
                )
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе заданий: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("tasks_paginate:"))
async def paginate_tasks(callback: CallbackQuery, user, language: str):
    """Пагинация между заданиями"""
    try:
        parts = callback.data.split(":")
        direction = parts[1]
        current_index = int(parts[2])
        active_tasks = await get_user_active_tasks(user)
        if not active_tasks:
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_single_button_keyboard(language)
            )
            await callback.answer()
            return
        if direction == "next":
            new_index = (current_index + 1) % len(active_tasks)
        elif direction == "prev":
            new_index = (current_index - 1) % len(active_tasks)
        else:
            new_index = current_index
        task = active_tasks[new_index]
        task_msg = get_message(
            'task_assigned',
            language,
            title=task.title,
            description=task.description
        )
        await callback.message.edit_text(
            task_msg,
            reply_markup=get_task_pagination_keyboard(
                task_id=task.id,
                current_index=new_index,
                total_tasks=len(active_tasks),
                language=language
            )
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пагинации заданий: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_task:"))
async def view_specific_task(callback: CallbackQuery, user, language: str):
    """Просмотр конкретного задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            task_msg = get_message(
                'task_assigned',
                language,
                title=task.title,
                description=task.description
            )
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_task_detail_keyboard(task_id, language)
            )
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при просмотре конкретного задания: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("complete_task:"))
@log_user_activity('task_completed')
async def start_task_completion(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начало выполнения задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            await state_manager.set_state(state, TaskStates.waiting_for_task_completion)
            await state_manager.update_state_data(
                state,
                completing_task_id=task_id,
                task_description=task.description
            )
            completion_msg = get_message('ask_task_completion_with_context', language).format(
                title=task.title,
                description=task.description
            )
            await callback.message.edit_text(
                completion_msg,
                reply_markup=get_single_button_keyboard(language, 'tasks', 'btn_back')
            )
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
            return
    except Exception as e:
        logger.error(f"Ошибка при начале выполнения задания {task_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.message(TaskStates.waiting_for_task_completion, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('task_completed', metadata_extra={'context': 'Обработка выполнения'})
async def process_task_completion(message: Message, state: FSMContext, user, language: str):
    """Обработка выполнения задания (текст или голос)"""
    try:
        completion_text = ""
        if message.content_type == ContentType.VOICE:
            processing_voice_msg = await message.answer(get_message('processing', language))
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Task Completion",
                language=language,
                status_msg=processing_voice_msg
            )
            try:
                await processing_voice_msg.delete()
            except Exception as delete_error:
                logger.warning(f"[Task Completion] Не удалось удалить сообщение статуса обработки голоса: {delete_error}")
            if not success:
                await message.answer(f"{get_message('error_processing', language)}: {error_message}")
                return
            completion_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            completion_text = message.text
        else:
            logger.warning(f"[Task Completion] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        if len(completion_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое выполнение задания")
            return
        await state_manager.update_state_data(state, completion_text=completion_text)
        await state_manager.set_state(state, TaskStates.describing_feelings)
        feelings_msg = get_message('ask_feelings_description', language)
        await message.answer(
            feelings_msg,
            reply_markup=get_single_button_keyboard(language, 'tasks', 'btn_back')
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке выполнения задания: {e}")
        await message.answer(get_message('error_processing', language))

@router.message(TaskStates.describing_feelings, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('task_completed', metadata_extra={'context': 'Обработка ощущений'})
async def process_feelings_description(message: Message, state: FSMContext, user, language: str):
    """Обработка описания ощущений при выполнении задания (текст или голос)"""
    status_message = None
    try:
        feelings_text = ""
        if message.content_type == ContentType.VOICE:
            processing_voice_msg = await message.answer(get_message('processing', language))
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Feelings Description",
                language=language,
                status_msg=processing_voice_msg
            )
            try:
                await processing_voice_msg.delete()
            except Exception as delete_error:
                logger.warning(f"[Feelings Description] Не удалось удалить сообщение статуса обработки голоса: {delete_error}")
            if not success:
                await message.answer(f"{get_message('error_processing', language)}: {error_message}")
                return
            feelings_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            feelings_text = message.text
        else:
            logger.warning(f"[Feelings Description] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        if len(feelings_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое описание ощущений")
            return
        processing_msg = get_message('task_processing', language)
        status_message = await message.answer(processing_msg)
        state_data = await state_manager.get_state_data(state)
        task_id = state_data.get('completing_task_id')
        completion_text = state_data.get('completion_text', '')
        if not task_id:
            logger.error("Не найден ID задания в состоянии")
            await status_message.edit_text(get_message('error_generic', language))
            return
        completion_result = await complete_task(
            task_id=task_id,
            user=user,
            completion_text=completion_text,
            feelings_text=feelings_text,
        )
        await state_manager.clear_state(state)

        if not completion_result or not completion_result.get('success'):
            logger.error(f"Сервис вернул ошибку при выполнении задания {task_id}: {completion_result.get('error')}")
            await status_message.edit_text(get_message('error_processing', language))
            return
        task_completion_obj = completion_result.get('task_completion')
        if task_completion_obj:
            bot_instance = state_manager.get_bot()
            if bot_instance:
                 asyncio.create_task(
                     _run_analysis_and_notify_user(
                         task_completion=task_completion_obj,
                         user=user,
                         status_message=status_message,
                         bot_instance=bot_instance
                     )
                 )
        else:
            logger.warning(f"Объект TaskCompletion не возвращён после выполнения задания {task_id}")
            await status_message.edit_text(get_message('error_processing', language))
    except Exception as e:
        logger.error(f"Ошибка при обработке описания ощущений: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_processing', language))
        except:
            try:
                if status_message:
                    await status_message.edit_text(get_message('error_processing', language))
            except:
                pass

async def _run_analysis_and_notify_user(task_completion: TaskCompletion, user: User, status_message: Message, bot_instance):
    """
    Асинхронная задача для запуска анализа эффекта и уведомления пользователя.
    """
    try:
        analysis_result = await analyze_task_completion_effect(task_completion, user)
        target_chat_id = user.telegram_id
        use_edit = False
        message_to_edit = None
        if status_message:
            target_chat_id = status_message.chat.id
            use_edit = True
            message_to_edit = status_message
        if isinstance(analysis_result, dict) and analysis_result.get('invalid'):
            validation_comment = analysis_result.get('validation_comment', get_message('task_completion_invalid_default_comment', user.language))
            language = user.language
            final_message = get_message(
                'task_completion_invalid_formatted',
                language,
                validation_comment=validation_comment
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            buttons = [
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_try_again', language),
                        callback_data=f"complete_task:{task_completion.task.id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_skip_task', language),
                        callback_data=f"skip_task:{task_completion.task.id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_back', language),
                        callback_data="back_to_tasks"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        elif analysis_result and hasattr(analysis_result, 'id'):
            language = user.language
            parsed_result = analysis_result.api_response.get('result', {})
            formatted_message = parsed_result.get('formatted_message')
            if formatted_message:
                tokens_awarded = analysis_result.tokens_awarded
                final_message = formatted_message
                if tokens_awarded > 0:
                    updated_user = await User.objects.aget(telegram_id=user.telegram_id)
                    tokens_info = get_message('task_tokens_awarded', language, tokens=tokens_awarded, balance=updated_user.token_balance)
                    if tokens_info not in final_message:
                        final_message += f"\n\n{tokens_info}"
            else:
                effect_description = analysis_result.effect_description or get_message('no_effect_description', language)
                mood_impact_score = analysis_result.mood_impact_score
                if mood_impact_score is not None:
                    try:
                        mood_impact_score_int = int(mood_impact_score)
                        if mood_impact_score_int > 0:
                            mood_impact_display = f"🔺 +{mood_impact_score_int}"
                        elif mood_impact_score_int < 0:
                            mood_impact_display = f"🔻 {mood_impact_score_int}"
                        else:
                            mood_impact_display = f"➡️ {mood_impact_score_int}"
                    except (ValueError, TypeError):
                        mood_impact_display = "N/A"
                else:
                    mood_impact_display = "N/A"
                comment_for_user = analysis_result.comment or get_message('no_comment', language)
                recommendation_for_user = analysis_result.recommendation or get_message('no_recommendation', language)
                tokens_awarded = analysis_result.tokens_awarded
                updated_user = await User.objects.aget(telegram_id=user.telegram_id)
                main_analysis_text = get_message(
                    'task_effect_analysis_result_formatted',
                    language,
                    effect_description=effect_description,
                    mood_impact=mood_impact_display,
                    comment=comment_for_user,
                    recommendation=recommendation_for_user
                )
                if tokens_awarded > 0:
                    tokens_info = get_message('task_tokens_awarded', language, tokens=tokens_awarded, balance=updated_user.token_balance)
                    final_message = f"{main_analysis_text}\n\n{tokens_info}"
                else:
                    final_message = main_analysis_text
            reply_markup = get_back_keyboard(language)
        else:
            language = user.language
            final_message = get_message('task_analysis_error_formatted', language)
            reply_markup = get_back_keyboard(language)
        if use_edit and message_to_edit:
            try:
                await safe_edit_message_text(
                    message=message_to_edit,
                    text=final_message,
                    reply_markup=reply_markup
                )
                logger.debug(f"Сообщение отредактировано для задания {task_completion.task.id}")
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение: {edit_error}. Отправляем новое.")
                await bot_instance.send_message(
                    chat_id=target_chat_id,
                    text=final_message,
                    reply_markup=reply_markup
                )
        else:
            await bot_instance.send_message(
                chat_id=target_chat_id,
                text=final_message,
                reply_markup=reply_markup
            )
            logger.debug(f"Новое сообщение отправлено для задания {task_completion.task.id}")
    except Exception as task_error:
        logger.error(f"Критическая ошибка в _run_analysis_and_notify_user: {task_error}", exc_info=True)
        try:
            language = user.language if 'user' in locals() else 'ru'
            final_message = get_message('task_analysis_error_formatted', language)
            error_reply_markup = get_back_keyboard(language)
            if status_message and 'bot_instance' in locals():
                try:
                    await safe_edit_message_text(
                        message=status_message,
                        text=final_message,
                        reply_markup=error_reply_markup
                    )
                except:
                    try:
                        await bot_instance.send_message(
                            chat_id=status_message.chat.id,
                            text=final_message,
                            reply_markup=error_reply_markup
                        )
                    except:
                        pass
            elif 'bot_instance' in locals() and 'user' in locals():
                await bot_instance.send_message(
                    chat_id=user.telegram_id,
                    text=final_message,
                    reply_markup=error_reply_markup
                )
        except:
            pass

@router.callback_query(F.data.startswith("skip_task:"))
@log_user_activity('task_skipped')
async def skip_task_handler(callback: CallbackQuery, state: FSMContext, user, language: str): # Переименован для избежания конфликта
    """Пропуск задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        success = await skip_task(task_id, user) # Вызов сервиса
        if success:
            task_skipped_msg = get_message('task_skipped', language)
            await safe_answer_callback(callback, task_skipped_msg, show_alert=True)
            active_tasks = await get_user_active_tasks(user) # Вызов сервиса
            if not active_tasks:
                no_task_msg = get_message('task_no_active', language)
                await safe_edit_message_text(
                    message=callback.message,
                    text=no_task_msg,
                    reply_markup=get_task_main_menu_keyboard(language)
                )
            else:
                first_task = active_tasks[0]
                task_msg = get_message(
                    'task_assigned',
                    language,
                    title=first_task.title,
                    description=first_task.description
                )
                await safe_edit_message_text(
                    message=callback.message,
                    text=task_msg,
                    reply_markup=get_task_pagination_keyboard(
                        task_id=first_task.id,
                        current_index=0,
                        total_tasks=len(active_tasks),
                        language=language
                    )
                )
        else:
            error_msg = get_message('task_not_found', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(f"Не удалось пропустить задание {task_id} для пользователя {user.telegram_id}")
    except Exception as e:
        logger.error(f"Ошибка при пропуске задания {task_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("delete_task:"))
@log_user_activity('task_deleted')
async def delete_task_handler(callback: CallbackQuery, user, language: str):
    """Удаление задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        confirm_msg = get_message('confirm_delete_task', language)
        await callback.message.edit_text(
            confirm_msg,
            reply_markup=get_confirm_delete_task_keyboard(task_id, language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_task:"))
async def confirm_delete_task(callback: CallbackQuery, user, language: str):
    try:
        task_id = int(callback.data.split(":")[1])
        success = await delete_task(task_id, user)
        if success:
            task_deleted_msg = get_message('task_deleted', language)
            await callback.message.edit_text(
                task_deleted_msg,
                reply_markup=get_single_button_keyboard(language, 'tasks', 'btn_back')
            )
        else:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Не удалось удалить задание {task_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data == "cancel_delete_task")
async def cancel_delete_task(callback: CallbackQuery, language: str):
    """Отмена удаления задания"""
    try:
        cancel_msg = get_message('task_delete_cancelled', language)
        await callback.message.edit_text(
            cancel_msg,
            reply_markup=get_single_button_keyboard(language, 'tasks', 'btn_back')
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data == "task_history_main")
@log_user_activity('task', metadata_extra={'context': 'Просмотр истории заданий'})
async def show_task_history_main(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает историю заданий с пагинацией (аналогично активным заданиям)."""
    try:
        completed_tasks = await get_user_completed_tasks(user, limit=100)
        skipped_tasks = await get_user_skipped_tasks(user, limit=100)
        all_history_tasks = completed_tasks + skipped_tasks
        all_history_tasks.sort(key=lambda t: (t.completed_at or t.assigned_at), reverse=True)
        if not all_history_tasks:
            no_history_msg = get_message('task_history_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_history_msg,
                reply_markup=get_task_history_main_keyboard(language)
            )
        else:
            task_ids_for_pagination = [task.id for task in all_history_tasks]
            await state_manager.update_state_data(
                state,
                task_history_ids=task_ids_for_pagination
            )
            first_task = all_history_tasks[0]
            first_task_detail_msg = await _format_task_history_detail(first_task, language, state)
            await safe_edit_message_text(
                message=callback.message,
                text=first_task_detail_msg,
                reply_markup=get_task_history_list_keyboard(
                    task_ids=task_ids_for_pagination,
                    current_index=0,
                    current_task_status=first_task.status,
                    language=language
                )
            )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при показе истории заданий для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("task_history_paginate:"))
async def paginate_task_history(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пагинация по истории заданий."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2 or not parts[1].isdigit():
             raise ValueError("Некорректный формат callback_data для пагинации истории")
        target_index = int(parts[1])
        state_data = await state_manager.get_state_data(state)
        task_ids_for_pagination = state_data.get('task_history_ids', [])
        if not task_ids_for_pagination:
            logger.warning("Список ID заданий истории не найден в FSM при пагинации.")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        if not (0 <= target_index < len(task_ids_for_pagination)):
            logger.warning(f"Индекс пагинации {target_index} вне диапазона [0, {len(task_ids_for_pagination)-1}]")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        task_id = task_ids_for_pagination[target_index]
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
        except TherapyTask.DoesNotExist:
            logger.error(f"Задание {task_id} не найдено при пагинации для пользователя {user.telegram_id}.")
            await safe_answer_callback(callback, get_message('task_not_found', language), show_alert=True)
            return
        detail_msg = await _format_task_history_detail(task, language, state)
        await safe_edit_message_text(
            message=callback.message,
            text=detail_msg,
            reply_markup=get_task_history_list_keyboard(
                task_ids=task_ids_for_pagination,
                current_index=target_index,
                current_task_status=task.status,
                language=language
            )
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки callback_data для пагинации истории: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Неожиданная ошибка в paginate_task_history для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("task_history_restore:"))
@log_user_activity('task', metadata_extra={'context': 'Восстановление пропущенного задания'})
async def restore_skipped_task(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Восстановление пропущенного задания."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2:
             raise ValueError("Некорректный формат callback_data для восстановления задания")
        task_id = int(parts[1])
        success = await restore_task(task_id, user)
        if success:
            success_msg = get_message('task_restored', language)
            await safe_answer_callback(callback, success_msg, show_alert=True)
            state_data = await state_manager.get_state_data(state)
            task_history_ids = state_data.get('task_history_ids', [])
            if task_id in task_history_ids:
                task_history_ids.remove(task_id)
                await state_manager.update_state_data(state, task_history_ids=task_history_ids)
            else:
                logger.warning(f"ID задания {task_id} не найден в списке истории FSM при восстановлении.")
            await show_tasks(callback, user, language)
        else:
            error_msg = get_message('task_not_found_or_not_skipped', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(f"Не удалось восстановить задание {task_id} для пользователя {user.telegram_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки callback_data для восстановления задания: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при восстановлении задания {task_id} для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("view_detailed_task_analysis:"))
async def view_detailed_task_analysis(callback: CallbackQuery, user, language: str):
    """Просмотр детального анализа выполнения задания."""
    try:
        task_id = int(callback.data.split(":")[1])
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
        except TherapyTask.DoesNotExist:
            await safe_answer_callback(callback, get_message('task_not_found', language), show_alert=True)
            return
        if task.status != 'completed':
             await safe_answer_callback(callback, get_message('task_not_completed_for_analysis', language), show_alert=True)
             return
        try:
            completion = await TaskCompletion.objects.aget(task=task)
        except TaskCompletion.DoesNotExist:
            await safe_answer_callback(callback, get_message('task_completion_not_found', language), show_alert=True)
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('task_completion_not_found', language),
                reply_markup=get_task_history_main_keyboard(language)
            )
            return
        try:
            analysis = await TaskCompletionAnalysis.objects.aget(completion=completion, is_obsolete=False)
        except TaskCompletionAnalysis.DoesNotExist:
            await safe_answer_callback(callback, get_message('task_analysis_not_found', language), show_alert=True)
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('task_analysis_not_found', language),
                reply_markup=get_task_history_main_keyboard(language)
            )
            return
        except TaskCompletionAnalysis.MultipleObjectsReturned:
            analysis = await TaskCompletionAnalysis.objects.filter(completion=completion, is_obsolete=False).afirst()
            if not analysis:
                 await safe_answer_callback(callback, get_message('task_analysis_error', language), show_alert=True)
                 return
        tokens_awarded = analysis.tokens_awarded
        user_balance = user.token_balance
        if analysis.detailed_analysis:
            header = get_message('detailed_task_analysis_header', language).format(task_title=task.title)
            analysis_text = f"<b>{header}</b>\n\n{analysis.detailed_analysis}"
            if tokens_awarded > 0:
                tokens_msg = get_message('task_tokens_awarded', language, tokens=tokens_awarded, balance=user_balance)
                analysis_text += f"\n\n{tokens_msg}"
        else:
            analysis_text = get_message('task_analysis_no_details', language).format(task_title=task.title)
            if tokens_awarded > 0:
                tokens_msg = get_message('task_tokens_awarded', language, tokens=tokens_awarded, balance=user_balance)
                analysis_text += f"\n\n{tokens_msg}"
        reply_markup = get_task_history_main_keyboard(language)
        await safe_edit_message_text(
            message=callback.message,
            text=analysis_text,
            reply_markup=reply_markup
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError):
        logger.error(f"Ошибка парсинга task_id из callback_data: {callback.data}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре детального анализа задания {task_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

#=========================ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ=====================================

async def _format_task_history_detail(task: TherapyTask, language: str, state: FSMContext) -> str:
    """
    Форматирует текстовое сообщение с деталями задания из истории.
    """
    try:
        assigned_at = task.assigned_at.strftime('%d.%m.%Y %H:%M')
        status = task.get_status_display()
        complexity = task.complexity
        completed_at = ""
        if task.completed_at:
            completed_at = get_message('task_completed_at', language,
                                     completed_at=task.completed_at.strftime('%d.%m.%Y %H:%M'))
        completion_text = get_message('completion_not_found', language)
        feelings_text = get_message('feelings_not_found', language)
        try:
            completion = await TaskCompletion.objects.aget(task=task)
            if completion:
                completion_text = completion.completion_text or get_message('completion_text_missing', language)
                feelings_text = completion.feelings_text or get_message('feelings_text_missing', language)
        except TaskCompletion.DoesNotExist:
            logger.debug(f"Выполнение для задания {task.id} не найдено.")
        except Exception as completion_access_error:
            logger.error(f"Ошибка при доступе к выполнению задания {task.id}: {completion_access_error}")
            completion_text = get_message('completion_load_error', language)
            feelings_text = get_message('feelings_load_error', language)
        return get_message('task_history_detail', language,
                        title=task.title,
                        assigned_at=assigned_at,
                        completed_at=completed_at,
                        status=status,
                        complexity=complexity,
                        description=task.description,
                        completion_text=completion_text,
                        feelings_text=feelings_text)
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей задания {task.id}: {e}")
        return get_message('error_loading_task_details', language)
