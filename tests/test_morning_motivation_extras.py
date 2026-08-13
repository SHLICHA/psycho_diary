"""Тесты сборки предупреждений/кнопок утренней мотивации."""

from datetime import date, datetime, timedelta, timezone as dt_timezone

import pytz

from diary.tasks.morning_motivations import build_morning_motivation_extras


TZ = pytz.timezone('Europe/Moscow')
LOCAL_DATE = date(2026, 8, 12)


def _expires_at_days(days: int) -> datetime:
    """UTC datetime, соответствующий локальной дате LOCAL_DATE + days в 15:00 MSK."""
    local_dt = TZ.localize(datetime.combine(LOCAL_DATE + timedelta(days=days), datetime.min.time().replace(hour=15)))
    return local_dt.astimezone(dt_timezone.utc)


def test_no_premium_no_tokens_adds_recharge():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=False,
        premium_expires_at=None,
        token_balance=0,
        auto_analysis_enabled=True,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert 'автоматический анализ' in extras['additional_text'].lower() or 'Хочешь' in extras['additional_text']
    assert extras['additional_button_callback'] == 'premium_subscribe'
    assert extras['additional_button_text_key'] == 'btn_morning_motivation_recharge'
    assert extras['renewal_button_callback'] is None
    assert extras['expiry_text'] == ''


def test_expired_subscription_shows_renew_even_with_tokens():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=False,
        premium_expires_at=_expires_at_days(-1),
        token_balance=10,
        auto_analysis_enabled=False,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert 'закончилась' in extras['expiry_text'].lower() or 'истекла' in extras['expiry_text'].lower()
    assert 'психологического профиля' in extras['expiry_text'].lower() or 'анализ дня' in extras['expiry_text'].lower()
    assert extras['renewal_button_callback'] == 'settings_premium'
    assert extras['renewal_button_text_key'] == 'btn_morning_motivation_renew_subscription'
    assert extras['additional_text'] == ''
    assert extras['additional_button_callback'] is None


def test_expired_subscription_preferred_over_recharge_when_no_tokens():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=False,
        premium_expires_at=_expires_at_days(-3),
        token_balance=0,
        auto_analysis_enabled=True,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert extras['expiry_text']
    assert extras['renewal_button_callback'] == 'settings_premium'
    assert extras['additional_text'] == ''
    assert extras['additional_button_callback'] is None


def test_premium_expires_in_2_days():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=True,
        premium_expires_at=_expires_at_days(2),
        token_balance=0,
        auto_analysis_enabled=True,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert '2' in extras['expiry_text']
    assert 'анализ' in extras['expiry_text'].lower() or 'профиль' in extras['expiry_text'].lower()
    assert extras['renewal_button_callback'] == 'settings_premium'
    assert extras['renewal_button_text_key'] == 'btn_manage_subscription'
    assert extras['additional_button_callback'] is None


def test_premium_expires_in_7_days():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=True,
        premium_expires_at=_expires_at_days(7),
        token_balance=5,
        auto_analysis_enabled=True,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert '7' in extras['expiry_text']
    assert extras['renewal_button_callback'] == 'settings_premium'


def test_premium_far_from_expiry_no_warning():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=True,
        premium_expires_at=_expires_at_days(30),
        token_balance=0,
        auto_analysis_enabled=True,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert extras['expiry_text'] == ''
    assert extras['additional_text'] == ''
    assert extras['renewal_button_callback'] is None
    assert extras['additional_button_callback'] is None


def test_no_premium_with_tokens_suggests_auto_analysis():
    extras = build_morning_motivation_extras(
        language='ru',
        is_premium_active=False,
        premium_expires_at=None,
        token_balance=3,
        auto_analysis_enabled=False,
        user_local_date=LOCAL_DATE,
        user_tz=TZ,
    )
    assert extras['additional_button_callback'] == 'settings_toggle_auto_analysis'
    assert extras['expiry_text'] == ''
