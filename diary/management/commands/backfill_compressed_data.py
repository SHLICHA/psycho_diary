"""
Management command: backfill compressed_psych_profile и day_context_summary.

Использование:
    python manage.py backfill_compressed_data --dry-run    # посмотреть что будет
    python manage.py backfill_compressed_data --run         # запустить
    python manage.py backfill_compressed_data --run --batch-size=20 --sleep=3

Безопасно:
- Не удаляет данные
- Не меняет существующую логику
- Пропускает уже заполненные поля
- Можно остановить (Ctrl+C) и продолжить
"""

import time
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Заполняет compressed_psych_profile и day_context_summary для существующих данных."

    def add_arguments(self, parser):
        parser.add_argument(
            '--run',
            action='store_true',
            help='Запустить бэкфилл (без этого флага — dry-run только).'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать что будет сделано, без записи в БД.'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Размер батча для обработки (по умолчанию 50).'
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=2.0,
            help='Пауза в секундах между батчами (по умолчанию 2.0).'
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=30,
            help='Сколько дней назад бэкфиллить day_context_summary (по умолчанию 30).'
        )

    def handle(self, *args, **options):
        is_run = options['run']
        is_dry_run = options['dry_run'] or not is_run
        batch_size = options['batch_size']
        sleep_seconds = options['sleep']
        days_back = options['days_back']

        if is_dry_run:
            self.stdout.write(self.style.WARNING(
                "═══ DRY RUN ═══\n"
                "Никакие данные не будут изменены.\n"
                "Используйте --run для реального запуска."
            ))

        # ─── Шаг 1: compressed_psych_profile ─────────────────────
        self._backfill_compressed_profiles(is_dry_run, batch_size, sleep_seconds)

        # ─── Шаг 2: day_context_summary ──────────────────────────
        self._backfill_day_context(is_dry_run, batch_size, sleep_seconds, days_back)

        # ─── Итог ────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n═══ BACKFILL ЗАВЕРШЁН ═══\n"
            f"Режим: {'ЗАПУСК' if is_run else 'DRY RUN'}\n"
        ))

    def _backfill_compressed_profiles(self, is_dry_run, batch_size, sleep_seconds):
        """Бэкфилл compressed_psych_profile для пользователей."""
        from users.models import User
        from diary.services.compressed_profile_service import compressed_profile_service

        self.stdout.write(f"\n── Шаг 1: compressed_psych_profile ──")

        total_users = User.objects.count()
        self.stdout.write(f"Всего пользователей: {total_users}")

        processed = 0
        skipped_no_data = 0
        skipped_already_has = 0
        generated = 0
        errors = 0

        for offset in range(0, total_users, batch_size):
            batch = list(User.objects.all()[offset:offset + batch_size])
            if not batch:
                break

            for user in batch:
                processed += 1

                # Пропускаем если уже есть
                if user.compressed_psych_profile and len(user.compressed_psych_profile) > 0:
                    skipped_already_has += 1
                    continue

                # Генерируем
                profile = compressed_profile_service.generate_for_user(user)
                if not profile:
                    skipped_no_data += 1
                    continue

                if is_dry_run:
                    self.stdout.write(
                        f"  [DRY] User {user.username} (tg:{user.telegram_id}): "
                        f"будет сгенерирован (summary={len(profile['psych_summary'])} симв.)"
                    )
                    generated += 1
                else:
                    try:
                        with transaction.atomic():
                            user.compressed_psych_profile = profile
                            user.save(update_fields=['compressed_psych_profile'])
                        generated += 1
                        if generated % 10 == 0:
                            self.stdout.write(f"  ... сгенерировано: {generated}")
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"  [ERROR] User {user.username}: {e}"
                            )
                        )

            if not is_dry_run and offset + batch_size < total_users:
                time.sleep(sleep_seconds)

        self.stdout.write(f"\n  Обработано: {processed}")
        self.stdout.write(f"  Сгенерировано: {generated}")
        self.stdout.write(f"  Уже есть: {skipped_already_has}")
        self.stdout.write(f"  Нет данных: {skipped_no_data}")
        self.stdout.write(f"  Ошибки: {errors}")

    def _backfill_day_context(self, is_dry_run, batch_size, sleep_seconds, days_back):
        """Бэкфилл day_context_summary для CombinedDiaryEntry."""
        from diary.models import CombinedDiaryEntry, DailyAnalysis
        from diary.services.day_context_service import day_context_service
        from datetime import date, timedelta

        self.stdout.write(f"\n── Шаг 2: day_context_summary ──")

        cutoff_date = date.today() - timedelta(days=days_back)

        total_entries = CombinedDiaryEntry.objects.filter(
            date__gte=cutoff_date
        ).count()

        self.stdout.write(
            f"CombinedDiaryEntry за последние {days_back} дней (с {cutoff_date}): {total_entries}"
        )

        processed = 0
        skipped_already_has = 0
        skipped_no_data = 0
        generated = 0
        errors = 0

        for offset in range(0, total_entries, batch_size):
            batch = list(
                CombinedDiaryEntry.objects
                .filter(date__gte=cutoff_date)
                .select_related('daily_analysis')
                [offset:offset + batch_size]
            )
            if not batch:
                break

            for entry in batch:
                processed += 1

                # Пропускаем если уже есть
                if entry.day_context_summary and len(entry.day_context_summary) > 0:
                    skipped_already_has += 1
                    continue

                # Пробуем через DailyAnalysis
                daily_analysis = getattr(entry, 'daily_analysis', None)
                if daily_analysis:
                    ctx = day_context_service.generate_from_daily_analysis(daily_analysis)
                else:
                    # Fallback: из данных самого entry
                    ctx = day_context_service.generate_from_combined_entry(entry)

                if not ctx:
                    skipped_no_data += 1
                    continue

                if is_dry_run:
                    self.stdout.write(
                        f"  [DRY] Entry {entry.date} (user:{entry.user_id}): "
                        f"будет сгенерирован (trend={ctx.get('trend', '?')})"
                    )
                    generated += 1
                else:
                    try:
                        with transaction.atomic():
                            entry.day_context_summary = ctx
                            entry.save(update_fields=['day_context_summary'])
                        generated += 1
                        if generated % 20 == 0:
                            self.stdout.write(f"  ... сгенерировано: {generated}")
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"  [ERROR] Entry {entry.date} (user:{entry.user_id}): {e}"
                            )
                        )

            if not is_dry_run and offset + batch_size < total_entries:
                time.sleep(sleep_seconds)

        self.stdout.write(f"\n  Обработано: {processed}")
        self.stdout.write(f"  Сгенерировано: {generated}")
        self.stdout.write(f"  Уже есть: {skipped_already_has}")
        self.stdout.write(f"  Нет данных: {skipped_no_data}")
        self.stdout.write(f"  Ошибки: {errors}")
