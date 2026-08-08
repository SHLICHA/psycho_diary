"""Task handlers (transport-only)."""
from __future__ import annotations

import logging
import asyncio

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, ContentType, BufferedInputFile
from aiogram.fsm.context import FSMContext

from messages import get_message
from bot.states.task_states import TaskStates
from bot.keyboards import (
    get_back_keyboard,
    get_confirm_delete_task_keyboard,
    get_single_button_keyboard,
    get_task_history_main_keyboard,
    get_task_history_list_keyboard,
)
from bot.decorators.analytics_decorator import log_user_activity
from bot.decorators.premium_decorator import requires_premium
from bot.utils.audio_utils import process_voice_message
from bot.utils.state_manager import state_manager
from bot.utils.task_impact_chart import generate_task_impact_chart_image
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from diary.services.task_management_service import (
    get_user_task_by_id,
    complete_task_with_feelings_use_case,
    analyze_completed_task_for_notification_use_case,
    skip_task,
    delete_task,
    restore_skipped_task_use_case,
)
from diary.services.task_display_service import task_display_service
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diary.models import TaskCompletion
    from users.models import User

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "tasks")
@router.callback_query(F.data == "back_to_tasks")
@log_user_activity('task')
async def show_tasks(callback: CallbackQuery, user, language: str):
    """Показ текущих заданий с пагинацией"""
    try:
        view = await task_display_service.build_active_tasks_view(user, language)
        await callback.message.edit_text(
            view['text'],
            reply_markup=view['keyboard'],
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
        view = await task_display_service.build_active_tasks_page_view(
            user,
            language,
            index=current_index,
            direction=direction,
            empty_reply_mode='back_only',
        )
        await callback.message.edit_text(
            view['text'],
            reply_markup=view['keyboard'],
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
        view = await task_display_service.build_task_detail_view(user, task_id, language)
        if view['success']:
            await callback.message.edit_text(
                view['text'],
                reply_markup=view['keyboard'],
            )
        else:
            await callback.answer(view['alert_text'])
            logger.warning(
                f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}"
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при просмотре конкретного задания: {e}")
        await callback.answer(get_message('error_generic', language))


@router.callback_query(F.data.startswith("complete_task:"))
@log_user_activity('task_completed')
async def start_task_completion(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начало выполнения задания"""
    task_id = None
    try:
        task_id = int(callback.data.split(":")[1])
        view = await task_display_service.build_start_completion_view(user, task_id, language)
        if not view['success']:
            await safe_answer_callback(callback, view['alert_text'], show_alert=True)
            logger.warning(
                f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}"
            )
            return

        await state_manager.set_state(state, view['fsm_state'])
        await state_manager.update_state_data(state, **view['fsm_data'])
        await callback.message.edit_text(
            view['text'],
            reply_markup=view['keyboard'],
        )
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
        completion_response = await complete_task_with_feelings_use_case(
            user=user,
            task_id=task_id,
            completion_text=completion_text,
            feelings_text=feelings_text,
            language=language,
        )
        await state_manager.clear_state(state)

        if not completion_response.success:
            logger.error(
                f"Сервис вернул ошибку при выполнении задания {task_id}: "
                f"{completion_response.error}"
            )
            await status_message.edit_text(
                completion_response.message or get_message('error_processing', language)
            )
            return
        task_completion_obj = (completion_response.data or {}).get('task_completion')
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
        except Exception as send_error:
            logger.debug(f"[process_feelings_description] answer failed: {send_error}")
            try:
                if status_message:
                    await status_message.edit_text(get_message('error_processing', language))
            except Exception as edit_error:
                logger.debug(f"[process_feelings_description] status edit failed: {edit_error}")


async def _notify_user_of_analysis_result(task_completion: TaskCompletion, user: User, status_message: Message, bot_instance: Bot):
    """
    Transport-обёртка: use case анализа → send/edit уведомления.
    """
    language = getattr(user, 'language', None) or 'ru'
    try:
        response = await analyze_completed_task_for_notification_use_case(
            task_completion=task_completion,
            user=user,
            language=language,
        )
        payload = response.data or {}
        text = payload.get('notification_text') or get_message('task_analysis_error_formatted', language)
        keyboard = payload.get('notification_keyboard') or get_back_keyboard(language)

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
                    text=text,
                    reply_markup=keyboard
                )
            except Exception as edit_error:
                logger.warning(
                    f"[tasks.notify_analysis] edit failed task_id={task_completion.task.id}: "
                    f"{edit_error}; sending new"
                )
                await bot_instance.send_message(
                    chat_id=target_chat_id,
                    text=text,
                    reply_markup=keyboard
                )
        else:
            await bot_instance.send_message(
                chat_id=target_chat_id,
                text=text,
                reply_markup=keyboard
            )

    except Exception as task_error:
        logger.error(
            f"[tasks.notify_analysis] failed user_id={user.id}: {task_error}",
            exc_info=True,
        )
        try:
            error_text = get_message('task_analysis_error_formatted', language)
            error_keyboard = get_back_keyboard(language)
            if status_message:
                try:
                    await safe_edit_message_text(
                        message=status_message,
                        text=error_text,
                        reply_markup=error_keyboard
                    )
                except Exception as edit_error:
                    logger.debug(f"[_notify_user_of_analysis_result] edit failed: {edit_error}")
                    try:
                        await bot_instance.send_message(
                            chat_id=status_message.chat.id,
                            text=error_text,
                            reply_markup=error_keyboard
                        )
                    except Exception as send_error:
                        logger.debug(
                            f"[_notify_user_of_analysis_result] fallback send failed: {send_error}"
                        )
            else:
                await bot_instance.send_message(
                    chat_id=user.telegram_id,
                    text=error_text,
                    reply_markup=error_keyboard
                )
        except Exception as notify_error:
            logger.debug(f"[_notify_user_of_analysis_result] error notify failed: {notify_error}")


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
            view = await task_display_service.build_active_tasks_view(user, language)
            await safe_edit_message_text(
                message=callback.message,
                text=view['text'],
                reply_markup=view['keyboard'],
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
        view = await task_display_service.build_task_history_view(user, language)
        if view['mode'] == 'list':
            await state_manager.update_state_data(
                state,
                task_history_ids=view.get('task_ids', []),
            )
        await safe_edit_message_text(
            message=callback.message,
            text=view['text'],
            reply_markup=view['keyboard'],
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
        task = await get_user_task_by_id(user, task_id)
        if not task:
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
        state_data = await state_manager.get_state_data(state)
        task_history_ids = state_data.get('task_history_ids', [])
        use_case_result = await restore_skipped_task_use_case(
            user,
            task_id,
            task_history_ids=task_history_ids,
        )
        if use_case_result['success']:
            success_msg = get_message(use_case_result['alert_text_key'], language)
            await safe_answer_callback(callback, success_msg, show_alert=True)
            if task_id not in task_history_ids:
                logger.warning(
                    f"ID задания {task_id} не найден в списке истории FSM при восстановлении."
                )
            await state_manager.update_state_data(
                state,
                task_history_ids=use_case_result['updated_task_history_ids'],
            )
            await show_tasks(callback, user, language)
        else:
            error_msg = get_message(use_case_result['alert_text_key'], language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(
                f"Не удалось восстановить задание {task_id} для пользователя {user.telegram_id}"
            )
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
        logger.debug(
            f"[tasks.impact_chart] sent message_id={sent_message.message_id} user_id={user.id}"
        )
    except Exception as e:
        logger.error(f"[tasks.impact_chart] failed user_id={user.id}: {e}", exc_info=True)
        try:
            await callback.message.answer(get_message('error_processing', language))
        except Exception as send_error:
            logger.error(f"[tasks.impact_chart] error reply failed: {send_error}")
        try:
            await processing_msg.delete()
        except Exception as delete_error:
            logger.debug(f"[tasks.impact_chart] processing_msg delete failed: {delete_error}")
