import pytest

from users.models import User
from users.services.email_merge_service import EmailMergeError, EmailMergeService


pytestmark = pytest.mark.django_db


def test_create_merge_request_builds_dual_transport_metadata_for_telegram_to_max():
    target_user = User.objects.create_user(
        username='target_max_user',
        email='shared-transport@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=9001001,
    )
    requester_user = User.objects.create_user(
        username='requester_tg_user',
        email='',
        telegram_id=7001001,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-transport@example.com',
        source_platform='telegram',
        source_context='profile_edit',
    )

    assert merge_request.target_user_id == target_user.id
    assert merge_request.metadata.get('confirmation_mode') == 'dual_transport'
    assert merge_request.metadata.get('target_confirmation_required') is True
    assert merge_request.metadata.get('target_platform') == 'max'
    assert merge_request.metadata.get('target_confirmation_status') == 'pending'
    assert merge_request.metadata.get('target_confirmation_token')


def test_web_source_always_requires_target_confirmation_via_available_messenger():
    target_user = User.objects.create_user(
        username='target_web_owner',
        email='shared-web@example.com',
        password='testpass123',
        telegram_id=7003001,
        max_id=None,
    )
    requester_user = User.objects.create_user(
        username='requester_web_user',
        email='',
        telegram_id=7003002,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-web@example.com',
        source_platform='web',
        source_context='complete_registration',
    )

    assert merge_request.metadata.get('target_confirmation_required') is True
    assert merge_request.metadata.get('target_platform') == 'telegram'
    assert target_user.id == merge_request.target_user_id


def test_create_merge_request_fails_when_target_has_no_messenger():
    User.objects.create_user(
        username='web_only_owner',
        email='web-only@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=None,
    )
    requester_user = User.objects.create_user(
        username='requester_needs_messenger',
        email='',
        telegram_id=7004001,
    )

    with pytest.raises(EmailMergeError) as exc_info:
        EmailMergeService.create_merge_request(
            requester_user=requester_user,
            email='web-only@example.com',
            source_platform='telegram',
            source_context='profile_edit',
        )

    assert exc_info.value.code == 'target_messenger_unavailable'


def test_payment_labeled_as_telegram_still_requires_dual_when_target_is_telegram_only():
    """Регрессия: неверный/старый source_platform не должен отключать dual-confirm."""
    target_user = User.objects.create_user(
        username='target_tg_only',
        email='shared-tg-only@example.com',
        password='testpass123',
        telegram_id=7005001,
        max_id=None,
    )
    requester_user = User.objects.create_user(
        username='requester_max_mislabeled',
        email='',
        telegram_id=None,
        max_id=9005001,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-tg-only@example.com',
        source_platform='telegram',  # ошибочная метка, как в старом payment bug
        source_context='payment_receipt_email',
    )

    assert merge_request.metadata.get('target_confirmation_required') is True
    assert merge_request.metadata.get('target_platform') == 'telegram'
    assert merge_request.target_user_id == target_user.id

    requester_confirmation = EmailMergeService.confirm_merge_request(
        requester_user=requester_user,
        confirmation_token=merge_request.confirmation_token,
    )
    assert requester_confirmation.status == 'pending_target_confirmation'


def test_requester_confirmation_waits_for_target_confirmation_when_dual_transport_required():
    target_user = User.objects.create_user(
        username='target_max_user_wait',
        email='shared-wait@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=9001002,
    )
    requester_user = User.objects.create_user(
        username='requester_tg_user_wait',
        email='',
        telegram_id=7001002,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-wait@example.com',
        source_platform='telegram',
        source_context='payment_receipt_email',
    )

    requester_confirmation = EmailMergeService.confirm_merge_request(
        requester_user=requester_user,
        confirmation_token=merge_request.confirmation_token,
    )
    assert requester_confirmation.status == 'pending_target_confirmation'

    target_confirmation_token = merge_request.metadata.get('target_confirmation_token')
    target_confirmation = EmailMergeService.confirm_target_transport(
        target_user=target_user,
        target_confirmation_token=target_confirmation_token,
        approve=True,
    )

    assert target_confirmation.status == 'confirmed'
    merge_request.refresh_from_db()
    assert merge_request.status == 'confirmed'


