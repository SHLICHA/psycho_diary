"""
Handlers для работы с терапевтическими заданиями
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType,InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from messages import get_message, get_button_text
from bot.states.task_states import TaskStates
from bot.keyboards import (
    get_confirm_delete_task_keyboard,
    get_task_pagination_keyboard,
    get_task_detail_keyboard,
    get_cancel_keyboard,
    get_back_keyboard,
    get_task_history_main_keyboard,
    get_task_history_list_keyboard,
    get_task_history_detail_keyboard,
    get_task_main_menu_keyboard
    )
from bot.utils.audio_utils import process_voice_message
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.services.task_service import task_service
from bot.services.yandex_object_storage import yandex_storage_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from diary.models import TherapyTask, TaskCompletion, TaskCompletionAnalysis
from core.constants import TEXT_MESSAGE_MAX_LENGTH

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "tasks")
@router.callback_query(F.data == "back_to_tasks")
async def show_tasks(callback: CallbackQuery, user, language: str):
    """Показ текущих заданий с пагинацией"""
    try:
        active_tasks = await task_service.get_user_active_tasks(user)
        if active_tasks:
            first_task = active_tasks[0]
            task_msg = get_message(
                'task_assigned',
                language,
                title=first_task.title,
                description=first_task.description
            )
            completed_tasks_check = await task_service.get_user_completed_tasks(user, limit=1)
            skipped_tasks_check = await task_service.get_user_skipped_tasks(user, limit=1)
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
            completed_tasks_check = await task_service.get_user_completed_tasks(user, limit=1)
            skipped_tasks_check = await task_service.get_user_skipped_tasks(user, limit=1)
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
        active_tasks = await task_service.get_user_active_tasks(user)
        if not active_tasks:
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_back_keyboard(language)
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
                reply_markup=get_cancel_keyboard(language, 'tasks')
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
async def process_task_completion(message: Message, state: FSMContext, user, language: str):
    """Обработка выполнения задания (текст или голос)"""
    try:
        # --- НАЧАЛО НОВОГО БЛОКА ОБРАБОТКИ ТЕКСТА/ГОЛОСА ---
        completion_text = ""

        if message.content_type == ContentType.VOICE:
            # Обработка голосового сообщения с помощью вспомогательной функции
            # Создаем временное сообщение статуса "Обработка" для process_voice_message
            processing_voice_msg = await message.answer(get_message('processing', language))
            
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Task Completion",
                language=language,
                status_msg=processing_voice_msg # Передаем сообщение статуса для редактирования
            )

            # Удаляем временное сообщение статуса обработки голоса
            try:
                await processing_voice_msg.delete()
            except Exception as delete_error:
                logger.warning(f"[Task Completion] Не удалось удалить сообщение статуса обработки голоса: {delete_error}")

            if not success:
                await message.answer(f"{get_message('error_processing', language)}: {error_message}")
                return # Не очищаем состояние, чтобы пользователь мог повторить
            
            completion_text = recognized_text

        elif message.content_type == ContentType.TEXT:
            # Обработка текстового сообщения (старая логика)
            completion_text = message.text
        else:
            # На случай, если фильтр как-то пропустит неподдерживаемый тип
            logger.warning(f"[Task Completion] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        # --- КОНЕЦ НОВОГО БЛОКА ---

        # --- Остальная логика обработчика (валидация, сохранение состояния) ---
        if len(completion_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое выполнение задания")
            return
        # Убираем ограничение TEXT_MESSAGE_MAX_LENGTH, так как оно не определено в коде
        # if len(completion_text) > TEXT_MESSAGE_MAX_LENGTH:
        #     error_msg = get_message('text_too_long', language)
        #     await message.answer(error_msg)
        #     logger.warning(f"Текст выполнения слишком длинный: {len(completion_text)} символов")
        #     return
        await state_manager.update_state_data(state, completion_text=completion_text)
        await state_manager.set_state(state, TaskStates.describing_feelings)
        feelings_msg = get_message('ask_feelings_description', language)
        await message.answer(
            feelings_msg,
            reply_markup=get_cancel_keyboard(language)
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке выполнения задания: {e}")
        await message.answer(get_message('error_processing', language))

@router.message(TaskStates.describing_feelings, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def process_feelings_description(message: Message, state: FSMContext, user, language: str):
    """Обработка описания ощущений при выполнении задания (текст или голос)"""
    status_message = None
    try:
        # --- НАЧАЛО НОВОГО БЛОКА ОБРАБОТКИ ТЕКСТА/ГОЛОСА ---
        feelings_text = ""

        if message.content_type == ContentType.VOICE:
            # Обработка голосового сообщения с помощью вспомогательной функции
            # Создаем временное сообщение статуса "Обработка" для process_voice_message
            processing_voice_msg = await message.answer(get_message('processing', language))
            
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Feelings Description",
                language=language,
                status_msg=processing_voice_msg # Передаем сообщение статуса для редактирования
            )

            # Удаляем временное сообщение статуса обработки голоса
            try:
                await processing_voice_msg.delete()
            except Exception as delete_error:
                logger.warning(f"[Feelings Description] Не удалось удалить сообщение статуса обработки голоса: {delete_error}")

            if not success:
                await message.answer(f"{get_message('error_processing', language)}: {error_message}")
                return # Не очищаем состояние, чтобы пользователь мог повторить
            
            feelings_text = recognized_text

        elif message.content_type == ContentType.TEXT:
            # Обработка текстового сообщения (старая логика)
            feelings_text = message.text
        else:
            # На случай, если фильтр как-то пропустит неподдерживаемый тип
            logger.warning(f"[Feelings Description] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        # --- КОНЕЦ НОВОГО БЛОКА ---

        # --- Остальная логика обработчика (валидация, обработка задания) ---
        if len(feelings_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое описание ощущений")
            return
        # Убираем ограничение TEXT_MESSAGE_MAX_LENGTH, так как оно не определено в коде
        # if len(feelings_text) > TEXT_MESSAGE_MAX_LENGTH:
        #     error_msg = get_message('text_too_long', language)
        #     await message.answer(error_msg)
        #     logger.warning(f"Текст ощущений слишком длинный: {len(feelings_text)} символов")
        #     return
        processing_msg = get_message('task_processing', language)
        status_message = await message.answer(processing_msg)
        state_data = await state_manager.get_state_data(state)
        task_id = state_data.get('completing_task_id')
        completion_text = state_data.get('completion_text', '')
        if not task_id:
            logger.error("Не найден ID задания в состоянии")
            await status_message.edit_text(get_message('error_generic', language))
            return
        try:
            completion_result = await task_service.complete_task(
                task_id=task_id,
                user=user,
                completion_text=completion_text,
                feelings_text=feelings_text,
                status_message=status_message 
            )
            await state_manager.clear_state(state)
            if not completion_result:
                logger.error(f"Сервис вернул None при выполнении задания {task_id}")
                await status_message.edit_text(get_message('error_processing', language))
                return
        except Exception as service_error:
            logger.error(f"Ошибка при выполнении задания через сервис: {service_error}")
            await status_message.edit_text(get_message('error_processing', language))
            return
    except Exception as e:
        logger.error(f"Ошибка при обработке описания ощущений: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_processing', language))
        except:
            try:
                if status_message: # Проверяем, существует ли status_message
                    await status_message.edit_text(get_message('error_processing', language))
            except:
                pass

@router.callback_query(F.data.startswith("skip_task:"))
async def skip_task(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пропуск задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        success = await task_service.skip_task(task_id, user)
        if success:
            task_skipped_msg = get_message('task_skipped', language)
            await safe_answer_callback(callback, task_skipped_msg, show_alert=True)
            logger.info(f"Задание {task_id} пропущено пользователем {user.telegram_id}. Обновление списка активных заданий.")
            active_tasks = await task_service.get_user_active_tasks(user)
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
async def delete_task(callback: CallbackQuery, user, language: str):
    """Удаление задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Удаление задания ID: {task_id}")
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
        success = await task_service.delete_task(task_id, user)
        if success:
            task_deleted_msg = get_message('task_deleted', language)
            await callback.message.edit_text(
                task_deleted_msg,
                reply_markup=get_back_keyboard(language)
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
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data == "task_history_main")
async def show_task_history_main(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает историю заданий с пагинацией (аналогично активным заданиям)."""
    try:
        completed_tasks = await task_service.get_user_completed_tasks(user, limit=100)
        skipped_tasks = await task_service.get_user_skipped_tasks(user, limit=100)
        all_history_tasks = completed_tasks + skipped_tasks
        def get_sort_key(task):
            return task.completed_at
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
async def restore_skipped_task(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Восстановление пропущенного задания."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2:
             raise ValueError("Некорректный формат callback_data для восстановления задания")
        task_id = int(parts[1])
        success = await task_service.restore_task(task_id, user)
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
                reply_markup=get_back_keyboard(language)
            )
            return
        try:
            analysis = await TaskCompletionAnalysis.objects.aget(completion=completion, is_obsolete=False)
        except TaskCompletionAnalysis.DoesNotExist:
            await safe_answer_callback(callback, get_message('task_analysis_not_found', language), show_alert=True)
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('task_analysis_not_found', language),
                reply_markup=get_back_keyboard(language)
            )
            return
        except TaskCompletionAnalysis.MultipleObjectsReturned:
            analysis = await TaskCompletionAnalysis.objects.filter(completion=completion, is_obsolete=False).afirst()
            if not analysis:
                 await safe_answer_callback(callback, get_message('task_analysis_error', language), show_alert=True)
                 return
        if analysis.detailed_analysis:
            header = get_message('detailed_task_analysis_header', language).format(task_title=task.title)
            analysis_text = f"<b>{header}</b>\n\n{analysis.detailed_analysis}"
        else:
            analysis_text = get_message('task_analysis_no_details', language).format(task_title=task.title)

        back_button = [[InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="task_history_main"
        )]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=back_button)
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
        detail_msg = f"📝 <b>Задание: {task.title}</b>\n"
        detail_msg += f"🕒 <b>Назначено:</b> {task.assigned_at.strftime('%d.%m.%Y %H:%M')}\n"
        if task.completed_at:
             detail_msg += f"✅ <b>Завершено:</b> {task.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
        detail_msg += f"📊 <b>Статус:</b> {task.get_status_display()}\n"
        detail_msg += f"⭐ <b>Приоритет:</b> {task.priority}\n\n"      
        detail_msg += f"<b>Описание:</b>\n{task.description}\n\n"
        completion_text = "Выполнение не найдено"
        feelings_text = "Ощущения не найдены"
        try:
            completion = await TaskCompletion.objects.aget(task=task)
            if completion:
                completion_text = completion.completion_text or "Текст выполнения отсутствует"
                feelings_text = completion.feelings_text or "Описание ощущений отсутствует"
        except TaskCompletion.DoesNotExist:
            logger.debug(f"Выполнение для задания {task.id} не найдено.")
        except Exception as completion_access_error:
            logger.error(f"Ошибка при доступе к выполнению задания {task.id}: {completion_access_error}")
            completion_text = "Ошибка при загрузке выполнения"
            feelings_text = "Ошибка при загрузке ощущений" 
        detail_msg += f"<b>Выполнение:</b>\n{completion_text}\n\n"
        detail_msg += f"<b>Ощущения:</b>\n{feelings_text}\n"
        return detail_msg
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей задания {task.id}: {e}")
        return get_message('error_loading_task_details', language)
