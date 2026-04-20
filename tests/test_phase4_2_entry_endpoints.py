"""Phase 4.2 tests: additional diary entry endpoints (date, analysis, comment)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from diary.models import DiaryEntry, PsychoAnalysis
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="entry_endpoints_user",
        email="entry-endpoints@example.com",
        password="testpass123",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(auth_user)
    return str(refresh.access_token)


def test_entries_by_date_returns_only_current_user_entries(api_client, auth_user, auth_token):
    target_day = timezone.now().date()

    matching_entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Matching day entry",
        language="ru",
        word_count=3,
    )
    DiaryEntry.objects.filter(id=matching_entry.id).update(created_at=timezone.now() - timedelta(hours=1))

    other_day_entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Another day entry",
        language="ru",
        word_count=3,
    )
    DiaryEntry.objects.filter(id=other_day_entry.id).update(created_at=timezone.now() - timedelta(days=2))

    another_user = User.objects.create_user(username="entry_endpoints_another")
    foreign_entry = DiaryEntry.objects.create(
        user=another_user,
        text="Foreign entry",
        language="ru",
        word_count=2,
    )
    DiaryEntry.objects.filter(id=foreign_entry.id).update(created_at=timezone.now() - timedelta(hours=2))

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get(f"/api/v1/entries/date/{target_day}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == matching_entry.id


def test_entries_by_date_invalid_date_returns_400(api_client, auth_user, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get("/api/v1/entries/date/not-a-date/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "invalid_date_format"


def test_entry_analysis_returns_analysis_payload(api_client, auth_user, auth_token):
    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Entry with analysis",
        language="ru",
        word_count=3,
    )

    PsychoAnalysis.objects.create(
        entry=entry,
        mood_score=8,
        comment="Стабильная динамика",
        recommendation="Продолжай практику благодарности",
        processing_time=1.25,
        insights_extracted=2,
        analysis_text="Полный анализ",
        api_response={"usage": {"total_tokens": 321}},
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get(f"/api/v1/entries/{entry.id}/analysis/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["entry_id"] == entry.id
    assert response.data["mood_score"] == 8
    assert response.data["insights_extracted"] == 2


def test_entry_analysis_not_found_for_entry_without_analysis(api_client, auth_user, auth_token):
    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Entry without analysis",
        language="ru",
        word_count=3,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get(f"/api/v1/entries/{entry.id}/analysis/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["error"]["code"] == "analysis_not_found"


def test_entry_analysis_not_found_for_foreign_entry(api_client, auth_user, auth_token):
    another_user = User.objects.create_user(username="foreign_analysis_user")
    foreign_entry = DiaryEntry.objects.create(
        user=another_user,
        text="Foreign entry",
        language="ru",
        word_count=2,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get(f"/api/v1/entries/{foreign_entry.id}/analysis/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_entry_comment_updates_user_comment(api_client, auth_user, auth_token):
    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Entry for comment",
        language="ru",
        word_count=3,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.post(
        f"/api/v1/entries/{entry.id}/comment/",
        {"user_comment": "Спасибо, это было полезно"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK

    entry.refresh_from_db()
    assert entry.user_comment == "Спасибо, это было полезно"
    assert response.data["entry"]["id"] == entry.id


def test_entry_comment_empty_payload_returns_400(api_client, auth_user, auth_token):
    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Entry for comment",
        language="ru",
        word_count=3,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.post(
        f"/api/v1/entries/{entry.id}/comment/",
        {"user_comment": "   "},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "user_comment_required"


def test_entry_comment_not_found_for_foreign_entry(api_client, auth_user, auth_token):
    another_user = User.objects.create_user(username="foreign_comment_user")
    foreign_entry = DiaryEntry.objects.create(
        user=another_user,
        text="Foreign entry",
        language="ru",
        word_count=2,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.post(
        f"/api/v1/entries/{foreign_entry.id}/comment/",
        {"user_comment": "Should fail"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
