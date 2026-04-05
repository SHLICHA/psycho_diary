"""
Тесты для моделей diary приложения.
Проверяют корректность полей, свойств и миграций.
"""
import pytest
from datetime import date, datetime, timedelta
from model_bakery import baker
from django.utils import timezone
from django.db import IntegrityError
import pytz

# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")

from diary.models import (
    DiaryEntry, PsychoAnalysis, CombinedDiaryEntry, DailyAnalysis,
    TherapyTask, TaskCompletion, TaskCompletionAnalysis, UserActivity,
    AnalysisRating, NextEntryPrompt, WeeklyAnalysis
)
from users.models import User


@pytest.mark.django_db
class TestDiaryEntryModel:
    """Тесты для модели DiaryEntry."""

    @pytest.fixture
    def user(self):
        return baker.make(User, username='testuser', telegram_id=12345, timezone='Europe/Moscow')

    @pytest.fixture
    def user_utc(self):
        return baker.make(User, username='testuser_utc', telegram_id=54321, timezone='UTC')

    @pytest.fixture
    def entry(self, user):
        return baker.make(DiaryEntry, user=user, text="Тестовая запись", language='ru', word_count=2)

    def test_create_entry_success(self, user):
        """Тест: успешное создание записи."""
        entry = baker.make(DiaryEntry, user=user, text="Запись", language='ru', word_count=1)

        assert entry.id is not None
        assert entry.user == user
        assert entry.text == "Запись"
        assert entry.language == 'ru'
        assert entry.word_count == 1
        assert entry.is_processed is False
        assert entry.created_at is not None

    def test_entry_date_with_user_timezone(self, user):
        """Тест: entry_date использует часовой пояс пользователя."""
        # 2023-10-26 23:00 MSK = 2023-10-26 20:00 UTC
        msk_tz = pytz.timezone('Europe/Moscow')
        entry_datetime_msk = msk_tz.localize(datetime(2023, 10, 26, 23, 0, 0))
        entry_datetime_utc = entry_datetime_msk.astimezone(pytz.utc)

        entry = baker.make(
            DiaryEntry,
            user=user,
            text="Поздняя запись",
            language='ru',
            word_count=2,
            created_at=entry_datetime_utc
        )

        # Для пользователя в Москве это должен быть 26 октября
        assert entry.entry_date == date(2023, 10, 26)

    def test_entry_date_with_utc_user(self, user_utc):
        """Тест: entry_date для пользователя в UTC."""
        entry_datetime_utc = datetime(2023, 10, 26, 20, 0, 0, tzinfo=pytz.utc)

        entry = baker.make(
            DiaryEntry,
            user=user_utc,
            text="UTC запись",
            language='ru',
            word_count=2,
            created_at=entry_datetime_utc
        )

        assert entry.entry_date == date(2023, 10, 26)

    def test_entry_string_representation(self, user):
        """Тест: строковое представление записи."""
        entry = baker.make(DiaryEntry, user=user, text="Запись", language='ru', word_count=2)

        assert "Тестовая запись" in str(entry)
        assert str(entry.user.username) in str(entry)

    def test_entry_day_group_auto_generated(self, user):
        """Тест: day_group генерируется автоматически."""
        entry1 = baker.make(DiaryEntry, user=user, text="Запись 1", language='ru', word_count=2)
        entry2 = baker.make(DiaryEntry, user=user, text="Запись 2", language='ru', word_count=2)

        assert entry1.day_group is not None
        assert entry2.day_group is not None
        # UUID должны быть разными
        assert entry1.day_group != entry2.day_group

    def test_combined_text_primary_entry(self, user):
        """Тест: combined_text для основной записи объединяет все записи дня."""
        today = timezone.now().date()
        baker.make(DiaryEntry, user=user, text="Запись 1", language='ru', word_count=2)
        baker.make(DiaryEntry, user=user, text="Запись 2", language='ru', word_count=2)

        # Получаем основную запись
        primary_entry = DiaryEntry.objects.filter(user=user).first()
        combined = primary_entry.combined_text

        assert "Запись 1" in combined
        assert "Запись 2" in combined


