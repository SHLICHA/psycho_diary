import pytest

from diary.services.payment_service import process_user_email_for_pending_payment
from diary.services.user_profile_service import update_user_profile_field
from users.models import EmailMergeRequest, User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_profile_email_conflict_returns_confirmation_required(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    await User.objects.acreate(
        username='web_owner',
        email='shared@example.com',
        telegram_id=None,
    )
    telegram_user = await User.objects.acreate(
        username='tg_profile_user',
        email='',
        telegram_id=900001,
    )

    result = await update_user_profile_field(telegram_user, 'email', 'shared@example.com')

    assert result['success'] is False
    assert result['error_code'] == 'email_confirmation_required'
    assert result['confirmation_required'] is True
    assert result.get('confirmation_token')

    merge_request = await EmailMergeRequest.objects.filter(
        requester_user=telegram_user,
        source_platform='telegram',
        source_context='profile_edit',
        status='pending',
    ).afirst()
    assert merge_request is not None


@pytest.mark.asyncio
async def test_profile_email_conflict_without_confirmation_flag_returns_already_exists(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = False
    await User.objects.acreate(
        username='web_owner_flag_off',
        email='shared2@example.com',
        telegram_id=None,
    )
    telegram_user = await User.objects.acreate(
        username='tg_profile_user_flag_off',
        email='',
        telegram_id=900002,
    )

    result = await update_user_profile_field(telegram_user, 'email', 'shared2@example.com')

    assert result['success'] is False
    assert result['error_code'] == 'email_already_exists'


@pytest.mark.asyncio
async def test_payment_email_conflict_returns_confirmation_required(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    await User.objects.acreate(
        username='web_payment_owner',
        email='receipt@example.com',
        telegram_id=None,
    )
    telegram_user = await User.objects.acreate(
        username='tg_payment_user',
        email='',
        telegram_id=900003,
    )

    pending_payment_data = {
        'amount': 199,
        'description': 'Подписка PRO на 30 дней',
        'payment_type': 'subscription_month',
        'days': 30,
    }

    result = await process_user_email_for_pending_payment(
        telegram_user,
        'receipt@example.com',
        pending_payment_data,
    )

    assert result['success'] is False
    assert result['error_code'] == 'email_confirmation_required'
    assert result['confirmation_required'] is True
    assert result.get('confirmation_token')

    await telegram_user.arefresh_from_db()
    assert telegram_user.email == ''

    merge_request = await EmailMergeRequest.objects.filter(
        requester_user=telegram_user,
        source_platform='telegram',
        source_context='payment_receipt_email',
        status='pending',
    ).afirst()
    assert merge_request is not None
