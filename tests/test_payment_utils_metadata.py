import uuid
from types import SimpleNamespace

import pytest
from django.test import override_settings
from asgiref.sync import sync_to_async

from bot.utils import payment_utils
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
@override_settings(
    YOOKASSA_SHOP_ID='shop_id_test',
    YOOKASSA_SECRET_KEY='secret_key_test',
    BOT_USERNAME='psycho_test_bot',
)
async def test_create_yookassa_payment_metadata_contains_internal_and_legacy_ids(mocker):
    user = await sync_to_async(User.objects.create_user)(
        username='pay_meta_user',
        email='pay-meta@example.com',
        password='testpass123',
        telegram_id=987654321,
    )

    captured = {}

    def fake_create(payment_data, idempotence_key):
        captured['payment_data'] = payment_data
        captured['idempotence_key'] = idempotence_key
        return SimpleNamespace(id='pay_test_001')

    mocker.patch.object(payment_utils.YooPayment, 'create', side_effect=fake_create)

    payment = await payment_utils.create_yookassa_payment(
        user=user,
        amount=199.0,
        description='Тестовый платеж',
        receipt_items=[
            {
                'description': 'Тест',
                'quantity': '1',
                'amount': {'value': '199.00', 'currency': 'RUB'},
                'vat_code': '4',
                'payment_mode': 'full_payment',
                'payment_subject': 'service',
            }
        ],
        metadata={'tokens': '10'},
    )

    assert payment.id == 'pay_test_001'
    assert captured['payment_data']['metadata']['internal_user_id'] == str(user.id)
    assert captured['payment_data']['metadata']['user_id'] == str(user.telegram_id)
    assert captured['payment_data']['metadata']['source_platform'] == 'telegram'
    assert captured['payment_data']['metadata']['source_user_id'] == str(user.telegram_id)
    assert captured['payment_data']['metadata']['tokens'] == '10'
    assert uuid.UUID(captured['idempotence_key'])
