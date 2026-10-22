"""Web-access claim: bot-confirm задание/сброс пароля без SMTP."""

from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from model_bakery import baker
from rest_framework.test import APIClient

from users.models import User, WebAccessClaimRequest
from users.services.auth_token_service import create_web_access_set_password_token
from users.services.identity_policy_service import IdentityPolicyService
from users.services.web_access_claim_service import WebAccessClaimService


@pytest.fixture
def api():
    return APIClient()


def _make_user(*, email: str, telegram_id=None, max_id=None, with_password=False):
    user = baker.make(
        User,
        email=email,
        email_hash=IdentityPolicyService.build_email_hash(email),
        telegram_id=telegram_id,
        max_id=max_id,
        deletion_status='active',
    )
    if with_password:
        user.password = make_password('Str0ng!Pass9')
    else:
        user.set_unusable_password()
    user.save(update_fields=['password'])
    return user


@pytest.mark.django_db
def test_start_claim_prefers_requested_platform():
    user = _make_user(email='both@example.com', telegram_id=111, max_id=222)
    with patch.object(
        WebAccessClaimService,
        '_dispatch_bot_confirm',
        return_value={'ok': True, 'delivery': 'max'},
    ):
        result = WebAccessClaimService.start_claim(
            email='both@example.com',
            preferred_platform='max',
        )
    assert result.status == 'pending'
    assert result.platform == 'max'
    assert set(result.platforms) == {'telegram', 'max'}
    assert WebAccessClaimRequest.objects.filter(user=user, status='pending').count() == 1


@pytest.mark.django_db
def test_start_claim_allows_reset_when_password_exists():
    _make_user(email='haspw@example.com', telegram_id=333, with_password=True)
    with patch.object(
        WebAccessClaimService,
        '_dispatch_bot_confirm',
        return_value={'ok': True, 'delivery': 'telegram'},
    ):
        result = WebAccessClaimService.start_claim(email='haspw@example.com')
    assert result.status == 'pending'
    assert result.has_password is True
    assert result.claim is not None
    assert result.claim.metadata.get('purpose') == 'reset'


@pytest.mark.django_db
def test_api_claim_hides_not_found(api):
    response = api.post(
        '/api/v1/web-access/claim/',
        {'email': 'missing@example.com', 'platform': 'telegram'},
        format='json',
    )
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'accepted'
    assert body['platform'] is None
    assert body['delivery_ok'] is False


@pytest.mark.django_db
def test_api_claim_pending_when_dispatched(api):
    _make_user(email='tg@example.com', telegram_id=444)
    with patch(
        'users.services.web_access_claim_service.WebAccessClaimService._dispatch_bot_confirm',
        return_value={'ok': True, 'delivery': 'telegram'},
    ):
        response = api.post(
            '/api/v1/web-access/claim/',
            {'email': 'tg@example.com', 'platform': 'telegram'},
            format='json',
        )
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'pending'
    assert body['platform'] == 'telegram'
    assert body['delivery_ok'] is True


@pytest.mark.django_db
def test_api_set_password_issues_jwt(api):
    user = _make_user(email='setpw@example.com', telegram_id=555)
    token = create_web_access_set_password_token(user.id)
    response = api.post(
        '/api/v1/web-access/set-password/',
        {
            'token': token,
            'password': 'Str0ng!Pass9',
            'password_confirm': 'Str0ng!Pass9',
        },
        format='json',
    )
    assert response.status_code == 200
    body = response.json()
    assert 'access' in body
    assert 'refresh' in body
    user.refresh_from_db()
    assert user.has_usable_password()
    assert user.check_password('Str0ng!Pass9')
