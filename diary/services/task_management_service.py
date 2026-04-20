# /diary/services/task_management_service.py
"""
Сервис для управления терапевтическими заданиями.
Выносит бизнес-логику из хендлеров Telegram и bot.services.
"""

import asyncio
import logging
import json

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from asgiref.sync import sync_to_async
import pytz

from diary.models import DiaryEntry, TherapyTask, TaskCompletion, TaskCompletionAnalysis
from users.models import User, TokenTransaction
from diary.services.daily_state_service import daily_state_service
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from messages import get_message
from core.profile_field_utils import build_personal_fields_payload_for_ai
from diary.services.compressed_profile_service import compressed_profile_service

logger = logging.getLogger(__name__)

class TaskManagementService:
    """Сервис для работы с терапевтическими заданиями."""

    @classmethod
    async def assign_task(
        cls,
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
                    expires_at = timezone.now() + timedelta(days=7)
                    therapy_task = TherapyTask.objects.create(
                        user=user,
                        title=title,
                        description=description,
                        type=task_type,
                        complexity=complexity,
                        status='pending',
                        related_entry=related_entry,
                        expires_at=expires_at
                    )
                    return therapy_task
            therapy_task = await create_task_sync()
            return therapy_task
        except Exception as e:
            logger.error(f"[TaskManagementService] Ошибка при назначении задания: {e}")
            raise

    @classmethod
    async def get_user_active_tasks(
        cls,
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
            logger.error(f"[TaskManagementService] Ошибка при получении активных заданий: {e}")
            return []

    @classmethod
    async def get_user_completed_tasks(
        cls,
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
            logger.error(f"[TaskManagementService] Ошибка при получении выполненных заданий: {e}")
            return []

    @classmethod
    async def complete_task(
        cls,
        task_id: int,
        user: User,
        completion_text: str,
        feelings_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Выполнение задания с учетом часового пояса пользователя.
        Возвращает результат, но *не запускает* анализ и уведомления.
        """
        logger.debug(f"[TaskManagementService] Начало выполнения задания ID: {task_id} для пользователя {user.telegram_id}")
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
                    # Возвращаем task_completion, task_analysis будет отдельно
                return task_completion
            task_completion = await complete_task_sync()
            # Возврат информации о завершении, *без* запуска анализа
            result = {
                'task_completion': task_completion,
                'success': True
            }
            logger.debug(f"[TaskManagementService] Функция complete_task возвращает результат: {result}")
            return result
        except ValueError as ve:
            logger.warning(f"[TaskManagementService] Ожидаемая ошибка в complete_task для задания {task_id}: {ve}")
            return {'success': False, 'error': str(ve)}
        except Exception as e:
            logger.error(f"[TaskManagementService] Критическая ошибка в complete_task для задания {task_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def skip_task(cls, task_id: int, user: User) -> bool:
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
            logger.error(f"[TaskManagementService] Ошибка при пропуске задания: {e}")
            return False

    @classmethod
    async def delete_task(
        cls,
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
            logger.error(f"[TaskManagementService] Ошибка при удалении задания ID {task_id}: {e}")
            return False

    @classmethod
    async def analyze_task_completion_effect(
        cls,
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
            personal_fields_payload = build_personal_fields_payload_for_ai(user)
            compressed_profile = user.compressed_psych_profile or {}
            if not compressed_profile:
                generated_profile = compressed_profile_service.generate_for_user(user)
                compressed_profile = generated_profile or {}

            compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, indent=2)
            personal_fields_json = json.dumps(personal_fields_payload, ensure_ascii=False, indent=2)

            prompt = get_prompt(
                'task_effect_analysis',
                language=user.language,
                compressed_psych_profile_json=compressed_profile_json,
                personal_fields_json=personal_fields_json,
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
                    tokens_awarded=0,
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
            tokens_awarded_raw = parsed_result.get('tokens_awarded', 0)
            try:
                tokens_awarded = int(tokens_awarded_raw)
                if not (0 <= tokens_awarded <= 3):
                    logger.warning(f"Некорректное количество токенов из API: {tokens_awarded_raw}. Используем 0.")
                    tokens_awarded = 0
            except (ValueError, TypeError):
                logger.warning(f"Некорректный формат tokens_awarded из API: {tokens_awarded_raw}. Используем 0.")
                tokens_awarded = 0
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
                'tokens_awarded': tokens_awarded,
                'is_obsolete': False,
                'api_response': api_result
            }
            @sync_to_async
            def _create_analysis():
                return TaskCompletionAnalysis.objects.create(**analysis_data)
            analysis = await _create_analysis()
            if tokens_awarded > 0:
                await sync_to_async(TokenTransaction.create_and_update_balance)(
                    user=user,
                    amount=tokens_awarded,
                    transaction_type='task_completion',
                    description=f"Начисление за выполнение задания '{task_completion.task.title}'",
                    related_task_completion=task_completion
                )
                logger.debug(f"Пользователю {user.telegram_id} начислено {tokens_awarded} токенов за выполнение задания {task_completion.task.id} через TokenTransaction.create_and_update_balance.")
            logger.debug(f"[TaskManagementService] Анализ эффекта задания {task_completion.task.id} успешно создан: ID {analysis.id}")
            return analysis
        except Exception as e:
            logger.error(f"[TaskManagementService] Критическая ошибка при анализе эффекта выполнения задания "
                        f"ID {task_completion.task.id}: {e}", exc_info=True)
            try:
                analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
                    completion=task_completion,
                    effect_description=f"[Критическая ошибка сервера при анализе: {str(e)[:200]}]",
                    mood_impact_score=None,
                    comment="",
                    recommendation="",
                    detailed_analysis="",
                    tokens_awarded=0,
                    api_response={'error': 'critical_exception', 'details': str(e)}
                )
                return analysis
            except Exception as inner_e:
                logger.error(f"[TaskManagementService] Не удалось создать запись об ошибке анализа: {inner_e}")
            return None

    @classmethod
    async def get_user_skipped_tasks(cls, user: User, limit: int = 10) -> List[TherapyTask]:
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
            logger.error(f"[TaskManagementService] Ошибка при получении пропущенных заданий пользователя {user.telegram_id}: {e}")
            return []

    @classmethod
    async def restore_task(cls, task_id: int, user: User) -> bool:
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
            logger.error(f"[TaskManagementService] Ошибка при восстановлении задания {task_id} для пользователя {user.telegram_id}: {e}")
            return False

    @classmethod
    async def get_uncompleted_tasks_count_for_user(cls, user: User) -> int:
        """
        Подсчитывает количество незавершенных задач для пользователя (статус 'pending').

        Args:
            user: Объект пользователя Django.

        Returns:
            int: Количество незавершенных задач.
        """
        try:
            @sync_to_async
            def count_tasks_sync():
                return TherapyTask.objects.filter(
                    user=user,
                    status='pending'
                ).count()
            count = await count_tasks_sync()
            return count
        except Exception as e:
            logger.error(f"[TaskManagementService] Ошибка при подсчете незавершенных задач пользователя {user.telegram_id}: {e}", exc_info=True)
            return 0 # Возвращаем 0 в случае ошибки

# Удобные функции для импорта в хендлеры
async def get_uncompleted_tasks_count_for_user(user: User) -> int:
    """Удобная функция для получения количества незавершенных задач."""
    return await TaskManagementService.get_uncompleted_tasks_count_for_user(user)

async def assign_task(
    user: User,
    title: str,
    description: str,
    task_type: str = 'daily',
    complexity: str = 'medium',
    related_entry: DiaryEntry = None
) -> TherapyTask:
    """Удобная функция для назначения задания"""
    return await TaskManagementService.assign_task(user, title, description, task_type, complexity, related_entry)

async def get_user_active_tasks(user: User) -> List[TherapyTask]:
    """Удобная функция для получения активных заданий"""
    return await TaskManagementService.get_user_active_tasks(user)

async def get_user_completed_tasks(user: User, limit: int = 10) -> List[TherapyTask]:
    """Удобная функция для получения выполненных заданий"""
    return await TaskManagementService.get_user_completed_tasks(user, limit)

async def complete_task(
    task_id: int,
    user: User,
    completion_text: str,
    feelings_text: str,
) -> Optional[Dict[str, Any]]:
    """Удобная функция для выполнения задания"""
    return await TaskManagementService.complete_task(task_id, user, completion_text, feelings_text)

async def skip_task(task_id: int, user: User) -> bool:
    """Удобная функция для пропуска задания"""
    return await TaskManagementService.skip_task(task_id, user)

async def delete_task(task_id: int, user: User) -> bool:
    """Удобная функция для удаления задания"""
    return await TaskManagementService.delete_task(task_id, user)

async def get_user_skipped_tasks(user: User, limit: int = 10) -> List[TherapyTask]:
    """Удобная функция для получения пропущенных заданий."""
    return await TaskManagementService.get_user_skipped_tasks(user, limit)

async def restore_task(task_id: int, user: User) -> bool:
    """Удобная функция для восстановления пропущенного задания."""
    return await TaskManagementService.restore_task(task_id, user)

async def analyze_task_completion_effect(
    task_completion: TaskCompletion,
    user: User
) -> Optional[TaskCompletionAnalysis]:
    """Удобная функция для анализа эффекта выполнения задания."""
    return await TaskManagementService.analyze_task_completion_effect(task_completion, user)
