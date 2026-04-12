"""
Тесты для diary_display_service.py
"""
import pytest
from datetime import date, datetime, timedelta
from model_bakery import baker
from model_bakery.recipe import Recipe
from django.utils import timezone
import pytz

from diary.services.diary_display_service import diary_display_service
from diary.models import DiaryEntry, PsychoAnalysis, CombinedDiaryEntry, DailyAnalysis, AnalysisRating
from users.models import User

# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


@pytest.mark.django_db
class TestDiaryDisplayService:
    """Тесты для DiaryDisplayService."""

    @pytest.fixture
    def user(self):
        """Фикстура пользователя."""
        return baker.make(User, username='testuser', telegram_id=12345, timezone='Europe/Moscow', language='ru')

    @pytest.fixture
    def diary_entry(self, user):
        """Фикстура записи дневника."""
        return baker.make(DiaryEntry, user=user, text="Тестовая запись", language='ru', word_count=2)

    @pytest.fixture
    def analysis(self, diary_entry):
        """Фикстура анализа."""
        return baker.make(
            PsychoAnalysis,
            entry=diary_entry,
            mood_score=7,
            comment="Хороший день",
            recommendation="Продолжайте вести дневник",
            processing_time=1.5,
            insights_extracted=3,
            analysis_text="Тест"
        )

    @pytest.fixture
    def multiple_entries(self, user):
        """Фикстура нескольких записей за один день."""
        entries = []
        for i in range(3):
            entry = baker.make(
                DiaryEntry,
                user=user,
                text=f"Запись {i+1}",
                language='ru',
                word_count=2
            )
            entries.append(entry)
        return entries

    # === build_rating_keyboard ===

    @pytest.mark.asyncio
    async def test_build_rating_keyboard_no_existing_rating(self, user, analysis):
        """Тест: клавиатура рейтинга создается если нет существующего рейтинга."""
        has_rating, rating_buttons = await diary_display_service.build_rating_keyboard(analysis, user, 'ru')

        assert has_rating is False
        assert len(rating_buttons) == 1
        assert len(rating_buttons[0]) == 5  # 5 кнопок рейтинга
        # Проверяем callback_data кнопок
        for i, btn in enumerate(rating_buttons[0]):
            assert f"rate_analysis:{analysis.id}:{i+1}" == btn.callback_data

    @pytest.mark.asyncio
    async def test_build_rating_keyboard_existing_rating(self, user, analysis):
        """Тест: если рейтинг уже существует, возвращается has_rating=True."""
        baker.make(AnalysisRating, user=user, analysis=analysis, rating=4)

        has_rating, rating_buttons = await diary_display_service.build_rating_keyboard(analysis, user, 'ru')

        assert has_rating is True
        assert len(rating_buttons) == 0

    # === build_add_comment_button ===

    @pytest.mark.asyncio
    async def test_build_add_comment_button_no_comment(self, user, diary_entry):
        """Тест: кнопка комментария создается если нет комментария."""
        buttons = await diary_display_service.build_add_comment_button(diary_entry, 'ru')

        assert buttons is not None
        assert len(buttons) == 1
        assert f"request_add_comment:{diary_entry.id}" == buttons[0].callback_data

    @pytest.mark.asyncio
    async def test_build_add_comment_button_existing_comment(self, user, diary_entry):
        """Тест: если комментарий есть, кнопка не создается."""
        diary_entry.user_comment = "Мой комментарий"
        await diary_entry.asave()

        buttons = await diary_display_service.build_add_comment_button(diary_entry, 'ru')

        assert buttons is None

    @pytest.mark.asyncio
    async def test_build_add_comment_button_nonexistent_entry(self, user):
        """Тест: если записи нет, возвращается None."""
        from diary.models import DiaryEntry
        non_existent_entry = DiaryEntry(id=999999)

        buttons = await diary_display_service.build_add_comment_button(non_existent_entry, 'ru')

        assert buttons is None

    # === submit_rating ===

    @pytest.mark.asyncio
    async def test_submit_rating_success(self, user, analysis):
        """Тест: успешная отправка рейтинга."""
        result = await diary_display_service.submit_rating(analysis.id, user, 4)

        assert result['success'] is True, f"Ожидался успех, получено: {result}"
        assert result['rating'] == 4
        assert await AnalysisRating.objects.filter(user=user, analysis=analysis, rating=4).aexists()

    @pytest.mark.asyncio
    async def test_submit_rating_already_rated(self, user, analysis):
        """Тест: если рейтинг уже отправлен, возвращается ошибка."""
        baker.make(AnalysisRating, user=user, analysis=analysis, rating=4)

        result = await diary_display_service.submit_rating(analysis.id, user, 3)

        assert result['success'] is False
        assert result['error'] == 'already_rated'

    @pytest.mark.asyncio
    async def test_submit_rating_wrong_user(self, user, analysis):
        """Тест: пользователь не может оценить чужой анализ."""
        other_user = baker.make(User, username='otheruser', telegram_id=99999)

        result = await diary_display_service.submit_rating(analysis.id, other_user, 5)

        assert result['success'] is False
        assert result['error'] == 'forbidden'

    @pytest.mark.asyncio
    async def test_submit_rating_nonexistent_analysis(self, user):
        """Тест: если анализа нет, возвращается ошибка."""
        result = await diary_display_service.submit_rating(999999, user, 3)

        assert result['success'] is False
        assert result['error'] == 'not_found'

    # === remove_rating_buttons_from_keyboard ===

    @pytest.mark.asyncio
    async def test_remove_rating_buttons_from_keyboard(self):
        """Тест: кнопки рейтинга удаляются из клавиатуры."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Rate 1", callback_data="rate_analysis:1:1")],
            [InlineKeyboardButton(text="Other", callback_data="other_action")]
        ])

        updated_keyboard = await diary_display_service.remove_rating_buttons_from_keyboard(keyboard)

        assert len(updated_keyboard.inline_keyboard) == 1
        assert updated_keyboard.inline_keyboard[0][0].callback_data == "other_action"

    @pytest.mark.asyncio
    async def test_remove_rating_buttons_from_keyboard_no_rating_buttons(self):
        """Тест: если нет кнопок рейтинга, клавиатура не меняется."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Other", callback_data="other_action")]
        ])

        updated_keyboard = await diary_display_service.remove_rating_buttons_from_keyboard(keyboard)

        assert len(updated_keyboard.inline_keyboard) == 1
        assert updated_keyboard.inline_keyboard[0][0].callback_data == "other_action"

    @pytest.mark.asyncio
    async def test_remove_rating_buttons_from_keyboard_none(self):
        """Тест: если клавиатура None, возвращается None."""
        result = await diary_display_service.remove_rating_buttons_from_keyboard(None)
        assert result is None

    # === format_mood_stars ===

    @pytest.mark.asyncio
    async def test_format_mood_stars_perfect_score(self):
        """Тест: полная оценка (10/10)."""
        result = await diary_display_service.format_mood_stars(10.0)
        assert result == "⭐⭐⭐⭐⭐"

    @pytest.mark.asyncio
    async def test_format_mood_stars_half_score(self):
        """Тест: половина оценки (5/10)."""
        result = await diary_display_service.format_mood_stars(5.0)
        assert result == "⭐⭐☆☆☆"

    @pytest.mark.asyncio
    async def test_format_mood_stars_low_score(self):
        """Тест: низкая оценка (2/10)."""
        result = await diary_display_service.format_mood_stars(2.0)
        assert result == "⭐☆☆☆☆"

    @pytest.mark.asyncio
    async def test_format_mood_stars_zero(self):
        """Тест: нулевая оценка."""
        result = await diary_display_service.format_mood_stars(0)
        assert result == ""

    @pytest.mark.asyncio
    async def test_format_mood_stars_none(self):
        """Тест: None оценка."""
        result = await diary_display_service.format_mood_stars(None)
        assert result == ""

    # === get_entry_with_pagination ===

    @pytest.mark.asyncio
    async def test_get_entry_with_pagination_prev(self, user, multiple_entries):
        """Тест: пагинация назад."""
        # multiple_entries[1] - средняя запись
        result = await diary_display_service.get_entry_with_pagination(
            user, multiple_entries[1].id, 'prev'
        )

        assert result['success'] is True
        assert result['entry'].id == multiple_entries[0].id
        assert result['is_first'] is True
        assert result['is_last'] is False

    @pytest.mark.asyncio
    async def test_get_entry_with_pagination_next(self, user, multiple_entries):
        """Тест: пагинация вперед."""
        result = await diary_display_service.get_entry_with_pagination(
            user, multiple_entries[1].id, 'next'
        )

        assert result['success'] is True
        assert result['entry'].id == multiple_entries[2].id
        assert result['is_first'] is False
        assert result['is_last'] is True

    @pytest.mark.asyncio
    async def test_get_entry_with_pagination_first_entry_prev(self, user, multiple_entries):
        """Тест: попытка перейти назад с первой записи."""
        result = await diary_display_service.get_entry_with_pagination(
            user, multiple_entries[0].id, 'prev'
        )

        assert result['success'] is False
        assert result['error'] == 'first_entry'
        assert result['is_first'] is True

    @pytest.mark.asyncio
    async def test_get_entry_with_pagination_last_entry_next(self, user, multiple_entries):
        """Тест: попытка перейти вперед с последней записи."""
        result = await diary_display_service.get_entry_with_pagination(
            user, multiple_entries[2].id, 'next'
        )

        assert result['success'] is False
        assert result['error'] == 'last_entry'
        assert result['is_last'] is True

    @pytest.mark.asyncio
    async def test_get_entry_with_pagination_nonexistent_entry(self, user):
        """Тест: несуществующая запись."""
        result = await diary_display_service.get_entry_with_pagination(user, 999999, 'prev')

        assert result['success'] is False
        assert result['error'] == 'not_found'

    # === format_entry_for_display ===

    @pytest.mark.asyncio
    async def test_format_entry_for_display_with_analysis(self, user, diary_entry, analysis):
        """Тест: форматирование записи с анализом."""
        entries = [diary_entry]
        target_date = diary_entry.created_at.date()

        result = await diary_display_service.format_entry_for_display(
            diary_entry, entries, target_date, 'ru'
        )

        assert result['success'] is True
        assert 'text' in result
        assert 'keyboard' in result
        assert "Тестовая запись" in result['text']

    @pytest.mark.asyncio
    async def test_format_entry_for_display_without_analysis(self, user, diary_entry):
        """Тест: форматирование записи без анализа."""
        entries = [diary_entry]
        target_date = diary_entry.created_at.date()

        result = await diary_display_service.format_entry_for_display(
            diary_entry, entries, target_date, 'ru'
        )

        assert result['success'] is True
        assert 'text' in result
        assert 'keyboard' in result

    # === format_full_day_analysis ===

    @pytest.fixture
    def combined_entry_with_analysis(self, user):
        """Фикстура CombinedDiaryEntry с DailyAnalysis."""
        combined = baker.make(
            CombinedDiaryEntry,
            user=user,
            date=date(2023, 10, 26),
            text="Объединенная запись",
            entry_count=1,
            average_mood_score=7.5
        )
        baker.make(
            DailyAnalysis,
            combined_entry=combined,
            mood_trend='improving',
            key_themes=["работа", "семья"],
            emotional_patterns=["радость"],
            insights=["инсайт 1"],
            recommendations=["совет 1", "совет 2"],
            overall_analysis_text="Хороший день, много позитива"
        )
        return combined

    @pytest.mark.asyncio
    async def test_format_full_day_analysis_success(self, user, combined_entry_with_analysis):
        """Тест: успешное форматирование полного анализа дня."""
        daily_analysis = combined_entry_with_analysis.daily_analysis

        result = await diary_display_service.format_full_day_analysis(
            combined_entry_with_analysis,
            daily_analysis,
            2023, 10, 26,
            'ru'
        )

        assert result['success'] is True
        assert 'text' in result
        assert 'keyboard' in result
        assert "Хороший день, много позитива" in result['text']
        assert "improving" in result['text'] or "Улучшается" in result['text']

    @pytest.mark.asyncio
    async def test_format_full_day_analysis_no_overall_text(self, user, combined_entry_with_analysis):
        """Тест: анализ без overall_analysis_text."""
        combined_entry_with_analysis.daily_analysis.overall_analysis_text = ""
        await combined_entry_with_analysis.daily_analysis.asave()

        result = await diary_display_service.format_full_day_analysis(
            combined_entry_with_analysis,
            combined_entry_with_analysis.daily_analysis,
            2023, 10, 26,
            'ru'
        )

        assert result['success'] is True
        assert "Общий текстовый анализ отсутствует" in result['text']

    # === build_entry_result_keyboard ===

    @pytest.mark.asyncio
    async def test_build_entry_result_keyboard(self, user, diary_entry, analysis):
        """Тест: создание полной клавиатуры для результата анализа."""
        keyboard = await diary_display_service.build_entry_result_keyboard(
            diary_entry, analysis, user, 'ru'
        )

        assert keyboard is not None
        assert isinstance(keyboard.inline_keyboard, list)
        assert len(keyboard.inline_keyboard) > 0
        # Должна быть кнопка "Назад"
        last_row = keyboard.inline_keyboard[-1]
        assert any(btn.callback_data == "main_menu" for btn in last_row)
