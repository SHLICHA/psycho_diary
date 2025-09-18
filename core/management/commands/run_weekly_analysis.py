# /home/shlicha/psycho_diary/core/management/commands/run_weekly_analysis.py
"""
Django management команда для ручного запуска еженедельного анализа
"""

import asyncio
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from diary.services.weekly_analysis_service import weekly_analysis_service

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Запуск еженедельного анализа для указанного пользователя'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int, help='Telegram ID пользователя')

    def handle(self, *args, **options):
        telegram_id = options['telegram_id']
        self.stdout.write(f'Запуск еженедельного анализа для пользователя с Telegram ID: {telegram_id}')

        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Пользователь с Telegram ID {telegram_id} не найден')
            )
            return

        try:
            # Запуск асинхронной функции внутри синхронной команды
            result = asyncio.run(weekly_analysis_service.perform_weekly_analysis(user))
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f'Анализ успешно завершен для {user.username} ({user.telegram_id})')
                )
                if result['weekly_analysis']:
                    self.stdout.write(
                        f"Создан анализ недели ID: {result['weekly_analysis'].id}"
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Ошибка при анализе: {result["message"]}')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Команда остановлена с ошибкой: {e}')
            )
            raise
