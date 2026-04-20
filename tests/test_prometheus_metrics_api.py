"""
Integration tests for Prometheus metrics endpoint.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from users.models import User
from core.services.monitoring_service import monitoring_service


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create an authenticated test user."""
    user = User.objects.create_user(
        username='prometheus_test_user',
        email='prometheus@test.com',
        password='testpass123',
    )
    return user


@pytest.fixture
def auth_token(db, authenticated_user):
    """Get JWT token for authenticated user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(authenticated_user)
    return str(refresh.access_token)


@pytest.fixture(autouse=True)
def reset_monitoring(db):
    """Reset monitoring service before each test."""
    monitoring_service.reset()
    yield
    monitoring_service.reset()


class TestPrometheusMetricsEndpoint:
    """Test Prometheus metrics endpoint."""
    
    def test_prometheus_endpoint_requires_authentication(self, api_client):
        """Prometheus endpoint should require authentication."""
        url = reverse('monitoring-prometheus')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_prometheus_endpoint_returns_text_plain(self, api_client, auth_token):
        """Prometheus endpoint should return text/plain content."""
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'text/plain' in response['Content-Type']
    
    def test_prometheus_endpoint_returns_valid_format(self, api_client, auth_token):
        """Prometheus endpoint should return valid exposition format."""
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        assert isinstance(content, str)
        
        # Should contain HELP and TYPE comments
        assert '# HELP' in content
        assert '# TYPE' in content
        
        # Should contain metric names
        assert 'psycho_diary_' in content
    
    def test_prometheus_endpoint_empty_snapshot(self, api_client, auth_token):
        """Prometheus endpoint with empty snapshot should return valid format."""
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have total metrics at 0
        assert 'psycho_diary_total_success_total 0.0' in content
        assert 'psycho_diary_total_failure_total 0.0' in content
    
    def test_prometheus_endpoint_with_use_case_metrics(self, api_client, auth_token, db):
        """Prometheus endpoint should include use case metrics."""
        # Record some use case metrics
        import asyncio
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=True,
            duration_ms=150.5,
        ))
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=False,
            duration_ms=200.0,
        ))
        
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have use case metrics
        assert 'use_case="new_entry"' in content
        assert 'psycho_diary_use_cases_total{use_case="new_entry"} 2.0' in content
        assert 'psycho_diary_use_cases_success_total{use_case="new_entry"} 1.0' in content
        assert 'psycho_diary_use_cases_failure_total{use_case="new_entry"} 1.0' in content
    
    def test_prometheus_endpoint_with_ai_call_metrics(self, api_client, auth_token, db):
        """Prometheus endpoint should include AI call metrics."""
        import asyncio
        
        # Record AI call metrics
        asyncio.run(monitoring_service.record_ai_call_event(
            flow='deepseek_analysis',
            success=True,
            duration_ms=2500.0,
            metadata={'tokens': 1500},
        ))
        
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have AI call metrics
        assert 'flow="deepseek_analysis"' in content
        assert 'psycho_diary_ai_calls_total{flow="deepseek_analysis"} 1.0' in content
        assert 'psycho_diary_ai_calls_success_total{flow="deepseek_analysis"} 1.0' in content
    
    def test_prometheus_endpoint_with_transport_metrics(self, api_client, auth_token, db):
        """Prometheus endpoint should include transport metrics."""
        import asyncio
        
        # Record transport metrics
        asyncio.run(monitoring_service.record_transport_event(
            transport_event='telegram_message',
            success=True,
            duration_ms=50.0,
        ))
        asyncio.run(monitoring_service.record_transport_event(
            transport_event='telegram_message',
            success=True,
            duration_ms=45.0,
        ))
        
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have transport metrics
        assert 'event="telegram_message"' in content
        assert 'psycho_diary_transport_events_total{event="telegram_message"} 2.0' in content
        assert 'psycho_diary_transport_events_success_total{event="telegram_message"} 2.0' in content
    
    def test_prometheus_endpoint_with_multiple_metrics_per_bucket(self, api_client, auth_token, db):
        """Prometheus endpoint with multiple metrics per bucket type."""
        import asyncio
        
        # Record multiple use case metrics
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=True,
            duration_ms=150.0,
        ))
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='clarify_entry',
            success=True,
            duration_ms=100.0,
        ))
        
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have both use cases
        assert 'use_case="new_entry"' in content
        assert 'use_case="clarify_entry"' in content
        assert 'psycho_diary_use_cases_total{use_case="new_entry"} 1.0' in content
        assert 'psycho_diary_use_cases_total{use_case="clarify_entry"} 1.0' in content
    
    def test_prometheus_endpoint_totals_aggregation(self, api_client, auth_token, db):
        """Prometheus endpoint should correctly aggregate totals."""
        import asyncio
        
        # Record metrics from different buckets
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=True,
            duration_ms=150.0,
        ))
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=False,
            duration_ms=200.0,
        ))
        asyncio.run(monitoring_service.record_ai_call_event(
            flow='deepseek_analysis',
            success=True,
            duration_ms=2500.0,
        ))
        
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        content = response.data
        
        # Should have correct totals: 2 successes, 1 failure
        assert 'psycho_diary_total_success_total 2.0' in content
        assert 'psycho_diary_total_failure_total 1.0' in content
    
    def test_prometheus_endpoint_response_encoding(self, api_client, auth_token):
        """Prometheus endpoint response should be UTF-8 encoded."""
        url = reverse('monitoring-prometheus')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        response = api_client.get(url)
        
        # Check charset in Content-Type
        assert 'charset=utf-8' in response['Content-Type']


class TestPrometheusMetricsVsJsonEndpoint:
    """Test that Prometheus and JSON endpoints return consistent data."""
    
    def test_prometheus_and_json_consistency(self, api_client, auth_token, db):
        """Prometheus and JSON endpoints should reflect same metrics."""
        import asyncio
        
        # Record some metrics
        asyncio.run(monitoring_service.record_use_case_event(
            use_case='new_entry',
            success=True,
            duration_ms=150.0,
        ))
        
        # Get JSON endpoint
        json_url = reverse('monitoring-metrics')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_token}')
        json_response = api_client.get(json_url)
        json_data = json_response.json()
        
        # Get Prometheus endpoint
        prometheus_url = reverse('monitoring-prometheus')
        prometheus_response = api_client.get(prometheus_url)
        prometheus_text = prometheus_response.data
        
        # Check that both endpoints show the same counts
        assert json_data['use_cases']['new_entry']['count'] == 1
        assert 'use_case="new_entry"} 1.0' in prometheus_text
        
        assert json_data['totals']['success'] == 1
        assert 'psycho_diary_total_success_total 1.0' in prometheus_text
