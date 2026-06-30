"""Run dedicated MAX bot runtime coordinator."""

import asyncio

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from bot.transports.max.runtime import MaxTransportCoordinator


class Command(BaseCommand):
    help = 'Запуск выделенного MAX runtime (polling/webhook coordinator)'

    def handle(self, *args, **options):
        if not getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
            raise CommandError('MAX_TRANSPORT_ENABLED=false. Включите флаг для запуска MAX runtime.')

        call_command('check_max_bot_config')

        stop_event = asyncio.Event()

        async def _runner() -> None:
            coordinator = MaxTransportCoordinator()
            await coordinator.run(stop_event)

        self.stdout.write(self.style.SUCCESS('Starting dedicated MAX runtime...'))
        try:
            asyncio.run(_runner())
        except KeyboardInterrupt:
            stop_event.set()
            self.stdout.write(self.style.SUCCESS('MAX runtime stopped by user'))
