"""Celery tasks for post-merge day reanalysis, profile rebuild, and donor purge."""

from __future__ import annotations

import logging
from datetime import date

from asgiref.sync import async_to_sync
from celery import shared_task

from users.models import User

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def post_merge_reanalyze_week_task(self, user_id: int, date_iso_list: list[str]) -> dict:
    """Переанализ дней последней календарной недели после merge."""
    from diary.services.full_day_analysis_service import full_day_analysis_service

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}

    if user.deletion_status != 'active':
        return {'status': 'skipped', 'reason': 'user_not_active', 'user_id': user_id}

    results = []
    analyze = async_to_sync(full_day_analysis_service.perform_full_day_analysis)
    for raw in date_iso_list or []:
        try:
            target = date.fromisoformat(raw)
        except ValueError:
            results.append({'date': raw, 'success': False, 'error': 'bad_date'})
            continue
        try:
            outcome = analyze(user, target)
            results.append({'date': raw, 'success': bool(outcome.get('success')), 'detail': outcome.get('message')})
        except Exception as exc:
            logger.exception('post_merge day reanalysis failed user=%s date=%s', user_id, raw)
            results.append({'date': raw, 'success': False, 'error': str(exc)})

    return {'status': 'done', 'user_id': user_id, 'results': results}


@shared_task(bind=True, max_retries=3)
def post_merge_rebuild_profile_task(self, user_id: int) -> dict:
    """Пересборка психологического профиля, когда оба аккаунта имели профиль."""
    from diary.services.user_profile_analysis_service import user_profile_analysis_service

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}

    if user.deletion_status != 'active':
        return {'status': 'skipped', 'reason': 'user_not_active', 'user_id': user_id}

    try:
        outcome = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)(user)
        return {
            'status': 'done' if outcome.get('success') else 'failed',
            'user_id': user_id,
            'outcome': {k: v for k, v in outcome.items() if k != 'user'},
        }
    except Exception as exc:
        logger.exception('post_merge profile rebuild failed user=%s', user_id)
        raise self.retry(exc=exc, countdown=60)


@shared_task
def purge_merged_users_task() -> dict:
    """Hard-delete merged_* anonymized donors older than 30 days."""
    from users.services.account_merge_service import AccountMergeService

    return AccountMergeService.purge_due_merged_users()
