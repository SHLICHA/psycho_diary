"""Unit tests for BOT_PUBLIC_DOMAIN → webhook/polling resolution."""

from core.public_domain import (
    MAX_WEBHOOK_PATH,
    PAYMENT_WEBHOOK_PATH,
    join_public_url,
    normalize_public_domain,
    resolve_max_transport_mode,
    resolve_max_webhook_url,
    resolve_payment_webhook_url,
)


def test_normalize_public_domain_strips_slash():
    assert normalize_public_domain(' https://www.psychodiary.ru/ ') == 'https://www.psychodiary.ru'
    assert normalize_public_domain('') == ''
    assert normalize_public_domain(None) == ''


def test_join_public_url():
    assert (
        join_public_url('https://www.psychodiary.ru', MAX_WEBHOOK_PATH)
        == 'https://www.psychodiary.ru/api/max/webhook/'
    )
    assert join_public_url('', MAX_WEBHOOK_PATH) == ''


def test_resolve_mode_auto_polling_without_domain():
    assert (
        resolve_max_transport_mode(
            explicit_mode='',
            public_domain='',
            explicit_webhook_url='',
        )
        == 'polling'
    )


def test_resolve_mode_auto_webhook_with_domain():
    assert (
        resolve_max_transport_mode(
            explicit_mode='',
            public_domain='https://www.psychodiary.ru',
            explicit_webhook_url='',
        )
        == 'webhook'
    )


def test_resolve_mode_auto_webhook_with_explicit_url_only():
    assert (
        resolve_max_transport_mode(
            explicit_mode='',
            public_domain='',
            explicit_webhook_url='https://www.psychodiary.ru/api/max/webhook/',
        )
        == 'webhook'
    )


def test_resolve_mode_explicit_override_polling():
    assert (
        resolve_max_transport_mode(
            explicit_mode='polling',
            public_domain='https://www.psychodiary.ru',
        )
        == 'polling'
    )


def test_resolve_mode_explicit_override_webhook():
    assert (
        resolve_max_transport_mode(
            explicit_mode='webhook',
            public_domain='',
            explicit_webhook_url='https://example.com/api/max/webhook/',
        )
        == 'webhook'
    )


def test_resolve_max_webhook_url_from_domain():
    assert (
        resolve_max_webhook_url(public_domain='https://www.psychodiary.ru')
        == 'https://www.psychodiary.ru/api/max/webhook/'
    )


def test_resolve_max_webhook_url_explicit_wins():
    assert (
        resolve_max_webhook_url(
            public_domain='https://www.psychodiary.ru',
            explicit_webhook_url='https://custom.example/hook',
        )
        == 'https://custom.example/hook/'
    )


def test_resolve_payment_webhook_url_from_domain():
    assert (
        resolve_payment_webhook_url(public_domain='https://www.psychodiary.ru')
        == f'https://www.psychodiary.ru{PAYMENT_WEBHOOK_PATH}'
    )


def test_resolve_payment_webhook_url_empty_without_domain():
    assert resolve_payment_webhook_url(public_domain='') == ''
