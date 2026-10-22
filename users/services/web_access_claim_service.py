"""Bot-confirm flow: задать / сбросить web-пароль на существующий User без второго аккаунта."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from django.utils import timezone

from users.models import User, WebAccessClaimRequest
from users.services.auth_token_service import create_web_access_set_password_token
from users.services.identity_policy_service import IdentityPolicyService


class WebAccessClaimError(Exception):
    def __init__(self, code: str, message: str = ''):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


@dataclass
class WebAccessClaimStartResult:
    status: str
    code: Optional[str] = None
    claim: Optional[WebAccessClaimRequest] = None
    platform: Optional[str] = None
    platforms: list[str] = field(default_factory=list)
    set_password_token: Optional[str] = None
    delivery: Optional[dict] = None
    has_password: bool = False


class WebAccessClaimService:
    DEFAULT_TTL_SECONDS = 600
    SUPPORTED_PLATFORMS = ('telegram', 'max')

    @classmethod
    def available_platforms(cls, user: User) -> list[str]:
        platforms: list[str] = []
        if getattr(user, 'telegram_id', None):
            platforms.append('telegram')
        if getattr(user, 'max_id', None):
            platforms.append('max')
        return platforms

    @classmethod
    def _pick_platform(cls, user: User, preferred: Optional[str] = None) -> Optional[str]:
        available = cls.available_platforms(user)
        if not available:
            return None
        if preferred in available:
            return preferred
        if preferred and preferred not in available:
            return None
        # Default priority: Telegram, then MAX
        for name in cls.SUPPORTED_PLATFORMS:
            if name in available:
                return name
        return available[0]

    @classmethod
    def start_claim(
        cls,
        *,
        email: str,
        preferred_platform: Optional[str] = None,
    ) -> WebAccessClaimStartResult:
        """
        Старт bot-confirm для задания или сброса web-пароля.

        Статусы:
          - not_found: email не найден
          - no_messenger: email есть, но нет TG/MAX
          - platform_unavailable: запрошенный канал не привязан
          - pending: подтверждение отправлено в бот
        """
        email = (email or '').strip()
        if not email:
            raise WebAccessClaimError('email_required', 'Укажите email.')

        preferred = (preferred_platform or '').strip().lower() or None
        if preferred and preferred not in cls.SUPPORTED_PLATFORMS:
            raise WebAccessClaimError('invalid_platform', 'Поддерживаются telegram и max.')

        email_hash = IdentityPolicyService.build_email_hash(email)
        user = User.objects.filter(email_hash=email_hash, deletion_status='active').first()
        if user is None:
            return WebAccessClaimStartResult(status='not_found', code='not_found')

        has_password = user.has_usable_password()
        platforms = cls.available_platforms(user)
        if not platforms:
            return WebAccessClaimStartResult(
                status='no_messenger',
                code='no_messenger',
                has_password=has_password,
            )

        platform = cls._pick_platform(user, preferred)
        if platform is None:
            return WebAccessClaimStartResult(
                status='platform_unavailable',
                code='platform_unavailable',
                platforms=platforms,
                has_password=has_password,
            )

        WebAccessClaimRequest.objects.filter(user=user, status='pending').update(status='cancelled')
        token = secrets.token_urlsafe(24)
        claim = WebAccessClaimRequest.objects.create(
            user=user,
            email_hash=email_hash,
            confirmation_token=token,
            target_platform=platform,
            status='pending',
            expires_at=timezone.now() + timedelta(seconds=cls.DEFAULT_TTL_SECONDS),
            metadata={
                'email_hint': email[:2] + '***',
                'purpose': 'reset' if has_password else 'set',
            },
        )
        delivery = cls._dispatch_bot_confirm(claim)
        claim.metadata = {**(claim.metadata or {}), 'delivery': delivery}
        claim.save(update_fields=['metadata', 'updated_at'])
        return WebAccessClaimStartResult(
            status='pending',
            claim=claim,
            platform=platform,
            platforms=platforms,
            delivery=delivery if isinstance(delivery, dict) else None,
            has_password=has_password,
        )

    @classmethod
    def _dispatch_bot_confirm(cls, claim: WebAccessClaimRequest) -> dict:
        try:
            from bot.transports.web_access_claim_dispatcher import dispatch_web_access_claim_confirmation
            return async_to_sync(dispatch_web_access_claim_confirmation)(claim)
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    @classmethod
    def confirm_from_bot(
        cls,
        *,
        actor_user: User,
        claim_id: int | None = None,
        confirmation_token: str | None = None,
        approve: bool = True,
    ) -> WebAccessClaimStartResult:
        with transaction.atomic():
            qs = WebAccessClaimRequest.objects.select_for_update()
            if claim_id is not None:
                claim = qs.filter(pk=claim_id).first()
            elif confirmation_token:
                claim = qs.filter(confirmation_token=confirmation_token).first()
            else:
                claim = None
            if claim is None:
                raise WebAccessClaimError('claim_not_found', 'Запрос не найден.')
            if claim.status != 'pending':
                raise WebAccessClaimError('claim_not_pending', 'Запрос уже обработан.')
            if claim.expires_at <= timezone.now():
                claim.status = 'expired'
                claim.save(update_fields=['status', 'updated_at'])
                raise WebAccessClaimError('claim_expired', 'Срок запроса истёк.')
            if actor_user.id != claim.user_id:
                raise WebAccessClaimError('claim_wrong_user', 'Подтвердить может только владелец аккаунта.')
            if not approve:
                claim.status = 'cancelled'
                claim.save(update_fields=['status', 'updated_at'])
                return WebAccessClaimStartResult(
                    status='cancelled',
                    claim=claim,
                    platform=claim.target_platform,
                )
            claim.status = 'confirmed'
            claim.confirmed_at = timezone.now()
            claim.save(update_fields=['status', 'confirmed_at', 'updated_at'])
            set_token = create_web_access_set_password_token(claim.user_id)
            claim.metadata = {**(claim.metadata or {}), 'set_password_issued': True}
            claim.save(update_fields=['metadata', 'updated_at'])
            return WebAccessClaimStartResult(
                status='confirmed',
                claim=claim,
                platform=claim.target_platform,
                set_password_token=set_token,
            )

    @classmethod
    async def aconfirm_from_bot(cls, **kwargs) -> WebAccessClaimStartResult:
        return await sync_to_async(cls.confirm_from_bot)(**kwargs)
