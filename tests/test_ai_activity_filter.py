import pytest
from datetime import timedelta
from django.test import override_settings
from django.utils import timezone

from diary.models import UserActivity
from diary.tasks.ai_activity_filter import is_user_active_for_ai_tasks
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
def test_is_user_active_for_ai_tasks_respects_configured_inactivity_days():
    user = User.objects.create(username='activity_user_config', telegram_id=12346, auto_analysis_enabled=True)

    with override_settings(AI_INACTIVITY_DAYS=7):
        recent_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
        recent_activity.timestamp = timezone.now() - timedelta(days=6)
        recent_activity.save(update_fields=['timestamp'])
        assert is_user_active_for_ai_tasks(user)

        old_activity = UserActivity.objects.create(user=user, activity_type='entry_created')
        old_activity.timestamp = timezone.now() - timedelta(days=8)
        old_activity.save(update_fields=['timestamp'])
        assert is_user_active_for_ai_tasks(user)
