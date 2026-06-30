"""Preflight checks for MAX runtime configuration."""

from __future__ import annotations

from typing import Any


ALLOWED_MODES = {'polling', 'webhook'}


def normalize_transport_mode(mode: str | None) -> str:
    """Normalize MAX transport mode with safe fallback to polling."""
    value = (mode or 'polling').strip().lower()
    if value not in ALLOWED_MODES:
        return 'polling'
    return value


def collect_preflight_errors(app_settings: Any, mode: str | None = None) -> list[str]:
    """Return list of MAX runtime config errors, empty list means config is valid."""
    selected_mode = normalize_transport_mode(mode or getattr(app_settings, 'MAX_TRANSPORT_MODE', 'polling'))
    errors: list[str] = []

    if not (getattr(app_settings, 'MAX_BOT_TOKEN', '') or '').strip():
        errors.append('MAX_BOT_TOKEN is empty')
    if not (getattr(app_settings, 'MAX_API_BASE_URL', '') or '').strip():
        errors.append('MAX_API_BASE_URL is empty')

    api_timeout = int(getattr(app_settings, 'MAX_API_TIMEOUT_SECONDS', 10))
    if api_timeout <= 0:
        errors.append('MAX_API_TIMEOUT_SECONDS must be > 0')

    rate_limit_rps = float(getattr(app_settings, 'MAX_RATE_LIMIT_RPS', 10))
    rate_limit_burst = int(getattr(app_settings, 'MAX_RATE_LIMIT_BURST', 50))
    if rate_limit_rps <= 0:
        errors.append('MAX_RATE_LIMIT_RPS must be > 0')
    if rate_limit_burst <= 0:
        errors.append('MAX_RATE_LIMIT_BURST must be > 0')

    max_message_length = int(getattr(app_settings, 'MAX_MESSAGE_MAX_LENGTH', 3500))
    if max_message_length < 100:
        errors.append('MAX_MESSAGE_MAX_LENGTH must be >= 100')

    state_ttl = int(getattr(app_settings, 'MAX_STATE_TTL_SECONDS', 3600))
    if state_ttl <= 0:
        errors.append('MAX_STATE_TTL_SECONDS must be > 0')

    if selected_mode == 'webhook':
        if not (getattr(app_settings, 'MAX_WEBHOOK_URL', '') or '').strip():
            errors.append('MAX_WEBHOOK_URL is empty for webhook mode')
    else:
        polling_timeout = int(getattr(app_settings, 'MAX_POLLING_TIMEOUT_SECONDS', 30))
        polling_idle_sleep = float(getattr(app_settings, 'MAX_POLLING_IDLE_SLEEP_SECONDS', 1.5))
        if polling_timeout <= 0:
            errors.append('MAX_POLLING_TIMEOUT_SECONDS must be > 0')
        if polling_idle_sleep < 0:
            errors.append('MAX_POLLING_IDLE_SLEEP_SECONDS must be >= 0')

    return errors
