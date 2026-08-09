from types import SimpleNamespace

from bot.transports.max.preflight import collect_preflight_errors, normalize_transport_mode


def _build_settings(**overrides):
    defaults = {
        'MAX_TRANSPORT_MODE': 'polling',
        'MAX_BOT_TOKEN': 'token',
        'MAX_API_BASE_URL': 'https://platform-api2.max.ru',
        'MAX_API_TIMEOUT_SECONDS': 10,
        'MAX_WEBHOOK_URL': '',
        'MAX_POLLING_TIMEOUT_SECONDS': 30,
        'MAX_POLLING_IDLE_SLEEP_SECONDS': 1.5,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_normalize_transport_mode_fallback_to_polling():
    assert normalize_transport_mode('invalid') == 'polling'
    assert normalize_transport_mode(None) == 'polling'


def test_collect_preflight_errors_valid_polling_config():
    settings_obj = _build_settings(MAX_TRANSPORT_MODE='polling', MAX_API_CA_CERT_PATHS=[])
    assert collect_preflight_errors(settings_obj) == []


def test_collect_preflight_errors_webhook_requires_url():
    settings_obj = _build_settings(MAX_TRANSPORT_MODE='webhook', MAX_WEBHOOK_URL='')
    errors = collect_preflight_errors(settings_obj)
    assert 'MAX_WEBHOOK_URL is empty for webhook mode' in errors


def test_collect_preflight_errors_missing_token():
    settings_obj = _build_settings(MAX_BOT_TOKEN='')
    errors = collect_preflight_errors(settings_obj)
    assert 'MAX_BOT_TOKEN is empty' in errors
