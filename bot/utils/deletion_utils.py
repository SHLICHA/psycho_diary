"""
Утилиты для удаления данных бота
"""

import logging
from django.db import transaction
from diary.models import DiaryEntry, PsychoAnalysis, TaskCompletion, TherapyTask
from users.models import User

logger = logging.getLogger(__name__)

async def delete_entry_safe(
    entry_id: int,
    user: User
) -> bool:
    """
    Безопасное удаление записи дневника
    
    Args:
        entry_id: ID записи
        user: Пользователь
        
    Returns:
        bool: Успешность удаления
    """
    logger.info(f"Безопасное удаление записи {entry_id} пользователя {user.telegram_id}")
    
    try:
        # Получаем запись с проверкой владельца
        try:
            entry = await DiaryEntry.objects.aget(
                id=entry_id,
                user=user
            )
            logger.info(f"Запись найдена: {entry.text[:50]}...")
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            return False
        
        # Удаляем запись и связанные данные в транзакции
        async with transaction.atomic():
            # Удаляем связанные данные
            await _delete_related_data(entry)
            
            # Удаляем саму запись
            await entry.adelete()
            
        logger.info(f"Запись {entry_id} успешно удалена")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при безопасном удалении записи {entry_id}: {e}")
        return False

async def _delete_related_data(entry: DiaryEntry):
    """
    Удаление связанных данных записи
    
    Args:
        entry: Запись дневника
    """
    logger.info(f"Удаление связанных данных записи {entry.id}")
    
    try:
        # Удаляем анализ записи (если есть)
        if hasattr(entry, 'analysis'):
            try:
                analysis = await PsychoAnalysis.objects.aget(entry=entry)
                await analysis.adelete()
                logger.info(f"Анализ записи {entry.id} удален")
            except PsychoAnalysis.DoesNotExist:
                logger.info(f"Анализ записи {entry.id} не найден")
        
        # Удаляем ключевые моменты (если есть)
        if hasattr(entry, 'key_points'):
            try:
                async for key_point in entry.key_points.all():
                    await key_point.adelete()
                logger.info(f"Ключевые моменты записи {entry.id} удалены")
            except Exception as key_points_error:
                logger.error(f"Ошибка при удалении ключевых моментов записи {entry.id}: {key_points_error}")
        
        # Удаляем информацию о голосовом сообщении (если есть)
        if hasattr(entry, 'voice_to_text'):
            try:
                voice_to_text = await entry.voice_to_text
                await voice_to_text.adelete()
                logger.info(f"Информация о голосовом сообщении записи {entry.id} удалена")
            except Exception as voice_error:
                logger.error(f"Ошибка при удалении информации о голосовом сообщении записи {entry.id}: {voice_error}")
        
        # Удаляем выполнения заданий (если есть)
        if hasattr(entry, 'task_completion'):
            try:
                task_completion = await entry.task_completion
                await _delete_task_completion_related_data(task_completion)
                await task_completion.adelete()
                logger.info(f"Выполнение задания записи {entry.id} удалено")
            except Exception as task_completion_error:
                logger.error(f"Ошибка при удалении выполнения задания записи {entry.id}: {task_completion_error}")
        
        logger.info(f"Все связанные данные записи {entry.id} удалены")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении связанных данных записи {entry.id}: {e}")

async def _delete_task_completion_related_data(task_completion: TaskCompletion):
    """
    Удаление связанных данных выполнения задания
    
    Args:
        task_completion: Выполнение задания
    """
    logger.info(f"Удаление связанных данных выполнения задания {task_completion.id}")
    
    try:
        # Удаляем анализ выполнения задания (если есть)
        if hasattr(task_completion, 'analysis'):
            try:
                analysis = await task_completion.analysis
                await analysis.adelete()
                logger.info(f"Анализ выполнения задания {task_completion.id} удален")
            except Exception as analysis_error:
                logger.error(f"Ошибка при удалении анализа выполнения задания {task_completion.id}: {analysis_error}")
        
        logger.info(f"Все связанные данные выполнения задания {task_completion.id} удалены")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении связанных данных выполнения задания {task_completion.id}: {e}")

