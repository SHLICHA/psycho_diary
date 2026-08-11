"""Tests for AccountMergeService data merge after email confirm."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from diary.models import CombinedDiaryEntry, DiaryEntry
from users.models import EmailMergeRequest, User
from users.services.account_merge_service import AccountMergeService
from users.services.email_merge_service import EmailMergeService


pytestmark = pytest.mark.django_db


def _make_users(*, tg_entries=0, max_entries=0):
    target = User.objects.create_user(
        username='merge_target_tg',
        email='shared-merge@example.com',
        password='testpass123',
        telegram_id=8110001,
        max_id=None,
        token_balance=10,
        is_premium=True,
        premium_expires_at=timezone.now() + timedelta(days=5),
        language='ru',
        timezone='UTC',
        is_onboarding_completed=True,
    )
    requester = User.objects.create_user(
        username='merge_requester_max',
        email='',
        telegram_id=None,
        max_id=9110001,
        token_balance=7,
        is_premium=True,
        premium_expires_at=timezone.now() + timedelta(days=3),
        language='ru',
        timezone='UTC',
        is_onboarding_completed=True,
    )
    for i in range(tg_entries):
        DiaryEntry.objects.create(
            user=target,
            text=f'tg entry {i}',
            language='ru',
            word_count=2,
        )
    for i in range(max_entries):
        DiaryEntry.objects.create(
            user=requester,
            text=f'max entry {i}',
            language='ru',
            word_count=2,
        )
    return target, requester


def _confirm_both(requester, target, email='shared-merge@example.com'):
    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester,
        email=email,
        source_platform='max',
        source_context='profile_edit',
    )
    EmailMergeService.confirm_merge_request_by_id(requester, merge_request.id)
    result = EmailMergeService.confirm_target_transport_by_request_id(
        target_user=target,
        merge_request_id=merge_request.id,
        approve=True,
    )
    merge_request.refresh_from_db()
    return result, merge_request


@pytest.fixture
def execute_enabled(settings):
    settings.EMAIL_MERGE_EXECUTE_ENABLED = True
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    settings.MAX_TRANSPORT_ENABLED = False


def test_merge_prefers_account_with_more_diary_entries(execute_enabled):
    target, requester = _make_users(tg_entries=0, max_entries=3)

    with patch('django.db.transaction.on_commit', side_effect=lambda fn, using=None: fn()):
        with patch('users.services.account_merge_service.AccountMergeService._schedule_post_merge_jobs'):
            result, merge_request = _confirm_both(requester, target)

    assert result.status == 'merged'
    assert merge_request.status == 'merged'

    survivor = User.objects.get(id=merge_request.metadata['survivor_user_id'])
    donor = User.objects.get(id=merge_request.metadata['donor_user_id'])

    assert survivor.id == requester.id
    assert survivor.telegram_id == 8110001
    assert survivor.max_id == 9110001
    assert survivor.token_balance == 17
    assert survivor.is_premium is True
    assert survivor.premium_expires_at > timezone.now() + timedelta(days=5)

    assert DiaryEntry.objects.filter(user=survivor).count() == 3
    assert donor.deletion_status == 'anonymized'
    assert donor.telegram_id is None
    assert donor.max_id is None
    assert donor.username.startswith('merged_')


def test_merge_transfers_profile_package_without_rebuild_when_one_side_empty(execute_enabled):
    target, requester = _make_users(tg_entries=2, max_entries=0)
    requester.personality_description = 'MAX profile text'
    requester.life_facts = ['fact_a']
    requester.save(update_fields=['personality_description', 'life_facts'])

    with patch('django.db.transaction.on_commit', side_effect=lambda fn, using=None: fn()):
        with patch('users.services.account_merge_service.AccountMergeService._schedule_post_merge_jobs') as schedule:
            result, merge_request = _confirm_both(requester, target)

    assert result.status == 'merged'
    survivor = User.objects.get(id=merge_request.metadata['survivor_user_id'])
    assert survivor.personality_description == 'MAX profile text'
    assert survivor.life_facts == ['fact_a']
    assert merge_request.metadata.get('rebuild_profile') is False
    schedule.assert_called_once()
    assert schedule.call_args.args[0].rebuild_profile is False


def test_merge_marks_rebuild_when_both_have_profile(execute_enabled):
    target, requester = _make_users(tg_entries=1, max_entries=1)
    target.personality_description = 'TG profile'
    target.save(update_fields=['personality_description'])
    requester.personality_description = 'MAX profile'
    requester.save(update_fields=['personality_description'])

    with patch('django.db.transaction.on_commit', side_effect=lambda fn, using=None: fn()):
        with patch('users.services.account_merge_service.AccountMergeService._schedule_post_merge_jobs') as schedule:
            result, merge_request = _confirm_both(requester, target)

    assert result.status == 'merged'
    survivor = User.objects.get(id=merge_request.metadata['survivor_user_id'])
    assert survivor.personality_description == ''
    assert merge_request.metadata.get('rebuild_profile') is True
    assert schedule.call_args.args[0].rebuild_profile is True


def test_merge_fails_on_conflicting_telegram_ids(execute_enabled):
    target, requester = _make_users(tg_entries=1, max_entries=0)
    requester.telegram_id = 8220002
    requester.save(update_fields=['telegram_id'])

    with patch('users.services.account_merge_service.AccountMergeService._schedule_post_merge_jobs'):
        result, merge_request = _confirm_both(requester, target)

    assert result.status == 'merge_failed'
    assert result.code == 'conflicting_telegram_ids'
    assert merge_request.status == 'merge_failed'
    target.refresh_from_db()
    requester.refresh_from_db()
    assert target.deletion_status == 'active'
    assert requester.deletion_status == 'active'


def test_overlapping_combined_entries_deleted_for_reanalysis(execute_enabled):
    target, requester = _make_users(tg_entries=1, max_entries=1)
    today = timezone.now().date()
    CombinedDiaryEntry.objects.create(
        user=target,
        date=today,
        text='tg day',
        entry_count=1,
    )
    CombinedDiaryEntry.objects.create(
        user=requester,
        date=today,
        text='max day',
        entry_count=1,
    )

    with patch('django.db.transaction.on_commit', side_effect=lambda fn, using=None: fn()):
        with patch('users.services.account_merge_service.AccountMergeService._schedule_post_merge_jobs') as schedule:
            result, merge_request = _confirm_both(requester, target)

    assert result.status == 'merged'
    survivor_id = merge_request.metadata['survivor_user_id']
    assert not CombinedDiaryEntry.objects.filter(user_id=survivor_id, date=today).exists()
    assert today.isoformat() in merge_request.metadata.get('reanalyze_dates', [])
    assert today.isoformat() in schedule.call_args.args[0].reanalyze_dates


def test_purge_only_merged_anonymized_users(execute_enabled):
    merged = User.objects.create_user(
        username='merged_999',
        email='',
        telegram_id=None,
        deletion_status='anonymized',
        deleted_at=timezone.now() - timedelta(days=31),
    )
    gdpr = User.objects.create_user(
        username='deleted_user_123',
        email='',
        telegram_id=None,
        deletion_status='anonymized',
        deleted_at=timezone.now() - timedelta(days=31),
    )
    stats = AccountMergeService.purge_due_merged_users()
    assert stats['purged'] == 1
    assert not User.objects.filter(id=merged.id).exists()
    assert User.objects.filter(id=gdpr.id).exists()


def test_execute_disabled_leaves_confirmed(settings):
    settings.EMAIL_MERGE_EXECUTE_ENABLED = False
    target, requester = _make_users(tg_entries=1, max_entries=0)
    result, merge_request = _confirm_both(requester, target)
    assert result.status == 'confirmed'
    merge_request.refresh_from_db()
    assert merge_request.status == 'confirmed'
