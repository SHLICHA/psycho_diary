"""
Периодическая задача для очистки списковых полей пользователя от элементов вида {"remove": ...}
Запускается раз в час. Очищает данные у пользователей, у которых сейчас 3:30 по их часовому поясу.
"""

import asyncio
import logging
from datetime import datetime
import pytz

from celery import shared_task
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from users.models import User

logger = logging.getLogger(__name__)

def _filter_remove_items(items_list):
    """
    Фильтрует список, удаляя элементы вида {"remove": ...}.
    """
    if not items_list:
        return []
    return [item for item in items_list if not (isinstance(item, dict) and 'remove' in item)]

@shared_task
def run_garbage_collection():
    """
    Запускает очистку списковых полей у пользователей, у которых сейчас 3:30 по их времени.
    Запускается раз в час Celery Beat.
    """
    return asyncio.run(run_garbage_collection_async())

async def run_garbage_collection_async():
    """
    Асинхронная корутина для очистки списковых полей.
    """
    try:
        # Получаем всех активных пользователей
        await sync_to_async(close_old_connections)()
        users = await sync_to_async(list)(
            User.objects.filter(
                is_blocked=False,
                deletion_status='active',
                deleted_at__isnull=True
            ).only(
                'id', 'telegram_id', 'timezone', 'life_facts', 'hobbies', 'core_values', 'triggers',
                'strengths', 'areas_for_growth', 'practical_patterns', 'aspirations'
            )
        )

        utc_now = datetime.now(pytz.utc)
        total_processed = 0
        total_cleaned = 0

        for user in users:
            try:
                user_timezone_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Неизвестный часовой пояс у пользователя {user.telegram_id}: {user_timezone_str}. Используется UTC.")
                    user_tz = pytz.UTC
                user_local_time = utc_now.astimezone(user_tz)
                current_user_hour = user_local_time.hour
                current_user_minute = user_local_time.minute

                # Проверяем, наступил ли у пользователя 3:30
                #if current_user_hour == 15:
                if current_user_hour == 3 and current_user_minute == 30:
                    # Только если 3:30 — начинаем очистку
                    was_updated = False
                    fields_to_update = []

                    # Поля, которые являются списками
                    list_fields = [
                        'life_facts', 'hobbies', 'core_values', 'triggers',
                        'strengths', 'areas_for_growth', 'practical_patterns', 'aspirations'
                    ]

                    for field_name in list_fields:
                        current_list = getattr(user, field_name, [])
                        if not isinstance(current_list, list):
                            continue
                        filtered_list = _filter_remove_items(current_list)
                        if len(filtered_list) != len(current_list):
                            logger.debug(f"Очищены 'remove' элементы из '{field_name}' пользователя {user.telegram_id}")
                            setattr(user, field_name, filtered_list)
                            fields_to_update.append(field_name)
                            was_updated = True

                    if was_updated:
                        # Асинхронное сохранение
                        await sync_to_async(close_old_connections)()
                        await sync_to_async(user.save)(update_fields=fields_to_update)
                        total_cleaned += 1

                    total_processed += 1

            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке пользователя {user.telegram_id} для очистки: {e}", exc_info=True)

        # Логируем только если были очистки
        if total_cleaned > 0:
            logger.info(f"Задача очистки списковых полей завершена. "
                        f"Обработано пользователей: {total_processed}, "
                        f"Очищено: {total_cleaned}")
        return (f"Обработано: {total_processed}, "
                f"Очищено: {total_cleaned}")

    except Exception as e:
        logger.critical(f"Критическая ошибка в задаче очистки списковых полей: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"