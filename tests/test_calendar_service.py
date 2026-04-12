"""
Тесты для calendar_service.py
"""
import pytest
from datetime import date, datetime

import pytz
from django.test import override_settings
from django.utils import timezone

from core.services.calendar_service import calendar_service, CalendarService
from users.models import User


# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
from model_bakery import baker
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


class TestCalendarServiceCalculatePrevMonth:
    """Тесты для calculate_prev_month."""

    def test_prev_month_same_year(self):
        assert calendar_service.calculate_prev_month(2026, 6) == (2026, 5)

    def test_prev_month_january_rollover(self):
        assert calendar_service.calculate_prev_month(2026, 1) == (2025, 12)

    def test_prev_month_december(self):
        assert calendar_service.calculate_prev_month(2026, 12) == (2026, 11)

    def test_prev_month_february(self):
        assert calendar_service.calculate_prev_month(2026, 2) == (2026, 1)


class TestCalendarServiceCalculateNextMonth:
    """Тесты для calculate_next_month."""

    def test_next_month_same_year(self):
        assert calendar_service.calculate_next_month(2026, 6) == (2026, 7)

    def test_next_month_december_rollover(self):
        assert calendar_service.calculate_next_month(2026, 12) == (2027, 1)

    def test_next_month_november(self):
        assert calendar_service.calculate_next_month(2026, 11) == (2026, 12)

    def test_next_month_january(self):
        assert calendar_service.calculate_next_month(2026, 1) == (2026, 2)


class TestCalendarServiceGetTargetDate:
    """Тесты для get_target_date_from_callback."""

    def test_default_day(self):
        result = calendar_service.get_target_date_from_callback(2026, 4)
        assert result == date(2026, 4, 1)

    def test_specific_day(self):
        result = calendar_service.get_target_date_from_callback(2026, 4, 15)
        assert result == date(2026, 4, 15)


class TestCalendarServiceIsSameMonth:
    """Тесты для is_same_month."""

    def test_same_month_true(self):
        assert calendar_service.is_same_month(date(2026, 4, 15), 2026, 4) is True

    def test_same_month_false_month(self):
        assert calendar_service.is_same_month(date(2026, 5, 15), 2026, 4) is False

    def test_same_month_false_year(self):
        assert calendar_service.is_same_month(date(2025, 4, 15), 2026, 4) is False


class TestCalendarServiceIsSameYear:
    """Тесты для is_same_year."""

    def test_same_year_true(self):
        assert calendar_service.is_same_year(date(2026, 4, 15), 2026) is True

    def test_same_year_false(self):
        assert calendar_service.is_same_year(date(2025, 4, 15), 2026) is False


@pytest.mark.django_db(transaction=True)
class TestCalendarServiceGetUserLocalDate:
    """Тесты для get_user_local_date."""

    def test_utc_user(self):
        user = baker.make(User, telegram_id=80001, timezone='UTC')
        local_date = calendar_service.get_user_local_date(user)
        assert isinstance(local_date, date)
        # UTC — совпадает с today в UTC
        utc_today = timezone.now().date()
        assert local_date == utc_today

    def test_user_with_timezone(self):
        user = baker.make(User, telegram_id=80002, timezone='Europe/Moscow')
        local_date = calendar_service.get_user_local_date(user)
        assert isinstance(local_date, date)


@pytest.mark.django_db(transaction=True)
class TestCalendarServiceGetUserLocalDateTime:
    """Тесты для get_user_local_datetime."""

    def test_utc_user(self):
        user = baker.make(User, telegram_id=80010, timezone='UTC')
        local_dt = calendar_service.get_user_local_datetime(user)
        assert isinstance(local_dt, datetime)

    def test_user_with_timezone(self):
        user = baker.make(User, telegram_id=80011, timezone='Asia/Yekaterinburg')
        local_dt = calendar_service.get_user_local_datetime(user)
        assert isinstance(local_dt, datetime)


@pytest.mark.django_db(transaction=True)
class TestCalendarServiceUpdateUserCalendarPosition:
    """Тесты для update_user_calendar_position."""

    @pytest.fixture
    def test_user(self):
        return baker.make(
            User, telegram_id=90001,
            current_calendar_year=2026,
            current_calendar_month=4
        )

    @pytest.mark.asyncio
    async def test_update_calendar_position(self, test_user):
        updated = await calendar_service.update_user_calendar_position(test_user, 2026, 5)
        assert updated.current_calendar_year == 2026
        assert updated.current_calendar_month == 5
        # Перезагрузим из БД для проверки сохранения
        refreshed = await User.objects.aget(id=test_user.id)
        assert refreshed.current_calendar_year == 2026
        assert refreshed.current_calendar_month == 5

    @pytest.mark.asyncio
    async def test_update_calendar_position_year_rollover(self, test_user):
        updated = await calendar_service.update_user_calendar_position(test_user, 2027, 1)
        assert updated.current_calendar_year == 2027
        assert updated.current_calendar_month == 1
        refreshed = await User.objects.aget(id=test_user.id)
        assert refreshed.current_calendar_year == 2027
        assert refreshed.current_calendar_month == 1
