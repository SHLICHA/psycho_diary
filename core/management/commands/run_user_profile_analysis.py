"""Manual command to run only user profile analysis with detailed logging."""

import asyncio
import json
import logging
from time import perf_counter
from typing import Any, Dict

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError

from core.profile_field_utils import PERSONAL_LIST_FIELDS
from diary.services.user_profile_analysis_service import user_profile_analysis_service
from users.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run only user profile analysis for a user with detailed before/after logs.'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int, help='Telegram ID of the user')
        parser.add_argument(
            '--compact-log',
            action='store_true',
            help='Print compact summary only (without per-field details)',
        )

    def handle(self, *args, **options):
        telegram_id = options['telegram_id']
        detailed = not options['compact_log']

        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist as exc:
            raise CommandError(f'User with telegram_id {telegram_id} does not exist.') from exc

        self.stdout.write(
            self.style.WARNING(
                f'Starting profile analysis for user {user.username} (ID: {user.telegram_id})'
            )
        )

        started = perf_counter()
        try:
            result = asyncio.run(self.async_handle(user, detailed=detailed))
        except Exception as exc:
            logger.error('Error during profile analysis command execution', exc_info=True)
            raise CommandError(f'Error during profile analysis: {exc}') from exc

        elapsed = perf_counter() - started
        self.stdout.write(f'Elapsed: {elapsed:.2f}s')

        if detailed and result.get('before') and result.get('after'):
            self._print_stats_block('BEFORE', result['before'])
            self._print_stats_block('AFTER', result['after'])
            self._print_delta_block(result['before'], result['after'])

        if result.get('success'):
            self.stdout.write(self.style.SUCCESS(result['message']))
            return

        raise CommandError(result.get('message', 'Profile analysis command failed'))

    async def async_handle(self, user: User, detailed: bool = True) -> Dict[str, Any]:
        before = self._collect_stats(user)
        logger.info(
            '[run_user_profile_analysis] BEFORE user=%s description_chars=%s total_items=%s',
            user.telegram_id,
            before['personality_description_chars'],
            before['personal_items_total'],
        )

        profile_result = await user_profile_analysis_service.perform_user_profile_analysis(user)
        await sync_to_async(user.refresh_from_db)()

        after = self._collect_stats(user)
        logger.info(
            '[run_user_profile_analysis] AFTER user=%s success=%s error=%s description_chars=%s total_items=%s',
            user.telegram_id,
            profile_result.get('success', False),
            profile_result.get('error'),
            after['personality_description_chars'],
            after['personal_items_total'],
        )

        message = profile_result.get('message') or 'Profile analysis finished.'
        if profile_result.get('success'):
            message = f'Profile analysis completed successfully: {message}'
        else:
            message = f'Profile analysis failed: {message}'

        result: Dict[str, Any] = {
            'success': bool(profile_result.get('success')),
            'message': message,
            'error': profile_result.get('error'),
        }
        if detailed:
            result['before'] = before
            result['after'] = after
        return result

    def _collect_stats(self, user: User) -> Dict[str, Any]:
        per_field_counts: Dict[str, int] = {}
        for field_name in PERSONAL_LIST_FIELDS:
            raw = getattr(user, field_name, None)
            per_field_counts[field_name] = len(raw) if isinstance(raw, list) else 0

        compressed = user.compressed_psych_profile or {}
        compressed_json = json.dumps(compressed, ensure_ascii=False, separators=(',', ':'))

        return {
            'personality_description_chars': len((user.personality_description or '').strip()),
            'compressed_profile_chars': len(compressed_json),
            'personal_items_total': sum(per_field_counts.values()),
            'personal_items_per_field': per_field_counts,
        }

    def _print_stats_block(self, title: str, stats: Dict[str, Any]) -> None:
        self.stdout.write(self.style.WARNING(f'[{title}]'))
        self.stdout.write(
            '  description_chars={description} compressed_chars={compressed} total_personal_items={total}'.format(
                description=stats['personality_description_chars'],
                compressed=stats['compressed_profile_chars'],
                total=stats['personal_items_total'],
            )
        )
        per_field = stats.get('personal_items_per_field', {})
        if per_field:
            fields_view = ', '.join(f'{name}={count}' for name, count in per_field.items())
            self.stdout.write(f'  per_field: {fields_view}')

    def _print_delta_block(self, before: Dict[str, Any], after: Dict[str, Any]) -> None:
        self.stdout.write(self.style.WARNING('[DELTA]'))
        self.stdout.write(
            '  description_chars_delta={desc_delta:+d} compressed_chars_delta={compressed_delta:+d} total_personal_items_delta={items_delta:+d}'.format(
                desc_delta=after['personality_description_chars'] - before['personality_description_chars'],
                compressed_delta=after['compressed_profile_chars'] - before['compressed_profile_chars'],
                items_delta=after['personal_items_total'] - before['personal_items_total'],
            )
        )
