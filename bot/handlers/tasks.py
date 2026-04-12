"""
Handlers для работы с терапевтическими заданиями
"""

import logging
import asyncio

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, ContentType, BufferedInputFile
from aiogram.fsm.context import FSMContext

from messages import get_message, get_button_text
from bot.states.task_states import TaskStates
from bot.keyboards import (
    get_back_keyboard,
    get_confirm_delete_task_keyboard,
    get_task_pagination_keyboard,
    get_task_detail_keyboard,
    get_single_button_keyboard,
    get_task_history_main_keyboard,
    get_task_history_list_keyboard,
    get_task_main_menu_keyboard
)
from bot.decorators.analytics_decorator import log_user_activity
from bot.decorators.premium_decorator import requires_premium
from bot.utils.audio_utils import process_voice_message
from bot.utils.state_manager import state_manager
from bot.utils.task_impact_chart import generate_task_impact_chart_image
from bot.utils.message_utils import send_message_to_user
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from diary.models import TherapyTask, TaskCompletion, TaskCompletionAnalysis
from diary.services.task_management_service import (
    get_user_active_tasks,
    get_user_completed_tasks,
    complete_task,
    skip_task,
    delete_task,
    get_user_skipped_tasks,
    restore_task,
    analyze_task_completion_effect
)
from diary.services.task_display_service import task_display_service
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
                    _notify_user_of_analysis_result(
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


async def _notify_user_of_analysis_result(task_completion: TaskCompletion, user: User, status_message: Message, bot_instance: Bot):
    """
    Асинхронная задача для уведомления пользователя о результате анализа выполнения задания.
    Использует task_display_service для форматирования результата.
    """
    try:
        analysis_result = await analyze_task_completion_effect(task_completion, user)

        # Форматируем результат через сервис
        notification = await task_display_service.format_task_analysis_notification(
            analysis_result, user, task_completion
        )

        # Отправляем/редактируем сообщение
        target_chat_id = user.telegram_id
        use_edit = False
        message_to_edit = None
        if status_message:
            target_chat_id = status_message.chat.id
            use_edit = True
            message_to_edit = status_message

        if use_edit and message_to_edit:
            try:
                await safe_edit_message_text(
                    message=message_to_edit,
                    text=notification.text,
                    reply_markup=notification.keyboard
                )
                logger.debug(f"Сообщение отредактировано для задания {task_completion.task.id}")
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение: {edit_error}. Отправляем новое.")
                await bot_instance.send_message(
                    chat_id=target_chat_id,
                    text=notification.text,
                    reply_markup=notification.keyboard
                )
        else:
            await bot_instance.send_message(
                chat_id=target_chat_id,
                text=notification.text,
                reply_markup=notification.keyboard
            )
            logger.debug(f"Новое сообщение отправлено для задания {task_completion.task.id}")

    except Exception as task_error:
        logger.error(f"Критическая ошибка в _notify_user_of_analysis_result: {task_error}", exc_info=True)
        try:
            language = user.language if 'user' in locals() else 'ru'
            error_text = get_message('task_analysis_error_formatted', language)
            error_keyboard = get_back_keyboard(language)
            if status_message and 'bot_instance' in locals():
                try:
                    await safe_edit_message_text(
                        message=status_message,
                        text=error_text,
                        reply_markup=error_keyboard
                    )
                except:
                    try:
                        await bot_instance.send_message(
                            chat_id=status_message.chat.id,
                            text=error_text,
                            reply_markup=error_keyboard
                        )
                    except:
                        pass
            elif 'bot_instance' in locals() and 'user' in locals():
                await bot_instance.send_message(
                    chat_id=user.telegram_id,
                    text=error_text,
                    reply_markup=error_keyboard
                )
        except:
            pass


@router.callback_query(F.data.startswith("skip_task:"))
@log_user_activity('task_skipped')
async def skip_task_handler(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Пропуск задания"""
    try:
        task_id = int(callback.data.split(":")[1])
        success = await skip_task(task_id, user)
        if success:
            task_skipped_msg = get_message('task_skipped', language)
            await safe_answer_callback(callback, task_skipped_msg, show_alert=True)
            active_tasks = await get_user_active_tasks(user)
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
    """Показывает историю заданий с пагинацией."""
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
            detail = await task_display_service.format_task_history_detail(first_task, language)
            await safe_edit_message_text(
                message=callback.message,
                text=detail.text,
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
        detail = await task_display_service.format_task_history_detail(task, language)
        await safe_edit_message_text(
            message=callback.message,
            text=detail.text,
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
        result = await task_display_service.get_task_analysis_detail(user, task_id)

        if not result['success']:
            await safe_answer_callback(callback, result['message'], show_alert=True)
            await safe_edit_message_text(
                message=callback.message,
                text=result['message'],
                reply_markup=get_task_history_main_keyboard(language)
            )
            return

        await safe_edit_message_text(
            message=callback.message,
            text=result['text'],
            reply_markup=result['keyboard']
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError):
        logger.error(f"Ошибка парсинга task_id из callback_data: {callback.data}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре детального анализа задания: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)


@router.callback_query(F.data == "show_task_impact_chart")
@requires_premium(alert_message_key='feature_requires_premium')
@log_user_activity('task_chart_viewed', metadata_extra={'context': 'Просмотр графика влияния заданий'})
async def send_task_impact_chart(callback: CallbackQuery, user, language: str, bot: Bot):
    """Отправляет изображение с графиком влияния выполненных заданий."""
    days = 30
    try:
        await safe_answer_callback(callback, "")
        processing_msg = await callback.message.answer(get_message('processing', language))
        chart_image_buffer = await generate_task_impact_chart_image(user, days=days, language=language)
        chart_input_file = BufferedInputFile(chart_image_buffer.getvalue(), filename='task_impact_chart.png')
        dismiss_kb = get_single_button_keyboard(
            language=language,
            button_callback_data="delete_current_chart",
            button_text="btn_remove"
        )
        sent_message = await callback.message.answer_photo(
            photo=chart_input_file,
            caption=get_message('task_impact_chart_caption', language, days=days),
            reply_markup=dismiss_kb
        )
        await processing_msg.delete()
        logger.debug(f"[send_task_impact_chart] График отправлен в сообщении ID {sent_message.message_id} пользователю {user.telegram_id}")
    except Exception as e:
        logger.error(f"[send_task_impact_chart] Ошибка генерации/отправки графика: {e}", exc_info=True)
        try:
            await callback.message.answer(get_message('error_processing', language))
        except Exception as send_error:
            logger.error(f"[send_task_impact_chart] Ошибка при отправке сообщения об ошибке пользователю: {send_error}")
        try:
            await processing_msg.delete()
        except:
            pass
