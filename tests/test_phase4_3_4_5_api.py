"""Phase 4 completion tests: profile, progress and tasks history endpoints."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from diary.models import DiaryEntry, PsychoAnalysis, TherapyTask, TaskCompletion, UserActivity, WeeklyAnalysis
from users.models import User, UserProfileHistory, TokenTransaction, Payment


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="phase4_complete_user",
        email="phase4-complete@example.com",
        password="testpass123",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(auth_user)
    return str(refresh.access_token)


def _auth(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")


def test_profile_history_tokens_transactions_endpoints(api_client, auth_user, auth_token):
    UserProfileHistory.objects.create(
        user=auth_user,
        awareness_level=3,
        personality_traits={"focus": "growth"},
        life_facts=["moved city"],
        hobbies=["reading"],
        core_values=["honesty"],
        triggers=["overload"],
        strengths=["consistency"],
        areas_for_growth=["boundaries"],
        personality_insights={"trend": "stable"},
        habits=["journaling"],
        skills=["reflection"],
        aspirations=["balance"],
        personality_description={"text": "short profile"},
    )

    TokenTransaction.create_and_update_balance(
        user=auth_user,
        amount=20,
        transaction_type="bonus",
        description="Initial bonus",
    )
    TokenTransaction.create_and_update_balance(
        user=auth_user,
        amount=-5,
        transaction_type="analysis",
        description="Consumed for analysis",
    )

    Payment.objects.create(
        user=auth_user,
        yookassa_payment_id="phase4_payment_001",
        amount_rub=Decimal("199.00"),
        payment_type="tokens_10",
        tokens_granted=10,
        status="succeeded",
    )

    _auth(api_client, auth_token)

    history_response = api_client.get("/api/v1/profile/history/")
    tokens_response = api_client.get("/api/v1/profile/tokens/")
    transactions_response = api_client.get("/api/v1/profile/transactions/")

    assert history_response.status_code == status.HTTP_200_OK
    assert tokens_response.status_code == status.HTTP_200_OK
    assert transactions_response.status_code == status.HTTP_200_OK

    assert history_response.data["count"] >= 1
    assert tokens_response.data["token_balance"] == 15
    assert tokens_response.data["total_earned"] == 20
    assert tokens_response.data["total_spent"] == 5
    assert len(transactions_response.data["token_transactions"]) >= 2
    assert len(transactions_response.data["payments"]) >= 1


def test_progress_endpoints_return_expected_payload(api_client, auth_user, auth_token):
    today = timezone.now()

    entry = DiaryEntry.objects.create(
        user=auth_user,
        text="Entry for progress",
        language="ru",
        word_count=3,
    )
    DiaryEntry.objects.filter(id=entry.id).update(created_at=today - timedelta(days=1))

    PsychoAnalysis.objects.create(
        entry=entry,
        mood_score=7,
        comment="Stable",
        recommendation="Keep going",
        processing_time=1.1,
        insights_extracted=2,
        analysis_text="Detailed",
        api_response={},
    )

    task = TherapyTask.objects.create(
        user=auth_user,
        title="Completed task",
        description="Desc",
        type="daily",
        status="completed",
    )
    TaskCompletion.objects.create(
        task=task,
        completion_text="Done",
        feelings_text="Calmer",
    )

    WeeklyAnalysis.objects.create(
        user=auth_user,
        week_start_date=(today - timedelta(days=7)).date(),
        summary_text="Summary",
        progress_insights={"mood": "up"},
        statistics={"entries": 3},
        comparison_with_previous={"delta": 1},
    )

    UserActivity.objects.create(
        user=auth_user,
        activity_type="entry_created",
        metadata={"entry_id": entry.id},
    )

    _auth(api_client, auth_token)

    progress_response = api_client.get("/api/v1/progress/")
    streak_response = api_client.get("/api/v1/progress/streak/")
    mood_response = api_client.get("/api/v1/progress/mood/daily/")
    weekly_response = api_client.get("/api/v1/progress/weekly/")
    activity_response = api_client.get("/api/v1/progress/activity/")

    assert progress_response.status_code == status.HTTP_200_OK
    assert streak_response.status_code == status.HTTP_200_OK
    assert mood_response.status_code == status.HTTP_200_OK
    assert weekly_response.status_code == status.HTTP_200_OK
    assert activity_response.status_code == status.HTTP_200_OK

    assert progress_response.data["total_entries"] >= 1
    assert progress_response.data["total_tasks_completed"] >= 1
    assert "avg_mood_score" in progress_response.data

    assert "current_streak" in streak_response.data
    assert "max_streak" in streak_response.data

    assert mood_response.data["period"] == "daily"
    assert len(mood_response.data["points"]) >= 1

    assert len(weekly_response.data) >= 1
    assert "summary" in activity_response.data
    assert len(activity_response.data["recent"]) >= 1


def test_progress_mood_invalid_period_returns_400(api_client, auth_user, auth_token):
    _auth(api_client, auth_token)
    response = api_client.get("/api/v1/progress/mood/invalid/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_tasks_history_returns_only_historical_statuses(api_client, auth_user, auth_token):
    TherapyTask.objects.create(
        user=auth_user,
        title="Done task",
        description="Desc",
        type="daily",
        status="completed",
        completed_at=timezone.now(),
    )
    TherapyTask.objects.create(
        user=auth_user,
        title="Skipped task",
        description="Desc",
        type="daily",
        status="skipped",
    )
    TherapyTask.objects.create(
        user=auth_user,
        title="Pending task",
        description="Desc",
        type="daily",
        status="pending",
    )

    _auth(api_client, auth_token)
    response = api_client.get("/api/v1/tasks/history/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    statuses = {item["status"] for item in response.data["results"]}
    assert statuses == {"completed", "skipped"}
