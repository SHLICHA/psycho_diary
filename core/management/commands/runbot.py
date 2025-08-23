"""
Django management команда для запуска бота
"""
import asyncio
import sys
import os
from django.core.management.base import BaseCommand

from bot.main import main

class Command(BaseCommand):
    help = 'Запуск Telegram бота'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting psycho diary bot...')
        )
        
        try:
            # Добавляем текущую директорию в путь поиска
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)
            sys.path.insert(0, project_root)
            asyncio.run(main())
            
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('Bot stopped by user')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Bot stopped with error: {e}')
            )
            raise