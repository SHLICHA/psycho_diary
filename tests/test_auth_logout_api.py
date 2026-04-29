"""Tests for auth logout endpoint."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


def _make_tokens(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def test_logout_blacklists_refresh_token():
    user = User.objects.create_user(
        username="logout_user",
        email="logout-user@example.com",
        password="testpass123",
    )
    access, refresh = _make_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    logout_response = client.post("/api/v1/logout/", {"refresh": refresh}, format="json")
    assert logout_response.status_code == status.HTTP_200_OK

    refresh_response = client.post("/api/v1/refresh/", {"refresh": refresh}, format="json")
    assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_requires_refresh_token():
    user = User.objects.create_user(
        username="logout_missing_refresh_user",
        email="logout-missing-refresh@example.com",
        password="testpass123",
    )
    access, _ = _make_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.post("/api/v1/logout/", {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "refresh_required"
