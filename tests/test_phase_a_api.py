"""Phase A API: settings, onboarding, therapy, diary parity, progress availability."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core.service_response import ServiceResponse
from diary.models import DiaryEntry
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="phase_a_user",
        email="phase-a@example.com",
        password="testpass123",
        language="ru",
        timezone="Europe/Moscow",
        is_onboarding_completed=True,
        token_balance=10,
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(auth_user).access_token)


def _auth(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")


def test_settings_get_and_patch_language(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.settings_service.get_task_limit_info",
        new=AsyncMock(return_value={"success": True, "current_limit": 1, "max_allowed": 1, "awareness_level": 5}),
    )
    mocker.patch(
        "diary.services.settings_service.get_timezone_info",
        new=AsyncMock(return_value={"success": True, "current_timezone": "Europe/Moscow"}),
    )

    get_resp = api_client.get("/api/v1/settings/")
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.data["language"] == "ru"
    assert get_resp.data["task_limit"]["current_limit"] == 1

    mocker.patch(
        "diary.services.settings_service.update_user_language",
        new=AsyncMock(return_value={"success": True, "new_language": "en"}),
    )
    patch_resp = api_client.patch("/api/v1/settings/", {"language": "en"}, format="json")
    assert patch_resp.status_code == status.HTTP_200_OK
    assert patch_resp.data["updated"]["language"] == "en"


def test_settings_task_limit_and_timezone_lookup(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.settings_service.update_task_limit",
        new=AsyncMock(return_value={"success": True, "new_limit": 2, "action": "increased"}),
    )
    resp = api_client.post("/api/v1/settings/task-limit/", {"increment": 1}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["new_limit"] == 2

    mocker.patch(
        "diary.services.settings_service.process_city_timezone_lookup",
        new=AsyncMock(
            return_value={
                "success": True,
                "timezone_data": {"timezone": "Europe/Berlin", "city": "Berlin", "country": "DE"},
                "source": "cache",
            }
        ),
    )
    lookup = api_client.post("/api/v1/settings/timezone/lookup/", {"city_name": "Berlin"}, format="json")
    assert lookup.status_code == status.HTTP_200_OK
    assert lookup.data["timezone_data"]["timezone"] == "Europe/Berlin"


def test_reminders_alias_uses_settings_service_toggle(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    auth_user.notifications_enabled = True
    auth_user.save(update_fields=["notifications_enabled"])
    mocker.patch(
        "diary.services.settings_service.toggle_user_notifications",
        new=AsyncMock(return_value={"success": True, "new_state": False, "status_message_key": "notifications_disabled"}),
    )
    resp = api_client.patch("/api/v1/reminders/", {"notifications_enabled": False}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["updated"]["notifications_enabled"] is False


def test_onboarding_status_and_accept_agreement(api_client, auth_token, mocker):
    user = User.objects.create_user(
        username="onboarding_user",
        email="onboarding@example.com",
        password="testpass123",
        is_onboarding_completed=False,
        language="ru",
    )
    from rest_framework_simplejwt.tokens import RefreshToken

    token = str(RefreshToken.for_user(user).access_token)
    _auth(api_client, token)

    mocker.patch(
        "diary.services.onboarding_service.resolve_start_routing_use_case",
        new=AsyncMock(
            return_value={
                "success": True,
                "mode": "start_onboarding",
                "text": "welcome",
                "reply_markup": "STRIP_ME",
                "set_state": "waiting_for_agreement_1",
            }
        ),
    )
    status_resp = api_client.get("/api/v1/onboarding/status/")
    assert status_resp.status_code == status.HTTP_200_OK
    assert status_resp.data["mode"] == "start_onboarding"
    assert "reply_markup" not in status_resp.data

    step1 = api_client.post("/api/v1/onboarding/accept-agreement/", {"step": 1}, format="json")
    assert step1.status_code == status.HTTP_200_OK
    assert step1.data["mode"] == "agreement_2"

    mocker.patch(
        "diary.services.onboarding_service.build_onboarding_timezone_prompt_view",
        new=AsyncMock(
            return_value={
                "success": True,
                "mode": "timezone_prompt",
                "text": "pick tz",
                "current_timezone": "Europe/Moscow",
                "reply_markup": object(),
            }
        ),
    )
    step2 = api_client.post("/api/v1/onboarding/accept-agreement/", {"step": 2}, format="json")
    assert step2.status_code == status.HTTP_200_OK
    assert step2.data["mode"] == "timezone"
    assert "reply_markup" not in step2.data


def test_onboarding_timezone_and_first_entry(api_client, mocker):
    user = User.objects.create_user(
        username="onboarding_user2",
        email="onboarding2@example.com",
        password="testpass123",
        is_onboarding_completed=False,
        language="ru",
    )
    from rest_framework_simplejwt.tokens import RefreshToken

    token = str(RefreshToken.for_user(user).access_token)
    _auth(api_client, token)

    mocker.patch(
        "diary.services.settings_service.set_timezone_and_resolve_next_step",
        new=AsyncMock(
            return_value={
                "success": True,
                "mode": "onboarding_first_entry",
                "next": "onboarding_first_entry",
                "text": "write first entry",
                "new_timezone": "Europe/Berlin",
                "reply_markup": None,
                "set_state": "waiting_for_first_entry",
            }
        ),
    )
    tz_resp = api_client.post("/api/v1/onboarding/timezone/", {"timezone": "Europe/Berlin"}, format="json")
    assert tz_resp.status_code == status.HTTP_200_OK
    assert tz_resp.data["next"] == "onboarding_first_entry"
    assert "set_state" not in tz_resp.data

    real_entry = DiaryEntry.objects.create(
        user=user, text="first", language="ru", word_count=1
    )
    mock_response = ServiceResponse.ok(
        data={
            "entry": real_entry,
            "analysis": None,
            "mood_score": 7,
            "comment": "ok",
            "recommendation": "go",
            "formatted_message_ai": "saved",
        },
        onboarding_completed=True,
    )
    from bot.services.diary_service import diary_service

    mocker.patch.object(
        diary_service,
        "process_first_onboarding_entry_use_case",
        new=AsyncMock(return_value=mock_response),
    )
    first = api_client.post("/api/v1/onboarding/first-entry/", {"text": "hello world"}, format="json")
    assert first.status_code == status.HTTP_201_CREATED
    assert first.data["mode"] == "entry_saved"
    assert first.data["mood_score"] == 7


def test_therapy_chat_flow(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    auth_user.is_premium = True
    auth_user.save(update_fields=["is_premium"])

    welcome = api_client.get("/api/v1/therapy-chat/welcome/")
    assert welcome.status_code == status.HTTP_200_OK
    assert welcome.data["mode"] == "premium"
    assert "reply_markup" not in welcome.data

    mocker.patch(
        "diary.services.therapy_chat_service.TherapyChatService.start_chat",
        new=AsyncMock(return_value={"success": True, "initial_history": [], "error": None}),
    )
    start = api_client.post("/api/v1/therapy-chat/start/")
    assert start.status_code == status.HTTP_200_OK
    assert start.data["initial_history"] == []

    mocker.patch(
        "diary.services.therapy_chat_service.TherapyChatService.process_user_message",
        new=AsyncMock(
            return_value={
                "success": True,
                "response_text": "hello back",
                "updated_history": [
                    {"role": "Пользователь", "content": "hi"},
                    {"role": "ИИ", "content": "hello back"},
                ],
                "error": None,
            }
        ),
    )
    msg = api_client.post(
        "/api/v1/therapy-chat/message/",
        {"text": "hi", "history": []},
        format="json",
    )
    assert msg.status_code == status.HTTP_200_OK
    assert msg.data["response_text"] == "hello back"

    mocker.patch(
        "diary.services.therapy_chat_service.TherapyChatService.end_chat",
        new=AsyncMock(return_value={"success": True, "message": "Чат завершён."}),
    )
    end = api_client.post("/api/v1/therapy-chat/end/")
    assert end.status_code == status.HTTP_200_OK


def test_diary_comment_clarifications_edit_delete_rate(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    from bot.services.diary_service import diary_service

    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="base entry",
        language="ru",
        word_count=2,
        clarification_questions_asked=["Q1?", "Q2?"],
    )

    comment_resp = ServiceResponse.ok(
        data={"entry": entry, "analysis": None, "formatted_message_ai": "ok"},
    )
    mocker.patch.object(
        diary_service,
        "process_user_comment_use_case",
        new=AsyncMock(return_value=comment_resp),
    )
    c = api_client.post(f"/api/v1/entries/{entry.id}/comment/", {"user_comment": "note"}, format="json")
    assert c.status_code == status.HTTP_200_OK
    assert "entry" in c.data

    clar_resp = ServiceResponse.ok(data={"entry": entry, "analysis": None})
    mocker.patch.object(
        diary_service,
        "process_clarification_answers_use_case",
        new=AsyncMock(return_value=clar_resp),
    )
    clar = api_client.post(
        f"/api/v1/entries/{entry.id}/clarifications/",
        {"text": "a1\na2"},
        format="json",
    )
    assert clar.status_code == status.HTTP_200_OK

    edit_resp = ServiceResponse.ok(
        data={
            "day_view": {"success": True, "mode": "empty", "text": "no entries", "keyboard": object()},
            "target_date": str(date.today()),
        },
        entry_id=entry.id,
    )
    mocker.patch.object(
        diary_service,
        "process_entry_edit_use_case",
        new=AsyncMock(return_value=edit_resp),
    )
    edit = api_client.post(
        f"/api/v1/entries/{entry.id}/edit-with-analysis/",
        {"text": "updated text", "target_date": str(date.today())},
        format="json",
    )
    assert edit.status_code == status.HTTP_200_OK
    assert edit.data["day_view"]["mode"] == "empty"
    assert "keyboard" not in edit.data["day_view"]

    del_resp = ServiceResponse.ok(
        data={
            "day_view": {"success": True, "mode": "empty", "text": "gone"},
            "alert_message": "deleted",
            "deleted": True,
        }
    )
    mocker.patch.object(
        diary_service,
        "process_delete_specific_entry_use_case",
        new=AsyncMock(return_value=del_resp),
    )
    entry2 = DiaryEntry.objects.create(user=auth_user, text="to delete", language="ru", word_count=2)
    delete = api_client.post(
        f"/api/v1/entries/{entry2.id}/confirm-delete/",
        {"target_date": str(date.today())},
        format="json",
    )
    assert delete.status_code == status.HTTP_200_OK
    assert delete.data["deleted"] is True


def test_day_by_date_and_reanalyze(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    today = date.today().isoformat()

    mocker.patch(
        "diary.services.diary_display_service.diary_display_service.build_day_entries_view",
        new=AsyncMock(return_value={"success": True, "mode": "empty", "text": "empty day", "keyboard": object()}),
    )
    get_day = api_client.get(f"/api/v1/days/date/{today}/")
    assert get_day.status_code == status.HTTP_200_OK
    assert get_day.data["mode"] == "empty"
    assert "keyboard" not in get_day.data

    from bot.services.diary_service import diary_service

    mocker.patch.object(
        diary_service,
        "delete_entire_day_use_case",
        new=AsyncMock(
            return_value={
                "success": True,
                "alert_message": "day deleted",
                "archive_view": {"text": "archive", "keyboard": object()},
            }
        ),
    )
    delete_day = api_client.delete(f"/api/v1/days/date/{today}/")
    assert delete_day.status_code == status.HTTP_200_OK
    assert delete_day.data["success"] is True

    auth_user.is_premium = True
    auth_user.save(update_fields=["is_premium"])
    mocker.patch.object(
        diary_service,
        "start_full_day_reanalysis_use_case",
        new=AsyncMock(return_value={"mode": "ready", "status_text": "processing", "confirm_alert": "ok"}),
    )
    mocker.patch(
        "diary.services.full_day_analysis_service.perform_full_day_analysis",
        new=AsyncMock(return_value={"success": True, "message": "done", "daily_analysis": None}),
    )
    reanalyze = api_client.post(f"/api/v1/days/date/{today}/reanalyze/")
    assert reanalyze.status_code == status.HTTP_200_OK
    assert reanalyze.data["success"] is True


def test_restore_streak_availability(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.progress_service.check_restore_streak_availability",
        new=AsyncMock(return_value={"available": True, "dates": [date(2026, 4, 18)]}),
    )
    resp = api_client.get("/api/v1/progress/restore-streak/availability/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["available"] is True
    assert resp.data["dates"] == ["2026-04-18"]


def test_service_bridge_strip_transport():
    from api.service_bridge import strip_transport

    payload = {
        "mode": "main_menu",
        "text": "hi",
        "reply_markup": "kb",
        "set_state": "x",
        "nested": {"keyboard": 1, "value": 2},
    }
    cleaned = strip_transport(payload)
    assert cleaned == {"mode": "main_menu", "text": "hi", "nested": {"value": 2}}
