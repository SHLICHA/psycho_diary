# /home/shlicha/psycho_diary/diary/tasks/task_expiration.py

"""
Периодические задачи для обновления статуса просроченных заданий.
"""

import logging
from datetime import datetime, timedelta
import pytz
from asgiref.sync import sync_to_async
from celery import shared_task
from django.utils import timezone

from diary.models import TherapyTask
from users.models import User

logger = logging.getLogger(__name__)

@shared_task
def expire_tasks():
    """
    Обновление статуса просроченных заданий.
    Запускается каждую минуту Celery Beat.
    """
    logger.info("Запуск задачи обновления статуса просроченных заданий.")
    return expire_tasks_sync()

def expire_tasks_sync():
    """
    Синхронная корутина для обновления статуса просроченных заданий.
    """
    try:
        now = timezone.now()
        # Находим все задания со статусом 'pending' и 'in_progress', 
        # у которых дата истечения меньше текущей
        expired_tasks = TherapyTask.objects.filter(
            status='pending',
            expires_at__lte=now
        )
        expired_count = expired_tasks.count()
        if expired_count > 0:
            # Обновляем статус на 'expired'
            expired_tasks.update(status='expired')
            logger.info(f"Обновлено {expired_count} просроченных заданий.")
        else:
            logger.info("Нет просроченных заданий для обновления.")
        return f"Обновлено {expired_count} просроченных заданий."
    except Exception as e:
        logger.error(f"Критическая ошибка в задаче обновления статуса просроченных заданий: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"

# В основной задаче вызываем expire_tasks_sync напрямую
@shared_task
def expire_tasks():
    """
    Обновление статуса просроченных заданий.
    Запускается каждую минуту Celery Beat.
    """
    logger.info("Запуск задачи обновления статуса просроченных заданий.")
    return expire_tasks_sync()