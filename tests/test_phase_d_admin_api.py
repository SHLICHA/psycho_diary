"""Phase D: admin feedback / export / stats API."""

from unittest.mock import AsyncMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from users.models import Feedback, User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="regular_user",
        email="regular@example.com",
        password="testpass123",
        telegram_id=111,
    )


@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username="admin_user",
        email="admin@example.com",
        password="testpass123",
        telegram_id=399096554,
        is_staff=True,
    )


@pytest.fixture
def admin_token(admin_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(admin_user).access_token)


@pytest.fixture
def user_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(auth_user).access_token)


def _auth(api_client, token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def test_admin_endpoints_forbidden_for_regular_user(api_client, user_token):
    _auth(api_client, user_token)
    resp = api_client.get("/api/v1/admin/stats/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_admin_feedback_list_detail_reply(api_client, admin_user, auth_user, admin_token, mocker):
    _auth(api_client, admin_token)
    fb = Feedback.objects.create(user=auth_user, message="Need help please", status="new")

    from core.services.feedback_service import FeedbackDisplayData, feedback_service

    display = FeedbackDisplayData(
        feedback_id=fb.id,
        username=auth_user.username,
        created_at="08.08.2026 12:00",
        is_voice=False,
        is_photo=False,
        message_preview="Need help please",
        full_message="Need help please",
        photo_file_id=None,
        status="new",
    )
    mocker.patch.object(
        feedback_service,
        "get_feedbacks_with_pagination",
        new=AsyncMock(
            return_value={
                "feedbacks": [fb],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "has_next": False,
                "has_prev": False,
            }
        ),
    )
    mocker.patch.object(
        feedback_service,
        "format_feedback_for_display",
        new=AsyncMock(return_value=display),
    )

    listed = api_client.get("/api/v1/admin/feedback/")
    assert listed.status_code == status.HTTP_200_OK
    assert listed.data["total"] == 1
    assert listed.data["results"][0]["feedback_id"] == fb.id

    mocker.patch.object(feedback_service, "get_feedback_by_id", new=AsyncMock(return_value=fb))
    detail = api_client.get(f"/api/v1/admin/feedback/{fb.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data["feedback"]["full_message"] == "Need help please"

    mocker.patch.object(
        feedback_service,
        "process_admin_feedback_reply_use_case",
        new=AsyncMock(
            return_value={
                "success": True,
                "mode": "ready_to_send",
                "feedback_id": fb.id,
                "reply_text": "We can help",
                "notify_chat_id": auth_user.telegram_id,
                "notify_text": "support reply",
                "admin_ack_text": "ok",
                "persist_reply": True,
            }
        ),
    )
    mocker.patch.object(feedback_service, "reply_to_feedback", new=AsyncMock(return_value=fb))
    mocker.patch(
        "bot.utils.message_utils.send_message_to_user",
        new=AsyncMock(return_value=True),
    )

    reply = api_client.post(
        f"/api/v1/admin/feedback/{fb.id}/reply/",
        {"reply_text": "We can help"},
        format="json",
    )
    assert reply.status_code == status.HTTP_200_OK
    assert reply.data["success"] is True


def test_admin_stats(api_client, admin_token, mocker):
    _auth(api_client, admin_token)
    from core.services.admin_service import admin_service

    mocker.patch.object(
        admin_service,
        "get_admin_stats",
        new=AsyncMock(return_value={"total_users": 3, "premium_users": 1}),
    )
    resp = api_client.get("/api/v1/admin/stats/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["stats"]["total_users"] == 3


def test_admin_export(api_client, admin_token, mocker):
    _auth(api_client, admin_token)
    from core.services.database_export_service import database_export_service

    mocker.patch.object(database_export_service, "collect_all_models_data", return_value={"user": []})
    mocker.patch.object(
        database_export_service,
        "write_data_to_excel",
        side_effect=lambda output, data: output.write(b"PK\x03\x04fake-xlsx"),
    )
    mocker.patch.object(
        database_export_service,
        "generate_excel_filename",
        return_value="database_backup_test.xlsx",
    )
    resp = api_client.post("/api/v1/admin/export/")
    assert resp.status_code == status.HTTP_200_OK
    assert "spreadsheetml" in resp["Content-Type"]
    assert "database_backup_test.xlsx" in resp["Content-Disposition"]