def test_target_rejection_cancels_merge_request():
    target_user = User.objects.create_user(
        username='target_max_user_reject',
        email='shared-reject@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=9001003,
    )
    requester_user = User.objects.create_user(
        username='requester_tg_user_reject',
        email='',
        telegram_id=7001003,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-reject@example.com',
        source_platform='telegram',
        source_context='profile_edit',
    )

    target_confirmation_token = merge_request.metadata.get('target_confirmation_token')
    target_rejection = EmailMergeService.confirm_target_transport(
        target_user=target_user,
        target_confirmation_token=target_confirmation_token,
        approve=False,
    )

    assert target_rejection.status == 'rejected'
    assert target_rejection.code == 'merge_request_rejected_by_target'
    merge_request.refresh_from_db()
    assert merge_request.status == 'cancelled'


def test_reverse_direction_max_to_telegram_is_supported():
    target_user = User.objects.create_user(
        username='target_tg_user',
        email='shared-reverse@example.com',
        password='testpass123',
        telegram_id=7002001,
        max_id=None,
    )
    requester_user = User.objects.create_user(
        username='requester_max_user',
        email='',
        telegram_id=None,
        max_id=9002001,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='shared-reverse@example.com',
        source_platform='max',
        source_context='settings_email',
    )

    assert merge_request.metadata.get('target_platform') == 'telegram'
    target_confirmation_token = merge_request.metadata.get('target_confirmation_token')

    target_confirmation = EmailMergeService.confirm_target_transport(
        target_user=target_user,
        target_confirmation_token=target_confirmation_token,
        approve=True,
    )
    assert target_confirmation.status == 'pending_requester_confirmation'

    requester_confirmation = EmailMergeService.confirm_merge_request(
        requester_user=requester_user,
        confirmation_token=merge_request.confirmation_token,
    )
    assert requester_confirmation.status == 'confirmed'

    merge_request.refresh_from_db()
    assert merge_request.status == 'confirmed'


def test_requester_can_confirm_and_cancel_by_merge_request_id():
    User.objects.create_user(
        username='target_for_id_ops',
        email='id-ops@example.com',
        password='testpass123',
        telegram_id=None,
        max_id=9010001,
    )
    requester_user = User.objects.create_user(
        username='requester_for_id_ops',
        email='',
        telegram_id=7010001,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='id-ops@example.com',
        source_platform='telegram',
        source_context='profile_edit',
    )

    pending_result = EmailMergeService.confirm_merge_request_by_id(
        requester_user=requester_user,
        merge_request_id=merge_request.id,
    )
    assert pending_result.status == 'pending_target_confirmation'

    cancelled_result = EmailMergeService.cancel_merge_request_by_id(
        requester_user=requester_user,
        merge_request_id=merge_request.id,
    )
    assert cancelled_result.status == 'cancelled'


def test_target_can_confirm_by_merge_request_id():
    target_user = User.objects.create_user(
        username='target_by_id',
        email='target-by-id@example.com',
        password='testpass123',
        telegram_id=7010002,
        max_id=None,
    )
    requester_user = User.objects.create_user(
        username='requester_by_id',
        email='',
        telegram_id=None,
        max_id=9010002,
    )

    merge_request = EmailMergeService.create_merge_request(
        requester_user=requester_user,
        email='target-by-id@example.com',
        source_platform='max',
        source_context='profile_edit',
    )

    result = EmailMergeService.confirm_target_transport_by_request_id(
        target_user=target_user,
        merge_request_id=merge_request.id,
        approve=True,
    )
    assert result.status == 'pending_requester_confirmation'
