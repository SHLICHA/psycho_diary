"""
Сервис для работы с терапевтическими заданиями
"""

import asyncio
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Q
from asgiref.sync import sync_to_async
from aiogram.types import Message

from diary.services.daily_state_service import daily_state_service
from diary.models import DiaryEntry, TherapyTask, TaskCompletion, TaskAnalysis, TaskCompletionAnalysis, KeyPoint
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
        Возвращает словарь с результатами или None.
        """
        try:
            @sync_to_async
            def complete_task_sync():
                with transaction.atomic():
                    try:
                        task = TherapyTask.objects.select_related('related_entry').get(
                            id=task_id,
                            user=user,
                            status__in=['pending', 'in_progress']
                        )
                    except TherapyTask.DoesNotExist:
                        logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                        raise ValueError("Задание не найдено или не принадлежит вам")
                    task_completion = TaskCompletion.objects.create(
                        task=task,
                        completion_text=completion_text,
                        feelings_text=feelings_text,
                        time_spent=5
                    )
                    task.status = 'completed'
                    task.completed_at = datetime.now()
                    task.save(update_fields=['status', 'completed_at'])
                    task_analysis = TaskAnalysis.objects.create(
                        completion=task_completion,
                        bot_response="Отличная работа! Выполнил задание честно и подробно.",
                        insights_updated=True,
                        quality_score=8,
                        feedback_given=True
                    )
                return task_completion, task_analysis

            task_completion, task_analysis = await complete_task_sync()
            asyncio.create_task(self._run_analysis_and_notify_user(task_completion, user, status_message))
            return {
                'task_completion': task_completion,
                'task_analysis': task_analysis,
                'effect_analysis_started': True
            }
        except Exception as e:
            return None

    async def _run_analysis_and_notify_user(self, task_completion: TaskCompletion, user: User, status_message: Optional[Message] = None):
        """
        Асинхронная задача для запуска анализа эффекта и уведомления пользователя.
        Выполняется отдельно от основного потока обработки.
        Если передан status_message, результат будет отредактирован в нем.
        Иначе будет отправлено новое сообщение.
        """
        try:
            from bot.main import bot as global_bot
            effect_analysis = await self.analyze_task_completion_effect(task_completion, user)
            try:
                target_chat_id = user.telegram_id
                target_message_id = None
                use_edit = False
                if status_message:
                    target_chat_id = status_message.chat.id
                    target_message_id = status_message.message_id
                    use_edit = True
                if effect_analysis:
                    from messages import get_message
                    language = user.language
                    effect_description = effect_analysis.effect_description
                    mood_impact_score = effect_analysis.mood_impact_score if effect_analysis.mood_impact_score is not None else "N/A"
                    comment_for_user = effect_analysis.comment if effect_analysis.comment else "Нет комментария"
                    recommendation_for_user = effect_analysis.recommendation if effect_analysis.recommendation else "Нет рекомендации"
                    effect_msg = get_message(
                        'task_effect_analysis_result',
                        language,
                        effect_description=effect_description,
                        mood_impact=mood_impact_score,
                        comment=comment_for_user,
                        recommendation=recommendation_for_user
                    )
                    reply_markup = get_back_keyboard(language)
                    if use_edit:
                        try:
                            await safe_edit_message_text(
                                message=status_message,
                                text=effect_msg,
                                reply_markup=reply_markup
                            )
                        except Exception as edit_error:
                            logger.warning(f"[Асинхронная задача] Не удалось отредактировать сообщение: {edit_error}. Отправляем новое.")
                            await global_bot.send_message(chat_id=target_chat_id, text=effect_msg, reply_markup=reply_markup)
                    else:
                        await global_bot.send_message(chat_id=target_chat_id, text=effect_msg, reply_markup=reply_markup)
                else:
                    error_msg = get_message('error_processing', user.language)
                    error_reply_markup = get_back_keyboard(user.language) 
                    if use_edit:
                        try:
                            await safe_edit_message_text(
                                message=status_message,
                                text=error_msg,
                                reply_markup=error_reply_markup
                            )
                        except Exception as edit_error:
                            logger.warning(f"[Асинхронная задача] Не удалось отредактировать сообщение об ошибке: {edit_error}. Отправляем новое.")
                            if global_bot:
                                await global_bot.send_message(chat_id=target_chat_id, text=error_msg, reply_markup=error_reply_markup)
                            else:
                                logger.error("[Асинхронная задача] Глобальный бот не найден для отправки сообщения об ошибке.")
                    else:
                        await global_bot.send_message(chat_id=target_chat_id, text=error_msg, reply_markup=error_reply_markup)
            except Exception as notify_error:
                logger.error(f"[Асинхронная задача] Ошибка отправки/редактирования сообщения об эффекте пользователю {user.telegram_id}: {notify_error}")
        except Exception as task_error:
            logger.error(f"[Асинхронная задача] Критическая ошибка в _run_analysis_and_notify_user: {task_error}")
    
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
                    if hasattr(task, 'completion'):
                        try:
                            completion = TaskCompletion.objects.get(task=task)
                            if hasattr(completion, 'analysis'):
                                try:
                                    analysis = TaskAnalysis.objects.get(completion=completion)
                                    analysis.delete()
                                except TaskAnalysis.DoesNotExist:
                                    pass
                            completion.delete()
                        except TaskCompletion.DoesNotExist:
                            pass
                    task.delete()
                return True
            success = await delete_task_sync()
            return success
        except Exception as e:
            logger.error(f"Ошибка при удалении задания: {e}")
            return False
    
    async def analyze_task_completion_effect(
        self,
        task_completion: TaskCompletion,
        user: User
    ) -> Optional[TaskCompletionAnalysis]:
        """
        Асинхронно анализирует влияние выполнения задания на эмоциональное состояние дня.
        Вызывается после успешного выполнения задания.
        """
        try:
            related_entry = task_completion.task.related_entry
            if not related_entry:
                logger.warning(f"Задание {task_completion.task.id} не связано с записью дневника. "
                               f"Анализ эффекта пропущен.")
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description="[Данные недоступны: Задание не связано с записью дневника.]",
                    mood_impact_score=None,
                    key_points_before={},
                    key_points_after={},
                    api_response={"error": "No related entry"}
                )
                return analysis
            entry_date = await related_entry.aentry_date()
            combined_entry = await daily_state_service.get_daily_state(user, entry_date)
            if not combined_entry:
                logger.warning(f"CombinedDiaryEntry для {entry_date} не найден. Анализ эффекта ограничен.")
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description="[Данные недоступны: CombinedDiaryEntry не найден.]",
                    mood_impact_score=None,
                    key_points_before={},
                    key_points_after={},
                    api_response={"error": "CombinedDiaryEntry not found"}
                )
                return analysis
            key_points_before_data = {}
            try:
                @sync_to_async
                def _get_key_points_before_sync():
                    user_tz_str = user.timezone if user.timezone else 'UTC'
                    import pytz
                    user_tz = pytz.timezone(user_tz_str)
                    start_of_day_local = datetime.combine(entry_date, datetime.min.time())
                    start_of_day_user_tz = user_tz.localize(start_of_day_local)
                    start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
                    end_of_day_local = datetime.combine(entry_date, datetime.max.time())
                    end_of_day_user_tz = user_tz.localize(end_of_day_local)
                    end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)

                    kps = KeyPoint.objects.filter(
                        entry__user=user,
                        entry__created_at__gte=start_of_day_utc,
                        entry__created_at__lte=task_completion.created_at
                    ).select_related('entry')
                    points_dict = {}
                    for kp in kps:
                        if kp.type not in points_dict:
                            points_dict[kp.type] = []
                        points_dict[kp.type].append({
                            'text': kp.text,
                            'confidence': kp.confidence
                        })
                    return points_dict
                key_points_before_data = await _get_key_points_before_sync()
            except Exception as kp_error:
                logger.error(f"Ошибка при получении ключевых моментов 'до': {kp_error}")
                key_points_before_data = {}
            user_profile_data = {
                'username': user.username or f"user_{user.telegram_id}",
                'first_name': user.first_name or "",
                'awareness_level': user.awareness_level,
                'is_premium': user.is_premium,
            }
            day_text = combined_entry.text
            avg_mood_before = combined_entry.average_mood_score
            completion_text = task_completion.completion_text
            feelings_text = task_completion.feelings_text
            task_title = task_completion.task.title
            task_description = task_completion.task.description
            prompt = await self._generate_task_effect_prompt(
                user_profile_data, day_text, avg_mood_before,
                task_title, task_description,
                completion_text, feelings_text,
                key_points_before_data,
                user.language
            )
            api_result = await deepseek_api_service.analyze_text(prompt, language=user.language, analysis_type='default')
            if not api_result.get('success'):
                logger.error(f"Ошибка API при анализе эффекта задания: {api_result.get('error')}")
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description=f"[Ошибка анализа API: {api_result.get('error', 'Неизвестная ошибка API')}]",
                    mood_impact_score=None,
                    key_points_before=key_points_before_data,
                    key_points_after={},
                    api_response=api_result
                )
                return analysis
            parsed_result = api_result.get('result', {})
            effect_desc = parsed_result.get('analysis', 'Эффект задания проанализирован.')
            mood_score_from_api = parsed_result.get('mood_score')
            comment_from_api = parsed_result.get('comment', '')
            recommendation_from_api = parsed_result.get('recommendation', '')
            key_points_after_data = parsed_result.get('key_points', [])
            user_insights_data = parsed_result.get('user_insights', [])
            mood_impact_score = parsed_result.get('mood_impact_score')
            if mood_impact_score is not None:
                try:
                    mood_impact_score = int(mood_impact_score)
                except (ValueError, TypeError):
                    logger.warning(f"Некорректный формат mood_impact_score: {mood_impact_score}")
                    mood_impact_score = None
            else:
                if mood_score_from_api is not None and avg_mood_before is not None:
                    try:
                        mood_impact_score = int(mood_score_from_api) - int(avg_mood_before)
                    except (ValueError, TypeError):
                        logger.warning(f"Невозможно вычислить mood_impact_score: API={mood_score_from_api}, До={avg_mood_before}")
                        mood_impact_score = None
                else:
                    mood_impact_score = None
            analysis_data = {
                'completion': task_completion,
                'effect_description': effect_desc,
                'mood_impact_score': mood_impact_score,
                'comment': comment_from_api,
                'recommendation': recommendation_from_api,
                'key_points_before': key_points_before_data,
                'key_points_after': key_points_after_data,
                'api_response': api_result
            }
            analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(**analysis_data)
            return analysis
        except Exception as e:
            logger.error(f"Критическая ошибка при анализе эффекта выполнения задания "
                         f"ID {task_completion.task.id}: {e}", exc_info=True)
            try:
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description=f"[Критическая ошибка сервера при анализе: {str(e)[:200]}]",
                    mood_impact_score=None,
                    key_points_before={},
                    key_points_after={},
                    api_response={'error': 'critical_exception', 'details': str(e)}
                )
                return analysis
            except Exception as inner_e:
                logger.error(f"Не удалось создать запись об ошибке анализа: {inner_e}")
            return None

    # TODO Вынести промпт в prompts.py
    async def _generate_task_effect_prompt(
        self,
        user_profile: dict,
        day_text: str,
        avg_mood_before: float,
        task_title: str,
        task_description: str,
        completion_text: str,
        feelings_text: str,
        key_points_before: dict,
        language: str
    ) -> str:
        """
        Генерирует промпт для анализа влияния выполнения задания.
        """
        if language == 'ru':
            prompt = (
                "Проанализируй влияние выполнения терапевтического задания на эмоциональное состояние пользователя за день.\n"
                "Ответь в формате JSON, строго придерживаясь структуры, заключенной в тройные обратные кавычки с указанием json (```json ... ```).\n\n"
                "Контекст:\n"
                f"Профиль пользователя:\n{json.dumps(user_profile, ensure_ascii=False, indent=2)}\n\n"
                f"Текст всех записей пользователя за день:\n{day_text}\n\n"
                f"Средняя оценка настроения до выполнения задания: {avg_mood_before}/10\n\n"
                f"Ключевые моменты дня до выполнения задания:\n{json.dumps(key_points_before, ensure_ascii=False, indent=2)}\n\n"
                "Выполненное задание:\n"
                f"Название: {task_title}\n"
                f"Описание: {task_description}\n\n"
                "Ответ пользователя на задание:\n"
                f"Выполнение: {completion_text}\n"
                f"Ощущения: {feelings_text}\n\n"
                "Проанализируй, как выполнение задания повлияло на эмоциональное состояние, описанное в записях дня.\n"
                "Сравни содержание записей, выполнение и ощущения.\n"
                "Сформулируй краткий вывод об эффекте.\n"
                "Оцени, на сколько баллов (целое число) это могло повлиять на среднюю оценку дня (может быть отрицательным).\n"
                "Если влияние неочевидно или нейтрально, укажи это и поставь значение 0.\n\n"
                "Пример структуры ответа:\n"
                "```json\n"
                "{\n"
                "  \"effect_description\": \"Выполнение задания коррелирует с упоминанием позитивных событий и улучшением настроения.\",\n"
                "  \"mood_impact_score\": 2\n"
                "}\n"
                "```\n\n"
                "Требуемый формат ответа:\n"
                "```json\n"
                "{\n"
                "  \"effect_description\": \"строка, краткое описание эффекта (1-2 предложения)\",\n"
                "  \"mood_impact_score\": целое число (оценка влияния на настроение дня, может быть отрицательным)\n"
                "}\n"
                "```\n"
            )
        else:
            prompt = (
                "Analyze the impact of completing a therapeutic task on the user's emotional state for the day.\n"
                "Respond in JSON format, strictly adhering to the structure enclosed in triple backticks (```json ... ```).\n\n"
                "Context:\n"
                f"User Profile:\n{json.dumps(user_profile, ensure_ascii=False, indent=2)}\n\n"
                f"Text of all user's entries for the day:\n{day_text}\n\n"
                f"Average mood score before completing the task: {avg_mood_before}/10\n\n"
                f"Key points of the day before completing the task:\n{json.dumps(key_points_before, ensure_ascii=False, indent=2)}\n\n"
                "Completed Task:\n"
                f"Title: {task_title}\n"
                f"Description: {task_description}\n\n"
                "User's response to the task:\n"
                f"Completion: {completion_text}\n"
                f"Feelings: {feelings_text}\n\n"
                "Analyze how completing the task influenced the emotional state described in the day's entries.\n"
                "Compare the content of the entries, the completion, and the feelings.\n"
                "Formulate a brief conclusion about the effect.\n"
                "Estimate by how many points (integer) this could have affected the average daily score (can be negative).\n"
                "If the impact is unclear or neutral, state so and put a value of 0.\n\n"
                "Example response structure:\n"
                "```json\n"
                "{\n"
                "  \"effect_description\": \"Completing the task correlates with mentioning positive events and improved mood.\",\n"
                "  \"mood_impact_score\": 2\n"
                "}\n"
                "```\n\n"
                "Required response format:\n"
                "```json\n"
                "{\n"
                "  \"effect_description\": \"string, a brief description of the effect (1-2 sentences)\",\n"
                "  \"mood_impact_score\": integer (estimated impact on the day's mood score, can be negative)\n"
                "}\n"
                "```\n"
            )

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