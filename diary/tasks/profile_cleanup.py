"""Celery задачи для TTL-очистки профилей пользователей."""

import logging

from asgiref.sync import async_to_sync
from celery import shared_task

from diary.services.profile_cleanup_service import profile_cleanup_service
from users.models import User

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_profile_cleanup(self, batch_size: int = 100) -> dict:
    """Периодически очищает stale-данные профиля активных пользователей."""
    logger.info(f"[ProfileCleanupTask] Старт batch cleanup, batch_size={batch_size}")

    processed_users = 0
    changed_users = 0
    changed_fields = 0
    removed_items = 0
    stale_items = 0
    rebuilt_profiles = 0
    failed_users = 0

    user_ids = list(
        User.objects.filter(is_blocked=False)
        .order_by("id")
        .values_list("id", flat=True)
    )

    for start in range(0, len(user_ids), batch_size):
        batch_ids = user_ids[start:start + batch_size]
        users = User.objects.filter(id__in=batch_ids).order_by("id")

        batch_processed = 0
        batch_changed = 0
        batch_removed = 0
        batch_stale = 0

        for user in users:
            processed_users += 1
            batch_processed += 1
            try:
                cleanup_result = async_to_sync(profile_cleanup_service.cleanup_user_profile)(user)
                if cleanup_result.get("changed"):
                    changed_users += 1
                    batch_changed += 1
                    changed_fields += cleanup_result.get("changed_fields_count", 0)
                    removed_items += cleanup_result.get("removed_items", 0)
                    batch_removed += cleanup_result.get("removed_items", 0)
                stale_items += cleanup_result.get("stale_items", 0)
                batch_stale += cleanup_result.get("stale_items", 0)
                if cleanup_result.get("compressed_profile_rebuilt"):
                    rebuilt_profiles += 1

                logger.debug(
                    f"[ProfileCleanupTask] User {user.telegram_id}: changed={cleanup_result.get('changed')}, "
                    f"changed_fields={cleanup_result.get('changed_fields', [])}, "
                    f"removed_items={cleanup_result.get('removed_items', 0)}, "
                    f"stale_items={cleanup_result.get('stale_items', 0)}, "
                    f"compressed_action={cleanup_result.get('compressed_profile_action', 'skipped')}"
                )
            except Exception as exc:
                failed_users += 1
                logger.error(
                    f"[ProfileCleanupTask] User {user.telegram_id}: ошибка cleanup: {exc}",
                    exc_info=True,
                )

        logger.info(
            f"[ProfileCleanupTask] Batch {start // batch_size + 1}: "
            f"processed={batch_processed}, changed={batch_changed}, "
            f"removed_items={batch_removed}, stale_items={batch_stale}"
        )

    result = {
        "status": "completed",
        "processed_users": processed_users,
        "changed_users": changed_users,
        "changed_fields": changed_fields,
        "removed_items": removed_items,
        "stale_items": stale_items,
        "rebuilt_profiles": rebuilt_profiles,
        "failed_users": failed_users,
    }
    logger.info(f"[ProfileCleanupTask] Завершено: {result}")
    return result