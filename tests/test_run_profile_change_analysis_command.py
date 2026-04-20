import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from model_bakery import baker

from users.models import User


@pytest.mark.django_db
def test_run_profile_change_analysis_rejects_non_positive_snapshots():
    with pytest.raises(CommandError, match='--num-snapshots must be >= 1'):
        call_command('run_profile_change_analysis', 123456, '--num-snapshots', 0)


@pytest.mark.django_db
def test_run_profile_change_analysis_user_not_found_raises():
    with pytest.raises(CommandError, match='does not exist'):
        call_command('run_profile_change_analysis', 999999, '--num-snapshots', 3)


@pytest.mark.django_db
def test_run_profile_change_analysis_raises_on_async_error(mocker):
    user = baker.make(User, telegram_id=12345, username='cmd_user')

    mocker.patch(
        'core.management.commands.run_profile_change_analysis.Command.async_handle',
        side_effect=RuntimeError('boom'),
    )

    with pytest.raises(CommandError, match='Error during analysis: boom'):
        call_command('run_profile_change_analysis', user.telegram_id, '--num-snapshots', 3)


@pytest.mark.django_db
def test_run_profile_change_analysis_raises_when_result_failed(mocker):
    user = baker.make(User, telegram_id=12346, username='cmd_user_2')

    mocker.patch(
        'core.management.commands.run_profile_change_analysis.Command.async_handle',
        return_value={'success': False, 'message': 'Profile Change Analysis failed'},
    )

    with pytest.raises(CommandError, match='Profile Change Analysis failed'):
        call_command('run_profile_change_analysis', user.telegram_id, '--num-snapshots', 3)


@pytest.mark.django_db
def test_run_profile_change_analysis_success(mocker):
    user = baker.make(User, telegram_id=12347, username='cmd_user_3')

    mocker.patch(
        'core.management.commands.run_profile_change_analysis.Command.async_handle',
        return_value={'success': True, 'message': 'ok'},
    )

    call_command('run_profile_change_analysis', user.telegram_id, '--num-snapshots', 3)
