"""Wave 3 MAX: premium / tokens payments."""

from unittest.mock import AsyncMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.messages import route_text_message
from bot.handlers.max.payments import handle_premium_menu
from bot.states.payment_states import PaymentStates
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def max_user(db):
    return User.objects.create_user(
        username='max_wave3',
        email='max_wave3@example.com',
        max_id=880003,
        language='ru',
        is_onboarding_completed=True,
    )


@pytest.mark.asyncio
async def test_premium_menu_command(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.payments.build_premium_menu_view',
        return_value={'text': 'Premium menu', 'reply_markup': None},
    )
    result = await route_text_message(max_user, '/premium', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'premium'
    send_func.assert_awaited()


@pytest.mark.asyncio
async def test_settings_premium_callback(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.payments.build_premium_menu_view',
        return_value={'text': 'Premium', 'reply_markup': None},
    )
    result = await route_callback(max_user, 'settings_premium', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'premium'


@pytest.mark.asyncio
async def test_subscription_requires_email(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.payments.initiate_subscription_payment',
        new=AsyncMock(return_value={'success': True, 'requires_email': True}),
    )
    mocker.patch(
        'bot.handlers.max.payments.build_payment_initiation_view',
        return_value={
            'mode': 'requires_email',
            'text': 'Введите email',
            'pending_payment_data': {'product': 'subscription_month'},
        },
    )
    result = await route_callback(
        max_user, 'purchase_subscription:month', send_func, max_id=max_user.max_id
    )
    assert result['mode'] == 'requires_email'
    assert max_state.matches_state(max_user.max_id, PaymentStates.waiting_for_email)


@pytest.mark.asyncio
async def test_token_purchase_ready(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.payments.initiate_token_payment',
        new=AsyncMock(return_value={'success': True}),
    )
    mocker.patch(
        'bot.handlers.max.payments.build_payment_initiation_view',
        return_value={'mode': 'payment_ready', 'text': 'Оплатите: https://pay.example'},
    )
    result = await route_callback(
        max_user, 'purchase_tokens:50', send_func, max_id=max_user.max_id
    )
    assert result['handled'] == 'purchase_tokens'
    assert result['mode'] == 'payment_ready'


@pytest.mark.asyncio
async def test_payment_email_flow(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(
        max_user.max_id,
        PaymentStates.waiting_for_email,
        pending_payment_data={'product': 'subscription_month'},
        payment_kind='subscription',
    )
    mocker.patch(
        'bot.handlers.max.payments.process_user_email_for_pending_payment',
        new=AsyncMock(return_value={'success': True, 'confirmation_url': 'https://pay'}),
    )
    mocker.patch(
        'bot.handlers.max.payments.build_email_payment_result_view',
        return_value={
            'mode': 'payment_ready',
            'clear_state': True,
            'messages': ['Ссылка на оплату', 'Email сохранён'],
        },
    )
    result = await route_text_message(
        max_user, 'user@example.com', send_func, max_id=max_user.max_id
    )
    assert result['mode'] == 'payment_ready'
    assert max_state.get_fsm_state(max_user.max_id) is None
    assert send_func.await_count == 2


@pytest.mark.asyncio
async def test_handle_premium_direct(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    mocker.patch(
        'bot.handlers.max.payments.build_premium_menu_view',
        return_value={'text': 'OK', 'reply_markup': None},
    )
    assert (await handle_premium_menu(max_user, send_func, max_id=max_user.max_id))['handled'] == 'premium'
