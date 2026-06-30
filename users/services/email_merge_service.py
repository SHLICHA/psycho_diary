"""Сервис explicit confirm flow для merge-конфликтов по email."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from asgiref.sync import sync_to_async
from django.utils import timezone

from users.models import EmailMergeRequest, User
from users.services.identity_policy_service import IdentityPolicyService


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
    def _resolve_target_platform(cls, merge_request: EmailMergeRequest) -> Optional[str]:
        """Определяет второй канал для двустороннего подтверждения Telegram/MAX."""
        source_platform = (merge_request.source_platform or '').lower()
        target_user = merge_request.target_user

        if source_platform == 'telegram' and getattr(target_user, 'max_id', None):
            return 'max'
        if source_platform == 'max' and getattr(target_user, 'telegram_id', None):
            return 'telegram'
        return None

    @classmethod
    def _build_transport_confirmation_metadata(cls, merge_request: EmailMergeRequest) -> dict:
        """Формирует metadata для двустороннего transport confirmation flow."""
        target_platform = cls._resolve_target_platform(merge_request)
        now = timezone.now()
        metadata = dict(merge_request.metadata or {})

        metadata.update(
            {
                'confirmation_mode': 'dual_transport',
                'requester_platform': merge_request.source_platform,
                'requester_confirmed': False,
                'requester_confirmed_at': None,
                'target_platform': target_platform,
                'target_confirmation_required': bool(target_platform),
                'target_confirmation_token': secrets.token_urlsafe(32) if target_platform else None,
                'target_confirmation_status': 'pending' if target_platform else 'not_required',
                'target_confirmation_expires_at': (
                    now + timedelta(seconds=cls.TARGET_CONFIRMATION_TTL_SECONDS)
                ).isoformat()
                if target_platform
                else None,
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
        merge_request.metadata = cls._build_transport_confirmation_metadata(merge_request)
        merge_request.save(update_fields=['metadata', 'updated_at'])
        return merge_request

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
        merge_request = EmailMergeRequest.objects.filter(
            requester_user=requester_user,
            confirmation_token=confirmation_token,
        ).first()

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

            target_required = bool(metadata.get('target_confirmation_required'))
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
            return EmailMergeConfirmationResult(status='confirmed', merge_request=merge_request)

        merge_request.status = 'confirmed'
        merge_request.confirmed_at = now
        merge_request.save(update_fields=['status', 'confirmed_at', 'updated_at'])
        return EmailMergeConfirmationResult(status='confirmed', merge_request=merge_request)

    @classmethod
    def confirm_target_transport(
        cls,
        target_user: User,
        target_confirmation_token: str,
        approve: bool,
    ) -> EmailMergeConfirmationResult:
        """Подтверждение merge во втором канале (Telegram/MAX)."""
        merge_request = None
        for candidate in EmailMergeRequest.objects.filter(target_user=target_user, status='pending').order_by('-created_at'):
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
            return EmailMergeConfirmationResult(status='confirmed', merge_request=merge_request)

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
        merge_request = EmailMergeRequest.objects.filter(
            id=merge_request_id,
            requester_user=requester_user,
        ).first()
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