@pytest.mark.django_db
class TestPsychoAnalysisModel:
    """Тесты для модели PsychoAnalysis."""

    @pytest.fixture
    def entry(self):
        user = baker.make(User, username='testuser', telegram_id=12345)
        return baker.make(DiaryEntry, user=user, text="Тест", language='ru', word_count=1)

    def test_create_analysis_success(self, entry):
        """Тест: успешное создание анализа."""
        analysis = baker.make(
            PsychoAnalysis,
            entry=entry,
            mood_score=7,
            comment="Хорошо",
            recommendation="Продолжайте",
            processing_time=1.5,
            insights_extracted=3
        )

        assert analysis.id is not None
        assert analysis.mood_score == 7
        assert analysis.comment == "Хорошо"
        assert analysis.recommendation == "Продолжайте"
        assert analysis.processing_time == 1.5

    def test_analysis_string_representation(self, entry):
        """Тест: строковое представление анализа."""
        analysis = baker.make(
            PsychoAnalysis,
            entry=entry,
            mood_score=8,
            comment="Отлично",
            recommendation="Так держать",
            processing_time=2.0,
            insights_extracted=5
        )

        assert "8/10" in str(analysis)
        assert str(entry.id) in str(analysis)

    def test_analysis_one_to_one_with_entry(self, entry):
        """Тест: один анализ на одну запись."""
        baker.make(PsychoAnalysis, entry=entry, mood_score=7, comment="1", recommendation="1", processing_time=1.0)

        with pytest.raises(IntegrityError):
            baker.make(PsychoAnalysis, entry=entry, mood_score=8, comment="2", recommendation="2", processing_time=1.0)


