"""Сервис explicit confirm flow для merge-конфликтов по email."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from users.models import EmailMergeRequest, User
from users.services.identity_policy_service import IdentityPolicyService


class EmailMergeError(Exception):
    """Ошибка создания/ведения merge-request."""

    def __init__(self, code: str, message: str = ''):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


@dataclass(frozen=True)
class EmailMergeConfirmationResult:
    status: str
    code: Optional[str] = None
    merge_request: Optional[EmailMergeRequest] = None


class EmailMergeService:
    """Операции создания и подтверждения merge-request по email."""

    DEFAULT_TTL_SECONDS = 600
    TARGET_CONFIRMATION_TTL_SECONDS = 600

    @classmethod
    def _maybe_execute_merge(cls, merge_request: EmailMergeRequest) -> EmailMergeConfirmationResult:
        """После dual-confirm запускает data merge при EMAIL_MERGE_EXECUTE_ENABLED."""
        from django.conf import settings

        from users.services.account_merge_service import AccountMergeService

        if not getattr(settings, 'EMAIL_MERGE_EXECUTE_ENABLED', False):
            return EmailMergeConfirmationResult(status='confirmed', merge_request=merge_request)

        merge_result = AccountMergeService.execute_merge(merge_request)
        if merge_result.status == 'merged':
            return EmailMergeConfirmationResult(
                status='merged',
                code='merged',
                merge_request=merge_result.merge_request,
            )
        if merge_result.status == 'merge_failed':
            return EmailMergeConfirmationResult(
                status='merge_failed',
                code=merge_result.code or 'merge_failed',
                merge_request=merge_result.merge_request,
            )
        return EmailMergeConfirmationResult(status='confirmed', merge_request=merge_request)

    @classmethod
    def resolve_target_delivery_platform(
        cls,
        *,
        target_user: User,
        source_platform: str = 'web',
        requester_user: User | None = None,
    ) -> str:
        """
        Выбирает канал доставки target-confirm.

        Dual-confirm обязателен всегда; без мессенджера у владельца email — ошибка.
        Предпочтение: complementary к source_platform, иначе любой доступный канал target.
        """
        target_tg = getattr(target_user, 'telegram_id', None)
        target_max = getattr(target_user, 'max_id', None)
        if not target_tg and not target_max:
            # Web-only email owner: confirm via emailed OTP (not messenger).
            return 'email'

        source = (source_platform or 'web').lower()
        requester_tg = getattr(requester_user, 'telegram_id', None) if requester_user else None
        requester_max = getattr(requester_user, 'max_id', None) if requester_user else None

        # Complementary: TG requester → MAX target, MAX requester → TG target.
        if source == 'telegram' and target_max:
            return 'max'
        if source == 'max' and target_tg:
            return 'telegram'

        # Web / same-platform / unknown: prefer channel target has that requester lacks.
        if target_tg and not requester_tg:
            return 'telegram'
        if target_max and not requester_max:
            return 'max'

        if target_tg:
            return 'telegram'
        return 'max'

    @classmethod
    def _build_transport_confirmation_metadata(
        cls,
        merge_request: EmailMergeRequest,
        *,
        target_platform: str,
    ) -> dict:
        """Формирует metadata для обязательного двустороннего transport confirmation."""
        now = timezone.now()
        metadata = dict(merge_request.metadata or {})

        metadata.update(
            {
                'confirmation_mode': 'dual_transport',
                'requester_platform': merge_request.source_platform,
                'requester_confirmed': False,
                'requester_confirmed_at': None,
                'target_platform': target_platform,
                'target_confirmation_required': True,
                'target_confirmation_token': secrets.token_urlsafe(32),
                'target_confirmation_status': 'pending',
                'target_confirmation_expires_at': (
                    now + timedelta(seconds=cls.TARGET_CONFIRMATION_TTL_SECONDS)
                ).isoformat(),
                'target_confirmed_at': None,
            }
        )
        return metadata

    @classmethod
    def create_merge_request(
        cls,
        requester_user: User,
        email: str,
        source_platform: str = 'web',
        source_context: str = 'complete_registration',
    ) -> EmailMergeRequest:
        email_hash = IdentityPolicyService.build_email_hash(email)
        target_user = User.objects.get(email_hash=email_hash)

        target_platform = cls.resolve_target_delivery_platform(
            target_user=target_user,
            source_platform=source_platform,
            requester_user=requester_user,
        )

        now = timezone.now()
        # Инвалидация активных pending-запросов от того же инициатора по тому же email.
        EmailMergeRequest.objects.filter(
            requester_user=requester_user,
            email_hash=email_hash,
            status='pending',
        ).update(status='cancelled')

        merge_request = EmailMergeRequest.objects.create(
            requester_user=requester_user,
            target_user=target_user,
            email_hash=email_hash,
            confirmation_token=secrets.token_urlsafe(32),
            source_platform=source_platform,
            source_context=source_context,
            status='pending',
            expires_at=now + timedelta(seconds=cls.DEFAULT_TTL_SECONDS),
            metadata={'email': email},
        )
        merge_request.metadata = cls._build_transport_confirmation_metadata(
            merge_request,
            target_platform=target_platform,
        )
        merge_request.save(update_fields=['metadata', 'updated_at'])
        if target_platform == 'email':
            cls.dispatch_target_email_otp(merge_request, email=email)
        return merge_request

    @classmethod
    def dispatch_target_email_otp(cls, merge_request: EmailMergeRequest, *, email: str) -> dict:
        """Отправляет OTP владельцу email (web-only target)."""
        from users.services.auth_token_service import create_merge_email_otp
        from users.services.email_delivery_service import EmailDeliveryService

        code = create_merge_email_otp(merge_request.id)
        language = getattr(merge_request.target_user, 'language', None) or 'ru'
        sent = EmailDeliveryService.send_merge_otp(
            to_email=email,
            otp_code=code,
            language=language,
        )
        metadata = dict(merge_request.metadata or {})
        metadata['email_otp_sent'] = bool(sent)
        merge_request.metadata = metadata
        merge_request.save(update_fields=['metadata', 'updated_at'])
        return {'ok': bool(sent), 'delivery': 'email'}

    @classmethod
    def confirm_target_email_otp(
        cls,
        *,
        merge_request_id: int,
        otp_code: str,
        actor_user: User | None = None,
    ) -> EmailMergeConfirmationResult:
        """Подтверждение target-стороны кодом из письма."""
        from users.services.auth_token_service import validate_merge_email_otp

        merge_request = EmailMergeRequest.objects.filter(pk=merge_request_id).first()
        if merge_request is None:
            return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')
        if (merge_request.metadata or {}).get('target_platform') != 'email':
            return EmailMergeConfirmationResult(status='error', code='target_not_email_otp')
        if actor_user and actor_user.id not in (
            merge_request.target_user_id,
            merge_request.requester_user_id,
        ):
            return EmailMergeConfirmationResult(status='error', code='otp_forbidden')
        if not validate_merge_email_otp(merge_request_id, otp_code):
            return EmailMergeConfirmationResult(status='error', code='otp_invalid')
        target_token = (merge_request.metadata or {}).get('target_confirmation_token')
        if not target_token:
            return EmailMergeConfirmationResult(status='error', code='target_confirmation_token_invalid')
        return cls.confirm_target_transport(
            merge_request.target_user,
            target_token,
            approve=True,
        )

    @classmethod
    async def acreate_merge_request(
        cls,
        requester_user: User,
        email: str,
        source_platform: str = 'web',
        source_context: str = 'complete_registration',
    ) -> EmailMergeRequest:
        """Async wrapper для transport-слоя."""
        return await sync_to_async(cls.create_merge_request)(
            requester_user,
            email,
            source_platform,
            source_context,
        )

    @classmethod
    def confirm_merge_request(
        cls,
        requester_user: User,
        confirmation_token: str,
    ) -> EmailMergeConfirmationResult:
        with transaction.atomic():
            merge_request = (
                EmailMergeRequest.objects.select_for_update()
                .select_related('requester_user', 'target_user')
                .filter(
                    requester_user=requester_user,
                    confirmation_token=confirmation_token,
                )
                .first()
            )

            if merge_request is None:
                return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')

            if merge_request.status != 'pending':
                return EmailMergeConfirmationResult(status='error', code='merge_request_not_pending')

            now = timezone.now()
            if merge_request.expires_at <= now:
                merge_request.status = 'expired'
                merge_request.save(update_fields=['status', 'updated_at'])
                return EmailMergeConfirmationResult(status='error', code='merge_request_expired')

            metadata = dict(merge_request.metadata or {})
            if metadata.get('confirmation_mode') == 'dual_transport':
                metadata['requester_confirmed'] = True
                metadata['requester_confirmed_at'] = now.isoformat()

                target_required = bool(metadata.get('target_confirmation_required', True))
                target_status = metadata.get('target_confirmation_status')

                if target_required and target_status != 'approved':
                    merge_request.metadata = metadata
                    merge_request.save(update_fields=['metadata', 'updated_at'])
                    return EmailMergeConfirmationResult(
                        status='pending_target_confirmation',
                        code='pending_target_confirmation',
                        merge_request=merge_request,
                    )

                merge_request.metadata = metadata
                merge_request.status = 'confirmed'
                merge_request.confirmed_at = now
                merge_request.save(update_fields=['metadata', 'status', 'confirmed_at', 'updated_at'])
                return cls._maybe_execute_merge(merge_request)

            # Legacy single-confirm path (не должен создаваться новыми запросами).
            merge_request.status = 'confirmed'
            merge_request.confirmed_at = now
            merge_request.save(update_fields=['status', 'confirmed_at', 'updated_at'])
            return cls._maybe_execute_merge(merge_request)

    @classmethod
    def confirm_target_transport(
        cls,
        target_user: User,
        target_confirmation_token: str,
        approve: bool,
    ) -> EmailMergeConfirmationResult:
        """Подтверждение merge во втором канале (Telegram/MAX)."""
        with transaction.atomic():
            merge_request = None
            for candidate in (
                EmailMergeRequest.objects.select_for_update()
                .select_related('requester_user', 'target_user')
                .filter(target_user=target_user, status='pending')
                .order_by('-created_at')
            ):
                candidate_metadata = dict(candidate.metadata or {})
                if candidate_metadata.get('target_confirmation_token') == target_confirmation_token:
                    merge_request = candidate
                    break

            if merge_request is None:
                return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')

            metadata = dict(merge_request.metadata or {})

            now = timezone.now()
            target_expires_at = metadata.get('target_confirmation_expires_at')
            if target_expires_at:
                expires_dt = datetime.fromisoformat(target_expires_at)
                if timezone.is_naive(expires_dt):
                    expires_dt = timezone.make_aware(expires_dt, timezone.get_current_timezone())
                if expires_dt <= now:
                    metadata['target_confirmation_status'] = 'expired'
                    merge_request.metadata = metadata
                    merge_request.status = 'expired'
                    merge_request.save(update_fields=['metadata', 'status', 'updated_at'])
                    return EmailMergeConfirmationResult(status='error', code='target_confirmation_expired')

            if not approve:
                metadata['target_confirmation_status'] = 'rejected'
                metadata['target_confirmed_at'] = now.isoformat()
                merge_request.metadata = metadata
                merge_request.status = 'cancelled'
                merge_request.save(update_fields=['metadata', 'status', 'updated_at'])
                return EmailMergeConfirmationResult(
                    status='rejected',
                    code='merge_request_rejected_by_target',
                    merge_request=merge_request,
                )

            metadata['target_confirmation_status'] = 'approved'
            metadata['target_confirmed_at'] = now.isoformat()
            merge_request.metadata = metadata

            if metadata.get('requester_confirmed'):
                merge_request.status = 'confirmed'
                merge_request.confirmed_at = now
                merge_request.save(update_fields=['metadata', 'status', 'confirmed_at', 'updated_at'])
                return cls._maybe_execute_merge(merge_request)

            merge_request.save(update_fields=['metadata', 'updated_at'])
            return EmailMergeConfirmationResult(
                status='pending_requester_confirmation',
                code='pending_requester_confirmation',
                merge_request=merge_request,
            )

    @classmethod
    async def aconfirm_target_transport(
        cls,
        target_user: User,
        target_confirmation_token: str,
        approve: bool,
    ) -> EmailMergeConfirmationResult:
        """Async wrapper для confirm_target_transport."""
        return await sync_to_async(cls.confirm_target_transport)(
            target_user,
            target_confirmation_token,
            approve,
        )

    @classmethod
    async def aconfirm_merge_request(
        cls,
        requester_user: User,
        confirmation_token: str,
    ) -> EmailMergeConfirmationResult:
        """Async wrapper для transport-слоя."""
        return await sync_to_async(cls.confirm_merge_request)(requester_user, confirmation_token)

    @classmethod
    def confirm_merge_request_by_id(
        cls,
        requester_user: User,
        merge_request_id: int,
    ) -> EmailMergeConfirmationResult:
        """Подтверждение merge-request по ID для inline-callback flow."""
        merge_request = EmailMergeRequest.objects.filter(
            id=merge_request_id,
            requester_user=requester_user,
        ).first()
        if merge_request is None:
            return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')
        return cls.confirm_merge_request(
            requester_user=requester_user,
            confirmation_token=merge_request.confirmation_token,
        )

    @classmethod
    async def aconfirm_merge_request_by_id(
        cls,
        requester_user: User,
        merge_request_id: int,
    ) -> EmailMergeConfirmationResult:
        """Async wrapper для confirm_merge_request_by_id."""
        return await sync_to_async(cls.confirm_merge_request_by_id)(requester_user, merge_request_id)

    @classmethod
    def cancel_merge_request_by_id(
        cls,
        requester_user: User,
        merge_request_id: int,
    ) -> EmailMergeConfirmationResult:
        """Отмена merge-request инициатором."""
        with transaction.atomic():
            merge_request = (
                EmailMergeRequest.objects.select_for_update()
                .filter(
                    id=merge_request_id,
                    requester_user=requester_user,
                )
                .first()
            )
            if merge_request is None:
                return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')
            if merge_request.status != 'pending':
                return EmailMergeConfirmationResult(status='error', code='merge_request_not_pending')

            metadata = dict(merge_request.metadata or {})
            metadata['cancelled_by'] = 'requester'
            metadata['cancelled_at'] = timezone.now().isoformat()
            merge_request.metadata = metadata
            merge_request.status = 'cancelled'
            merge_request.save(update_fields=['metadata', 'status', 'updated_at'])
            return EmailMergeConfirmationResult(status='cancelled', merge_request=merge_request)

    @classmethod
    async def acancel_merge_request_by_id(
        cls,
        requester_user: User,
        merge_request_id: int,
    ) -> EmailMergeConfirmationResult:
        """Async wrapper для cancel_merge_request_by_id."""
        return await sync_to_async(cls.cancel_merge_request_by_id)(requester_user, merge_request_id)

    @classmethod
    def confirm_target_transport_by_request_id(
        cls,
        target_user: User,
        merge_request_id: int,
        approve: bool,
    ) -> EmailMergeConfirmationResult:
        """Подтверждение/отклонение target-side по ID merge-request."""
        merge_request = EmailMergeRequest.objects.filter(
            id=merge_request_id,
            target_user=target_user,
            status='pending',
        ).first()
        if merge_request is None:
            return EmailMergeConfirmationResult(status='error', code='merge_request_not_found')

        target_token = (merge_request.metadata or {}).get('target_confirmation_token')
        if not target_token:
            return EmailMergeConfirmationResult(status='error', code='target_confirmation_token_invalid')

        return cls.confirm_target_transport(target_user, target_token, approve)

    @classmethod
    async def aconfirm_target_transport_by_request_id(
        cls,
        target_user: User,
        merge_request_id: int,
        approve: bool,
    ) -> EmailMergeConfirmationResult:
        """Async wrapper для confirm_target_transport_by_request_id."""
        return await sync_to_async(cls.confirm_target_transport_by_request_id)(
            target_user,
            merge_request_id,
            approve,
        )


def build_requester_merge_result_view(
    result: EmailMergeConfirmationResult,
    delivery_result: Optional[dict],
    language: str,
) -> dict:
    """Transport payload для результата подтверждения merge инициатором."""
    from messages import get_message

    if result.status == 'cancelled':
        return {
            'success': True,
            'mode': 'cancelled',
            'text': get_message('merge_request_cancelled', language=language),
        }

    if result.status == 'confirmed':
        return {
            'success': True,
            'mode': 'confirmed',
            'text': get_message('merge_request_confirmed', language=language),
        }

    if result.status == 'merged':
        return {
            'success': True,
            'mode': 'merged',
            'text': get_message('merge_accounts_completed', language=language),
        }

    if result.status == 'merge_failed':
        fail_key = 'merge_accounts_failed'
        if result.code == 'user_not_active':
            fail_key = 'merge_accounts_failed_user_not_active'
        return {
            'success': False,
            'mode': 'merge_failed',
            'alert_text': get_message(fail_key, language=language),
            'show_alert': True,
            'text': get_message(fail_key, language=language),
        }

    if result.status == 'pending_target_confirmation' and result.merge_request is not None:
        if delivery_result and delivery_result.get('success'):
            return {
                'success': True,
                'mode': 'target_sent',
                'text': get_message('merge_target_confirmation_sent', language=language),
            }
        if delivery_result and delivery_result.get('delivery') == 'max_deferred':
            return {
                'success': True,
                'mode': 'max_deferred',
                'text': get_message('merge_target_confirmation_deferred_max', language=language),
            }
        if delivery_result and not delivery_result.get('success'):
            return {
                'success': False,
                'mode': 'delivery_failed',
                'alert_text': get_message('merge_target_delivery_failed', language=language),
                'show_alert': True,
                'text': get_message('merge_target_delivery_failed', language=language),
            }

    return {
        'success': False,
        'mode': 'error',
        'alert_text': get_message('error_generic', language=language),
        'show_alert': True,
    }


def build_target_merge_result_view(
    result: EmailMergeConfirmationResult,
    language: str,
) -> dict:
    """Transport payload для результата подтверждения merge целевым пользователем."""
    from messages import get_message

    if result.status == 'rejected':
        return {
            'success': True,
            'mode': 'rejected',
            'text': get_message('merge_target_rejected', language=language),
        }

    if result.status == 'pending_requester_confirmation':
        return {
            'success': True,
            'mode': 'pending_requester',
            'text': get_message('merge_target_approved_wait_requester', language=language),
        }

    if result.status == 'confirmed':
        return {
            'success': True,
            'mode': 'confirmed',
            'text': get_message('merge_request_confirmed', language=language),
        }

    if result.status == 'merged':
        return {
            'success': True,
            'mode': 'merged',
            'text': get_message('merge_accounts_completed', language=language),
        }

    if result.status == 'merge_failed':
        fail_key = 'merge_accounts_failed'
        if result.code == 'user_not_active':
            fail_key = 'merge_accounts_failed_user_not_active'
        return {
            'success': False,
            'mode': 'merge_failed',
            'alert_text': get_message(fail_key, language=language),
            'show_alert': True,
            'text': get_message(fail_key, language=language),
        }

    if result.code == 'target_confirmation_expired':
        return {
            'success': True,
            'mode': 'expired',
            'text': get_message('merge_request_expired', language=language),
        }

    return {
        'success': False,
        'mode': 'error',
        'alert_text': get_message('error_generic', language=language),
        'show_alert': True,
    }
