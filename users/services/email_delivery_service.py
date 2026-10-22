"""Тонкая доставка транзакционных писем через Django email backend."""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class EmailDeliveryService:
    """Отправка писем; без EMAIL_HOST использует console backend (dev)."""

    @classmethod
    def send(
        cls,
        *,
        subject: str,
        body: str,
        to_email: str,
        html_body: Optional[str] = None,
    ) -> bool:
        if not to_email or not to_email.strip():
            logger.warning('EmailDeliveryService: empty recipient')
            return False
        fail_silently = getattr(settings, 'EMAIL_FAIL_SILENTLY', True)
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost')
        try:
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[to_email.strip()],
                fail_silently=fail_silently,
                html_message=html_body,
            )
            ok = bool(sent)
            if ok:
                logger.info('Email sent to %s subject=%r', to_email[:3] + '***', subject)
            else:
                logger.warning('Email not sent to %s subject=%r', to_email[:3] + '***', subject)
            return ok
        except Exception:
            logger.exception('EmailDeliveryService failed for %s', to_email[:3] + '***')
            if not fail_silently:
                raise
            return False

    @classmethod
    def send_password_reset(cls, *, to_email: str, reset_url: str, language: str = 'ru') -> bool:
        if language == 'en':
            subject = 'Psycho Diary — password reset'
            body = (
                'You requested a password reset.\n\n'
                f'Open this link (valid for a short time):\n{reset_url}\n\n'
                'If you did not request this, ignore the email.'
            )
        else:
            subject = 'Psycho Diary — сброс пароля'
            body = (
                'Вы запросили сброс пароля.\n\n'
                f'Откройте ссылку (действует короткое время):\n{reset_url}\n\n'
                'Если это были не вы — просто проигнорируйте письмо.'
            )
        return cls.send(subject=subject, body=body, to_email=to_email)

    @classmethod
    def send_merge_otp(cls, *, to_email: str, otp_code: str, language: str = 'ru') -> bool:
        if language == 'en':
            subject = 'Psycho Diary — confirm account merge'
            body = (
                'Someone asked to merge another account with yours using this email.\n\n'
                f'Confirmation code: {otp_code}\n\n'
                'If this was not you, ignore the email.'
            )
        else:
            subject = 'Psycho Diary — подтверждение объединения аккаунтов'
            body = (
                'Кто-то запросил объединение другого аккаунта с вашим по этому email.\n\n'
                f'Код подтверждения: {otp_code}\n\n'
                'Если это были не вы — проигнорируйте письмо.'
            )
        return cls.send(subject=subject, body=body, to_email=to_email)
