from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from diary.models import UserActivity


def get_ai_inactivity_days(inactivity_days: int | None = None) -> int:
    if inactivity_days is not None:
        return inactivity_days
    return getattr(settings, 'AI_INACTIVITY_DAYS', 30)


def _latest_user_activity_timestamp(user):
    last_activity = getattr(user, 'last_activity', None)
    last_entry = getattr(user, 'last_entry', None)

    if last_activity and last_entry:
        return max(last_activity, last_entry)
    if last_activity:
        return last_activity
    if last_entry:
        return last_entry
    return None


def is_user_active_for_ai_tasks(user, inactivity_days: int | None = None) -> bool:
    """
    Возвращает True, если у пользователя есть активность за последние N дней.
    Используется для фильтрации периодических ИИ-задач и исключения неактивных пользователей.

    Вызывать только из sync-контекста. В async-задачах использовать ais_user_active_for_ai_tasks.
    """
    if not user:
        return False

    inactivity_days = get_ai_inactivity_days(inactivity_days)
    cutoff = timezone.now() - timedelta(days=inactivity_days)

    recent_activity_exists = UserActivity.objects.filter(
        user=user,
        timestamp__gte=cutoff,
    ).exists()

    if recent_activity_exists:
        return True

    latest_activity = _latest_user_activity_timestamp(user)
    if not latest_activity:
        return False

    created_at = getattr(user, 'created_at', None)
    if created_at and latest_activity <= created_at:
        return False

    return latest_activity >= cutoff


async def ais_user_active_for_ai_tasks(user, inactivity_days: int | None = None) -> bool:
    """
    Async-безопасная проверка активности для Celery-задач с asyncio.run().

    Оборачивает sync-ORM, чтобы не получать SynchronousOnlyOperation.
    """
    return await sync_to_async(is_user_active_for_ai_tasks, thread_sensitive=True)(
        user, inactivity_days
    )
