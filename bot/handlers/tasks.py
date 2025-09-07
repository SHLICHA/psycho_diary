"""
Handlers для работы с терапевтическими заданиями
"""
# TODO Реализовать просмотр истории заданий

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.services.task_service import task_service
from diary.models import TherapyTask, TaskCompletion, TaskAnalysis
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
                    # === НОВЫЙ ПАРАМЕТР ===
                    show_history_button=has_completed_or_skipped 
                )
            )
        else:
            # === ИЗМЕНЕНИЕ: Проверяем наличие завершенных заданий и передаем флаг ===
            completed_tasks_check = await task_service.get_user_completed_tasks(user, limit=1)
            skipped_tasks_check = await task_service.get_user_skipped_tasks(user, limit=1)
            has_completed_or_skipped = bool(completed_tasks_check or skipped_tasks_check)
            
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_task_main_menu_keyboard(
                    language=language,
                    show_history_button=has_completed_or_skipped # Показываем кнопку истории, если есть завершенные
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
            await safe_answer_callback(callback, error_msg, show_alert=True) # Показываем как уведомление
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
            # Не используем await callback.answer() после safe_answer_callback
            return # Выходим из функции
            
        # await callback.answer() # Убираем общий callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при начале выполнения задания {task_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True) # Показываем ошибку как уведомление
        # Не используем await callback.answer() после safe_answer_callback

@router.message(TaskStates.waiting_for_task_completion)
async def process_task_completion(message: Message, state: FSMContext, user, language: str):
    """Обработка выполнения задания"""
    try:
        completion_text = message.text
        if len(completion_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое выполнение задания")
            return
        if len(completion_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст выполнения слишком длинный: {len(completion_text)} символов")
            return
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

@router.message(TaskStates.describing_feelings)
async def process_feelings_description(message: Message, state: FSMContext, user, language: str):
    """Обработка описания ощущений при выполнении задания"""
    try:
        feelings_text = message.text
        if len(feelings_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое описание ощущений")
            return
        if len(feelings_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст ощущений слишком длинный: {len(feelings_text)} символов")
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
                if 'status_message' in locals():
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

'''@router.callback_query(F.data.startswith("view_task_history:"))
async def view_task_history(callback: CallbackQuery, user, language: str):
    """Просмотр истории заданий"""
    try:
        completed_tasks = await task_service.get_user_completed_tasks(user, limit=10)
        if completed_tasks:
            history_msg = "🎯 <b>История выполненных заданий</b>\n\n"
            for i, task in enumerate(completed_tasks, 1):
                task_type = task.get_type_display()
                history_msg += f"<b>{i}. {task.title}</b> ({task_type})\n"
                history_msg += f"🕒 {task.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
                history_msg += f"⭐ Приоритет: {task.priority}\n\n"
            buttons = []
            for i, task in enumerate(completed_tasks, 1):
                buttons.append([
                    InlineKeyboardButton(
                        text=f"👁 Просмотреть задание {i}",
                        callback_data=f"view_completed_task:{task.id}"
                    )
                ])
            buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_back', language),
                    callback_data="tasks"
                )
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(
                history_msg,
                reply_markup=keyboard
            )
        else:
            no_tasks_msg = get_message('task_no_completed', language)
            await callback.message.edit_text(
                no_tasks_msg,
                reply_markup=get_back_keyboard(language)
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при просмотре истории заданий: {e}")
        await callback.answer(get_message('error_generic', language))'''

'''@router.callback_query(F.data.startswith("view_completed_task:"))
async def view_completed_task(callback: CallbackQuery, user, language: str):
    """Просмотр выполненного задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            completion_text = "Выполнение не доступен"
            feelings_text = "Ощущения не доступны"
            try:
                if hasattr(task, 'completion'):
                    try:
                        completion = await TaskCompletion.objects.aget(task=task)
                        completion_text = completion.completion_text or "Выполнение записано"
                        feelings_text = completion.feelings_text or "Ощущения не описаны"
                    except TaskCompletion.DoesNotExist:
                        logger.info("Выполнение для задания не найдено")
            except Exception as completion_error:
                logger.error(f"Ошибка при получении выполнения: {completion_error}")
            task_msg = f"🎯 <b>Выполненное задание: {task.title}</b>\n\n"
            task_msg += f"📝 <b>Описание:</b>\n{task.description}\n\n"
            task_msg += f"🕒 <b>Выполнено:</b> {task.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
            task_msg += f"⭐ <b>Приоритет:</b> {task.priority}\n\n"
            task_msg += f"✅ <b>Выполнение:</b>\n{completion_text}\n\n"
            task_msg += f"💭 <b>Ощущения:</b>\n{feelings_text}"
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_back_keyboard(language)
            )
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при просмотре выполненного задания: {e}")
        await callback.answer(get_message('error_generic', language))'''

@router.callback_query(F.data == "task_history_main")
async def show_task_history_main(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает историю заданий с пагинацией (аналогично активным заданиям)."""
    try:
        logger.info(f"Пользователь {user.telegram_id} открыл историю заданий.")

        # 1. Получаем выполненные и пропущенные задания
        completed_tasks = await task_service.get_user_completed_tasks(user, limit=100)
        skipped_tasks = await task_service.get_user_skipped_tasks(user, limit=100)
        
        logger.debug(f"Найдено {len(completed_tasks)} выполненных и {len(skipped_tasks)} пропущенных заданий.")

        # 2. Объединяем и сортируем по дате завершения/пропуска (от новых к старым)
        all_history_tasks = completed_tasks + skipped_tasks
        # Сортируем по дате завершения/обновления/назначения
        def get_sort_key(task):
            return task.completed_at
        all_history_tasks.sort(key=lambda t: (t.completed_at or t.assigned_at), reverse=True) 

        if not all_history_tasks:
            no_history_msg = get_message('task_history_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_history_msg,
                reply_markup=get_task_history_main_keyboard(language) # Или другая клавиатура "Назад"
            )
        else:
            # 3. Сохраняем список ID в FSM для последующей пагинации
            task_ids_for_pagination = [task.id for task in all_history_tasks]
            await state_manager.update_state_data(
                state, # Передаем объект состояния FSMContext
                task_history_ids=task_ids_for_pagination
            )
            
            # 4. Показываем ПЕРВОЕ задание из списка С КЛАВИАТУРОЙ ПАГИНАЦИИ
            first_task = all_history_tasks[0]
            first_task_detail_msg = await _format_task_history_detail(first_task, language, state)
            
            await safe_edit_message_text(
                message=callback.message,
                text=first_task_detail_msg,
                reply_markup=get_task_history_list_keyboard( # Используем клавиатуру списка
                    task_ids=task_ids_for_pagination, # Передаем список ID
                    current_index=0, # Индекс первого задания
                    current_task_status=first_task.status, # Передаем статус первого задания
                    language=language
                )
            )
            
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при показе истории заданий для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

'''@router.callback_query(F.data.startswith("task_history_list:"))
async def show_task_history_list_at_index(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Показывает список истории заданий, начиная с определенного индекса (для кнопки "Назад" из деталей)."""
    try:
        parts = callback.data.split(":")
        target_index = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        state_data = await state_manager.get_state_data(state)
        task_ids_for_pagination = state_data.get('task_history_ids', [])
        if not task_ids_for_pagination:
            logger.warning("Список ID заданий истории не найден в FSM.")
            await show_task_history_main(callback, state, user, language)
            return
        if not (0 <= target_index < len(task_ids_for_pagination)):
            logger.warning(f"Неверный индекс {target_index} для списка заданий длиной {len(task_ids_for_pagination)}. Используется 0.")
            target_index = 0
        task_id = task_ids_for_pagination[target_index]
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
        except TherapyTask.DoesNotExist:
            logger.error(f"Задание {task_id} не найдено для пользователя {user.telegram_id}.")
            await safe_answer_callback(callback, get_message('task_not_found', language), show_alert=True)
            await show_task_history_main(callback, state, user, language)
            return
        detail_msg = await _format_task_history_detail(task, language, state)
        await safe_edit_message_text(
            message=callback.message,
            text=detail_msg,
            reply_markup=get_task_history_detail_keyboard(
                task_id=task.id,
                task_status=task.status,
                current_index=target_index,
                language=language
            )
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки callback_data для списка истории: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Неожиданная ошибка в show_task_history_list_at_index для пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))'''

@router.callback_query(F.data.startswith("task_history_paginate:"))
async def paginate_task_history(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пагинация по истории заданий."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2 or not parts[1].isdigit():
             raise ValueError("Некорректный формат callback_data для пагинации истории")
        target_index = int(parts[1])
        logger.debug(f"Пагинация истории заданий: переход к индексу {target_index}")

        # Получаем список ID из FSM
        state_data = await state_manager.get_state_data(state)
        task_ids_for_pagination = state_data.get('task_history_ids', [])
        
        if not task_ids_for_pagination:
            logger.warning("Список ID заданий истории не найден в FSM при пагинации.")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return

        # Проверяем границы индекса
        if not (0 <= target_index < len(task_ids_for_pagination)):
            logger.warning(f"Индекс пагинации {target_index} вне диапазона [0, {len(task_ids_for_pagination)-1}]")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return

        # Находим задание по индексу
        task_id = task_ids_for_pagination[target_index]
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
        except TherapyTask.DoesNotExist:
            logger.error(f"Задание {task_id} не найдено при пагинации для пользователя {user.telegram_id}.")
            await safe_answer_callback(callback, get_message('task_not_found', language), show_alert=True)
            return

        # Отформатировать и отобразить
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
        # return_index = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        logger.info(f"Попытка восстановления пропущенного задания {task_id} пользователем {user.telegram_id}")

        success = await task_service.restore_task(task_id, user)
        
        if success:
            success_msg = get_message('task_restored', language)
            await safe_answer_callback(callback, success_msg, show_alert=True)
            logger.info(f"Задание {task_id} успешно восстановлено для пользователя {user.telegram_id}")
            
            # Обновляем список ID в FSM, убирая восстановленное задание
            state_data = await state_manager.get_state_data(state)
            task_history_ids = state_data.get('task_history_ids', [])
            if task_id in task_history_ids:
                task_history_ids.remove(task_id)
                await state_manager.update_state_data(state, task_history_ids=task_history_ids)
                logger.debug(f"ID задания {task_id} удален из списка истории в FSM.")
            else:
                logger.warning(f"ID задания {task_id} не найден в списке истории FSM при восстановлении.")
            
            # Возвращаем пользователя к списку активных заданий
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

@router.callback_query(F.data.startswith("task_history_paginate:"))
async def paginate_task_history(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пагинация по истории заданий."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2 or not parts[1].isdigit():
             raise ValueError("Некорректный формат callback_data для пагинации истории")
        target_index = int(parts[1])
        logger.debug(f"Пагинация истории заданий: переход к индексу {target_index}")
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
            reply_markup=get_task_history_detail_keyboard(
                task_id=task.id,
                task_status=task.status,
                current_index=target_index,
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
        analysis_text = "Анализ не найден"
        
        try:
            try:
                completion = await TaskCompletion.objects.aget(task=task)
                
                if completion:
                    completion_text = completion.completion_text or "Текст выполнения отсутствует"
                    feelings_text = completion.feelings_text or "Описание ощущений отсутствует"
                    try:
                        try:
                            analysis = await TaskAnalysis.objects.aget(completion=completion)
                            if analysis:
                                analysis_text = analysis.bot_response or "Анализ от бота отсутствует"
                        except TaskAnalysis.DoesNotExist:
                            logger.debug(f"Анализ для выполнения задания {task.id} не найден.")
                            analysis_text = "Анализ от бота отсутствует"
                        except Exception as analysis_access_error:
                            logger.error(f"Ошибка при доступе к анализа выполнения для задания {task.id}: {analysis_access_error}")
                            analysis_text = "Ошибка при загрузке анализа"
                    except Exception as analysis_general_error:
                        logger.error(f"Общая ошибка при обработке анализа для задания {task.id}: {analysis_general_error}")
                        analysis_text = "Ошибка при загрузке анализа"
            except TaskCompletion.DoesNotExist:
                logger.debug(f"Выполнение для задания {task.id} не найдено.")
            except Exception as completion_access_error:
                logger.error(f"Ошибка при доступе к выполнению задания {task.id}: {completion_access_error}")
                completion_text = "Ошибка при загрузке выполнения"
                feelings_text = "Ошибка при загрузке ощущений"
        except Exception as general_completion_error:
            logger.error(f"Общая ошибка при получении выполнения задания {task.id}: {general_completion_error}")
            completion_text = "Ошибка при загрузке выполнения"
            feelings_text = "Ошибка при загрузке ощущений"
        detail_msg += f"<b>Выполнение:</b>\n{completion_text}\n\n"
        detail_msg += f"<b>Ощущения:</b>\n{feelings_text}\n\n"
        detail_msg += f"<b>Анализ выполнения:</b>\n{analysis_text}\n"
        return detail_msg
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей задания {task.id}: {e}")
        return get_message('error_loading_task_details', language)
