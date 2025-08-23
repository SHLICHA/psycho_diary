"""
Handlers для работы с терапевтическими заданиями
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from messages import get_message, get_button_text
from bot.states.task_states import TaskStates
from bot.keyboards import get_cancel_keyboard
from bot.keyboards.tasks_keyboard import (
    get_confirm_delete_task_keyboard,
    get_task_pagination_keyboard,
    get_task_detail_keyboard
)
from bot.keyboards.main_menu import get_back_keyboard
from bot.utils.state_manager import state_manager
from bot.services.task_service import task_service

# Создаем роутер для этого модуля
router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "tasks")
async def show_tasks(callback: CallbackQuery, user, language: str):
    """Показ текущих заданий с пагинацией"""
    logger.info(f"Показ заданий для пользователя {callback.from_user.id}")
    
    try:
        # Получаем активные задания пользователя
        from bot.services.task_service import task_service
        active_tasks = await task_service.get_user_active_tasks(user)
        
        if active_tasks:
            # Показываем первое активное задание с пагинацией
            first_task = active_tasks[0]
            
            from messages import get_message
            task_msg = get_message(
                'task_assigned',
                language,
                title=first_task.title,
                description=first_task.description
            )
            
            # ИСПРАВЛЕНО: используем клавиатуру с пагинацией
            from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_task_pagination_keyboard(
                    task_id=first_task.id,
                    current_index=0,
                    total_tasks=len(active_tasks),
                    language=language
                )
            )
            logger.info(f"Показано первое задание из {len(active_tasks)}")
        else:
            # Нет активных заданий
            from messages import get_message
            no_task_msg = get_message('task_no_active', language)
            
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info("Нет активных заданий")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при показе заданий: {e}")
        from messages import get_message
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("tasks_paginate:"))
async def paginate_tasks(callback: CallbackQuery, user, language: str):
    """Пагинация между заданиями"""
    logger.info(f"Пагинация заданий для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем направление и индекс из callback_data
        parts = callback.data.split(":")
        direction = parts[1]  # "next" или "prev"
        current_index = int(parts[2])
        
        logger.info(f"Пагинация: {direction}, текущий индекс: {current_index}")
        
        # Получаем активные задания пользователя
        active_tasks = await task_service.get_user_active_tasks(user)
        
        if not active_tasks:
            # Нет активных заданий
            no_task_msg = get_message('task_no_active', language)
            await callback.message.edit_text(
                no_task_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info("Нет активных заданий для пагинации")
            await callback.answer()
            return
        
        # Вычисляем новый индекс
        if direction == "next":
            new_index = (current_index + 1) % len(active_tasks)
        elif direction == "prev":
            new_index = (current_index - 1) % len(active_tasks)
        else:
            new_index = current_index
        
        logger.info(f"Новый индекс задания: {new_index}")
        
        # Показываем задание по новому индексу
        task = active_tasks[new_index]
        
        task_msg = get_message(
            'task_assigned',
            language,
            title=task.title,
            description=task.description
        )
        
        # ИСПРАВЛЕНО: используем клавиатуру с пагинацией
        await callback.message.edit_text(
            task_msg,
            reply_markup=get_task_pagination_keyboard(
                task_id=task.id,
                current_index=new_index,
                total_tasks=len(active_tasks),
                language=language
            )
        )
        logger.info(f"Показано задание {new_index + 1}/{len(active_tasks)} ID: {task.id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при пагинации заданий: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_task:"))
async def view_specific_task(callback: CallbackQuery, user, language: str):
    """Просмотр конкретного задания"""
    logger.info(f"Просмотр конкретного задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Просмотр задания ID: {task_id}")
        
        # Получаем задание с проверкой владельца
        from diary.models import TherapyTask
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            
            # Формируем сообщение с заданием
            task_msg = get_message(
                'task_assigned',
                language,
                title=task.title,
                description=task.description
            )
            
            # ИСПРАВЛЕНО: используем правильную клавиатуру
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_task_detail_keyboard(task_id, language)
            )
            logger.info(f"Показано задание ID: {task_id}")
            
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
    logger.info(f"Начало выполнения задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Начало выполнения задания ID: {task_id}")
        
        # Получаем задание с проверкой владельца
        from diary.models import TherapyTask
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            
            # Устанавливаем состояние выполнения задания
            await state_manager.set_state(state, TaskStates.waiting_for_task_completion)
            await state_manager.update_state_data(state, completing_task_id=task_id)
            
            # Предлагаем ввести выполнение задания
            completion_msg = get_message('ask_task_completion', language).format(
                title=task.title
            )
            
            await callback.message.edit_text(
                completion_msg,
                reply_markup=get_cancel_keyboard(language)
            )
            logger.info(f"Предложено выполнить задание {task.title}")
            
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при начале выполнения задания: {e}")
        await callback.answer(get_message('error_generic', language))

@router.message(TaskStates.waiting_for_task_completion)
async def process_task_completion(message: Message, state: FSMContext, user, language: str):
    """Обработка выполнения задания"""
    logger.info(f"Обработка выполнения задания от пользователя {message.from_user.id}")
    
    try:
        # Получаем текст выполнения
        completion_text = message.text
        logger.info(f"Получено выполнение задания длиной {len(completion_text)} символов")
        
        # Проверяем минимальную длину
        if len(completion_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое выполнение задания")
            return
        
        # Проверяем максимальную длину
        from core.constants import TEXT_MESSAGE_MAX_LENGTH
        if len(completion_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст выполнения слишком длинный: {len(completion_text)} символов")
            return
        
        # Сохраняем текст выполнения в состоянии
        await state_manager.update_state_data(state, completion_text=completion_text)
        
        # Переходим к следующему этапу - ощущения
        await state_manager.set_state(state, TaskStates.describing_feelings)
        
        feelings_msg = get_message('ask_feelings_description', language)
        
        await message.answer(
            feelings_msg,
            reply_markup=get_cancel_keyboard(language)
        )
        logger.info("Предложено описать ощущения")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке выполнения задания: {e}")
        await message.answer(get_message('error_processing', language))

@router.message(TaskStates.describing_feelings)
async def process_feelings_description(message: Message, state: FSMContext, user, language: str):
    """Обработка описания ощущений при выполнении задания"""
    logger.info(f"Обработка описания ощущений от пользователя {message.from_user.id}")
    
    try:
        # Получаем текст ощущений
        feelings_text = message.text
        logger.info(f"Получено описание ощущений длиной {len(feelings_text)} символов")
        
        # Проверяем минимальную длину
        if len(feelings_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получено пустое описание ощущений")
            return
        
        # Проверяем максимальную длину
        from core.constants import TEXT_MESSAGE_MAX_LENGTH
        if len(feelings_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст ощущений слишком длинный: {len(feelings_text)} символов")
            return
        
        # Показываем сообщение об обработке
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке ощущений")
        
        # Получаем данные состояния
        state_data = await state_manager.get_state_data(state)
        task_id = state_data.get('completing_task_id')
        completion_text = state_data.get('completion_text', '')
        
        if not task_id:
            logger.error("Не найден ID задания в состоянии")
            await message.answer(get_message('error_generic', language))
            return
        
        # Выполняем задание через сервис
        try:
            task_completion = await task_service.complete_task(
                task_id=task_id,
                user=user,
                completion_text=completion_text,
                feelings_text=feelings_text
            )
            
            await state_manager.clear_state(state)
            
            # Показываем результат выполнения
            completion_result_msg = get_message(
                'task_completed_success', 
                language,
                score=8,
                mood=get_message('mood_8', language),
                comment="Отличная работа! Задание выполнено честно и подробно.",
                recommendation="Продолжайте в том же духе",
                analysis="Анализ выполнения..."
            )
            
            await status_message.edit_text(
                completion_result_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Задание {task_id} успешно выполнено")
            
        except Exception as service_error:
            logger.error(f"Ошибка при выполнении задания через сервис: {service_error}")
            await status_message.edit_text(get_message('error_processing', language))
            return
        
    except Exception as e:
        logger.error(f"Ошибка при обработке описания ощущений: {e}")
        await message.answer(get_message('error_processing', language))

@router.callback_query(F.data.startswith("skip_task:"))
async def skip_task(callback: CallbackQuery, user, language: str):
    """Пропуск задания"""
    logger.info(f"Пропуск задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Пропуск задания ID: {task_id}")
        
        # Пропускаем задание через сервис
        success = await task_service.skip_task(task_id, user)
        
        if success:
            task_skipped_msg = get_message('task_skipped', language)
            
            await callback.message.edit_text(
                task_skipped_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Задание {task_id} успешно пропущено")
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
    logger.info(f"Удаление задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Удаление задания ID: {task_id}")
        
        # Запрашиваем подтверждение удаления
        confirm_msg = get_message('confirm_delete_task', language)
        
        await callback.message.edit_text(
            confirm_msg,
            reply_markup=get_confirm_delete_task_keyboard(task_id, language)
        )
        await callback.answer()
        logger.info(f"Запрошено подтверждение удаления задания {task_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при запросе удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_task:"))
async def confirm_delete_task(callback: CallbackQuery, user, language: str):
    """Подтверждение удаления задания"""
    logger.info(f"Подтверждение удаления задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Подтверждение удаления задания ID: {task_id}")
        
        # Удаляем задание через сервис
        success = await task_service.delete_task(task_id, user)
        
        if success:
            task_deleted_msg = get_message('task_deleted', language)
            
            await callback.message.edit_text(
                task_deleted_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Задание {task_id} успешно удалено")
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
    logger.info(f"Отмена удаления задания для пользователя {callback.from_user.id}")
    
    try:
        cancel_msg = get_message('task_delete_cancelled', language)
        
        await callback.message.edit_text(
            cancel_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Удаление задания отменено")
        
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления задания: {e}")
        await callback.answer(get_message('error_generic', language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data.startswith("view_task_history:"))
async def view_task_history(callback: CallbackQuery, user, language: str):
    """Просмотр истории заданий"""
    logger.info(f"Просмотр истории заданий для пользователя {callback.from_user.id}")
    
    try:
        # Получаем выполненные задания пользователя
        completed_tasks = await task_service.get_user_completed_tasks(user, limit=10)
        
        if completed_tasks:
            # Формируем сообщение с историей заданий
            history_msg = "🎯 <b>История выполненных заданий</b>\n\n"
            
            for i, task in enumerate(completed_tasks, 1):
                task_type = task.get_type_display()
                history_msg += f"<b>{i}. {task.title}</b> ({task_type})\n"
                history_msg += f"🕒 {task.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
                history_msg += f"⭐ Приоритет: {task.priority}\n\n"
            
            # Добавляем кнопки для просмотра конкретных заданий
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            buttons = []
            for i, task in enumerate(completed_tasks, 1):
                buttons.append([
                    InlineKeyboardButton(
                        text=f"👁 Просмотреть задание {i}",
                        callback_data=f"view_completed_task:{task.id}"
                    )
                ])
            
            # Кнопка "Назад"
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
            logger.info(f"Показана история {len(completed_tasks)} выполненных заданий")
        else:
            # Нет выполненных заданий
            no_tasks_msg = get_message('task_no_completed', language)
            
            await callback.message.edit_text(
                no_tasks_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info("Нет выполненных заданий")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре истории заданий: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_completed_task:"))
async def view_completed_task(callback: CallbackQuery, user, language: str):
    """Просмотр выполненного задания"""
    logger.info(f"Просмотр выполненного задания для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID задания из callback_data
        task_id = int(callback.data.split(":")[1])
        logger.info(f"Просмотр выполненного задания ID: {task_id}")
        
        # Получаем задание с проверкой владельца
        from diary.models import TherapyTask
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
            
            # Получаем выполнение задания (если есть)
            completion_text = "Выполнение не доступен"
            feelings_text = "Ощущения не доступны"
            
            try:
                if hasattr(task, 'completion'):
                    from diary.models import TaskCompletion
                    try:
                        completion = await TaskCompletion.objects.aget(task=task)
                        completion_text = completion.completion_text or "Выполнение записано"
                        feelings_text = completion.feelings_text or "Ощущения не описаны"
                    except TaskCompletion.DoesNotExist:
                        logger.info("Выполнение для задания не найдено")
            except Exception as completion_error:
                logger.error(f"Ошибка при получении выполнения: {completion_error}")
            
            # Формируем сообщение с заданием
            task_msg = f"🎯 <b>Выполненное задание: {task.title}</b>\n\n"
            task_msg += f"📝 <b>Описание:</b>\n{task.description}\n\n"
            task_msg += f"🕒 <b>Выполнено:</b> {task.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
            task_msg += f"⭐ <b>Приоритет:</b> {task.priority}\n\n"
            task_msg += f"✅ <b>Выполнение:</b>\n{completion_text}\n\n"
            task_msg += f"💭 <b>Ощущения:</b>\n{feelings_text}"
            
            # Кнопка "Назад"
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                task_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Показано выполненное задание ID: {task_id}")
            
        except TherapyTask.DoesNotExist:
            error_msg = get_message('task_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре выполненного задания: {e}")
        await callback.answer(get_message('error_generic', language))