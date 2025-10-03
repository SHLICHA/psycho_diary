"""
Сервис для работы с терапевтическими заданиями
"""

import asyncio
import logging
import json
import pytz

from typing import List, Dict, Any, Optional
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from asgiref.sync import sync_to_async
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from prompts.get_prompt import get_prompt
from messages import get_message
from diary.services import daily_state_service
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
        complexity: str = 'medium',
        related_entry: DiaryEntry = None
    ) -> TherapyTask:
        """
        Назначение терапевтического задания пользователю
        
        Args:
            user: Пользователь
            title: Название задания
            description: Описание задания
            task_type: Тип задания
            complexity: Сложность задания
            
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
                        complexity=complexity,
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
                        status='completed'
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
        Выполнение задания с учетом часового пояса пользователя.
        """
        logger.debug(f"Начало выполнения задания ID: {task_id} для пользователя {user.telegram_id}")
        try:
            user_local_time = await user.aget_local_datetime_now()
            @sync_to_async
            def complete_task_sync():
                with transaction.atomic():
                    try:
                        task = TherapyTask.objects.select_related('related_entry', 'completion').get(
                            id=task_id,
                            user=user,
                            status__in=['pending', 'in_progress', 'completed']
                        )
                    except TherapyTask.DoesNotExist:
                        logger.warning(f"[SYNC] Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                        raise ValueError("Задание не найдено или не принадлежит вам")
                    
                    task_completion = None
                    if hasattr(task, 'completion'):
                        task_completion = task.completion
                        task_completion.completion_text = completion_text
                        task_completion.feelings_text = feelings_text
                        task_completion.save(update_fields=['completion_text', 'feelings_text'])             
                    else:
                        logger.debug(f"[SYNC] Создание нового TaskCompletion для задания {task_id}")
                        task_completion = TaskCompletion.objects.create(
                            task=task,
                            completion_text=completion_text,
                            feelings_text=feelings_text,
                            created_at=user_local_time
                        )
                        logger.debug(f"[SYNC] TaskCompletion создан: ID {task_completion.id}")
                    
                    old_status = task.status
                    task.status = 'completed'
                    if old_status != 'completed': 
                        task.completed_at = user_local_time
                    task.save(update_fields=['status', 'completed_at'])
                    task_analysis = None   
                return task_completion, task_analysis
            task_completion, task_analysis = await complete_task_sync()
            asyncio.create_task(self._run_analysis_and_notify_user(task_completion, user, status_message))
            result = {
                'task_completion': task_completion,
                'task_analysis': task_analysis,
                'effect_analysis_started': True
            }
            logger.debug(f"Функция complete_task возвращает результат: {result}")
            return result 
        except ValueError as ve:
            logger.warning(f"Ожидаемая ошибка в complete_task для задания {task_id}: {ve}")
            return None
        except Exception as e:
            logger.error(f"Критическая ошибка в complete_task для задания {task_id}: {e}", exc_info=True)
            return None

    async def _run_analysis_and_notify_user(self, task_completion: TaskCompletion, user: User, status_message: Optional[Message] = None):
        """
        Асинхронная задача для запуска анализа эффекта и уведомления пользователя.
        """
        try:
            from bot.main import bot as global_bot
            analysis_result = await self.analyze_task_completion_effect(task_completion, user)
            target_chat_id = user.telegram_id
            use_edit = False
            message_to_edit = None
            
            if status_message:
                target_chat_id = status_message.chat.id
                use_edit = True
                message_to_edit = status_message
            if isinstance(analysis_result, dict) and analysis_result.get('invalid'):
                validation_comment = analysis_result.get('validation_comment', 'Выполнение задания не засчитано из-за недостаточной содержательности.')
                language = user.language
                final_message = get_message(
                    'task_completion_invalid_formatted', 
                    language, 
                    validation_comment=validation_comment
                )
                buttons = [
                    [
                        InlineKeyboardButton(
                            text=get_message('btn_try_again', language),
                            callback_data=f"complete_task:{task_completion.task.id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=get_message('btn_skip_task', language),
                            callback_data=f"skip_task:{task_completion.task.id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=get_message('btn_back', language),
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
                    final_message = formatted_message
                else:
                    effect_description = analysis_result.effect_description or get_message('no_effect_description', language)
                    mood_impact_score_raw = analysis_result.mood_impact_score
                    if mood_impact_score_raw is not None:
                        try:
                            mood_impact_score = int(mood_impact_score_raw)
                            if mood_impact_score > 0:
                                mood_impact_display = f"+{mood_impact_score}"
                            else:
                                mood_impact_display = str(mood_impact_score)
                        except (ValueError, TypeError):
                            mood_impact_display = "N/A"
                    else:
                        mood_impact_display = "N/A"   
                    comment_for_user = analysis_result.comment or get_message('no_comment', language)
                    recommendation_for_user = analysis_result.recommendation or get_message('no_recommendation', language)
                    final_message = get_message(
                        'task_effect_analysis_result_formatted',
                        language,
                        effect_description=effect_description,
                        mood_impact=mood_impact_display,
                        comment=comment_for_user,
                        recommendation=recommendation_for_user
                    )
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
                    if global_bot:
                        await global_bot.send_message(
                            chat_id=target_chat_id, 
                            text=final_message, 
                            reply_markup=reply_markup
                        )
            else:
                if global_bot:
                    await global_bot.send_message(
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
                if status_message and global_bot:
                    try:
                        await safe_edit_message_text(
                            message=status_message,
                            text=final_message,
                            reply_markup=error_reply_markup
                        )
                    except:
                        try:
                            await global_bot.send_message(
                                chat_id=status_message.chat.id,
                                text=final_message,
                                reply_markup=error_reply_markup
                            )
                        except:
                            pass
                elif global_bot and 'user' in locals():
                    await global_bot.send_message(
                        chat_id=user.telegram_id, 
                        text=final_message, 
                        reply_markup=error_reply_markup
                    )
            except:
                pass
    
    async def skip_task(self, task_id: int, user: User) -> bool:
        """
        Пропуск задания с учетом часового пояса пользователя.
        """
        try:
            user_local_time = await user.aget_local_datetime_now()
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
                    task.completed_at = user_local_time
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
                    if hasattr(task, 'completion'):
                        try:
                            completion = TaskCompletion.objects.get(task=task)
                            completion.delete()
                            logger.debug(f"[SYNC] TaskCompletion для задания {task_id} удален.")
                        except TaskCompletion.DoesNotExist:
                            logger.debug(f"[SYNC] TaskCompletion для задания {task_id} не найден при удалении.")
                    task.delete()
                    logger.debug(f"[SYNC] Задание ID {task_id} удалено.")
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
        try:
            related_entry = task_completion.task.related_entry
            completion_date = task_completion.created_at.date()
            assigned_combined_entry = None
            assigned_date_str = "N/A"
            if related_entry:
                assigned_date = await related_entry.aentry_date()
                assigned_date_str = assigned_date.isoformat()
                assigned_combined_entry = await daily_state_service.get_daily_state(user, assigned_date)
            else:
                logger.warning(f"Задание {task_completion.task.id} не связано с записью дневника.")
            completion_combined_entry = await daily_state_service.get_daily_state(user, completion_date)
            if not completion_combined_entry:
                logger.warning(f"CombinedDiaryEntry для дня выполнения ({completion_date}) не найден. "
                            f"Анализ будет выполнен без данных дня выполнения.")
                completion_combined_entry = None
            assigned_day_context = {
                "text": assigned_combined_entry.text if assigned_combined_entry else "",
                "analysis_result": assigned_combined_entry.analysis_result if assigned_combined_entry else {}
            }
            completion_day_context = {
                "text": completion_combined_entry.text if completion_combined_entry else "",
                "analysis_result": completion_combined_entry.analysis_result if completion_combined_entry else {}
            }
            user_profile_data = {
                'username': user.username or f"user_{user.telegram_id}",
                'first_name': user.first_name or "",
                'awareness_level': user.awareness_level,
                'personality_traits': user.personality_traits,
                'life_facts': user.life_facts,
                'hobbies': user.hobbies,
                'core_values': user.core_values,
                'triggers': user.triggers,
                'strengths': user.strengths,
                'areas_for_growth': user.areas_for_growth,
            }
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
                task_complexity=task_completion.task.complexity,
                completion_text=task_completion.completion_text,
                feelings_text=task_completion.feelings_text
            )
            api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
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
            parsed_result = api_result.get('result', {})
            is_valid = parsed_result.get('is_valid', True)
            if not is_valid:
                validation_comment = parsed_result.get('validation_comment', 'Выполнение задания признано недействительным.')
                logger.warning(f"Выполнение задания {task_completion.task.id} признано недействительным: {validation_comment}")
                task = task_completion.task
                task.status = 'pending'
                task.completed_at = None
                await sync_to_async(task.save)(update_fields=['status', 'completed_at'])
                await sync_to_async(task_completion.delete)()
                return {
                    'invalid': True,
                    'validation_comment': validation_comment
                }
            effect_desc = parsed_result.get('effect_description', 'Эффект задания проанализирован.')
            mood_impact_score_raw = parsed_result.get('mood_impact_score')
            effect_desc = parsed_result.get('effect_description', 'Эффект задания проанализирован.')
            mood_impact_score_raw = parsed_result.get('mood_impact_score')
            mood_impact_score = None
            if mood_impact_score_raw is not None:
                try:
                    mood_impact_score = int(mood_impact_score_raw)
                except (ValueError, TypeError):
                    logger.warning(f"Некорректный формат mood_impact_score из API: {mood_impact_score_raw}")
                    mood_impact_score = None
            comment_from_api = parsed_result.get('comment', '')
            recommendation_from_api = parsed_result.get('recommendation', '')
            detailed_analysis_from_api = parsed_result.get('detailed_analysis', '')
            @sync_to_async
            def _mark_previous_analyses_obsolete():
                with transaction.atomic():
                    TaskCompletionAnalysis.objects.filter(
                        completion__task=task_completion.task,
                        is_obsolete=False
                    ).update(is_obsolete=True)

            try:
                await _mark_previous_analyses_obsolete()
            except Exception as obsolete_error:
                logger.error(f"Ошибка при пометке предыдущих анализов как устаревших: {obsolete_error}")
            analysis_data = {
                'completion': task_completion,
                'effect_description': effect_desc,
                'mood_impact_score': mood_impact_score,
                'comment': comment_from_api,
                'recommendation': recommendation_from_api,
                'detailed_analysis': detailed_analysis_from_api,
                'is_obsolete': False,
                'api_response': api_result
            }
            @sync_to_async
            def _create_analysis():
                return TaskCompletionAnalysis.objects.create(**analysis_data)
            analysis = await _create_analysis()
            logger.debug(f"Анализ эффекта задания {task_completion.task.id} успешно создан: ID {analysis.id}")
            return analysis
        except Exception as e:
            logger.error(f"Критическая ошибка при анализе эффекта выполнения задания "
                        f"ID {task_completion.task.id}: {e}", exc_info=True)
            try:
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
                    ).order_by('-completed_at')[:limit]
                )
                return skipped_tasks
            skipped_tasks = await get_skipped_tasks_sync()
            return skipped_tasks
        except Exception as e:
            logger.error(f"Ошибка при получении пропущенных заданий пользователя {user.telegram_id}: {e}")
            return []

    async def restore_task(self, task_id: int, user: User) -> bool:
        """
        Восстановление пропущенного задания.
        """
        try:
            @sync_to_async
            def restore_task_sync():
                with transaction.atomic():
                    try:
                        task = TherapyTask.objects.select_for_update().get(
                            id=task_id,
                            user=user,
                            status='skipped'
                        )
                        task.status = 'pending'
                        task.completed_at = None
                        task.save(update_fields=['status', 'completed_at'])
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
    complexity: str = 'medium',
    related_entry: DiaryEntry = None
) -> TherapyTask:
    """Удобная функция для назначения задания"""
    return await task_service.assign_task(user, title, description, task_type, complexity, related_entry)

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

async def restore_task(task_id: int, user: User) -> bool:
    """Удобная функция для восстановления пропущенного задания."""
    return await task_service.restore_task(task_id, user)
