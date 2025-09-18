# /home/shlicha/psycho_diary/core/management/commands/run_weekly_analysis.py
"""
Django management команда для ручного запуска еженедельного анализа и последующего анализа профиля пользователя
"""

import asyncio
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from diary.services.weekly_analysis_service import weekly_analysis_service
# Импортируем новый сервис
from diary.services.user_profile_analysis_service import user_profile_analysis_service

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Запуск еженедельного анализа и последующего анализа профиля для указанного пользователя'

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
            # --- 1. Запуск еженедельного анализа ---
            self.stdout.write('-> Выполнение еженедельного анализа...')
            weekly_result = asyncio.run(weekly_analysis_service.perform_weekly_analysis(user))
            
            if weekly_result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f'-> Еженедельный анализ успешно завершен для {user.username} ({user.telegram_id})')
                )
                if weekly_result['weekly_analysis']:
                    self.stdout.write(
                        f"   Создан анализ недели ID: {weekly_result['weekly_analysis'].id}"
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f'-> Ошибка при еженедельном анализе: {weekly_result["message"]}')
                )
                # Можно остановиться здесь, если еженедельный анализ не удался
                # return

            # --- 2. Запуск анализа профиля пользователя (независимо от результата еженедельного) ---
            self.stdout.write('-> Выполнение анализа профиля пользователя...')
            profile_result = asyncio.run(user_profile_analysis_service.perform_user_profile_analysis(user))
            
            if profile_result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f'-> Анализ профиля пользователя успешно завершен для {user.username} ({user.telegram_id})')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'-> Ошибка при анализе профиля: {profile_result["message"]}')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Команда остановлена с ошибкой: {e}')
            )
            raise
