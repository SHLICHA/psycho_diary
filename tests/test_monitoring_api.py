import pytest
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username='metrics_user',
        email='metrics@example.com',
        password='testpass123',
    )


@pytest.mark.django_db
@patch('api.views.monitoring_service.get_snapshot')
def test_monitoring_metrics_endpoint_authenticated(mock_snapshot, api_client, auth_user):
    mock_snapshot.return_value = {
        'use_cases': {'diary.process_new_entry_use_case': {'count': 1, 'success': 1, 'failure': 0, 'last_duration_ms': 5.1, 'last_metadata': {}}},
        'ai_calls': {'diary.process_new_entry_logic': {'count': 1, 'success': 1, 'failure': 0, 'last_duration_ms': 42.0, 'last_metadata': {'provider': 'deepseek'}}},
        'transport': {'telegram.Message': {'count': 2, 'success': 2, 'failure': 0, 'last_duration_ms': 1.1, 'last_metadata': {'handler': 'x'}}},
        'totals': {'success': 4, 'failure': 0},
    }

    api_client.force_authenticate(user=auth_user)
    response = api_client.get('/api/v1/auth/monitoring/metrics/')

    assert response.status_code == status.HTTP_200_OK
    assert 'use_cases' in response.data
    assert 'ai_calls' in response.data
    assert 'transport' in response.data
    assert response.data['totals']['success'] == 4


@pytest.mark.django_db
def test_monitoring_metrics_endpoint_unauthenticated(api_client):
    response = api_client.get('/api/v1/auth/monitoring/metrics/')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
