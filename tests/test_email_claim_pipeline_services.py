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
        max_id=800001,
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
    assert merge_request.metadata.get('target_confirmation_required') is True
    assert merge_request.metadata.get('target_platform') == 'max'


@pytest.mark.asyncio
async def test_profile_email_save_updates_email_hash_for_future_conflicts(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    first_user = await User.objects.acreate(
        username='tg_first_owner',
        email='',
        telegram_id=900101,
    )
    second_user = await User.objects.acreate(
        username='max_second_owner',
        email='',
        telegram_id=None,
        max_id=800101,
    )

    first_result = await update_user_profile_field(
        first_user,
        'email',
        'shared-save@example.com',
        source_platform='telegram',
    )

    assert first_result['success'] is True

    await first_user.arefresh_from_db()
    assert first_user.email == 'shared-save@example.com'
    assert first_user.email_hash is not None

    second_result = await update_user_profile_field(
        second_user,
        'email',
        'shared-save@example.com',
        source_platform='max',
    )

    assert second_result['success'] is False
    assert second_result['error_code'] == 'email_confirmation_required'


@pytest.mark.asyncio
async def test_profile_email_conflict_without_confirmation_flag_returns_already_exists(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = False
    await User.objects.acreate(
        username='web_owner_flag_off',
        email='shared2@example.com',
        telegram_id=None,
        max_id=800002,
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
async def test_profile_email_conflict_fails_when_owner_has_no_messenger(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    await User.objects.acreate(
        username='web_only_owner',
        email='no-messenger@example.com',
        telegram_id=None,
        max_id=None,
    )
    telegram_user = await User.objects.acreate(
        username='tg_profile_no_messenger',
        email='',
        telegram_id=900010,
    )

    result = await update_user_profile_field(telegram_user, 'email', 'no-messenger@example.com')

    assert result['success'] is False
    assert result['error_code'] == 'target_messenger_unavailable'


@pytest.mark.asyncio
async def test_payment_email_conflict_returns_confirmation_required(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    await User.objects.acreate(
        username='web_payment_owner',
        email='receipt@example.com',
        telegram_id=None,
        max_id=800003,
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
        source_platform='telegram',
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
    assert merge_request.metadata.get('target_confirmation_required') is True


@pytest.mark.asyncio
async def test_payment_email_save_updates_email_hash_for_future_conflicts(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    first_user = await User.objects.acreate(
        username='payment_first_owner',
        email='',
        telegram_id=900102,
    )
    second_user = await User.objects.acreate(
        username='payment_second_owner',
        email='',
        telegram_id=None,
        max_id=800102,
    )
    pending_payment_data = {
        'amount': 199,
        'description': 'Подписка PRO на 30 дней',
        'payment_type': 'subscription_month',
        'days': 30,
    }

    first_result = await process_user_email_for_pending_payment(
        first_user,
        'payment-shared@example.com',
        pending_payment_data,
        source_platform='telegram',
    )

    assert first_result['success'] is True

    await first_user.arefresh_from_db()
    assert first_user.email == 'payment-shared@example.com'
    assert first_user.email_hash is not None

    second_result = await process_user_email_for_pending_payment(
        second_user,
        'payment-shared@example.com',
        pending_payment_data,
        source_platform='max',
    )

    assert second_result['success'] is False
    assert second_result['error_code'] == 'email_confirmation_required'


@pytest.mark.asyncio
async def test_payment_email_conflict_from_max_uses_max_source_platform(settings):
    settings.EMAIL_MERGE_CONFIRMATION_ENABLED = True
    await User.objects.acreate(
        username='tg_payment_owner',
        email='max-receipt@example.com',
        telegram_id=900020,
        max_id=None,
    )
    max_user = await User.objects.acreate(
        username='max_payment_user',
        email='',
        telegram_id=None,
        max_id=800020,
    )

    result = await process_user_email_for_pending_payment(
        max_user,
        'max-receipt@example.com',
        {
            'amount': 199,
            'description': 'Подписка PRO на 30 дней',
            'payment_type': 'subscription_month',
            'days': 30,
        },
        source_platform='max',
    )

    assert result['success'] is False
    assert result['error_code'] == 'email_confirmation_required'

    merge_request = await EmailMergeRequest.objects.filter(
        requester_user=max_user,
        source_platform='max',
        source_context='payment_receipt_email',
        status='pending',
    ).afirst()
    assert merge_request is not None
    assert merge_request.metadata.get('target_confirmation_required') is True
    assert merge_request.metadata.get('target_platform') == 'telegram'
