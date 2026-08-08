"""Phase B API: payments products/create/status/sync/webhook."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from users.models import Payment, User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        username="pay_user",
        email="pay@example.com",
        password="testpass123",
        language="ru",
    )


@pytest.fixture
def auth_token(auth_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(auth_user).access_token)


def _auth(api_client, auth_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth_token}")


def test_payment_products(api_client, auth_token):
    _auth(api_client, auth_token)
    resp = api_client.get("/api/v1/payments/products/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["currency"] == "RUB"
    assert len(resp.data["subscriptions"]) == 2
    assert len(resp.data["token_packs"]) == 5
    assert resp.data["subscriptions"][0]["sku"] == "subscription_month"


def test_payment_create_subscription_and_tokens(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.payment_service.initiate_subscription_payment",
        new=AsyncMock(
            return_value={
                "success": True,
                "requires_email": False,
                "confirmation_url": "https://yookassa.test/pay",
                "payment_id": 11,
                "yookassa_payment_id": "yo_11",
                "error": None,
            }
        ),
    )
    sub = api_client.post("/api/v1/payments/create/", {"product": "subscription_month"}, format="json")
    assert sub.status_code == status.HTTP_200_OK
    assert sub.data["confirmation_url"].startswith("https://")
    assert sub.data["payment_id"] == 11

    mocker.patch(
        "diary.services.payment_service.initiate_token_payment",
        new=AsyncMock(
            return_value={
                "success": True,
                "requires_email": True,
                "pending_payment_data": {
                    "amount": 50,
                    "token_count": 10,
                    "description": "tok",
                    "payment_type": "tokens_10",
                },
                "confirmation_url": None,
                "error": None,
            }
        ),
    )
    tok = api_client.post("/api/v1/payments/create/", {"product": "tokens_10"}, format="json")
    assert tok.status_code == status.HTTP_200_OK
    assert tok.data["requires_email"] is True


def test_payment_email_and_detail_list(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    mocker.patch(
        "diary.services.payment_service.process_user_email_for_pending_payment",
        new=AsyncMock(
            return_value={
                "success": True,
                "confirmation_url": "https://yookassa.test/pay2",
                "payment_id": 22,
                "yookassa_payment_id": "yo_22",
                "error": None,
            }
        ),
    )
    email_resp = api_client.post(
        "/api/v1/payments/email/",
        {
            "email": "pay@example.com",
            "pending_payment_data": {
                "amount": 199,
                "days": 30,
                "description": "sub",
                "payment_type": "subscription_month",
            },
        },
        format="json",
    )
    assert email_resp.status_code == status.HTTP_200_OK
    assert email_resp.data["confirmation_url"]

    payment = Payment.objects.create(
        user=auth_user,
        yookassa_payment_id="yo_detail_1",
        amount_rub=Decimal("199.00"),
        payment_type="subscription_month",
        subscription_days_granted=30,
        status="pending",
    )
    detail = api_client.get(f"/api/v1/payments/{payment.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data["payment"]["status"] == "pending"
    assert "token_balance" in detail.data["user"]

    listed = api_client.get("/api/v1/payments/")
    assert listed.status_code == status.HTTP_200_OK
    assert len(listed.data["results"]) >= 1


def test_payment_sync_and_webhook(api_client, auth_user, auth_token, mocker):
    _auth(api_client, auth_token)
    payment = Payment.objects.create(
        user=auth_user,
        yookassa_payment_id="yo_sync_1",
        amount_rub=Decimal("50.00"),
        payment_type="tokens_10",
        tokens_granted=10,
        status="pending",
    )

    mocker.patch(
        "diary.services.payment_service.sync_payment_status",
        new=AsyncMock(
            return_value={
                "success": True,
                "payment": payment,
                "status": "succeeded",
                "granted": True,
                "error": None,
            }
        ),
    )
    sync = api_client.post(f"/api/v1/payments/{payment.id}/sync/")
    assert sync.status_code == status.HTTP_200_OK
    assert sync.data["status"] == "succeeded"
    assert sync.data["payment"]["id"] == payment.id

    mocker.patch(
        "diary.services.payment_service.confirm_payment_by_yookassa_id",
        new=AsyncMock(
            return_value={
                "success": True,
                "payment": payment,
                "status": "succeeded",
                "granted": False,
                "error": None,
            }
        ),
    )
    webhook = api_client.post(
        "/api/v1/payments/webhook/",
        {"event": "payment.succeeded", "object": {"id": "yo_sync_1", "status": "succeeded"}},
        format="json",
    )
    assert webhook.status_code == status.HTTP_200_OK
    assert webhook.data["success"] is True

    alias = api_client.post(
        "/api/payments/webhook/",
        {"object": {"id": "yo_sync_1", "status": "succeeded"}},
        format="json",
    )
    assert alias.status_code == status.HTTP_200_OK


def test_confirm_payment_by_yookassa_id_idempotent(auth_user, mocker):
    from diary.services.payment_service import PaymentService

    payment = Payment.objects.create(
        user=auth_user,
        yookassa_payment_id="yo_confirm_1",
        amount_rub=Decimal("50.00"),
        payment_type="tokens_10",
        tokens_granted=10,
        status="pending",
    )

    class FakeYoo:
        status = "succeeded"

    mocker.patch("bot.utils.payment_utils.check_yookassa_config", return_value=True)
    mocker.patch("yookassa.Configuration")
    mocker.patch("yookassa.Payment.find_one", return_value=FakeYoo())
    process = mocker.patch.object(User, "process_payment", new=AsyncMock())

    import asyncio

    first = asyncio.run(PaymentService.confirm_payment_by_yookassa_id("yo_confirm_1"))
    assert first["success"] is True
    assert first["granted"] is True
    payment.refresh_from_db()
    assert payment.status == "succeeded"
    assert process.await_count == 1

    second = asyncio.run(PaymentService.confirm_payment_by_yookassa_id("yo_confirm_1", provider_status="succeeded"))
    assert second["success"] is True
    assert second["granted"] is False
    assert process.await_count == 1
