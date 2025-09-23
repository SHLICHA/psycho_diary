"""
Сервис для работы с терапевтическими заданиями
"""

import asyncio
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from asgiref.sync import sync_to_async
from aiogram.types import Message

from prompts.get_prompt import get_prompt
from diary.services.daily_state_service import daily_state_service
from diary.models import DiaryEntry, TherapyTask, TaskCompletion, TaskCompletionAnalysis
from users.models import User
from bot.services.deepseek_api import deepseek_api_service
from bot.utils.message_utils import safe_edit_message_text
from bot.keyboards import get_back_keyboard

logger = logging.getLogger(__name__)

class TaskService:
    """Сервис для работы с терапевтическими заданиями"""
    async def assign_task(
        self, 
        user: User, 
        title: str, 
        description: str, 
        task_type: str = 'daily',
        priority: int = 1,
        related_entry: DiaryEntry = None
    ) -> TherapyTask:
        """
        Назначение терапевтического задания пользователю
        
        Args:
            user: Пользователь
            title: Название задания
            description: Описание задания
            task_type: Тип задания
            priority: Приоритет задания
            
        Returns:
            TherapyTask: Назначенное задание
        """
        try:
            @sync_to_async
            def create_task_sync():
                with transaction.atomic():
                    therapy_task = TherapyTask.objects.create(
                        user=user,
                        title=title,
                        description=description,
                        type=task_type,
                        priority=priority,
                        status='pending',
                        related_entry=related_entry
                    )
                    return therapy_task
            therapy_task = await create_task_sync()
            return therapy_task
        except Exception as e:
            logger.error(f"Ошибка при назначении задания: {e}")
            raise
    
    async def get_user_active_tasks(
        self, 
        user: User
    ) -> List[TherapyTask]:
        """
        Получение активных заданий пользователя
        
        Args:
            user: Пользователь
            
        Returns:
            List[TherapyTask]: Список активных заданий
        """
        try:
            @sync_to_async
            def get_active_tasks_sync():
                active_tasks = list(
                    TherapyTask.objects.filter(
                        user=user,
                        status__in=['pending', 'in_progress']
                    ).order_by('assigned_at')
                )
                return active_tasks
            active_tasks = await get_active_tasks_sync()
            return active_tasks
        except Exception as e:
            logger.error(f"Ошибка при получении активных заданий: {e}")
            return []
    
    async def get_user_completed_tasks(
        self, 
        user: User, 
        limit: int = 10
    ) -> List[TherapyTask]:
        """
        Получение выполненных заданий пользователя
        
        Args:
            user: Пользователь
            limit: Лимит заданий
            
        Returns:
            List[TherapyTask]: Список выполненных заданий
        """
        try:
            @sync_to_async
            def get_completed_tasks_sync():
                completed_tasks = list(
                    TherapyTask.objects.filter(
                        user=user,
                        status='completed'  # Только выполненные
                    ).order_by('-completed_at')[:limit]
                )
                return completed_tasks
            completed_tasks = await get_completed_tasks_sync()
            return completed_tasks
        except Exception as e:
            logger.error(f"Ошибка при получении выполненных заданий: {e}")
            return []
    
    async def complete_task(
        self, 
        task_id: int, 
        user: User, 
        completion_text: str, 
        feelings_text: str,
        status_message: Optional[Message] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Выполнение задания.
        Возвращает словарь с результатами (включая TaskCompletion) или None.
        """
        logger.info(f"Начало выполнения задания ID: {task_id} для пользователя {user.telegram_id}")
        try:
            @sync_to_async
            def complete_task_sync():
                logger.debug(f"[SYNC] Получение задания ID {task_id} для пользователя {user.telegram_id}")
                with transaction.atomic():
                    try:
                        task = TherapyTask.objects.select_related('related_entry', 'completion').get(
                            id=task_id,
                            user=user,
                            status__in=['pending', 'in_progress', 'completed'] # Разрешаем выполнение уже выполненных
                        )
                        logger.debug(f"[SYNC] Задание найдено: {task.title}, текущий статус: {task.status}")
                    except TherapyTask.DoesNotExist:
                        logger.warning(f"[SYNC] Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                        raise ValueError("Задание не найдено или не принадлежит вам")
                    
                    # --- ЛОГИКА ДЛЯ ПОВТОРНОГО ВЫПОЛНЕНИЯ ---
                    task_completion = None
                    if hasattr(task, 'completion'):
                        # Задание уже было выполнено ранее. Обновляем существующий TaskCompletion.
                        logger.debug(f"[SYNC] TaskCompletion для задания {task_id} уже существует (ID {task.completion.id}). Обновление.")
                        task_completion = task.completion
                        task_completion.completion_text = completion_text
                        task_completion.feelings_text = feelings_text
                        task_completion.time_spent = 5 # TODO: Реальное время
                        # task_completion.created_at остается неизменным или обновляется?
                        # Если нужно обновить время выполнения:
                        # task_completion.created_at = timezone.now() 
                        task_completion.save(update_fields=['completion_text', 'feelings_text', 'time_spent'])
                        logger.debug(f"[SYNC] TaskCompletion ID {task_completion.id} обновлен.")
                        # Удаление TaskAnalysis больше не нужно, так как его нет
                        # if hasattr(task_completion, 'analysis'):
                        #     logger.debug(f"[SYNC] Удаление старого TaskAnalysis ID {task_completion.analysis.id} для TaskCompletion {task_completion.id}")
                        #     task_completion.analysis.delete()
                            
                    else:
                        # Задание выполняется впервые. Создаем новый TaskCompletion.
                        logger.debug(f"[SYNC] Создание нового TaskCompletion для задания {task_id}")
                        task_completion = TaskCompletion.objects.create(
                            task=task,
                            completion_text=completion_text,
                            feelings_text=feelings_text,
                            time_spent=5 # TODO: Реальное время
                        )
                        logger.debug(f"[SYNC] TaskCompletion создан: ID {task_completion.id}")
                    
                    # Обновляем статус задания (на случай, если оно было пропущено или выполняется повторно)
                    old_status = task.status
                    task.status = 'completed'
                    # Обновляем время завершения только если задание не было завершено ранее
                    # или если вы хотите фиксировать время последнего выполнения
                    if old_status != 'completed': 
                        task.completed_at = datetime.now()
                    task.save(update_fields=['status', 'completed_at'])
                    logger.debug(f"[SYNC] Статус задания {task_id} обновлен с '{old_status}' на 'completed'")
                    
                    # --- УДАЛЕНО: Создание заглушки TaskAnalysis ---
                    # logger.debug(f"[SYNC] Создание новой заглушки TaskAnalysis для выполнения {task_completion.id}")
                    # task_analysis = TaskAnalysis.objects.create(
                    #     completion=task_completion,
                    #     bot_response="Отличная работа! Выполнил задание честно и подробно.",
                    #     insights_updated=True,
                    #     quality_score=8,
                    #     feedback_given=True
                    # )
                    # logger.debug(f"[SYNC] TaskAnalysis заглушка создана: ID {task_analysis.id}")
                    # Возвращаем None вместо task_analysis
                    task_analysis = None 
                    
                return task_completion, task_analysis

            logger.debug(f"Вызов sync_to_async для complete_task_sync")
            task_completion, task_analysis = await complete_task_sync()
            logger.info(f"Задание ID {task_id} успешно обработано (выполнено/обновлено). TaskCompletion ID: {task_completion.id}")
            
            # Запуск фоновой задачи анализа эффекта
            logger.debug(f"Создание фоновой задачи _run_analysis_and_notify_user для TaskCompletion ID {task_completion.id}")
            asyncio.create_task(self._run_analysis_and_notify_user(task_completion, user, status_message))
            logger.debug(f"Фоновая задача _run_analysis_and_notify_user создана")
            
            # Формируем результат. task_analysis будет None
            result = {
                'task_completion': task_completion,
                'task_analysis': task_analysis, # Это будет None
                'effect_analysis_started': True
            }
            logger.debug(f"Функция complete_task возвращает результат: {result}")
            return result
            
        except ValueError as ve:
            # Это ожидаемая ошибка (например, задание не найдено)
            logger.warning(f"Ожидаемая ошибка в complete_task для задания {task_id}: {ve}")
            return None
        except Exception as e:
            logger.error(f"Критическая ошибка в complete_task для задания {task_id}: {e}", exc_info=True)
            # ВАЖНО: Возвращаем None, как и раньше, но теперь это залогировано
            return None

    async def _run_analysis_and_notify_user(self, task_completion: TaskCompletion, user: User, status_message: Optional[Message] = None):
        """
        Асинхронная задача для запуска анализа эффекта и уведомления пользователя.
        Выполняется отдельно от основного потока обработки.
        Если передан status_message, результат будет отредактирован в нем.
        Иначе будет отправлено новое сообщение.
        """
        try:
            logger.info(f"[Асинхронная задача] Запуск анализа эффекта для выполнения задания ID {task_completion.id}")
            from bot.main import bot as global_bot # Импортируем глобальный бот

            # === 1. Выполнение анализа ===
            effect_analysis = await self.analyze_task_completion_effect(task_completion, user)

            # === 2. Подготовка данных для уведомления ===
            target_chat_id = user.telegram_id
            target_message_id = None
            use_edit = False

            # Определяем, редактировать ли сообщение или отправлять новое
            if status_message:
                target_chat_id = status_message.chat.id
                target_message_id = status_message.message_id
                use_edit = True

            # === 3. Формирование и отправка сообщения ===
            if effect_analysis:
                from messages import get_message
                language = user.language

                # Используем поля из обновленной модели
                effect_description = effect_analysis.effect_description or "Нет описания эффекта"
                
                # mood_impact_score может быть None
                mood_impact_score_raw = effect_analysis.mood_impact_score
                if mood_impact_score_raw is not None:
                    try:
                        mood_impact_score = int(mood_impact_score_raw)
                        # Форматируем знак для отображения
                        if mood_impact_score > 0:
                            mood_impact_display = f"+{mood_impact_score}"
                        else:
                            mood_impact_display = str(mood_impact_score)
                    except (ValueError, TypeError):
                        mood_impact_display = "N/A"
                else:
                    mood_impact_display = "N/A"

                comment_for_user = effect_analysis.comment or "Нет комментария"
                recommendation_for_user = effect_analysis.recommendation or "Нет рекомендации"
                effect_msg = get_message(
                    'task_effect_analysis_result',
                    language,
                    effect_description=effect_description,
                    mood_impact=mood_impact_display, # Используем отформатированное значение
                    comment=comment_for_user,
                    recommendation=recommendation_for_user
                )
                
                reply_markup = get_back_keyboard(language)

                # Отправляем или редактируем сообщение
                if use_edit:
                    try:
                        await safe_edit_message_text(
                            message=status_message,
                            text=effect_msg,
                            reply_markup=reply_markup
                        )
                        logger.info(f"[Асинхронная задача] Сообщение об эффекте отредактировано для пользователя {user.telegram_id}")
                    except Exception as edit_error:
                        logger.warning(f"[Асинхронная задача] Не удалось отредактировать сообщение: {edit_error}. Отправляем новое.")
                        if global_bot:
                            await global_bot.send_message(chat_id=target_chat_id, text=effect_msg, reply_markup=reply_markup)
                            logger.info(f"[Асинхронная задача] Новое сообщение об эффекте отправлено пользователю {user.telegram_id}")
                        else:
                            logger.error("[Асинхронная задача] Глобальный бот не найден для отправки нового сообщения.")
                else:
                    if global_bot:
                        await global_bot.send_message(chat_id=target_chat_id, text=effect_msg, reply_markup=reply_markup)
                        logger.info(f"[Асинхронная задача] Новое сообщение об эффекте отправлено пользователю {user.telegram_id}")
                    else:
                        logger.error("[Асинхронная задача] Глобальный бот не найден для отправки сообщения.")

            else:
                # Обработка случая, если анализ не вернул результат (ошибка в analyze_task_completion_effect)
                logger.error(f"[Асинхронная задача] analyze_task_completion_effect вернул None для выполнения {task_completion.id}")
                error_msg = get_message('error_processing', user.language)
                error_reply_markup = get_back_keyboard(user.language) 
                
                if use_edit:
                    try:
                        await safe_edit_message_text(
                            message=status_message,
                            text=error_msg,
                            reply_markup=error_reply_markup
                        )
                        logger.info(f"[Асинхронная задача] Сообщение об ошибке отредактировано для пользователя {user.telegram_id}")
                    except Exception as edit_error:
                        logger.warning(f"[Асинхронная задача] Не удалось отредактировать сообщение об ошибке: {edit_error}. Отправляем новое.")
                        if global_bot:
                            await global_bot.send_message(chat_id=target_chat_id, text=error_msg, reply_markup=error_reply_markup)
                            logger.info(f"[Асинхронная задача] Новое сообщение об ошибке отправлено пользователю {user.telegram_id}")
                        else:
                            logger.error("[Асинхронная задача] Глобальный бот не найден для отправки сообщения об ошибке.")
                else:
                    if global_bot:
                        await global_bot.send_message(chat_id=target_chat_id, text=error_msg, reply_markup=error_reply_markup)
                        logger.info(f"[Асинхронная задача] Новое сообщение об ошибке отправлено пользователю {user.telegram_id}")
                    else:
                        logger.error("[Асинхронная задача] Глобальный бот не найден для отправки сообщения об ошибке.")

        except Exception as task_error:
            logger.error(f"[Асинхронная задача] Критическая ошибка в _run_analysis_and_notify_user: {task_error}", exc_info=True)
            # Попытка отправить сообщение об ошибке, если возможно
            try:
                from messages import get_message
                error_msg = get_message('error_processing', user.language if 'user' in locals() else 'ru')
                error_reply_markup = get_back_keyboard(user.language if 'user' in locals() else 'ru')
                
                if status_message and global_bot:
                    try:
                        await safe_edit_message_text(
                            message=status_message,
                            text=error_msg,
                            reply_markup=error_reply_markup
                        )
                    except:
                        try:
                            await global_bot.send_message(
                                chat_id=status_message.chat.id if status_message else (user.telegram_id if 'user' in locals() else 0),
                                text=error_msg,
                                reply_markup=error_reply_markup
                            )
                        except:
                            pass
                elif global_bot and 'user' in locals():
                    await global_bot.send_message(chat_id=user.telegram_id, text=error_msg, reply_markup=error_reply_markup)
            except:
                pass
    
    async def skip_task(
        self, 
        task_id: int, 
        user: User
    ) -> bool:
        """
        Пропуск задания
        
        Args:
            task_id: ID задания
            user: Пользователь
            
        Returns:
            bool: Успешность пропуска
        """
        try:
            @sync_to_async
            def skip_task_sync():
                try:
                    task = TherapyTask.objects.get(
                        id=task_id,
                        user=user,
                        status__in=['pending', 'in_progress']
                    )
                except TherapyTask.DoesNotExist:
                    logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                    return False
                with transaction.atomic():
                    task.status = 'skipped'
                    task.completed_at = datetime.now()
                    task.save(update_fields=['status', 'completed_at'])       
                return True
            success = await skip_task_sync()
            return success
        except Exception as e:
            logger.error(f"Ошибка при пропуске задания: {e}")
            return False
    
    async def delete_task(
        self, 
        task_id: int, 
        user: User
    ) -> bool:
        """
        Удаление задания
        
        Args:
            task_id: ID задания
            user: Пользователь
            
        Returns:
            bool: Успешность удаления
        """
        try:
            @sync_to_async
            def delete_task_sync():
                try:
                    task = TherapyTask.objects.get(
                        id=task_id,
                        user=user
                    )
                except TherapyTask.DoesNotExist:
                    logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                    return False
                with transaction.atomic():
                    # Удаление связанных объектов
                    if hasattr(task, 'completion'):
                        try:
                            completion = TaskCompletion.objects.get(task=task)
                            # Удаление TaskAnalysis больше не нужно
                            # if hasattr(completion, 'analysis'):
                            #     try:
                            #         analysis = TaskAnalysis.objects.get(completion=completion)
                            #         analysis.delete()
                            #     except TaskAnalysis.DoesNotExist:
                            #         pass # Анализ уже удален или не существовал
                            # Удаляем сам TaskCompletion
                            completion.delete()
                            logger.debug(f"[SYNC] TaskCompletion для задания {task_id} удален.")
                        except TaskCompletion.DoesNotExist:
                            logger.debug(f"[SYNC] TaskCompletion для задания {task_id} не найден при удалении.")
                    # Удаление самого задания
                    task.delete()
                    logger.info(f"[SYNC] Задание ID {task_id} удалено.")
                return True
            success = await delete_task_sync()
            return success
        except Exception as e:
            logger.error(f"Ошибка при удалении задания ID {task_id}: {e}")
            return False
    
    async def analyze_task_completion_effect(
        self,
        task_completion: TaskCompletion,
        user: User
    ) -> Optional[TaskCompletionAnalysis]:
        """
        Асинхронно анализирует влияние выполнения задания на эмоциональное состояние,
        сравнивая день назначения и день выполнения.

        Args:
            task_completion: Объект выполнения задания.
            user: Пользователь.

        Returns:
            TaskCompletionAnalysis: Объект анализа или None в случае ошибки.
        """
        logger.info(f"Начало анализа эффекта выполнения задания ID {task_completion.task.id} "
                    f"(выполнение ID {task_completion.id}) для пользователя {user.telegram_id}")
        try:
            logger.info(f"Начало анализа эффекта выполнения задания ID {task_completion.task.id} "
                        f"(выполнение ID {task_completion.id}) для пользователя {user.telegram_id}")

            # === 1. Подготовка данных ===
            related_entry = task_completion.task.related_entry
            completion_date = task_completion.created_at.date()

            # --- Получение CombinedDiaryEntry для дня назначения ---
            assigned_combined_entry = None
            assigned_date_str = "N/A"
            if related_entry:
                assigned_date = await related_entry.aentry_date()
                assigned_date_str = assigned_date.isoformat()
                assigned_combined_entry = await daily_state_service.get_daily_state(user, assigned_date)
                logger.debug(f"CombinedDiaryEntry для дня назначения ({assigned_date}): "
                            f"{'Найден' if assigned_combined_entry else 'Не найден'}")
            else:
                logger.warning(f"Задание {task_completion.task.id} не связано с записью дневника.")

            # --- Получение CombinedDiaryEntry для дня выполнения ---
            completion_combined_entry = await daily_state_service.get_daily_state(user, completion_date)
            if not completion_combined_entry:
                logger.error(f"CombinedDiaryEntry для дня выполнения ({completion_date}) не найден. "
                            f"Анализ невозможен.")
                # Создаем запись об ошибке
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description="[Ошибка: CombinedDiaryEntry дня выполнения не найден]",
                    mood_impact_score=None,
                    comment="",
                    recommendation="",
                    detailed_analysis="",
                    api_response={"error": "Completion day CombinedDiaryEntry not found"}
                )
                return analysis

            # === 2. Сбор контекста для промпта ===
            # --- Контекст дня назначения ---
            assigned_day_context = {
                "text": assigned_combined_entry.text if assigned_combined_entry else "",
                "analysis_result": assigned_combined_entry.analysis_result if assigned_combined_entry else {}
            }

            # --- Контекст дня выполнения ---
            completion_day_context = {
                "text": completion_combined_entry.text,
                "analysis_result": completion_combined_entry.analysis_result
            }

            # --- Профиль пользователя ---
            user_profile_data = {
                'username': user.username or f"user_{user.telegram_id}",
                'first_name': user.first_name or "",
                'awareness_level': user.awareness_level,
                'is_premium': user.is_premium,
                # Добавляем новые поля из модели User
                'personality_traits': user.personality_traits, # Это теперь словарь {trait: weight}
                'life_facts': user.life_facts, # Список строк
                'hobbies': user.hobbies, # Список строк
                'core_values': user.core_values, # Список строк
                'triggers': user.triggers, # Список строк
                'strengths': user.strengths, # Список строк
                'areas_for_growth': user.areas_for_growth, # Список строк
            }

            # === 3. Формирование промпта ===
            prompt = get_prompt(
                'task_effect_analysis',
                language=user.language,
                user_profile=user_profile_data,
                assigned_date=assigned_date_str,
                assigned_day_text=assigned_day_context['text'],
                assigned_day_analysis=json.dumps(assigned_day_context['analysis_result'], ensure_ascii=False, indent=2),
                completion_date=completion_date.isoformat(),
                completion_day_text=completion_day_context['text'],
                completion_day_analysis=json.dumps(completion_day_context['analysis_result'], ensure_ascii=False, indent=2),
                task_title=task_completion.task.title,
                task_description=task_completion.task.description,
                completion_text=task_completion.completion_text,
                feelings_text=task_completion.feelings_text
            )
            logger.debug(f"Промпт для анализа эффекта задания сформирован (длина: {len(prompt)} символов)")

            # === 4. Вызов DeepSeek API ===
            api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
            logger.debug(f"Ответ API от DeepSeek: success={api_result.get('success')}")

            # === 5. Обработка результата API ===
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"Ошибка API при анализе эффекта задания: {error_msg}")
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description=f"[Ошибка анализа API: {error_msg}]",
                    mood_impact_score=None,
                    comment="",
                    recommendation="",
                    detailed_analysis="",
                    api_response=api_result
                )
                return analysis

            # --- Парсинг результата ---
            parsed_result = api_result.get('result', {})
            logger.debug(f"Распарсенный результат от API: {parsed_result}")

            # Извлечение полей
            effect_desc = parsed_result.get('effect_description', 'Эффект задания проанализирован.')
            # mood_impact_score должно быть целым числом
            mood_impact_score_raw = parsed_result.get('mood_impact_score')
            mood_impact_score = None
            if mood_impact_score_raw is not None:
                try:
                    mood_impact_score = int(mood_impact_score_raw)
                    # Можно добавить проверку диапазона, если нужно, например: -10 до +10
                    # mood_impact_score = max(-10, min(10, mood_impact_score))
                except (ValueError, TypeError):
                    logger.warning(f"Некорректный формат mood_impact_score из API: {mood_impact_score_raw}")
                    mood_impact_score = None # Или значение по умолчанию, например 0

            comment_from_api = parsed_result.get('comment', '')
            recommendation_from_api = parsed_result.get('recommendation', '')
            detailed_analysis_from_api = parsed_result.get('detailed_analysis', '')

            # === 6. Обработка повторного выполнения ===
            # Помечаем предыдущие анализы как устаревшие
            @sync_to_async
            def _mark_previous_analyses_obsolete():
                from django.db import transaction
                with transaction.atomic():
                    TaskCompletionAnalysis.objects.filter(
                        completion__task=task_completion.task,
                        is_obsolete=False
                    ).update(is_obsolete=True)
                    logger.debug("Предыдущие анализы выполнения этого задания помечены как устаревшие.")

            try:
                await _mark_previous_analyses_obsolete()
            except Exception as obsolete_error:
                logger.error(f"Ошибка при пометке предыдущих анализов как устаревших: {obsolete_error}")

            # === 7. Создание/Сохранение результата анализа ===
            analysis_data = {
                'completion': task_completion,
                'effect_description': effect_desc,
                'mood_impact_score': mood_impact_score,
                'comment': comment_from_api,
                'recommendation': recommendation_from_api,
                'detailed_analysis': detailed_analysis_from_api,
                'is_obsolete': False, # Новый анализ актуален
                'api_response': api_result
            }

            # Создаем новый объект анализа
            @sync_to_async
            def _create_analysis():
                return TaskCompletionAnalysis.objects.create(**analysis_data)

            analysis = await _create_analysis()
            logger.info(f"Анализ эффекта выполнения задания ID {task_completion.task.id} успешно создан (ID {analysis.id}).")
            return analysis

        except Exception as e:
            logger.error(f"Критическая ошибка при анализе эффекта выполнения задания "
                        f"ID {task_completion.task.id}: {e}", exc_info=True)
            try:
                # Создаем запись об ошибке
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description=f"[Критическая ошибка сервера при анализе: {str(e)[:200]}]",
                    mood_impact_score=None,
                    comment="",
                    recommendation="",
                    detailed_analysis="",
                    api_response={'error': 'critical_exception', 'details': str(e)}
                )
                return analysis
            except Exception as inner_e:
                logger.error(f"Не удалось создать запись об ошибке анализа: {inner_e}")
            return None

    async def get_user_skipped_tasks(self, user: User, limit: int = 10) -> List[TherapyTask]:
        """
        Асинхронное получение пропущенных заданий пользователя.

        Args:
            user: Пользователь.
            limit: Лимит заданий.

        Returns:
            List[TherapyTask]: Список пропущенных заданий.
        """
        try:
            @sync_to_async
            def get_skipped_tasks_sync():
                skipped_tasks = list(
                    TherapyTask.objects.filter(
                        user=user,
                        status='skipped'
                    ).order_by('-completed_at')[:limit] # Сортируем по дате "завершения" (пропуска)
                )
                return skipped_tasks
            skipped_tasks = await get_skipped_tasks_sync()
            logger.debug(f"Получено {len(skipped_tasks)} пропущенных заданий для пользователя {user.telegram_id}")
            return skipped_tasks
        except Exception as e:
            logger.error(f"Ошибка при получении пропущенных заданий пользователя {user.telegram_id}: {e}")
            return []

    async def restore_task(self, task_id: int, user: User) -> bool:
        """
        Восстановление (перевод в статус 'pending') пропущенного задания.

        Args:
            task_id: ID задания.
            user: Пользователь.

        Returns:
            bool: Успешность операции.
        """
        try:
            @sync_to_async
            def restore_task_sync():
                with transaction.atomic():
                    try:
                        task = TherapyTask.objects.select_for_update().get(
                            id=task_id,
                            user=user,
                            status='skipped' # Только пропущенные можно восстановить
                        )
                        task.status = 'pending'
                        # Сбрасываем completed_at, так как задание снова активно
                        task.completed_at = None 
                        task.save(update_fields=['status', 'completed_at'])
                        logger.info(f"Задание {task_id} восстановлено для пользователя {user.telegram_id}")
                        return True
                    except TherapyTask.DoesNotExist:
                        logger.warning(f"Задание {task_id} не найдено, не принадлежит пользователю {user.telegram_id} или не пропущено")
                        return False
            success = await restore_task_sync()
            return success
        except Exception as e:
            logger.error(f"Ошибка при восстановлении задания {task_id} для пользователя {user.telegram_id}: {e}")
            return False

task_service = TaskService()


async def assign_task(
    user: User, 
    title: str, 
    description: str, 
    task_type: str = 'daily',
    priority: int = 1,
    related_entry: DiaryEntry = None
) -> TherapyTask:
    """Удобная функция для назначения задания"""
    return await task_service.assign_task(user, title, description, task_type, priority, related_entry)

async def get_user_active_tasks(user: User) -> List[TherapyTask]:
    """Удобная функция для получения активных заданий"""
    return await task_service.get_user_active_tasks(user)

async def get_user_completed_tasks(user: User, limit: int = 10) -> List[TherapyTask]:
    """Удобная функция для получения выполненных заданий"""
    return await task_service.get_user_completed_tasks(user, limit)

async def complete_task(
    task_id: int, 
    user: User, 
    completion_text: str, 
    feelings_text: str
) -> Optional[TaskCompletion]:
    """Удобная функция для выполнения задания"""
    return await task_service.complete_task(task_id, user, completion_text, feelings_text)

async def skip_task(task_id: int, user: User) -> bool:
    """Удобная функция для пропуска задания"""
    return await task_service.skip_task(task_id, user)

async def delete_task(task_id: int, user: User) -> bool:
    """Удобная функция для удаления задания"""
    return await task_service.delete_task(task_id, user)

async def get_user_skipped_tasks(user: User, limit: int = 10) -> List[TherapyTask]:
    """Удобная функция для получения пропущенных заданий."""
    return await task_service.get_user_skipped_tasks(user, limit)

# Удобная функция для восстановления задания
async def restore_task(task_id: int, user: User) -> bool:
    """Удобная функция для восстановления пропущенного задания."""
    return await task_service.restore_task(task_id, user)
