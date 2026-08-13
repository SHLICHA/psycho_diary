"""Unit-тесты Wave 3.17: admin stats + profile view builders."""
from types import SimpleNamespace

import pytest

from core.services.admin_service import AdminService
from diary.services.user_profile_service import UserProfileService


def _sample_stats(**overrides):
    base = {
        'total_users': 10,
        'active_users': 8,
        'active_users_last_7_days': 5,
        'blocked_users': 2,
        'premium_users': 3,
        'users_with_tokens': 4,
        'users_with_auto_analysis_enabled': 6,
        'users_completed_onboarding': 7,
        'users_with_entries': 6,
        'users_telegram_only': 4,
        'users_max_only': 2,
        'users_both_messengers': 1,
        'users_no_messenger': 1,
        'subscriptions_30_count': 1,
        'subscriptions_year_count': 1,
        'tokens_10_count': 1,
        'tokens_50_count': 0,
        'tokens_100_count': 0,
        'tokens_200_count': 0,
        'tokens_500_count': 0,
        'custom_tokens_count': 0,
        'total_entries': 20,
        'real_entries': 18,
        'recovered_entries': 2,
        'total_ratings': 4,
        'rating_distribution': {1: 0, 2: 1, 3: 1, 4: 1, 5: 1},
        'top_timezones': [('Europe/Moscow', 5)],
    }
    base.update(overrides)
    return base


def test_build_admin_stats_report_contains_sections():
    service = AdminService()
    report = service.build_admin_stats_report(_sample_stats())
    assert 'Статистика приложения' in report
    assert 'Europe/Moscow' in report
    assert '⭐⭐⭐⭐⭐' in report
    assert 'Только Telegram: 4' in report
    assert 'Только MAX: 2' in report
    assert 'Оба мессенджера (TG+MAX): 1' in report
    assert 'Без мессенджера (web): 1' in report


@pytest.mark.asyncio
async def test_get_admin_stats_bundle_forbidden(mocker):
    service = AdminService()
    mocker.patch.object(service, 'is_admin', return_value=False)
    bundle = await service.get_admin_stats_bundle(123)
    assert bundle['mode'] == 'forbidden'
    assert bundle['success'] is False


@pytest.mark.asyncio
async def test_get_admin_stats_bundle_ok(mocker):
    service = AdminService()
    mocker.patch.object(service, 'is_admin', return_value=True)
    mocker.patch.object(
        service, 'get_admin_stats', new=mocker.AsyncMock(return_value=_sample_stats())
    )
    bundle = await service.get_admin_stats_bundle(1)
    assert bundle['success'] is True
    assert bundle['mode'] == 'stats'
    assert len(bundle['charts']) == 2


def test_build_account_deletion_menu_view_positive(mocker):
    mocker.patch(
        'diary.services.user_profile_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_account_deletion_menu_keyboard',
        return_value='kb_del',
    )
    user = mocker.Mock(token_balance=15)
    view = UserProfileService.build_account_deletion_menu_view(user, 'ru')
    assert view['mode'] == 'deletion_menu'
    assert view['balance_warning'] == 'balance_warning_positive'
    assert view['reply_markup'] == 'kb_del'


def test_build_account_deletion_menu_view_zero(mocker):
    mocker.patch(
        'diary.services.user_profile_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_account_deletion_menu_keyboard',
        return_value='kb_del',
    )
    user = mocker.Mock(token_balance=0)
    view = UserProfileService.build_account_deletion_menu_view(user, 'ru')
    assert view['balance_warning'] == 'balance_warning_zero_or_negative'


@pytest.mark.asyncio
async def test_build_profile_screen_view(mocker):
    mocker.patch.object(
        UserProfileService,
        'get_user_profile_data',
        new=mocker.AsyncMock(return_value={
            'user_telegram_id': 1,
            'username': 'u',
            'first_name': 'A',
            'last_name': 'B',
            'notifications_status': 'on',
            'auto_analysis_status': 'on',
            'premium_status': 'off',
            'awareness_level': 2,
            'token_balance': 3,
            'registration_date': '01.01.2026',
            'last_entry': '—',
            'last_analysis_date': None,
            'has_psychological_data': False,
        }),
    )
    mocker.patch(
        'diary.services.user_profile_service.get_message',
        return_value='profile',
    )
    mocker.patch(
        'bot.keyboards.get_profile_keyboard',
        return_value='kb_profile',
    )
    view = await UserProfileService.build_profile_screen_view(mocker.Mock(), 'ru')
    assert view['success'] is True
    assert view['reply_markup'] == 'kb_profile'


@pytest.mark.asyncio
async def test_build_edit_profile_menu_view(mocker):
    mocker.patch.object(
        UserProfileService,
        'get_user_profile_data',
        new=mocker.AsyncMock(return_value={
            'hobbies_for_display': 'hobby',
            'life_facts_for_display': 'fact',
        }),
    )
    mocker.patch(
        'diary.services.user_profile_service.get_message',
        side_effect=lambda key, language=None, **kwargs: key,
    )
    mocker.patch(
        'bot.keyboards.get_edit_profile_keyboard',
        return_value='kb_edit',
    )
    user = SimpleNamespace(first_name='A', email=None, date_of_birth=None)
    view = await UserProfileService.build_edit_profile_menu_view(user, 'ru')
    assert view['mode'] == 'edit_menu'
    assert view['reply_markup'] == 'kb_edit'
