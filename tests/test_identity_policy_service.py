import pytest

from users.models import User
from users.services.identity_policy_service import IdentityPolicyService


pytestmark = pytest.mark.django_db


def test_resolve_email_claim_available_when_email_not_used():
    resolution = IdentityPolicyService.resolve_email_claim('free@example.com')

    assert resolution.status == 'available'
    assert resolution.code is None
    assert resolution.matched_user_id is None


def test_resolve_email_claim_conflict_for_register_flow():
    existing = User.objects.create_user(
        username='existing_web',
        email='exists@example.com',
        password='testpass123',
        telegram_id=None,
    )

    resolution = IdentityPolicyService.resolve_email_claim('exists@example.com')

    assert resolution.status == 'conflict'
    assert resolution.code == 'email_already_exists'
    assert resolution.matched_user_id == existing.id


def test_resolve_email_claim_self_for_same_user():
    existing = User.objects.create_user(
        username='owner',
        email='owner@example.com',
        password='testpass123',
        telegram_id=100200300,
    )

    resolution = IdentityPolicyService.resolve_email_claim(
        'owner@example.com',
        requester_user=existing,
    )

    assert resolution.status == 'self'
    assert resolution.code is None
    assert resolution.matched_user_id == existing.id


def test_resolve_email_claim_conflict_for_complete_registration():
    web_user = User.objects.create_user(
        username='web_user',
        email='web-user@example.com',
        password='testpass123',
        telegram_id=None,
    )
    telegram_user = User.objects.create_user(
        username='tg_user',
        email='',
        telegram_id=999888777,
    )

    resolution = IdentityPolicyService.resolve_email_claim(
        'web-user@example.com',
        requester_user=telegram_user,
    )

    assert resolution.status == 'conflict'
    assert resolution.code == 'email_already_exists'
    assert resolution.matched_user_id == web_user.id
