import pytest
from types import SimpleNamespace
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from users.models import User


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def test_max_webhook_get_health_defaults_polling(api_client, settings):
    settings.MAX_TRANSPORT_ENABLED = False
    settings.MAX_TRANSPORT_MODE = 'polling'

    response = api_client.get('/api/max/webhook/')

    assert response.status_code == status.HTTP_200_OK
    assert response.data['ok'] is True
    assert response.data['transport_enabled'] is False
    assert response.data['transport_mode'] == 'polling'


def test_max_webhook_post_ignores_non_message_callback(api_client):
    response = api_client.post('/api/max/webhook/', {'type': 'message_new'}, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.data['ok'] is True
    assert response.data['ignored'] is True


def test_max_webhook_post_processes_merge_target_yes(api_client):
    target_user = User.objects.create_user(
        username='max_target_webhook',
        email='max-webhook@example.com',
        max_id=770001,
    )

    with patch('api.views.EmailMergeService.confirm_target_transport_by_request_id') as mock_confirm:
        mock_confirm.return_value = SimpleNamespace(status='confirmed', code=None)

        response = api_client.post(
            '/api/max/webhook/',
            {
                'type': 'message_callback',
                'callback': {
                    'sender': {'user_id': target_user.max_id},
                    'payload': 'merge_target:yes:101',
                },
            },
            format='json',
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data['ok'] is True
    assert response.data['status'] == 'confirmed'
    assert response.data['code'] is None
    mock_confirm.assert_called_once_with(
        target_user=target_user,
        merge_request_id=101,
        approve=True,
    )


def test_max_webhook_post_returns_ignored_when_target_not_found(api_client):
    with patch('api.views.EmailMergeService.confirm_target_transport_by_request_id') as mock_confirm:
        response = api_client.post(
            '/api/max/webhook/',
            {
                'type': 'message_callback',
                'callback': {
                    'sender': {'user_id': 999991},
                    'payload': 'merge_target:no:202',
                },
            },
            format='json',
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data['ok'] is True
    assert response.data['ignored'] is True
    mock_confirm.assert_not_called()


def test_max_webhook_post_rejects_invalid_secret(api_client, settings):
    settings.MAX_WEBHOOK_SECRET = 'super-secret'

    response = api_client.post('/api/max/webhook/', {'type': 'message_new'}, format='json')

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data['ok'] is False
    assert response.data['error'] == 'invalid_webhook_secret'


def test_max_webhook_post_accepts_valid_secret(api_client, settings):
    settings.MAX_WEBHOOK_SECRET = 'super-secret'

    response = api_client.post(
        '/api/max/webhook/',
        {'type': 'message_new'},
        format='json',
        HTTP_X_MAX_WEBHOOK_SECRET='super-secret',
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data['ok'] is True
    assert response.data['ignored'] is True
