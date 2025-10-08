"""
Периодические задачи для обновления статуса просроченных заданий.
"""

import logging

from celery import shared_task
from django.utils import timezone

from diary.models import TherapyTask

logger = logging.getLogger(__name__)

@shared_task
def expire_tasks():
    """
    Обновление статуса просроченных заданий.
    Запускается каждую минуту Celery Beat.
    """
    logger.debug("Запуск задачи обновления статуса просроченных заданий.")
    return expire_tasks_sync()

def expire_tasks_sync():
    """
    Синхронная корутина для обновления статуса просроченных заданий.
    """
    try:
        now = timezone.now()
        expired_tasks = TherapyTask.objects.filter(
            status='pending',
            expires_at__lte=now
        )
        expired_count = expired_tasks.count()
        if expired_count > 0:
            expired_tasks.update(status='expired')
        return f"Обновлено {expired_count} просроченных заданий."
    except Exception as e:
        logger.error(f"Критическая ошибка в задаче обновления статуса просроченных заданий: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"
