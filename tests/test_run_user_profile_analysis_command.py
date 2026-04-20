import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from model_bakery import baker

from users.models import User


pytestmark = pytest.mark.django_db


def test_run_user_profile_analysis_user_not_found_raises():
    with pytest.raises(CommandError, match='does not exist'):
        call_command('run_user_profile_analysis', 999999)


def test_run_user_profile_analysis_raises_on_async_error(mocker):
    user = baker.make(User, telegram_id=223344, username='profile_cmd_user')

    mocker.patch(
        'core.management.commands.run_user_profile_analysis.Command.async_handle',
        side_effect=RuntimeError('boom'),
    )

    with pytest.raises(CommandError, match='Error during profile analysis: boom'):
        call_command('run_user_profile_analysis', user.telegram_id)


def test_run_user_profile_analysis_raises_when_result_failed(mocker):
    user = baker.make(User, telegram_id=223345, username='profile_cmd_user_2')

    mocker.patch(
        'core.management.commands.run_user_profile_analysis.Command.async_handle',
        return_value={
            'success': False,
            'message': 'Profile analysis failed: upstream unavailable',
            'before': {'personality_description_chars': 10, 'compressed_profile_chars': 20, 'personal_items_total': 3, 'personal_items_per_field': {}},
            'after': {'personality_description_chars': 9, 'compressed_profile_chars': 19, 'personal_items_total': 2, 'personal_items_per_field': {}},
        },
    )

    with pytest.raises(CommandError, match='Profile analysis failed: upstream unavailable'):
        call_command('run_user_profile_analysis', user.telegram_id)


def test_run_user_profile_analysis_success_prints_details(mocker):
    user = baker.make(User, telegram_id=223346, username='profile_cmd_user_3')
    out = io.StringIO()

    mocker.patch(
        'core.management.commands.run_user_profile_analysis.Command.async_handle',
        return_value={
            'success': True,
            'message': 'Profile analysis completed successfully: ok',
            'before': {
                'personality_description_chars': 100,
                'compressed_profile_chars': 250,
                'personal_items_total': 8,
                'personal_items_per_field': {'life_facts': 2, 'hobbies': 1},
            },
            'after': {
                'personality_description_chars': 120,
                'compressed_profile_chars': 210,
                'personal_items_total': 6,
                'personal_items_per_field': {'life_facts': 1, 'hobbies': 1},
            },
        },
    )

    call_command('run_user_profile_analysis', user.telegram_id, stdout=out)
    output = out.getvalue()

    assert '[BEFORE]' in output
    assert '[AFTER]' in output
    assert '[DELTA]' in output
    assert 'description_chars_delta=' in output
    assert 'Profile analysis completed successfully' in output
