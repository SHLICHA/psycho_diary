"""
Сервис для работы с терапевтическими заданиями
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Q
from diary.models import TherapyTask, TaskCompletion, TaskAnalysis
from users.models import User
from asgiref.sync import sync_to_async

# Настраиваем логирование на русском
logger = logging.getLogger(__name__)

class TaskService:
    """Сервис для работы с терапевтическими заданиями"""
    
    async def assign_task(
        self, 
        user: User, 
        title: str, 
        description: str, 
        task_type: str = 'daily',
        priority: int = 1
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
        logger.info(f"Назначение задания пользователю {user.telegram_id}")
        logger.info(f"Название: {title}")
        logger.info(f"Тип: {task_type}")
        logger.info(f"Приоритет: {priority}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для транзакций
            @sync_to_async
            def create_task_sync():
                with transaction.atomic():
                    therapy_task = TherapyTask.objects.create(
                        user=user,
                        title=title,
                        description=description,
                        type=task_type,
                        priority=priority,
                        status='pending'  # Ожидает выполнения
                    )
                    logger.info(f"Задание назначено, ID: {therapy_task.id}")
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
        logger.info(f"Получение активных заданий пользователя {user.telegram_id}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для запросов
            @sync_to_async
            def get_active_tasks_sync():
                active_tasks = list(
                    TherapyTask.objects.filter(
                        user=user,
                        status__in=['pending', 'in_progress']  # Только активные задания
                    ).order_by('assigned_at')
                )
                logger.info(f"Найдено {len(active_tasks)} активных заданий")
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
        logger.info(f"Получение выполненных заданий пользователя {user.telegram_id}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для запросов
            @sync_to_async
            def get_completed_tasks_sync():
                completed_tasks = list(
                    TherapyTask.objects.filter(
                        user=user,
                        status='completed'  # Только выполненные
                    ).order_by('-completed_at')[:limit]
                )
                logger.info(f"Найдено {len(completed_tasks)} выполненных заданий")
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
        feelings_text: str
    ) -> Optional[TaskCompletion]:
        """
        Выполнение задания
        
        Args:
            task_id: ID задания
            user: Пользователь
            completion_text: Текст выполнения задания
            feelings_text: Ощущения при выполнении
            
        Returns:
            TaskCompletion: Результат выполнения задания или None
        """
        logger.info(f"Выполнение задания {task_id} пользователем {user.telegram_id}")
        logger.info(f"Текст выполнения длиной: {len(completion_text)} символов")
        logger.info(f"Текст ощущений длиной: {len(feelings_text)} символов")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для всей операции
            @sync_to_async
            def complete_task_sync():
                with transaction.atomic():
                    # Получаем задание с проверкой владельца
                    try:
                        task = TherapyTask.objects.get(
                            id=task_id,
                            user=user,
                            status__in=['pending', 'in_progress']  # Только активные задания
                        )
                        logger.info(f"Задание найдено: {task.title}")
                    except TherapyTask.DoesNotExist:
                        logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                        raise ValueError("Задание не найдено или не принадлежит вам")
                    
                    # Создаем запись выполнения
                    task_completion = TaskCompletion.objects.create(
                        task=task,
                        completion_text=completion_text,
                        feelings_text=feelings_text,
                        time_spent=5  # Заглушка - время выполнения в минутах
                    )
                    logger.info(f"Выполнение задания создано, ID: {task_completion.id}")
                    
                    # Обновляем статус задания
                    task.status = 'completed'
                    task.completed_at = datetime.now()
                    task.save(update_fields=['status', 'completed_at'])
                    logger.info(f"Статус задания обновлен на 'completed'")
                    
                    # Создаем анализ выполнения (заглушка)
                    task_analysis = TaskAnalysis.objects.create(
                        completion=task_completion,
                        bot_response="Отличная работа! Выполнил задание честно и подробно.",
                        insights_updated=True,
                        quality_score=8,  # Заглушка
                        feedback_given=True
                    )
                    logger.info(f"Анализ выполнения создан, ID: {task_analysis.id}")
                
                return task_completion, task_analysis  # Возвращаем кортеж!
            
            task_completion, task_analysis = await complete_task_sync()  # Получаем оба значения!
            
            # Обновляем инсайты пользователя
            await self._update_user_insights(user, task_completion, task_analysis)
            logger.info("Инсайты пользователя обновлены")
            
            return task_completion  # Возвращаем только выполнение
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении задания: {e}")
            return None
    
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
        logger.info(f"Пропуск задания {task_id} пользователем {user.telegram_id}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для операции
            @sync_to_async
            def skip_task_sync():
                # Получаем задание с проверкой владельца
                try:
                    task = TherapyTask.objects.get(
                        id=task_id,
                        user=user,
                        status__in=['pending', 'in_progress']  # Только активные задания
                    )
                    logger.info(f"Задание найдено: {task.title}")
                except TherapyTask.DoesNotExist:
                    logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                    return False
                
                # Обновляем статус задания
                with transaction.atomic():
                    task.status = 'skipped'
                    task.completed_at = datetime.now()
                    task.save(update_fields=['status', 'completed_at'])
                    logger.info(f"Статус задания обновлен на 'skipped'")
                
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
        logger.info(f"Удаление задания {task_id} пользователем {user.telegram_id}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для операции
            @sync_to_async
            def delete_task_sync():
                # Получаем задание с проверкой владельца
                try:
                    task = TherapyTask.objects.get(
                        id=task_id,
                        user=user
                    )
                    logger.info(f"Задание найдено: {task.title}")
                except TherapyTask.DoesNotExist:
                    logger.warning(f"Задание {task_id} не найдено или не принадлежит пользователю {user.telegram_id}")
                    return False
                
                # Удаляем задание и связанные данные в транзакции
                with transaction.atomic():
                    # Удаляем связанные данные
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
                    
                    # Удаляем само задание
                    task.delete()
                    logger.info(f"Задание {task_id} успешно удалено")
                
                return True
            
            success = await delete_task_sync()
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при удалении задания: {e}")
            return False
    
    async def _update_user_insights(
        self, 
        user: User, 
        task_completion: TaskCompletion, 
        task_analysis: TaskAnalysis
    ):
        """
        Обновление инсайтов пользователя на основе выполнения задания
        
        Args:
            user: Пользователь
            task_completion: Выполнение задания
            task_analysis: Анализ выполнения
        """
        logger.info(f"Обновление инсайтов пользователя {user.telegram_id}")
        
        try:
            # ИСПРАВЛЕНО: используем sync_to_async для операции
            @sync_to_async
            def update_insights_sync():
                # Извлекаем ключевые моменты из текста выполнения
                completion_text = task_completion.completion_text.lower()
                feelings_text = task_completion.feelings_text.lower()
                
                # Простой анализ ключевых слов (заглушка)
                key_insights = []
                
                # Ключевые слова для инсайтов
                insight_keywords = {
                    'emotion': ['радость', 'грусть', 'гнев', 'страх', 'любовь', 'ненависть', 'удовольствие', 'боль'],
                    'behavior': ['поведение', 'действие', 'реакция', 'ответ', 'решение'],
                    'thought': ['мысль', 'идея', 'размышление', 'понимание', 'осознание'],
                    'trigger': ['триггер', 'провокатор', 'причина', 'повод', 'вызывает']
                }
                
                # Ищем ключевые слова в тексте
                for category, keywords in insight_keywords.items():
                    for keyword in keywords:
                        if keyword in completion_text or keyword in feelings_text:
                            key_insights.append({
                                'text': keyword,
                                'category': category,
                                'weight': 1
                            })
                
                logger.info(f"Найдено {len(key_insights)} ключевых инсайтов")
                return key_insights
            
            key_insights = await update_insights_sync()
            
            # Обновляем инсайты пользователя
            from diary.models import UserInsight
            for insight in key_insights:
                try:
                    # Проверяем существование инсайта
                    @sync_to_async
                    def check_insight_exists_sync():
                        return UserInsight.objects.filter(
                            user=user,
                            text=insight['text'],
                            category=insight['category']
                        ).exists()
                    
                    insight_exists = await check_insight_exists_sync()
                    
                    if insight_exists:
                        # Увеличиваем вес существующего инсайта
                        @sync_to_async
                        def update_insight_weight_sync():
                            user_insight = UserInsight.objects.get(
                                user=user,
                                text=insight['text'],
                                category=insight['category']
                            )
                            user_insight.weight += insight['weight']
                            user_insight.last_mentioned = datetime.now()
                            user_insight.save(update_fields=['weight', 'last_mentioned'])
                            return user_insight.weight
                        
                        new_weight = await update_insight_weight_sync()
                        logger.info(f"Инсайт '{insight['text']}' обновлен, новый вес: {new_weight}")
                    else:
                        # Создаем новый инсайт
                        @sync_to_async
                        def create_insight_sync():
                            return UserInsight.objects.create(
                                user=user,
                                text=insight['text'],
                                category=insight['category'],
                                weight=insight['weight'],
                                last_mentioned=datetime.now()
                            )
                        
                        user_insight = await create_insight_sync()
                        logger.info(f"Новый инсайт '{insight['text']}' создан")
                        
                except Exception as insight_error:
                    logger.error(f"Ошибка при обновлении инсайта '{insight['text']}': {insight_error}")
            
            logger.info("Инсайты пользователя успешно обновлены")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении инсайтов пользователя: {e}")

# Глобальный экземпляр сервиса заданий
task_service = TaskService()

# Удобные функции для использования
async def assign_task(
    user: User, 
    title: str, 
    description: str, 
    task_type: str = 'daily',
    priority: int = 1
) -> TherapyTask:
    """Удобная функция для назначения задания"""
    return await task_service.assign_task(user, title, description, task_type, priority)

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