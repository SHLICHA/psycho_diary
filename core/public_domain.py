"""Публичный домен и авто-режим webhook/polling для MAX и оплаты."""

from __future__ import annotations

MAX_WEBHOOK_PATH = '/api/max/webhook/'
PAYMENT_WEBHOOK_PATH = '/api/payments/webhook/'


def normalize_public_domain(value: str | None) -> str:
    """Нормализует публичный origin: без пробелов и завершающего ``/``."""
    normalized = (value or '').strip()
    if not normalized:
        return ''
    return normalized.rstrip('/')


def join_public_url(domain: str, path: str) -> str:
    """Склеивает origin и path в абсолютный URL."""
    origin = normalize_public_domain(domain)
    if not origin:
        return ''
    suffix = path if path.startswith('/') else f'/{path}'
    return f'{origin}{suffix}'


def _ensure_trailing_slash(url: str) -> str:
    value = (url or '').strip()
    if not value:
        return ''
    return value if value.endswith('/') else f'{value}/'


def resolve_max_transport_mode(
    *,
    explicit_mode: str | None,
    public_domain: str | None,
    explicit_webhook_url: str | None = None,
) -> str:
    """
    Режим MAX:
    - явный ``polling`` / ``webhook`` в env — приоритет;
    - иначе при наличии публичного адреса — ``webhook``;
    - иначе — ``polling``.
    """
    mode = (explicit_mode or '').strip().lower()
    if mode in {'polling', 'webhook'}:
        return mode
    if normalize_public_domain(public_domain) or (explicit_webhook_url or '').strip():
        return 'webhook'
    return 'polling'


def resolve_max_webhook_url(
    *,
    public_domain: str | None,
    explicit_webhook_url: str | None = None,
) -> str:
    """Явный MAX_WEBHOOK_URL или ``{BOT_PUBLIC_DOMAIN}/api/max/webhook/``."""
    explicit = (explicit_webhook_url or '').strip()
    if explicit:
        return _ensure_trailing_slash(explicit)
    return join_public_url(public_domain or '', MAX_WEBHOOK_PATH)


def resolve_payment_webhook_url(
    *,
    public_domain: str | None,
    explicit_webhook_url: str | None = None,
) -> str:
    """Явный PAYMENT_WEBHOOK_URL или ``{BOT_PUBLIC_DOMAIN}/api/payments/webhook/``."""
    explicit = (explicit_webhook_url or '').strip()
    if explicit:
        return _ensure_trailing_slash(explicit)
    return join_public_url(public_domain or '', PAYMENT_WEBHOOK_PATH)
