"""Phase 4.6 tests: Spectacular schema and Redoc endpoints."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_api_schema_endpoint_returns_openapi_document(api_client):
    response = api_client.get("/api/v1/schema/")

    assert response.status_code == status.HTTP_200_OK
    payload = response.data
    assert "openapi" in payload
    assert "info" in payload


@pytest.mark.django_db
def test_api_redoc_endpoint_returns_html(api_client):
    response = api_client.get("/api/v1/docs/")

    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response["Content-Type"]
    assert "redoc" in response.content.decode("utf-8").lower()
