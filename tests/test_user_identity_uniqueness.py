"""Tests for unique max_id / email_hash identity constraints."""

import pytest
from django.db import IntegrityError

from users.models import User
from users.services.identity_policy_service import IdentityPolicyService


pytestmark = pytest.mark.django_db


def test_user_save_sets_null_email_hash_when_email_empty():
    user = User.objects.create_user(
        username='no_email_user',
        email='',
        telegram_id=6100001,
    )
    user.refresh_from_db()
    assert user.email_hash is None


def test_multiple_users_without_email_are_allowed():
    User.objects.create_user(username='no_email_a', email='', telegram_id=6100002)
    User.objects.create_user(username='no_email_b', email='', telegram_id=6100003)
    assert User.objects.filter(email_hash__isnull=True).count() >= 2


def test_duplicate_email_hash_rejected():
    User.objects.create_user(
        username='email_owner_a',
        email='unique-hash@example.com',
        password='testpass123',
        telegram_id=None,
    )
    with pytest.raises(IntegrityError):
        User.objects.create_user(
            username='email_owner_b',
            email='unique-hash@example.com',
            password='testpass123',
            telegram_id=6100004,
        )


def test_duplicate_max_id_rejected():
    User.objects.create_user(
        username='max_owner_a',
        email='',
        telegram_id=None,
        max_id=7100001,
    )
    with pytest.raises(IntegrityError):
        User.objects.create_user(
            username='max_owner_b',
            email='',
            telegram_id=None,
            max_id=7100001,
        )


def test_identity_policy_uses_unique_email_hash_lookup():
    existing = User.objects.create_user(
        username='policy_owner',
        email='policy@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=7100002,
    )
    resolution = IdentityPolicyService.resolve_email_claim('policy@example.com')
    assert resolution.status == 'conflict'
    assert resolution.matched_user_id == existing.id
    assert existing.email_hash == IdentityPolicyService.build_email_hash('policy@example.com')
