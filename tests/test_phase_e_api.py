"""Phase E: legacy alignment — tasks complete use case + progress via ProgressService."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core.service_response import ServiceResponse
from diary.models import TherapyTask
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="phase_e_user",
        email="phase_e@example.com",
        password="testpass123",
        telegram_id=555001,
        language="ru",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(auth_user).access_token)


def _auth(api_client, token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.fixture
def pending_task(auth_user):
    return TherapyTask.objects.create(
        user=auth_user,
        title="Breathing",
        description="5 minutes",
        type="daily",
        status="pending",
    )


def test_task_complete_requires_texts(api_client, auth_token, pending_task):
    _auth(api_client, auth_token)
    resp = api_client.post(f"/api/v1/tasks/{pending_task.id}/complete/", {}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["error"]["code"] == "completion_and_feelings_required"


def test_task_complete_via_use_case(api_client, auth_user, auth_token, pending_task, mocker):
    _auth(api_client, auth_token)

    task_completion = MagicMock()
    mocker.patch(
        "diary.services.task_management_service.complete_task_with_feelings_use_case",
        new=AsyncMock(
            return_value=ServiceResponse.ok(
                data={"task_completion": task_completion, "task_id": pending_task.id},
                task_id=pending_task.id,
            )
        ),
    )
    mocker.patch(
        "diary.services.task_management_service.analyze_completed_task_for_notification_use_case",
        new=AsyncMock(
            return_value=ServiceResponse.ok(
                data={
                    "analysis": {"effect": "calm"},
                    "notification_text": "Good job",
                    "notification_keyboard": {"inline": []},
                }
            )
        ),
    )

    # Use case owns persistence; mark completed so serializer sees final state after refresh.
    pending_task.status = "completed"
    pending_task.save(update_fields=["status"])

    resp = api_client.post(
        f"/api/v1/tasks/{pending_task.id}/complete/",
        {
            "completion_text": "Сделал упражнение",
            "feelings_text": "Спокойствие",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["status"] == "completed"
    assert resp.data["analysis"]["notification_text"] == "Good job"
    assert "notification_keyboard" not in (resp.data.get("analysis") or {})


def test_progress_list_uses_progress_service(api_client, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.progress_service.get_user_progress_statistics",
        new=AsyncMock(
            return_value={
                "entries_count": 12,
                "tasks_completed": 4,
                "tasks_assigned": 10,
                "tasks_completion_percentage": 40.0,
                "streak_days": 3,
                "has_entry_today": True,
                "streak_reset_warning": "",
            }
        ),
    )
    resp = api_client.get("/api/v1/progress/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total_entries"] == 12
    assert resp.data["total_tasks_completed"] == 4
    assert resp.data["streak_days"] == 3
    assert resp.data["tasks_assigned"] == 10
    assert resp.data["has_entry_today"] is True
    assert "avg_mood_score" in resp.data
