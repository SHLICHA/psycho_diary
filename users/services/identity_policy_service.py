"""Policy-first сервис для merge/conflict разрешения identity по email."""

import hashlib
from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async

from users.models import User


@dataclass(frozen=True)
class EmailIdentityResolution:
    """Результат разрешения claim по email."""

    status: str
    code: Optional[str] = None
    matched_user_id: Optional[int] = None


class IdentityPolicyService:
    """Единые правила разрешения email-конфликтов между transport-аккаунтами."""

    @staticmethod
    def build_email_hash(email: str) -> str:
        return hashlib.sha256(email.lower().encode()).hexdigest()

    @classmethod
    def resolve_email_claim(
        cls,
        email: str,
        requester_user: Optional[User] = None,
    ) -> EmailIdentityResolution:
        """
        Определяет, может ли requester закрепить email за своим аккаунтом.

        status:
          - available: email не занят
          - self: email уже принадлежит requester
          - conflict: email занят другим аккаунтом
        """
        email_hash = cls.build_email_hash(email)
        matched_user = User.objects.filter(email_hash=email_hash).first()

        if matched_user is None:
            return EmailIdentityResolution(status='available')

        if requester_user and matched_user.id == requester_user.id:
            return EmailIdentityResolution(status='self', matched_user_id=matched_user.id)

        return EmailIdentityResolution(
            status='conflict',
            code='email_already_exists',
            matched_user_id=matched_user.id,
        )

    @classmethod
    async def aresolve_email_claim(
        cls,
        email: str,
        requester_user: Optional[User] = None,
    ) -> EmailIdentityResolution:
        """Async wrapper для использования в transport-слое (Telegram/MAX)."""
        return await sync_to_async(cls.resolve_email_claim)(email, requester_user)