async def delete_user_data_safe(
    user: User,
    include_entries: bool = True,
    include_tasks: bool = True,
    include_analytics: bool = True
) -> bool:
    """
    Безопасное удаление данных пользователя
    
    Args:
        user: Пользователь
        include_entries: Удалять ли записи дневника
        include_tasks: Удалять ли задания
        include_analytics: Удалять ли аналитику
        
    Returns:
        bool: Успешность удаления
    """
    logger.info(f"Безопасное удаление данных пользователя {user.telegram_id}")
    logger.info(f"Включены: записи={include_entries}, задания={include_tasks}, аналитика={include_analytics}")
    
    try:
        # Удаляем данные в транзакции
        async with transaction.atomic():
            # Удаляем записи дневника (если включено)
            if include_entries:
                await _delete_user_entries(user)
            
            # Удаляем задания (если включено)
            if include_tasks:
                await _delete_user_tasks(user)
            
            # Удаляем аналитику (если включено)
            if include_analytics:
                await _delete_user_analytics(user)
            
            # Удаляем самого пользователя (если нужно)
            # await user.adelete()  # Пока не удаляем пользователя, только данные
        
        logger.info(f"Данные пользователя {user.telegram_id} успешно удалены")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при безопасном удалении данных пользователя {user.telegram_id}: {e}")
        return False

async def _delete_user_entries(user: User):
    """
    Удаление записей пользователя
    
    Args:
        user: Пользователь
    """
    logger.info(f"Удаление записей пользователя {user.telegram_id}")
    
    try:
        # Получаем все записи пользователя
        entries = []
        async for entry in DiaryEntry.objects.filter(user=user):
            entries.append(entry)
        
        logger.info(f"Найдено {len(entries)} записей для удаления")
        
        # Удаляем каждую запись с связанными данными
        for entry in entries:
            await _delete_related_data(entry)
            await entry.adelete()
        
        logger.info(f"Все записи пользователя {user.telegram_id} удалены")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении записей пользователя {user.telegram_id}: {e}")

async def _delete_user_tasks(user: User):
    """
    Удаление заданий пользователя
    
    Args:
        user: Пользователь
    """
    logger.info(f"Удаление заданий пользователя {user.telegram_id}")
    
    try:
        from diary.models import TherapyTask
        
        # Получаем все задания пользователя
        tasks = []
        async for task in TherapyTask.objects.filter(user=user):
            tasks.append(task)
        
        logger.info(f"Найдено {len(tasks)} заданий для удаления")
        
        # Удаляем каждое задание с связанными данными
        for task in tasks:
            await _delete_task_related_data(task)
            await task.adelete()
        
        logger.info(f"Все задания пользователя {user.telegram_id} удалены")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении заданий пользователя {user.telegram_id}: {e}")

async def _delete_task_related_data(task: TherapyTask):
    """
    Удаление связанных данных задания
    
    Args:
        task: Задание
    """
    logger.info(f"Удаление связанных данных задания {task.id}")
    
    try:
        # Удаляем выполнение задания (если есть)
        if hasattr(task, 'completion'):
            try:
                completion = await task.completion
                await _delete_task_completion_related_data(completion)
                await completion.adelete()
                logger.info(f"Выполнение задания {task.id} удалено")
            except Exception as completion_error:
                logger.error(f"Ошибка при удалении выполнения задания {task.id}: {completion_error}")
        
        logger.info(f"Все связанные данные задания {task.id} удалены")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении связанных данных задания {task.id}: {e}")

