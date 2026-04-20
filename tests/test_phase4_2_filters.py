"""Phase 4.2 tests: filtering and ordering for entries/tasks API."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from diary.models import DiaryEntry, TherapyTask
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="filters_user",
        email="filters@example.com",
        password="testpass123",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(auth_user)
    return str(refresh.access_token)


def test_entries_filter_by_language_and_is_processed(api_client, auth_user, auth_token):
    DiaryEntry.objects.create(
        user=auth_user,
        text="Russian processed",
        language="ru",
        word_count=2,
        is_processed=True,
    )
    DiaryEntry.objects.create(
        user=auth_user,
        text="Russian not processed",
        language="ru",
        word_count=3,
        is_processed=False,
    )
    DiaryEntry.objects.create(
        user=auth_user,
        text="English processed",
        language="en",
        word_count=2,
        is_processed=True,
    )

    # Another user entry should never leak due to base queryset filter.
    another_user = User.objects.create_user(username="another_filters_user")
    DiaryEntry.objects.create(
        user=another_user,
        text="Another user",
        language="ru",
        word_count=2,
        is_processed=True,
    )

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
    response = api_client.get("/api/v1/entries/?language=ru&is_processed=true")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["language"] == "ru"
    assert response.data["results"][0]["is_processed"] is True


def test_entries_filter_by_date_range_and_ordering(api_client, auth_user, auth_token):
    today = timezone.now()

    old_entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Old entry",
        language="ru",
        word_count=2,
        is_processed=True,
    )
    recent_entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Recent entry",
        language="ru",
        word_count=10,
        is_processed=True,
    )

    DiaryEntry.objects.filter(id=old_entry.id).update(created_at=today - timedelta(days=5))
    DiaryEntry.objects.filter(id=recent_entry.id).update(created_at=today - timedelta(days=1))

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")

    response = api_client.get(
        "/api/v1/entries/?date_from={}&ordering=-word_count".format((today - timedelta(days=2)).date())
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == recent_entry.id


def test_tasks_filter_by_status_type_and_completed_flag(api_client, auth_user, auth_token):
    task_completed = TherapyTask.objects.create(
        user=auth_user,
        title="Completed daily",
        description="Desc",
        type="daily",
        status="completed",
        complexity="low",
    )
    task_pending = TherapyTask.objects.create(
        user=auth_user,
        title="Pending reflection",
        description="Desc",
        type="reflection",
        status="pending",
        complexity="high",
    )

    TherapyTask.objects.filter(id=task_completed.id).update(completed_at=timezone.now())

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")

    response = api_client.get("/api/v1/tasks/?status=completed&type=daily&completed=true")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == task_completed.id
    assert response.data["results"][0]["status"] == "completed"
    assert task_pending.id != response.data["results"][0]["id"]


def test_tasks_filter_by_complexity_and_ordering(api_client, auth_user, auth_token):
    now = timezone.now()

    first_task = TherapyTask.objects.create(
        user=auth_user,
        title="First",
        description="Desc",
        type="daily",
        status="pending",
        complexity="medium",
    )
    second_task = TherapyTask.objects.create(
        user=auth_user,
        title="Second",
        description="Desc",
        type="daily",
        status="pending",
        complexity="medium",
    )

    TherapyTask.objects.filter(id=first_task.id).update(assigned_at=now - timedelta(days=3))
    TherapyTask.objects.filter(id=second_task.id).update(assigned_at=now - timedelta(days=1))

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")

    response = api_client.get("/api/v1/tasks/?complexity=medium&ordering=assigned_at")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    ids = [item["id"] for item in response.data["results"]]
    assert ids == [first_task.id, second_task.id]
