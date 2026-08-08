import pytest
from datetime import date, timedelta

from diary.services.user_profile_service import UserProfileService


def test_validate_profile_field_input_email_success():
    result = UserProfileService.validate_profile_field_input('email', 'user@example.com')
    assert result['success'] is True
    assert result['processed_value'] == 'user@example.com'


def test_validate_profile_field_input_email_invalid():
    result = UserProfileService.validate_profile_field_input('email', 'bad-email')
    assert result['success'] is False
    assert result['error_key'] == 'invalid_email_format'


def test_validate_profile_field_input_dob_success():
    result = UserProfileService.validate_profile_field_input('date_of_birth', '01.02.2000')
    assert result['success'] is True
    assert result['processed_value'] == date(2000, 2, 1)


def test_validate_profile_field_input_dob_future():
    future = (date.today() + timedelta(days=2)).strftime('%d.%m.%Y')
    result = UserProfileService.validate_profile_field_input('date_of_birth', future)
    assert result['success'] is False
    assert result['error_key'] == 'invalid_date_future'


def test_validate_profile_field_input_dob_bad_format():
    result = UserProfileService.validate_profile_field_input('date_of_birth', '2000-02-01')
    assert result['success'] is False
    assert result['error_key'] == 'invalid_date_format'


def test_validate_profile_field_input_empty():
    result = UserProfileService.validate_profile_field_input('first_name', '   ')
    assert result['success'] is False
    assert result['error_key'] == 'invalid_input'


@pytest.mark.asyncio
async def test_process_profile_field_update_validation_failure(mocker):
    user = mocker.Mock(telegram_id=1)
    update_mock = mocker.AsyncMock()
    mocker.patch.object(UserProfileService, 'update_user_profile_field', new=update_mock)

    result = await UserProfileService.process_profile_field_update(user, 'email', 'bad')

    assert result['success'] is False
    assert result['error_code'] == 'invalid_email_format'
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_profile_field_update_success(mocker):
    user = mocker.Mock(telegram_id=2)
    update_mock = mocker.AsyncMock(return_value={'success': True})
    mocker.patch.object(UserProfileService, 'update_user_profile_field', new=update_mock)

    result = await UserProfileService.process_profile_field_update(user, 'first_name', 'Alex')

    assert result['success'] is True
    update_mock.assert_awaited_once_with(user, 'first_name', 'Alex')


@pytest.mark.asyncio
async def test_prepare_list_field_for_edit_cleans_and_saves(mocker):
    user = mocker.Mock(telegram_id=3, language='ru')
    user.hobbies = ['reading', {'remove': 'old'}, 'music']
    user.asave = mocker.AsyncMock()

    result = await UserProfileService.prepare_list_field_for_edit(
        user=user,
        field_name='hobbies',
        language='ru',
        max_length=3000,
    )

    assert result['success'] is True
    assert result['was_cleaned'] is True
    assert result['cleaned_list'] == ['reading', 'music']
    assert user.hobbies == ['reading', 'music']
    user.asave.assert_awaited_once()
    assert isinstance(result['display_text'], str)


@pytest.mark.asyncio
async def test_prepare_list_field_for_edit_no_cleanup_needed(mocker):
    user = mocker.Mock(telegram_id=4, language='ru')
    user.life_facts = ['fact1']
    user.asave = mocker.AsyncMock()

    result = await UserProfileService.prepare_list_field_for_edit(
        user=user,
        field_name='life_facts',
        language='ru',
    )

    assert result['success'] is True
    assert result['was_cleaned'] is False
    user.asave.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_list_field_for_edit_invalid_field(mocker):
    user = mocker.Mock(telegram_id=5)
    result = await UserProfileService.prepare_list_field_for_edit(user, 'email', 'ru')
    assert result['success'] is False
    assert result['error'] == 'invalid_field'