async def _delete_user_analytics(user: User):
    """
    Удаление аналитики пользователя
    
    Args:
        user: Пользователь
    """
    logger.info(f"Удаление аналитики пользователя {user.telegram_id}")
    
    try:
        from diary.models import UserActivity, TherapyProgress
        
        # Удаляем активность пользователя
        try:
            async for activity in UserActivity.objects.filter(user=user):
                await activity.adelete()
            logger.info(f"Активность пользователя {user.telegram_id} удалена")
        except Exception as activity_error:
            logger.error(f"Ошибка при удалении активности пользователя {user.telegram_id}: {activity_error}")
        
        # Удаляем прогресс терапии пользователя
        try:
            async for progress in TherapyProgress.objects.filter(user=user):
                await progress.adelete()
            logger.info(f"Прогресс терапии пользователя {user.telegram_id} удален")
        except Exception as progress_error:
            logger.error(f"Ошибка при удалении прогресса терапии пользователя {user.telegram_id}: {progress_error}")
        
        # Удаляем инсайты пользователя
        try:
            from diary.models import UserInsight
            async for insight in UserInsight.objects.filter(user=user):
                await insight.adelete()
            logger.info(f"Инсайты пользователя {user.telegram_id} удалены")
        except Exception as insight_error:
            logger.error(f"Ошибка при удалении инсайтов пользователя {user.telegram_id}: {insight_error}")
        
        logger.info(f"Аналитика пользователя {user.telegram_id} удалена")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении аналитики пользователя {user.telegram_id}: {e}")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def soft_delete_entry(
    entry_id: int,
    user: User
) -> bool:
    """
    Мягкое удаление записи (пометка как удаленной)
    
    Args:
        entry_id: ID записи
        user: Пользователь
        
    Returns:
        bool: Успешность мягкого удаления
    """
    logger.info(f"Мягкое удаление записи {entry_id} пользователя {user.telegram_id}")
    
    try:
        # Получаем запись с проверкой владельца
        try:
            entry = await DiaryEntry.objects.aget(
                id=entry_id,
                user=user
            )
            logger.info(f"Запись найдена: {entry.text[:50]}...")
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            return False
        
        # Помечаем запись как удаленную
        from datetime import datetime
        entry.deleted_at = datetime.now()
        await entry.asave(update_fields=['deleted_at'])
        
        logger.info(f"Запись {entry_id} помечена как удаленная")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при мягком удалении записи {entry_id}: {e}")
        return False

async def restore_soft_deleted_entry(
    entry_id: int,
    user: User
) -> bool:
    """
    Восстановление мягко удаленной записи
    
    Args:
        entry_id: ID записи
        user: Пользователь
        
    Returns:
        bool: Успешность восстановления
    """
    logger.info(f"Восстановление мягко удаленной записи {entry_id} пользователя {user.telegram_id}")
    
    try:
        # Получаем запись с проверкой владельца
        try:
            entry = await DiaryEntry.objects.aget(
                id=entry_id,
                user=user,
                deleted_at__isnull=False  # Только удаленные записи
            )
            logger.info(f"Удаленная запись найдена: {entry.text[:50]}...")
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Удаленная запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            return False
        
        # Снимаем пометку удаления
        entry.deleted_at = None
        await entry.asave(update_fields=['deleted_at'])
        
        logger.info(f"Запись {entry_id} восстановлена")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при восстановлении записи {entry_id}: {e}")
        return False

async def purge_soft_deleted_entries(
    user: User,
    days_old: int = 30
) -> int:
    """
    Полное удаление мягко удаленных записей старше N дней
    
    Args:
        user: Пользователь
        days_old: Сколько дней записи остаются в "корзине"
        
    Returns:
        int: Количество удаленных записей
    """
    logger.info(f"Полное удаление мягко удаленных записей пользователя {user.telegram_id} старше {days_old} дней")
    
    try:
        from datetime import datetime, timedelta
        from django.db.models import Q
        
        # Определяем дату, старше которой записи будут удалены
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        # Получаем мягко удаленные записи старше cutoff_date
        deleted_entries = []
        async for entry in DiaryEntry.objects.filter(
            Q(user=user) &
            Q(deleted_at__isnull=False) &
            Q(deleted_at__lt=cutoff_date)
        ):
            deleted_entries.append(entry)
        
        logger.info(f"Найдено {len(deleted_entries)} записей для полного удаления")
        
        # Удаляем каждую запись с связанными данными
        deleted_count = 0
        for entry in deleted_entries:
            try:
                await _delete_related_data(entry)
                await entry.adelete()
                deleted_count += 1
            except Exception as delete_error:
                logger.error(f"Ошибка при полном удалении записи {entry.id}: {delete_error}")
        
        logger.info(f"Полностью удалено {deleted_count} записей")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Ошибка при полном удалении мягко удаленных записей: {e}")
        return 0