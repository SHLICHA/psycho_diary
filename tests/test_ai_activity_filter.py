import asyncio
import pytest
from datetime import timedelta
from django.core.exceptions import SynchronousOnlyOperation
from django.test import override_settings
from django.utils import timezone

from diary.models import UserActivity
from diary.tasks.ai_activity_filter import (
    ais_user_active_for_ai_tasks,
    is_user_active_for_ai_tasks,
)
from users.models import User


@pytest.mark.django_db
def test_is_user_active_for_ai_tasks_uses_recent_user_activity():
    user = User.objects.create(username='activity_user', telegram_id=12345, auto_analysis_enabled=True)

    assert not is_user_active_for_ai_tasks(user)

    old_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
    old_activity.timestamp = timezone.now() - timedelta(days=31)
    old_activity.save(update_fields=['timestamp'])
    assert not is_user_active_for_ai_tasks(user)

    recent_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
    recent_activity.timestamp = timezone.now() - timedelta(days=10)
    recent_activity.save(update_fields=['timestamp'])
    assert is_user_active_for_ai_tasks(user)


@pytest.mark.django_db
def test_is_user_active_for_ai_tasks_uses_recent_last_entry_when_no_user_activity_exists():
    user = User.objects.create(username='activity_user_last_entry', telegram_id=12346, auto_analysis_enabled=True)
    user.created_at = timezone.now() - timedelta(days=40)
    user.save(update_fields=['created_at'])

    user.last_entry = timezone.now() - timedelta(days=10)
    user.save(update_fields=['last_entry'])

    assert is_user_active_for_ai_tasks(user)


@pytest.mark.django_db
def test_is_user_active_for_ai_tasks_respects_configured_inactivity_days():
    user = User.objects.create(username='activity_user_config', telegram_id=12347, auto_analysis_enabled=True)

    with override_settings(AI_INACTIVITY_DAYS=7):
        recent_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
        recent_activity.timestamp = timezone.now() - timedelta(days=6)
        recent_activity.save(update_fields=['timestamp'])
        assert is_user_active_for_ai_tasks(user)

        UserActivity.objects.filter(user=user).delete()
        old_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
        old_activity.timestamp = timezone.now() - timedelta(days=8)
        old_activity.save(update_fields=['timestamp'])
        assert not is_user_active_for_ai_tasks(user)


@pytest.mark.django_db(transaction=True)
def test_ais_user_active_for_ai_tasks_works_inside_asyncio_run():
    user = User.objects.create(username='activity_user_async', telegram_id=12348, auto_analysis_enabled=True)
    recent_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
    recent_activity.timestamp = timezone.now() - timedelta(days=5)
    recent_activity.save(update_fields=['timestamp'])

    async def _check():
        with pytest.raises(SynchronousOnlyOperation):
            is_user_active_for_ai_tasks(user)
        assert await ais_user_active_for_ai_tasks(user) is True

    asyncio.run(_check())


@pytest.mark.django_db(transaction=True)
def test_ais_user_active_for_ai_tasks_inactive_user():
    user = User.objects.create(username='activity_user_async_inactive', telegram_id=12349, auto_analysis_enabled=True)

    async def _check():
        assert await ais_user_active_for_ai_tasks(user) is False

    asyncio.run(_check())
