# /home/shlicha/psycho_diary/core/management/commands/run_weekly_analysis.py
"""
Django management команда для ручного запуска еженедельного анализа,
анализа профиля и анализа изменений профиля пользователя.
"""

import asyncio
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from diary.services.weekly_analysis_service import weekly_analysis_service
from diary.services.user_profile_analysis_service import user_profile_analysis_service
# Импортируем новый сервис для анализа изменений
from diary.services.user_profile_change_analysis_service import perform_profile_change_analysis
from diary.models import WeeklyAnalysis  # Нужно получить объект WeeklyAnalysis для передачи в change_analysis

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Запуск еженедельного анализа, анализа профиля и анализа изменений профиля для указанного пользователя'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int, nargs='?', default=None, help='Telegram ID пользователя (legacy режим)')
        parser.add_argument('--user-id', type=int, default=None, help='Внутренний user ID (users.User.id)')

    def handle(self, *args, **options):
        telegram_id = options.get('telegram_id')
        user_id = options.get('user_id')

        if user_id is not None and telegram_id is not None:
            self.stdout.write(self.style.ERROR('Используйте либо telegram_id, либо --user-id, но не оба параметра одновременно.'))
            return

        if user_id is None and telegram_id is None:
            self.stdout.write(self.style.ERROR('Нужно передать telegram_id или --user-id.'))
            return

        if user_id is not None:
            self.stdout.write(f'Запуск еженедельного анализа для пользователя с user_id: {user_id}')
        else:
            self.stdout.write(f'Запуск еженедельного анализа для пользователя с Telegram ID: {telegram_id}')

        try:
            if user_id is not None:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            if user_id is not None:
                self.stdout.write(self.style.ERROR(f'Пользователь с user_id {user_id} не найден'))
            else:
                self.stdout.write(self.style.ERROR(f'Пользователь с Telegram ID {telegram_id} не найден'))
            return

        try:
            # --- 1. Запуск еженедельного анализа ---
            self.stdout.write('-> Выполнение еженедельного анализа...')
            weekly_result = asyncio.run(weekly_analysis_service.perform_weekly_analysis(user))

            weekly_analysis_obj = weekly_result.get('weekly_analysis')
            weekly_analysis_success = weekly_result.get('success', False)

            if weekly_analysis_success:
                self.stdout.write(
                    self.style.SUCCESS(f'-> Еженедельный анализ успешно завершен для {user.username} ({user.telegram_id})')
                )
                if weekly_analysis_obj:
                    self.stdout.write(
                        f"   Создан/обновлён анализ недели ID: {weekly_analysis_obj.id}"
                    )
                else:
                    # Это маловероятно, если success=True, но на всякий случай
                    self.stdout.write(
                        self.style.WARNING(f'   Предупреждение: weekly_result.success=True, но weekly_analysis_obj отсутствует.')
                    )
                    return  # Прерываем, если объект недоступен
            else:
                self.stdout.write(
                    self.style.ERROR(f'-> Ошибка при еженедельном анализе: {weekly_result["message"]}')
                )
                # Останавливаем выполнение, если еженедельный анализ не удался
                return  # <-- Добавлено: остановка при неудаче


            # --- 2. Запуск анализа профиля пользователя ---
            # Выполняется только если еженедельный анализ успешен
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
                # Продолжаем выполнение, даже если анализ профиля не удался, так как change_analysis может быть полезен


            # --- 3. Запуск анализа изменений профиля ---
            # Выполняется только если еженедельный анализ успешен (и weekly_analysis_obj доступен)
            self.stdout.write('-> Выполнение анализа изменений профиля...')
            # Вызываем новый сервис, передав ему user, weekly_analysis_obj и количество слепков
            # perform_profile_change_analysis - это асинхронная функция
            change_result = asyncio.run(perform_profile_change_analysis(user, weekly_analysis_obj, num_snapshots_to_compare=3))

            if change_result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f'-> Анализ изменений профиля успешно завершен для {user.username} ({user.telegram_id})')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'-> Ошибка при анализе изменений профиля: {change_result["message"]}')
                )


        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Команда остановлена с ошибкой: {e}')
            )
            logger.error(f"Критическая ошибка в команде run_weekly_analysis для пользователя {user.id}: {e}", exc_info=True)
            raise  # Возбуждаем исключение дальше, чтобы получить полный трейсбек в случае необходимости