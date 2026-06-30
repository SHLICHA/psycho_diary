"""Validate MAX bot runtime configuration."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bot.transports.max.preflight import collect_preflight_errors, normalize_transport_mode


class Command(BaseCommand):
    help = 'Проверка конфигурации MAX runtime перед запуском бота'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            choices=['polling', 'webhook'],
            help='Принудительно проверить конфиг в указанном режиме (иначе берется MAX_TRANSPORT_MODE).',
        )

    def handle(self, *args, **options):
        mode = normalize_transport_mode(options.get('mode') or getattr(settings, 'MAX_TRANSPORT_MODE', 'polling'))
        errors = collect_preflight_errors(settings, mode=mode)

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(f'MAX preflight error: {error}'))
            raise CommandError('MAX bot configuration is invalid')

        self.stdout.write(self.style.SUCCESS(f'MAX config is valid. Mode: {mode}'))
