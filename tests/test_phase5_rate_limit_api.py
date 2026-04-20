"""Phase 5 tests: API rate limiting for exposed endpoints."""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


LOW_RATE_REST_FRAMEWORK = {
    **settings.REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
        'auth': '2/minute',
        'refresh': '2/minute',
        'link_generation': '1/minute',
        'monitoring': '2/minute',
        'monitoring_heavy': '2/minute',
        'entry_mutation': '2/minute',
        'task_mutation': '2/minute',
    },
}


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username='phase5_rate_user',
        email='phase5-rate@example.com',
        password='testpass123',
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(auth_user)
    return str(refresh.access_token)


@override_settings(REST_FRAMEWORK=LOW_RATE_REST_FRAMEWORK)
def test_login_rate_limit_returns_unified_429(api_client, auth_user):
    payload = {
        'email': auth_user.email,
        'password': 'testpass123',
    }

    first = api_client.post('/api/v1/auth/login/', payload, format='json')
    second = api_client.post('/api/v1/auth/login/', payload, format='json')
    third = api_client.post('/api/v1/auth/login/', payload, format='json')

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.data['error']['code'] == 'rate_limit_exceeded'
    assert third.data['error']['message']


@override_settings(REST_FRAMEWORK=LOW_RATE_REST_FRAMEWORK)
def test_monitoring_rate_limit_returns_unified_429(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')

    first = api_client.get('/api/v1/auth/monitoring/metrics/')
    second = api_client.get('/api/v1/auth/monitoring/metrics/')
    third = api_client.get('/api/v1/auth/monitoring/metrics/')

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.data['error']['code'] == 'rate_limit_exceeded'


@override_settings(REST_FRAMEWORK=LOW_RATE_REST_FRAMEWORK)
def test_entry_create_rate_limit_blocks_repeated_posts(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')

    first = api_client.post(
        '/api/v1/entries/',
        {'text': 'First throttled entry', 'language': 'ru'},
        format='json',
    )
    second = api_client.post(
        '/api/v1/entries/',
        {'text': 'Second throttled entry', 'language': 'ru'},
        format='json',
    )
    third = api_client.post(
        '/api/v1/entries/',
        {'text': 'Third throttled entry', 'language': 'ru'},
        format='json',
    )

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_201_CREATED
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.data['error']['code'] == 'rate_limit_exceeded'


@override_settings(REST_FRAMEWORK=LOW_RATE_REST_FRAMEWORK)
def test_task_create_rate_limit_blocks_repeated_posts(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')

    payload = {
        'title': 'Phase 5 task',
        'description': 'Rate-limited task creation',
        'type': 'daily',
        'status': 'pending',
    }

    first = api_client.post('/api/v1/tasks/', payload, format='json')
    second = api_client.post('/api/v1/tasks/', payload, format='json')
    third = api_client.post('/api/v1/tasks/', payload, format='json')

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_201_CREATED
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.data['error']['code'] == 'rate_limit_exceeded'


@override_settings(REST_FRAMEWORK=LOW_RATE_REST_FRAMEWORK)
def test_refresh_rate_limit_returns_unified_429(api_client, auth_user):
    login = api_client.post(
        '/api/v1/auth/login/',
        {
            'email': auth_user.email,
            'password': 'testpass123',
        },
        format='json',
    )
    assert login.status_code == status.HTTP_200_OK
    refresh_token = login.data['refresh']

    first = api_client.post('/api/v1/auth/refresh/', {'refresh': refresh_token}, format='json')
    second = api_client.post('/api/v1/auth/refresh/', {'refresh': refresh_token}, format='json')
    third = api_client.post('/api/v1/auth/refresh/', {'refresh': refresh_token}, format='json')

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.data['error']['code'] == 'rate_limit_exceeded'


@override_settings(MONITORING_REQUIRE_PRIVILEGED=True)
def test_monitoring_stats_denied_for_regular_user_when_strict_mode(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')

    response = api_client.get('/api/v1/auth/monitoring/stats/')

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data['error']['code'] == 'permission_denied'


@override_settings(MONITORING_REQUIRE_PRIVILEGED=True)
def test_monitoring_stats_allowed_for_superuser_when_strict_mode(api_client):
    admin = User.objects.create_superuser(
        username='phase5_admin',
        email='phase5-admin@example.com',
        password='testpass123',
    )
    from rest_framework_simplejwt.tokens import RefreshToken
    token = str(RefreshToken.for_user(admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    response = api_client.get('/api/v1/auth/monitoring/stats/')

    assert response.status_code == status.HTTP_200_OK