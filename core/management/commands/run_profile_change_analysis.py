# /home/shlicha/psycho_diary/diary/management/commands/run_profile_change_analysis.py
"""
Django management command to manually trigger profile change analysis for a user.
"""

import logging
import asyncio

from django.core.management.base import BaseCommand, CommandError
from django.db import models
from typing import Any, Dict, List, Type

from users.models import User
from diary.models import WeeklyAnalysis
from diary.services.weekly_analysis_service import weekly_analysis_service
from diary.services.user_profile_analysis_service import user_profile_analysis_service
from diary.services.user_profile_change_analysis_service import perform_profile_change_analysis

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manually triggers the full weekly analysis (including profile change analysis) for a specified user.'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int, help='Telegram ID of the user to analyze')
        parser.add_argument(
            '--num-snapshots',
            type=int,
            default=3,
            help='Number of historical snapshots to compare for change analysis (default: 3)'
        )

    def handle(self, *args, **options):
        telegram_id = options['telegram_id']
        num_snapshots = options['num_snapshots']

        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            raise CommandError(f'User with telegram_id {telegram_id} does not exist.')

        self.stdout.write(
            self.style.WARNING(f'Starting weekly analysis for user {user.username} (ID: {user.telegram_id})')
        )

        # Запускаем асинхронный процесс внутри синхронной команды
        try:
            # Создаём новый event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Выполняем основной асинхронный процесс
                result = loop.run_until_complete(self.async_handle(user, num_snapshots))
            finally:
                # Закрываем loop
                loop.close()
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during analysis: {e}')
            )
            return

        if result.get('success'):
            self.stdout.write(
                self.style.SUCCESS(result['message'])
            )
        else:
            self.stdout.write(
                self.style.ERROR(result['message'])
            )

    async def async_handle(self, user: User, num_snapshots: int) -> Dict[str, Any]:
        """Асинхронная логика выполнения команды."""
        from typing import Dict, Any # Импортируем внутри, чтобы избежать конфликта с верхним уровнем

        # 1. Выполнить еженедельный анализ (если еще не выполнен за текущую неделю)
        # (Это создаст WeeklyAnalysis)
        weekly_result = await weekly_analysis_service.perform_weekly_analysis(user)
        if not weekly_result.get('success'):
            error_msg = f'Weekly Analysis failed: {weekly_result.get("message", "Unknown error")}'
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "error": weekly_result.get("error")}

        weekly_analysis = weekly_result.get('weekly_analysis')
        if not weekly_analysis:
            # Если анализ уже существовал, получим его
            from datetime import datetime, timedelta
            import pytz
            user_tz = pytz.timezone(user.timezone or 'UTC')
            today_user_tz = datetime.now(user_tz).date()
            last_sunday = today_user_tz - timedelta(days=today_user_tz.weekday() + 1)
            week_start_date = last_sunday - timedelta(days=6)
            try:
                weekly_analysis = await WeeklyAnalysis.objects.aget(user=user, week_start_date=week_start_date)
            except WeeklyAnalysis.DoesNotExist:
                error_msg = 'Could not retrieve or create the WeeklyAnalysis object.'
                logger.error(error_msg)
                return {"success": False, "message": error_msg, "error": "weekly_analysis_not_found"}

        # 2. Выполнить анализ профиля
        profile_result = await user_profile_analysis_service.perform_user_profile_analysis(user)
        if not profile_result.get('success'):
            error_msg = f'Profile Analysis failed: {profile_result.get("message", "Unknown error")}'
            logger.error(error_msg)
            # Продолжаем, даже если анализ профиля не удался, чтобы попробовать анализ изменений

        # 3. Выполнить анализ изменений профиля
        changes_result = await perform_profile_change_analysis(user, weekly_analysis, num_snapshots)
        if not changes_result.get('success'):
            error_msg = f'Profile Change Analysis failed: {changes_result.get("message", "Unknown error")}'
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "error": changes_result.get("error")}

        success_msg = (
            f'Successfully completed weekly analysis and profile change analysis for user {user.username} (ID: {user.telegram_id}). '
            f'WeeklyAnalysis ID: {weekly_analysis.id}'
        )
        logger.info(success_msg)
        return {"success": True, "message": success_msg, "error": None}
