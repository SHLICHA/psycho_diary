import pytest
from datetime import date, time, datetime

import pytz
from django.db import close_old_connections, connections
from model_bakery import baker

from users.models import User
from diary.models import DiaryEntry, CombinedDiaryEntry, DailyAnalysis


@pytest.fixture
def user_without_timezone(db):
    """Фикстура для пользователя без установленного часового пояса."""
    return baker.make(User, timezone='', preferred_analysis_time=time(2, 0))


@pytest.fixture
def user_moscow_tz(db):
    return baker.make(User, username='testuser_msk', timezone='Europe/Moscow', preferred_analysis_time=time(1, 0))


@pytest.fixture
def user_utc_tz(db):
    """Фикстура для пользователя в UTC."""
    return baker.make(User, timezone='UTC', preferred_analysis_time=time(2, 0))


@pytest.fixture
def user_la_tz(db):
    """Фикстура для пользователя в Лос-Анджелесе."""
    return baker.make(User, timezone='America/Los_Angeles', preferred_analysis_time=time(22, 0))


@pytest.fixture
def diary_entry_yesterday_msk(user_moscow_tz):
    # Создаём запись "вчера" в 23:00 MSK -> 20:00 UTC
    entry_datetime_msk = datetime(2023, 10, 26, 23, 0, 0, tzinfo=pytz.timezone('Europe/Moscow'))
    entry_datetime_utc = entry_datetime_msk.astimezone(pytz.utc)
    return baker.make(DiaryEntry, user=user_moscow_tz, text="Запись вчера", created_at=entry_datetime_utc)


@pytest.fixture
def combined_entry_yesterday_msk(user_moscow_tz):
    """Фикстура для CombinedDiaryEntry за вчера в Москве."""
    return baker.make(
        CombinedDiaryEntry,
        user=user_moscow_tz,
        date=date(2023, 10, 26),
        text="Объединенная запись",
        entry_count=1,
        is_analyzed=False,
    )


@pytest.fixture
def frozen_time():
    from freezegun import freeze_time

    # Замораживаем время на 2023-10-27 12:00:00 UTC (это 15:00 MSK)
    with freeze_time("2023-10-27 12:00:00"):
        yield


@pytest.fixture
def combined_entry_yesterday_msk_not_analyzed(user_moscow_tz, diary_entry_yesterday_msk):
    # Создаём CDE, связанный с записью, is_analyzed=False
    return baker.make(
        CombinedDiaryEntry,
        user=user_moscow_tz,
        date=date(2023, 10, 26),
        text=diary_entry_yesterday_msk.text,
        entry_count=1,
        is_analyzed=False,
    )


@pytest.fixture
def combined_entry_yesterday_msk_analyzed(user_moscow_tz, diary_entry_yesterday_msk):
    """Фикстура для проанализированного CombinedDiaryEntry за вчера в Москве."""
    cde = CombinedDiaryEntry.objects.create(
        user=user_moscow_tz,
        date=date(2023, 10, 26),
        text=diary_entry_yesterday_msk.text,
        entry_count=1,
        is_analyzed=True,
    )

    # Создаём связанный DailyAnalysis. Предполагаем, что анализ создан позже записи.
    analysis_created_at = datetime(2023, 10, 26, 22, 0, 0, tzinfo=pytz.utc)
    DailyAnalysis.objects.create(
        combined_entry=cde,
        created_at=analysis_created_at,
        mood_trend='stable',
        key_themes=[],
        emotional_patterns=[],
        insights=[],
        recommendations=[],
        overall_analysis_text="Тестовый анализ",
    )
    return cde


@pytest.fixture(autouse=True)
def close_db_connections_after_test(request):
    yield
    if request.node.get_closest_marker('django_db') is not None:
        close_old_connections()
        connections.close_all()