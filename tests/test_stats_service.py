"""Integration tests for stats service and comprehensive stats endpoint."""

import asyncio
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.services.stats_dtos import AICallMetrics, StatsQuery
from core.services.stats_service import stats_service
from diary.models import DiaryEntry, PsychoAnalysis, TaskCompletion, TherapyTask
from users.models import Payment, User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user():
    return User.objects.create_user(
        username="stats_test_user",
        email="stats@test.com",
        password="testpass123",
        is_onboarding_completed=True,
    )


@pytest.fixture
def auth_token(authenticated_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(authenticated_user)
    return str(refresh.access_token)


class TestStatsServiceAIMetrics:
    def test_get_ai_metrics_empty(self):
        metrics = asyncio.run(stats_service.get_ai_metrics(days_back=7))

        assert isinstance(metrics, AICallMetrics)
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.error_rate == 0.0

    def test_get_ai_metrics_with_data(self, authenticated_user):
        entry = DiaryEntry.objects.create(
            user=authenticated_user,
            text="Test entry",
            language="en",
            word_count=10,
        )

        PsychoAnalysis.objects.create(
            entry=entry,
            mood_score=5,
            comment="Test comment",
            recommendation="Test recommendation",
            processing_time=1.5,
            insights_extracted=2,
            api_response={"usage": {"total_tokens": 500}},
        )

        metrics = asyncio.run(stats_service.get_ai_metrics(days_back=7))

        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0
        assert metrics.total_tokens_used == 500


class TestStatsServiceOnboardingFunnel:
    def test_get_onboarding_empty(self):
        metrics = asyncio.run(stats_service.get_onboarding_funnel(days_back=7))

        assert metrics.started_count == 0
        assert metrics.registered_count == 0
        assert metrics.first_entry_count == 0

    def test_get_onboarding_with_users(self):
        User.objects.create_user(username="user1", telegram_id=111111)
        User.objects.create_user(
            username="user2",
            email="user2@test.com",
            password="pass123",
        )
        user3 = User.objects.create_user(
            username="user3",
            email="user3@test.com",
            password="pass123",
        )
        DiaryEntry.objects.create(
            user=user3,
            text="First entry",
            language="en",
            word_count=10,
        )

        metrics = asyncio.run(stats_service.get_onboarding_funnel(days_back=7))

        assert metrics.started_count == 3
        assert metrics.registered_count == 2
        assert metrics.first_entry_count == 1


class TestStatsServiceRetentionMetrics:
    def test_get_retention_empty(self):
        metrics = asyncio.run(stats_service.get_retention_metrics(days_back=7))

        assert metrics.daily_active_users == 0
        assert metrics.weekly_active_users == 0
        assert metrics.monthly_active_users == 0
        assert metrics.users_with_active_streak == 0

    def test_get_retention_with_activity(self, authenticated_user):
        DiaryEntry.objects.create(
            user=authenticated_user,
            text="Activity",
            language="en",
            word_count=10,
        )
        second_user = User.objects.create_user(
            username="active_user",
            email="active@test.com",
        )
        DiaryEntry.objects.create(
            user=second_user,
            text="Another entry",
            language="en",
            word_count=12,
            is_recovered_streak=True,
        )

        metrics = asyncio.run(stats_service.get_retention_metrics(days_back=7))

        assert metrics.daily_active_users == 2
        assert metrics.weekly_active_users == 2
        assert metrics.monthly_active_users == 2
        assert metrics.users_with_active_streak == 2
        assert metrics.users_recovered_streak == 1


class TestStatsServiceTaskMetrics:
    def test_get_task_metrics_empty(self):
        metrics = asyncio.run(stats_service.get_task_metrics(days_back=7))

        assert metrics.total_tasks_created == 0
        assert metrics.total_tasks_completed == 0
        assert metrics.completion_rate == 0.0

    def test_get_task_metrics_with_tasks(self, authenticated_user):
        task1 = TherapyTask.objects.create(
            user=authenticated_user,
            title="Task 1",
            description="Test task",
            type="daily",
            status="completed",
        )
        TherapyTask.objects.create(
            user=authenticated_user,
            title="Task 2",
            description="Test task",
            type="daily",
            status="pending",
        )

        TaskCompletion.objects.create(
            task=task1,
            completion_text="Done",
            feelings_text="Better",
        )

        metrics = asyncio.run(stats_service.get_task_metrics(days_back=7))

        assert metrics.total_tasks_created == 2
        assert metrics.total_tasks_completed == 1
        assert metrics.completion_rate == 50.0


class TestStatsServiceEntryMetrics:
    def test_get_entry_metrics_empty(self):
        metrics = asyncio.run(stats_service.get_entry_metrics(days_back=7))

        assert metrics.total_entries == 0
        assert metrics.processed_entries == 0
        assert metrics.failed_entries == 0

    def test_get_entry_metrics_with_entries(self, authenticated_user):
        entry1 = DiaryEntry.objects.create(
            user=authenticated_user,
            text="Entry 1",
            language="en",
            word_count=10,
            is_processed=True,
            clarification_questions_asked=["How do you feel?", "Why?"],
            user_comment="Useful analysis",
        )
        DiaryEntry.objects.create(
            user=authenticated_user,
            text="Entry 2",
            language="en",
            word_count=15,
            is_processed=False,
            processing_error="Test error",
        )

        PsychoAnalysis.objects.create(
            entry=entry1,
            mood_score=5,
            comment="Good",
            recommendation="Keep it up",
            processing_time=1.2,
            insights_extracted=1,
            api_response={},
        )

        metrics = asyncio.run(stats_service.get_entry_metrics(days_back=7))

        assert metrics.total_entries == 2
        assert metrics.processed_entries == 1
        assert metrics.failed_entries == 1
        assert metrics.entries_with_clarifications == 1
        assert metrics.user_comments_count == 1


class TestStatsServiceEngagementMetrics:
    def test_get_engagement_metrics_with_payments(self, authenticated_user):
        authenticated_user.is_premium = True
        authenticated_user.save(update_fields=["is_premium"])

        DiaryEntry.objects.create(
            user=authenticated_user,
            text="Entry 1",
            language="en",
            word_count=10,
        )
        task = TherapyTask.objects.create(
            user=authenticated_user,
            title="Task",
            description="Test task",
            type="daily",
            status="completed",
        )
        TaskCompletion.objects.create(
            task=task,
            completion_text="Done",
            feelings_text="Okay",
        )
        Payment.objects.create(
            user=authenticated_user,
            yookassa_payment_id="payment_001",
            amount_rub=Decimal("199.00"),
            payment_type="tokens_10",
            tokens_granted=10,
            status="succeeded",
        )

        metrics = asyncio.run(stats_service.get_engagement_metrics(days_back=7))

        assert metrics.avg_entries_per_user == 1.0
        assert metrics.avg_tasks_per_user == 1.0
        assert metrics.users_with_premium == 1
        assert metrics.total_tokens_purchased == 10


class TestStatsServiceComprehensive:
    def test_get_comprehensive_stats_default(self):
        stats = asyncio.run(stats_service.get_comprehensive_stats(StatsQuery()))

        assert stats.timestamp is not None
        assert stats.period == "daily"
        assert stats.ai_metrics is not None
        assert stats.onboarding is not None
        assert stats.retention is not None
        assert stats.tasks is not None
        assert stats.entries is not None
        assert stats.engagement is not None

    def test_get_comprehensive_stats_with_period(self):
        for period in ["daily", "weekly", "monthly"]:
            stats = asyncio.run(stats_service.get_comprehensive_stats(StatsQuery(period=period)))
            assert stats.period == period

    def test_get_comprehensive_stats_invalid_query(self):
        with pytest.raises(ValueError):
            asyncio.run(
                stats_service.get_comprehensive_stats(
                    StatsQuery(period="invalid", days_back=7)
                )
            )


class TestComprehensiveStatsEndpoint:
    def test_endpoint_requires_authentication(self, api_client):
        response = api_client.get(reverse("monitoring-stats"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_endpoint_returns_valid_response(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
        response = api_client.get(reverse("monitoring-stats"))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "timestamp" in data
        assert "period" in data
        assert "ai_metrics" in data
        assert "onboarding" in data
        assert "retention" in data
        assert "tasks" in data
        assert "entries" in data
        assert "engagement" in data

    def test_endpoint_with_period_parameter(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")

        for period in ["daily", "weekly", "monthly"]:
            response = api_client.get(f"{reverse('monitoring-stats')}?period={period}")
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["period"] == period

    def test_endpoint_with_days_back_parameter(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
        response = api_client.get(f"{reverse('monitoring-stats')}?days_back=30")

        assert response.status_code == status.HTTP_200_OK
        assert "retention" in response.json()

    def test_endpoint_with_invalid_period(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
        response = api_client.get(f"{reverse('monitoring-stats')}?period=invalid")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_endpoint_with_invalid_days_back(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")

        response = api_client.get(f"{reverse('monitoring-stats')}?days_back=366")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = api_client.get(f"{reverse('monitoring-stats')}?days_back=0")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_endpoint_response_structure(self, api_client, auth_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")
        response = api_client.get(reverse("monitoring-stats"))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_calls" in data["ai_metrics"]
        assert "error_rate" in data["ai_metrics"]
        assert "started_count" in data["onboarding"]
        assert "registered_count" in data["onboarding"]
        assert "daily_active_users" in data["retention"]
        assert "users_with_active_streak" in data["retention"]
        assert "completion_rate" in data["tasks"]
        assert "total_entries" in data["entries"]
        assert "avg_processing_time_ms" in data["entries"]
        assert "avg_entries_per_user" in data["engagement"]
        assert "premium_conversion_rate" in data["engagement"]
