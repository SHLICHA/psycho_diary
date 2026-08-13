"""Unit tests for diary.services.activity_service."""

from unittest.mock import AsyncMock

import pytest

from diary.models import UserActivity
from diary.services.activity_service import (
    is_allowed_activity_type,
    record_max_dispatch_activity,
    record_user_activity,
    resolve_max_activity,
)
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def activity_user(db):
    return User.objects.create_user(
        username='activity_svc',
        email='activity_svc@example.com',
        max_id=990001,
        language='ru',
    )


def test_allowlist_rejects_noise_types():
    assert is_allowed_activity_type('entry_created')
    assert is_allowed_activity_type('onboarding')
    assert not is_allowed_activity_type('help_open')
    assert not is_allowed_activity_type('entry_process')
    assert not is_allowed_activity_type('main_menu')


def test_resolve_max_activity_mapping():
    assert resolve_max_activity('new_entry_process') == ('entry_created', False)
    assert resolve_max_activity('task_feelings') == ('task_completed', False)
    assert resolve_max_activity('main_menu') == (None, True)
    assert resolve_max_activity('rate_analysis', error=True) == (None, False)
    assert resolve_max_activity('rate_analysis', mode='already_rated') == (None, False)
    assert resolve_max_activity('start', referral_applied=True) == ('referral', False)
    assert resolve_max_activity('confirm_timezone') == ('onboarding', False)


@pytest.mark.asyncio
async def test_record_user_activity_writes_platform_and_touches_last(activity_user):
    before = activity_user.last_activity
    ok = await record_user_activity(
        activity_user,
        'entry_created',
        platform='max',
        metadata={'handled': 'new_entry_process'},
    )
    assert ok is True
    await activity_user.arefresh_from_db()
    assert activity_user.last_activity is not None
    if before:
        assert activity_user.last_activity >= before

    row = await UserActivity.objects.filter(user=activity_user).afirst()
    assert row is not None
    assert row.activity_type == 'entry_created'
    assert row.metadata.get('platform') == 'max'
    assert row.metadata.get('handled') == 'new_entry_process'


@pytest.mark.asyncio
async def test_record_skips_disallowed_type_but_can_touch_only(activity_user):
    ok = await record_user_activity(
        activity_user,
        'help_open',
        platform='telegram',
    )
    assert ok is True  # last_activity updated
    assert await UserActivity.objects.filter(user=activity_user).acount() == 0

    ok_touch = await record_user_activity(
        activity_user,
        None,
        platform='max',
        touch_only=True,
    )
    assert ok_touch is True
    assert await UserActivity.objects.filter(user=activity_user).acount() == 0


@pytest.mark.asyncio
async def test_record_swallows_db_errors(activity_user, mocker):
    mocker.patch(
        'diary.models.UserActivity.objects.acreate',
        new=AsyncMock(side_effect=RuntimeError('db down')),
    )
    ok = await record_user_activity(
        activity_user,
        'entry_created',
        platform='telegram',
        touch_last_activity=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_record_max_dispatch_activity(activity_user):
    ok = await record_max_dispatch_activity(
        activity_user,
        {'ok': True, 'handled': 'therapy_message'},
        event_type='message_created',
    )
    assert ok is True
    row = await UserActivity.objects.filter(user=activity_user).afirst()
    assert row.activity_type == 'chat'
    assert row.metadata['platform'] == 'max'


@pytest.mark.asyncio
async def test_record_max_dispatch_touch_only_main_menu(activity_user):
    activity_user.last_activity = None
    await activity_user.asave(update_fields=['last_activity'])

    ok = await record_max_dispatch_activity(
        activity_user,
        {'ok': True, 'handled': 'main_menu'},
        event_type='message_callback',
        payload='main_menu',
    )
    assert ok is True
    await activity_user.arefresh_from_db()
    assert activity_user.last_activity is not None
    assert await UserActivity.objects.filter(user=activity_user).acount() == 0