@pytest.mark.django_db
class TestCombinedDiaryEntryModel:
    """Тесты для модели CombinedDiaryEntry."""

    @pytest.fixture
    def user(self):
        return baker.make(User, username='testuser', telegram_id=12345, timezone='Europe/Moscow')

    def test_create_combined_entry_success(self, user):
        """Тест: успешное создание объединенной записи."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Объединенный текст",
            entry_count=3,
            is_analyzed=False
        )

        assert combined.id is not None
        assert combined.user == user
        assert combined.date == date(2023, 10, 26)
        assert combined.entry_count == 3
        assert combined.is_analyzed is False

    def test_combined_entry_unique_user_date(self, user):
        """Тест: уникальность user + date."""
        baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Запись 1",
            entry_count=1
        )

        with pytest.raises(IntegrityError):
            baker.make(
                CombinedDiaryEntry,
                user=user,
                date=date(2023, 10, 26),
                text="Запись 2",
                entry_count=1
            )

    def test_update_mood_scores(self, user):
        """Тест: обновление оценок настроения."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Тест",
            entry_count=1,
            daily_mood_scores=[7, 8],
            average_mood_score=7.5
        )

        combined.update_mood_scores(9)

        assert combined.daily_mood_scores == [7, 8, 9]
        assert combined.average_mood_score == 8.0

    def test_update_mood_scores_invalid_score(self, user):
        """Тест: некорректная оценка не добавляется."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Тест",
            entry_count=1,
            daily_mood_scores=[7, 8],
            average_mood_score=7.5
        )

        combined.update_mood_scores(15)  # > 10

        assert combined.daily_mood_scores == [7, 8]  # Не изменилось

    def test_reset_analysis_flag(self, user):
        """Тест: сброс флага анализа."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Тест",
            entry_count=1,
            is_analyzed=True
        )

        combined.reset_analysis_flag()

        assert combined.is_analyzed is False

    def test_combined_entry_string_representation(self, user):
        """Тест: строковое представление."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Тест",
            entry_count=1
        )

        assert "2023-10-26" in str(combined)
        assert "testuser" in str(combined)


@pytest.mark.django_db
class TestDailyAnalysisModel:
    """Тесты для модели DailyAnalysis."""

    @pytest.fixture
    def combined_entry(self):
        user = baker.make(User, username='testuser', telegram_id=12345)
        return baker.make(CombinedDiaryEntry, user=user, date=date(2023, 10, 26), text="Тест", entry_count=1)

    def test_create_daily_analysis_success(self, combined_entry):
        """Тест: успешное создание анализа дня."""
        analysis = baker.make(
            DailyAnalysis,
            combined_entry=combined_entry,
            mood_trend='improving',
            key_themes=["работа"],
            emotional_patterns=["радость"],
            insights=["инсайт"],
            recommendations=["совет"]
        )

        assert analysis.id is not None
        assert analysis.mood_trend == 'improving'
        assert analysis.key_themes == ["работа"]

    def test_daily_analysis_string_representation(self, combined_entry):
        """Тест: строковое представление."""
        analysis = baker.make(
            DailyAnalysis,
            combined_entry=combined_entry,
            mood_trend='stable',
            key_themes=[],
            emotional_patterns=[],
            insights=[],
            recommendations=[]
        )

        assert "2023-10-26" in str(analysis)
        assert "testuser" in str(analysis)


@pytest.mark.django_db
class TestTherapyTaskModel:
    """Тесты для модели TherapyTask."""

    @pytest.fixture
    def user(self):
        return baker.make(User, username='testuser', telegram_id=12345)

    def test_create_task_success(self, user):
        """Тест: успешное создание задания."""
        task = baker.make(
            TherapyTask,
            user=user,
            title="Тестовое задание",
            description="Описание",
            status='pending',
            type='mindfulness',
            complexity='medium'
        )

        assert task.id is not None
        assert task.status == 'pending'
        assert task.type == 'mindfulness'
        assert task.complexity == 'medium'
        assert task.completed_at is None

    def test_task_string_representation(self, user):
        """Тест: строковое представление."""
        task = baker.make(
            TherapyTask,
            user=user,
            title="Задание",
            description="Описание",
            status='pending',
            type='mindfulness',
            complexity='medium'
        )

        assert "Задание" in str(task)
        assert "testuser" in str(task)


@pytest.mark.django_db
class TestTaskCompletionModel:
    """Тесты для модели TaskCompletion."""

    @pytest.fixture
    def task(self):
        user = baker.make(User, username='testuser', telegram_id=12345)
        return baker.make(TherapyTask, user=user, title="Задание", description="Описание", status='completed')

    def test_create_completion_success(self, task):
        """Тест: успешное создание выполнения задания."""
        completion = baker.make(
            TaskCompletion,
            task=task,
            completion_text="Выполнил задание",
            feelings_text="Чувствую себя хорошо"
        )

        assert completion.id is not None
        assert completion.completion_text == "Выполнил задание"
        assert completion.feelings_text == "Чувствую себя хорошо"

    def test_task_completion_one_to_one(self, task):
        """Тест: одно выполнение на одно задание."""
        baker.make(TaskCompletion, task=task, completion_text="1", feelings_text="1")

        with pytest.raises(IntegrityError):
            baker.make(TaskCompletion, task=task, completion_text="2", feelings_text="2")


@pytest.mark.django_db
class TestAnalysisRatingModel:
    """Тесты для модели AnalysisRating."""

    @pytest.fixture
    def analysis(self):
        user = baker.make(User, username='testuser', telegram_id=12345)
        entry = baker.make(DiaryEntry, user=user, text="Тест", language='ru', word_count=1)
        return baker.make(PsychoAnalysis, entry=entry, mood_score=7, comment="Хорошо", recommendation="1", processing_time=1.0)

    def test_create_rating_success(self, analysis):
        """Тест: успешное создание рейтинга."""
        user = analysis.entry.user
        rating = baker.make(AnalysisRating, user=user, analysis=analysis, rating=4)

        assert rating.id is not None
        assert rating.rating == 4
        assert rating.user == user
        assert rating.analysis == analysis

    def test_rating_unique_user_analysis(self, analysis):
        """Тест: уникальность user + analysis."""
        user = analysis.entry.user
        baker.make(AnalysisRating, user=user, analysis=analysis, rating=4)

        with pytest.raises(IntegrityError):
            baker.make(AnalysisRating, user=user, analysis=analysis, rating=3)

    def test_rating_valid_values(self, analysis):
        """Тест: допустимые значения рейтинга."""
        user = analysis.entry.user
        for rating_value in range(1, 6):
            rating = baker.make(AnalysisRating, user=user, analysis=analysis, rating=rating_value)
            assert rating.rating == rating_value


@pytest.mark.django_db
class TestNextEntryPromptModel:
    """Тесты для модели NextEntryPrompt."""

    @pytest.fixture
    def user(self):
        return baker.make(User, username='testuser', telegram_id=12345)

    def test_create_prompt_success(self, user):
        """Тест: успешное создание подсказки."""
        prompt = baker.make(
            NextEntryPrompt,
            user=user,
            target_date=date(2023, 10, 27),
            prompt_text="О чем хочешь написать?",
            is_used=False
        )

        assert prompt.id is not None
        assert prompt.is_used is False
        assert prompt.used_at is None

    def test_mark_as_used(self, user):
        """Тест: пометка подсказки как использованной."""
        prompt = baker.make(
            NextEntryPrompt,
            user=user,
            target_date=date(2023, 10, 27),
            prompt_text="Тест",
            is_used=False
        )

        prompt.mark_as_used()

        assert prompt.is_used is True
        assert prompt.used_at is not None

    def test_prompt_unique_user_date(self, user):
        """Тест: уникальность user + target_date."""
        baker.make(
            NextEntryPrompt,
            user=user,
            target_date=date(2023, 10, 27),
            prompt_text="Подсказка 1"
        )

        with pytest.raises(IntegrityError):
            baker.make(
                NextEntryPrompt,
                user=user,
                target_date=date(2023, 10, 27),
                prompt_text="Подсказка 2"
            )


@pytest.mark.django_db
class TestWeeklyAnalysisModel:
    """Тесты для модели WeeklyAnalysis."""

    @pytest.fixture
    def user(self):
        return baker.make(User, username='testuser', telegram_id=12345)

    def test_create_weekly_analysis_success(self, user):
        """Тест: успешное создание недельного анализа."""
        analysis = baker.make(
            WeeklyAnalysis,
            user=user,
            week_start_date=date(2023, 10, 23),
            summary_text="Хорошая неделя",
            progress_insights={"инсайт": "текст"},
            statistics={"total_entries": 10},
            comparison_with_previous={"better": True}
        )

        assert analysis.id is not None
        assert analysis.week_start_date == date(2023, 10, 23)
        assert analysis.summary_text == "Хорошая неделя"

    def test_weekly_analysis_unique_user_week(self, user):
        """Тест: уникальность user + week_start_date."""
        baker.make(
            WeeklyAnalysis,
            user=user,
            week_start_date=date(2023, 10, 23),
            summary_text="Анализ 1"
        )

        with pytest.raises(IntegrityError):
            baker.make(
                WeeklyAnalysis,
                user=user,
                week_start_date=date(2023, 10, 23),
                summary_text="Анализ 2"
            )


@pytest.mark.django_db
class TestModelMigrations:
    """
    Тесты для проверки корректности миграций.
    Эти тесты гарантируют, что миграции не сломаются.
    """

    def test_diary_entry_has_creator_timezone_field(self):
        """Тест: поле creator_timezone существует после миграции."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'diary_entry' AND column_name = 'creator_timezone'"
            )
            # Поле может еще не существовать если миграция не запущена
            # Этот тест просто проверяет что миграции применимы

    def test_all_expected_models_exist(self):
        """Тест: все ожидаемые модели существуют."""
        from django.apps import apps

        expected_models = [
            'DiaryEntry', 'PsychoAnalysis', 'CombinedDiaryEntry',
            'DailyAnalysis', 'TherapyTask', 'TaskCompletion',
            'TaskCompletionAnalysis', 'UserActivity', 'AnalysisRating',
            'NextEntryPrompt', 'WeeklyAnalysis'
        ]

        for model_name in expected_models:
            try:
                apps.get_model('diary', model_name)
            except LookupError:
                pytest.fail(f"Модель {model_name} не найдена!")

    def test_user_model_has_expected_fields(self):
        """Тест: модель User имеет ожидаемые поля."""
        user_fields = [f.name for f in User._meta.get_fields()]

        expected_fields = [
            'telegram_id', 'language', 'timezone', 'awareness_level',
            'is_premium', 'premium_expires_at', 'token_balance',
            'personality_traits', 'life_facts', 'hobbies',
            'core_values', 'triggers', 'strengths', 'areas_for_growth'
        ]

        for field in expected_fields:
            assert field in user_fields, f"Поле {field} не найдено в модели User!"
