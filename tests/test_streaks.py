"""
Тесты для подсчёта серий (streaks).
"""
import pytest
from datetime import date, datetime, timedelta
from model_bakery import baker
from asgiref.sync import sync_to_async
import pytz
from django.db import transaction

from bot.utils.diary_utils import get_user_streaks
from diary.models import DiaryEntry
from users.models import User

# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


@pytest.mark.django_db(transaction=True)
class TestGetUserStreaks:
    """Тесты для функции get_user_streaks."""

    @pytest.fixture
    def user_moscow(self, db):
        return baker.make(User, username='testuser_msk', telegram_id=200001, timezone='Europe/Moscow')

    @pytest.fixture
    def user_utc(self, db):
        return baker.make(User, username='testuser_utc', telegram_id=200002, timezone='UTC')

    def _create_entry_for_date_sync(self, user, entry_date, hours=12):
        """Создаёт запись за указанную дату (синхронно)."""
        user_tz = pytz.timezone(user.timezone or 'UTC')
        naive_dt = datetime.combine(entry_date, datetime.min.time()) + timedelta(hours=hours)
        local_dt = user_tz.localize(naive_dt)
        utc_dt = local_dt.astimezone(pytz.utc)
        with transaction.atomic():
            entry = DiaryEntry.objects.create(
                user=user,
                text=f"Запись за {entry_date}",
                language='ru',
                word_count=5,
                creator_timezone=user.timezone or 'UTC'
            )
            DiaryEntry.objects.filter(pk=entry.pk).update(created_at=utc_dt)
            entry.refresh_from_db()
            return entry

    @pytest.mark.asyncio
    async def test_no_entries(self, user_moscow):
        """Тест: нет записей — серия 0, max 0, has_entry_today False."""
        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 0
        assert maximum == 0
        assert has_today is False

    @pytest.mark.asyncio
    async def test_entry_today_only(self, user_moscow):
        """Тест: запись только сегодня — серия 1, max 1, has_entry_today True."""
        today = datetime.now(pytz.timezone(user_moscow.timezone)).date()
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today)

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 1
        assert maximum == 1
        assert has_today is True

    @pytest.mark.asyncio
    async def test_entry_yesterday_only(self, user_moscow):
        """Тест: запись только вчера — серия 1, max 1, has_entry_today False."""
        today = datetime.now(pytz.timezone(user_moscow.timezone)).date()
        yesterday = today - timedelta(days=1)
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, yesterday)

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 1  # Серия 1 день (вчера)
        assert maximum == 1
        assert has_today is False

    @pytest.mark.asyncio
    async def test_consecutive_3_days_including_today(self, user_moscow):
        """Тест: 3 дня подряд включая сегодня."""
        tz = pytz.timezone(user_moscow.timezone)
        today = datetime.now(tz).date()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)

        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, day_before)
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, yesterday)
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today)

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 3
        assert maximum == 3
        assert has_today is True

    @pytest.mark.asyncio
    async def test_consecutive_5_days_not_including_today(self, user_moscow):
        """Тест: 5 дней подряд, но НЕ включая сегодня — серия 5, has_entry_today False."""
        tz = pytz.timezone(user_moscow.timezone)
        today = datetime.now(tz).date()
        # 5 дней начиная со вчера
        for i in range(1, 6):
            await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today - timedelta(days=i))

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 5
        assert maximum == 5
        assert has_today is False

    @pytest.mark.asyncio
    async def test_broken_streak(self, user_moscow):
        """Тест: серия с пропуском — максимальная считается, текущая — нет."""
        tz = pytz.timezone(user_moscow.timezone)
        today = datetime.now(tz).date()
        # 3 дня подряд давно (максимальная серия)
        for i in range(10, 13):
            await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today - timedelta(days=i))

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 0
        assert maximum == 3
        assert has_today is False

    @pytest.mark.asyncio
    async def test_broken_streak_with_yesterday_entry(self, user_moscow):
        """Тест: есть запись вчера, но не сегодня — серия = 1, has_entry_today False."""
        tz = pytz.timezone(user_moscow.timezone)
        today = datetime.now(tz).date()
        yesterday = today - timedelta(days=1)
        # Запись вчера
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, yesterday)
        # Запись 5 дней назад (разрыв)
        await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today - timedelta(days=5))

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 1  # Серия = 1 (вчера)
        assert maximum == 1
        assert has_today is False

    @pytest.mark.asyncio
    async def test_longest_streak_earlier(self, user_moscow):
        """Тест: максимальная серия была раньше, текущая меньше."""
        tz = pytz.timezone(user_moscow.timezone)
        today = datetime.now(tz).date()
        # Серия 7 дней давно
        for i in range(20, 27):
            await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today - timedelta(days=i))
        # Текущая серия 3 дня (включая сегодня)
        for i in range(0, 3):
            await sync_to_async(self._create_entry_for_date_sync)(user_moscow, today - timedelta(days=i))

        current, maximum, has_today = await get_user_streaks(user_moscow)
        assert current == 3
        assert maximum == 7
        assert has_today is True
