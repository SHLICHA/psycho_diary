"""Smoke baseline tests for Phase 4 API readiness gate."""

from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

from diary.models import DiaryEntry, PsychoAnalysis, TaskCompletion, TherapyTask
from users.models import Payment, User


@pytest.fixture(autouse=True)
def clear_rate_limit_cache_between_smoke_tests():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def telegram_user():
    return User.objects.create_user(
        username="telegram_smoke_user",
        telegram_id=987654321,
    )


@pytest.fixture
def web_user():
    return User.objects.create_user(
        username="web_smoke_user",
        email="web-smoke@example.com",
        password="testpass123",
    )


@pytest.mark.django_db(transaction=True)
def test_web_auth_and_monitoring_smoke(api_client):
    register_response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "phase4@example.com",
            "password": "strongpass123",
            "password_confirm": "strongpass123",
            "username": "phase4_user",
        },
        format="json",
    )

    assert register_response.status_code == status.HTTP_201_CREATED
    access_token = register_response.data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    metrics_response = api_client.get("/api/v1/auth/monitoring/metrics/")
    prometheus_response = api_client.get("/api/v1/auth/monitoring/prometheus/")
    stats_response = api_client.get("/api/v1/auth/monitoring/stats/")
    generate_link_response = api_client.post("/api/v1/auth/generate-link/")

    assert metrics_response.status_code == status.HTTP_200_OK
    assert prometheus_response.status_code == status.HTTP_200_OK
    assert stats_response.status_code == status.HTTP_200_OK
    assert generate_link_response.status_code == status.HTTP_200_OK

    assert "use_cases" in metrics_response.data
    assert "# HELP" in prometheus_response.data
    assert "ai_metrics" in stats_response.data
    assert "link" in generate_link_response.data


@pytest.mark.django_db(transaction=True)
def test_complete_registration_and_login_smoke(api_client, telegram_user):
    api_client.force_authenticate(user=telegram_user)
    complete_response = api_client.post(
        "/api/v1/auth/complete-registration/",
        {
            "email": "linked@example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        },
        format="json",
    )

    assert complete_response.status_code == status.HTTP_200_OK
    assert "access" in complete_response.data

    telegram_user.refresh_from_db()
    assert telegram_user.email == "linked@example.com"

    api_client.force_authenticate(user=None)
    login_response = api_client.post(
        "/api/v1/auth/login/",
        {
            "email": "linked@example.com",
            "password": "securepass123",
        },
        format="json",
    )

    assert login_response.status_code == status.HTTP_200_OK
    assert "access" in login_response.data


@pytest.mark.django_db(transaction=True)
def test_stats_endpoint_with_activity_smoke(api_client, web_user):
    entry = DiaryEntry.objects.create(
        user=web_user,
        text="Сегодня было лучше, чем вчера",
        language="ru",
        word_count=5,
        is_processed=True,
        clarification_questions_asked=["Что помогло?"],
        user_comment="Хочу сохранить это состояние",
    )
    PsychoAnalysis.objects.create(
        entry=entry,
        mood_score=7,
        comment="Позитивная динамика",
        recommendation="Закрепить ритуал дня",
        processing_time=1.4,
        insights_extracted=2,
        api_response={"usage": {"total_tokens": 250}},
    )
    task = TherapyTask.objects.create(
        user=web_user,
        title="Вечерняя рефлексия",
        description="Подвести итоги дня",
        type="daily",
        status="completed",
    )
    TaskCompletion.objects.create(
        task=task,
        completion_text="Сделано",
        feelings_text="Спокойнее",
    )
    Payment.objects.create(
        user=web_user,
        yookassa_payment_id="smoke_payment_001",
        amount_rub=Decimal("99.00"),
        payment_type="tokens_10",
        tokens_granted=10,
        status="succeeded",
    )

    login_response = api_client.post(
        "/api/v1/auth/login/",
        {
            "email": "web-smoke@example.com",
            "password": "testpass123",
        },
        format="json",
    )
    assert login_response.status_code == status.HTTP_200_OK

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
    response = api_client.get("/api/v1/auth/monitoring/stats/?period=daily&days_back=30")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["ai_metrics"]["total_calls"] >= 1
    assert data["entries"]["total_entries"] >= 1
    assert data["tasks"]["total_tasks_completed"] >= 1
    assert data["engagement"]["total_tokens_purchased"] >= 10


@pytest.mark.django_db(transaction=True)
def test_entry_creation_workflow_smoke(api_client):
    """Test complete entry creation and retrieval workflow."""
    register_response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "entry_test@example.com",
            "password": "testpass456",
            "password_confirm": "testpass456",
            "username": "entry_test_user",
        },
        format="json",
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    access_token = register_response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # Create entry
    create_response = api_client.post(
        "/api/v1/entries/",
        {
            "text": "Сегодня я осознал важность баланса между работой и отдыхом",
            "language": "ru",
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    entry_id = create_response.data["id"]

    # Retrieve entry
    get_response = api_client.get(f"/api/v1/entries/{entry_id}/")
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data["text"] == "Сегодня я осознал важность баланса между работой и отдыхом"
    assert get_response.data["language"] == "ru"

    # List entries
    list_response = api_client.get("/api/v1/entries/")
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data["results"]) >= 1


@pytest.mark.django_db(transaction=True)
def test_task_lifecycle_workflow_smoke(api_client):
    """Test complete task creation, retrieval, and completion workflow."""
    register_response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "task_test@example.com",
            "password": "testpass789",
            "password_confirm": "testpass789",
            "username": "task_test_user",
        },
        format="json",
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    access_token = register_response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # Create task
    create_response = api_client.post(
        "/api/v1/tasks/",
        {
            "title": "Проведите дыхательное упражнение",
            "description": "5 минут глубокого дыхания перед сном",
            "type": "daily",
            "status": "pending",
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    task_id = create_response.data["id"]
    assert create_response.data["status"] == "pending"

    # Retrieve task
    get_response = api_client.get(f"/api/v1/tasks/{task_id}/")
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data["title"] == "Проведите дыхательное упражнение"

    # List tasks
    list_response = api_client.get("/api/v1/tasks/")
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data["results"]) >= 1

    # Complete task
    complete_response = api_client.post(
        f"/api/v1/tasks/{task_id}/complete/",
        {},
        format="json",
    )
    assert complete_response.status_code == status.HTTP_200_OK
    assert complete_response.data["status"] == "completed"


@pytest.mark.django_db(transaction=True)
def test_profile_and_user_info_workflow_smoke(api_client):
    """Test user profile creation and management workflow."""
    register_response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "profile_test@example.com",
            "password": "testpass999",
            "password_confirm": "testpass999",
            "username": "profile_test_user",
        },
        format="json",
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    access_token = register_response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # Get user info
    user_response = api_client.get("/api/v1/users/me/")
    assert user_response.status_code == status.HTTP_200_OK
    assert user_response.data["username"] == "profile_test_user"
    assert user_response.data["email"] == "profile_test@example.com"

    # Create/update profile
    profile_response = api_client.get("/api/v1/profile/")
    assert profile_response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    # Verify user is in database
    assert User.objects.filter(username="profile_test_user").exists()