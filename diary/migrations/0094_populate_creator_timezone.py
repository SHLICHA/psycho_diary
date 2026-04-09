"""
Data migration: Populate creator_timezone for existing DiaryEntry records.

For each existing entry, we set creator_timezone to the current timezone of
the entry's owner. This is an approximation since we don't know what timezone
the user had at the time of creating the entry, but it's the best we can do.

Batched for safety on large tables.
"""

from django.db import migrations
from django.db import connection
import logging

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def populate_creator_timezone(apps, schema_editor):
    """
    Для существующих записей устанавливаем creator_timezone = текущему timezone владельца.
    Обрабатывает записи батчами по 1000 штук для безопасности на больших таблицах.
    """
    DiaryEntry = apps.get_model('diary', 'DiaryEntry')
    User = apps.get_model('users', 'User')

    # Получаем мапу user_id -> timezone
    users_tz = {}
    for user in User.objects.only('id', 'timezone').iterator(chunk_size=500):
        users_tz[user.id] = user.timezone if user.timezone else 'UTC'

    # Батчим по записям
    total_entries = DiaryEntry.objects.count()
    if total_entries == 0:
        logger.info("[0094] No DiaryEntry records to update.")
        return

    logger.info(f"[0094] Updating creator_timezone for {total_entries} entries in batches of {BATCH_SIZE}...")

    entry_qs = DiaryEntry.objects.only('id', 'user_id', 'creator_timezone')
    entries_updated = 0

    for offset in range(0, total_entries, BATCH_SIZE):
        batch = list(entry_qs[offset:offset + BATCH_SIZE])
        if not batch:
            break

        # Группируем по пользователю внутри батча
        user_entries = {}
        for entry in batch:
            uid = entry.user_id
            if uid not in user_entries:
                user_entries[uid] = []
            user_entries[uid].append(entry.id)

        # Обновляем батчами по пользователям
        for user_id, entry_ids in user_entries.items():
            tz = users_tz.get(user_id, 'UTC')
            DiaryEntry.objects.filter(id__in=entry_ids).update(creator_timezone=tz)

        entries_updated += len(batch)
        logger.info(f"[0094] Processed {entries_updated}/{total_entries} entries...")

        # Для больших таблиц — лог каждые 5000 записей
        if entries_updated % 5000 == 0:
            logger.info(f"[0094] Still working... {entries_updated}/{total_entries} done")

    logger.info(f"[0094] Done. Updated {entries_updated} entries.")


def reverse_populate(apps, schema_editor):
    """
    Обратная операция: сбрасываем creator_timezone в default значение.
    НЕ ставим пустую строку — это невалидный timezone.
    """
    DiaryEntry = apps.get_model('diary', 'DiaryEntry')

    # Сбрасываем в default='UTC' (соответствует дефолту из миграции 0093)
    DiaryEntry.objects.update(creator_timezone='UTC')
    logger.info("[0094_reverse] Reset all creator_timezone to 'UTC'.")


class Migration(migrations.Migration):

    atomic = False  # Не оборачиваем в одну транзакцию — позволяет батчить

    dependencies = [
        ('diary', '0093_diaryentry_creator_timezone'),
        ('users', '0006_user_date_of_birth_alter_user_email_citytimezone'),
    ]

    operations = [
        migrations.RunPython(
            populate_creator_timezone,
            reverse_populate,
        ),
    ]
