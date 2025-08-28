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
    get_back_keyboard
    )
from bot.utils.state_manager import state_manager
from bot.services.task_service import task_service
from diary.models import TherapyTask, TaskCompletion
from core.constants import TEXT_MESSAGE_MAX_LENGTH

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "tasks")
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
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_task_pagination_keyboard(
                    task_id=first_task.id,
                    current_index=0,
                    total_tasks=len(active_tasks),
                    language=language
                )
            )
        else:
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_back_keyboard(language)
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
        direction = parts[1]  # "next" или "prev"
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

# TODO Реализовать просмотр задания. Выполненные?
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

# TODO пересмотреть. Может просто callback "task"?
@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: CallbackQuery, user, language: str):
    """Возврат к списку заданий"""
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
            if callback.message.text != task_msg:
                await callback.message.edit_text(
                    task_msg,
                    reply_markup=get_task_pagination_keyboard(
                        task_id=first_task.id,
                        current_index=0,
                        total_tasks=len(active_tasks),
                        language=language
                    )
                )
            else:
                try:
                    await callback.message.edit_reply_markup(
                        reply_markup=get_task_pagination_keyboard(
                            task_id=first_task.id,
                            current_index=0,
                            total_tasks=len(active_tasks),
                            language=language
                        )
                    )
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    await callback.message.edit_text(
                        task_msg,
                        reply_markup=get_task_pagination_keyboard(
                            task_id=first_task.id,
                            current_index=0,
                            total_tasks=len(active_tasks),
                            language=language
                        )
                    )
        else:
            no_task_msg = get_message('task_no_active', language)
            if callback.message.text != no_task_msg:
                await callback.message.edit_text(
                    no_task_msg,
                    reply_markup=get_back_keyboard(language)
                )
            else:
                try:
                    from bot.keyboards.main_menu import get_back_keyboard
                    await callback.message.edit_reply_markup(
                        reply_markup=get_back_keyboard(language)
                    )
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    await callback.message.edit_text(
                        no_task_msg,
                        reply_markup=get_back_keyboard(language)
                    )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку заданий: {e}")
        from messages import get_message
        await callback.answer(get_message('error_generic', language))

# TODO Добавить текст задания
@router.callback_query(F.data.startswith("complete_task:"))
async def start_task_completion(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начало выполнения задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            await state_manager.set_state(state, TaskStates.waiting_for_task_completion)
            await state_manager.update_state_data(state, completing_task_id=task_id)
            completion_msg = get_message('ask_task_completion', language).format(
                title=task.title
            )
            await callback.message.edit_text(
                completion_msg,
                reply_markup=get_cancel_keyboard(language)
            )
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при начале выполнения задания: {e}")
        await callback.answer(get_message('error_generic', language))

# TODO при ошибке преложить еще раз через show_alert и перезапустить состояние
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

# TODO при ошибке преложить еще раз через show_alert и перезапустить состояние
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

# TODO Возможность вернуть в работу
@router.callback_query(F.data.startswith("skip_task:"))
async def skip_task(callback: CallbackQuery, user, language: str):
    """Пропуск задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        success = await task_service.skip_task(task_id, user)
        if success:
            task_skipped_msg = get_message('task_skipped', language)
            await callback.message.edit_text(
                task_skipped_msg,
                reply_markup=get_back_keyboard(language)
            )
        else:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Не удалось пропустить задание {task_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пропуске задания: {e}")
        await callback.answer(get_message('error_generic', language))

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

# TODO Сделать единую функцию подтверждения True/False
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

# TODO Сделать единую функцию подтверждения True/False
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

# TODO проверить после реализации просмотра списка заданий
@router.callback_query(F.data.startswith("view_task_history:"))
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
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_completed_task:"))
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
        await callback.answer(get_message('error_generic', language))