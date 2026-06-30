import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_check_max_bot_config_valid(settings):
    settings.MAX_TRANSPORT_MODE = 'polling'
    settings.MAX_BOT_TOKEN = 'token'
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 10
    settings.MAX_POLLING_TIMEOUT_SECONDS = 30
    settings.MAX_POLLING_IDLE_SLEEP_SECONDS = 1.5

    call_command('check_max_bot_config')


@pytest.mark.django_db
def test_check_max_bot_config_invalid(settings):
    settings.MAX_TRANSPORT_MODE = 'polling'
    settings.MAX_BOT_TOKEN = ''
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 10
    settings.MAX_POLLING_TIMEOUT_SECONDS = 30
    settings.MAX_POLLING_IDLE_SLEEP_SECONDS = 1.5

    with pytest.raises(CommandError, match='MAX bot configuration is invalid'):
        call_command('check_max_bot_config')


@pytest.mark.django_db
def test_runmaxbot_requires_enabled_flag(settings):
    settings.MAX_TRANSPORT_ENABLED = False

    with pytest.raises(CommandError, match='MAX_TRANSPORT_ENABLED=false'):
        call_command('runmaxbot')
