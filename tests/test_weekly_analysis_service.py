# /home/shlicha/psycho_diary/tests/test_weekly_analysis_service.py
"""
Тесты для WeeklyAnalysisService.
"""

import pytest
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import pytz

from diary.services.weekly_analysis_service import weekly_analysis_service
from diary.models import WeeklyAnalysis, CombinedDiaryEntry, DailyAnalysis
from users.models import User
from model_bakery import baker


@pytest.mark.django_db
class TestWeeklyAnalysisService:
    """Тесты для сервиса еженедельного анализа."""

    @pytest.fixture
    def user_with_data(self, db):
        """Фикстура пользователя с профилем для теста."""
        return baker.make(
            User,
            username='test_weekly_user',
            telegram_id=123456789,
            timezone='Europe/Moscow',
            awareness_level=5,
            personality_traits={"openness": 0.7},
            life_facts=["I live in Moscow"],
            hobbies=["reading"],
            core_values=["honesty"],
            triggers=["loud noises"],
            strengths=["persistence"],
            areas_for_growth=["public speaking"]
        )

    @pytest.fixture
    def week_dates(self):
        """Фикстура с датами для тестовой недели (Пн-Вс)."""
        # Неделя с 2023-10-23 (Пн) по 2023-10-29 (Вс)
        start_date = date(2023, 10, 23)
        dates = [start_date + timedelta(days=i) for i in range(7)]
        return start_date, dates

    @pytest.fixture
    def populate_week_data(self, user_with_data, week_dates):
        """Фикстура для заполнения тестовыми данными за неделю."""
        _, dates = week_dates
        combined_entries = []
        for i, d in enumerate(dates):
            cde = baker.make(
                CombinedDiaryEntry,
                user=user_with_data,
                date=d,
                text=f"Entry for {d}",
                entry_count=1,
                is_analyzed=True,
                average_mood_score=5.0 + (i * 0.5) # Разное настроение
            )
            # Создаем DailyAnalysis для каждой CombinedDiaryEntry
            baker.make(
                DailyAnalysis,
                combined_entry=cde,
                mood_trend='stable' if i % 2 == 0 else 'improving',
                key_themes=[{"theme": f"theme_{i}", "significance": 0.5}],
                emotional_patterns=[{"emotion": f"emotion_{i}"}],
                insights=[{"text": f"insight_{i}", "category": "other", "significance": 0.6}],
                overall_analysis_text=f"Overall analysis for {d}",
                recommendations=[f"Recommendation for {d}"]
            )
            combined_entries.append(cde)
        return combined_entries

    @pytest.fixture
    def previous_week_analysis(self, user_with_data):
        """Фикстура для предыдущего анализа недели."""
        start_date = date(2023, 10, 16) # Предыдущая неделя
        return baker.make(
            WeeklyAnalysis,
            user=user_with_data,
            week_start_date=start_date,
            summary_text="Previous week summary",
            consolidated_user_profile=user_with_data.get_profile_data(), # Упрощение
            statistics={"avg_mood_score": 4.5}
        )

    @pytest.mark.asyncio
    async def test_perform_weekly_analysis_success(
        self, user_with_data, populate_week_data, previous_week_analysis
    ):
        """Тест успешного выполнения еженедельного анализа."""
        # Замораживаем время на понедельник после недели анализа
        # Анализируем неделю 2023-10-23 - 2023-10-29, сегодня 2023-10-30 (Пн)
        test_date_in_user_tz = date(2023, 10, 30) 
        
        # Мокаем get_local_datetime, чтобы вернуть правильную дату
        with patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0))):
            
            # Мокаем вызов DeepSeek API
            mock_api_response = {
                'success': True,
                'result': {
                    "summary_text": "Great week!",
                    "progress_insights": {
                        "mood_trend": "improving",
                        "key_insights": [{"text": "Mood improved", "significance": 0.8}],
                        "notable_patterns": [],
                        "progress_notes": "User is doing well."
                    },
                    "user_profile_updates": {
                        "personality_traits": {"openness": 0.8}, # Обновление
                        "life_facts": [{"remove": "I live in Moscow"}, "I live in St. Petersburg"], # Замена
                        "hobbies": ["reading", "swimming"], # Добавление
                        "core_values": ["honesty"],
                        "triggers": ["loud noises"],
                        "strengths": ["persistence"],
                        "areas_for_growth": ["public speaking"],
                        "awareness_level_adjustment": {"new_level": 6, "reasoning": "Good progress"}
                    },
                    "statistics": {
                        "total_entries": 7,
                        "streak_days_current": 7,
                        "avg_mood_score": 6.0, # Обновленное среднее
                        "tasks_assigned": 0,
                        "tasks_completed": 0,
                        "unique_themes_count": 7,
                        "unique_emotions_count": 7,
                        "word_count_total": 100
                    },
                    "comparison_with_previous": {
                        "previous_week_start": "2023-10-16",
                        "mood_comparison": "Mood improved from 4.5 to 6.0",
                        "consistency_comparison": "Same consistency",
                        "profile_changes": ["Location updated"],
                        "progress_comment": "Positive dynamics."
                    }
                },
                'raw_response': '{"summary_text": "Great week!"}' # Имитация
            }

            with patch('diary.services.weekly_analysis_service.deepseek_api_service.send_prompt_and_parse', new=AsyncMock(return_value=mock_api_response)):
                
                # Выполняем анализ
                result = await weekly_analysis_service.perform_weekly_analysis(user_with_data)

                # Проверяем результат
                assert result['success'] is True
                assert 'weekly_analysis' in result
                assert result['weekly_analysis'] is not None
                
                weekly_analysis_obj = result['weekly_analysis']
                
                # Проверяем, что объект создан в БД
                assert WeeklyAnalysis.objects.filter(id=weekly_analysis_obj.id).exists()
                
                # Проверяем поля объекта
                assert weekly_analysis_obj.user == user_with_data
                assert weekly_analysis_obj.week_start_date == date(2023-10-23)
                assert weekly_analysis_obj.summary_text == "Great week!"
                assert weekly_analysis_obj.progress_insights['mood_trend'] == "improving"
                
                # Проверяем, что профиль пользователя обновился
                user_with_data.refresh_from_db()
                assert user_with_data.awareness_level == 6
                assert user_with_data.personality_traits["openness"] == 0.8
                # Проверяем замену факта
                assert "I live in St. Petersburg" in user_with_data.life_facts
                assert "I live in Moscow" not in user_with_data.life_facts
                # Проверяем добавление хобби
                assert "swimming" in user_with_data.hobbies


    @pytest.mark.asyncio
    async def test_perform_weekly_analysis_no_data(self, user_with_data):
        """Тест выполнения анализа, когда нет данных за неделю."""
        # Замораживаем время
        test_date_in_user_tz = date(2023, 11, 6) # Понедельник
        with patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0))):
            
            result = await weekly_analysis_service.perform_weekly_analysis(user_with_data)

            assert result['success'] is False
            assert result['error'] == 'no_data'
            assert result['weekly_analysis'] is None
            # Проверяем, что объект в БД не создан
            assert not WeeklyAnalysis.objects.filter(user=user_with_data).exists()


    @pytest.mark.asyncio
    async def test_perform_weekly_analysis_api_error(self, user_with_data, populate_week_data):
        """Тест выполнения анализа при ошибке API."""
        test_date_in_user_tz = date(2023, 10, 30)
        with patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0))):
            
            mock_api_response = {
                'success': False,
                'error': 'api_timeout',
                'message': 'Request timed out'
            }
            with patch('diary.services.weekly_analysis_service.deepseek_api_service.send_prompt_and_parse', new=AsyncMock(return_value=mock_api_response)):
                
                result = await weekly_analysis_service.perform_weekly_analysis(user_with_data)

                assert result['success'] is False
                assert result['error'] == 'api_timeout'
                assert result['weekly_analysis'] is None


    @pytest.mark.asyncio
    async def test_gather_weekly_context(self, user_with_data, populate_week_data, previous_week_analysis):
        """Тест сбора контекста для анализа."""
        # Тестируемая неделя
        week_start = date(2023, 10, 23)
        week_end = date(2023, 10, 29)
        
        context = await weekly_analysis_service._gather_weekly_context(user_with_data, week_start, week_end)
        
        assert context['has_data'] is True
        assert 'user_profile' in context
        assert len(context['daily_analyses']) == 7 # 7 дней
        assert context['previous_weekly_analysis'] is not None
        assert context['previous_weekly_analysis']['week_start_date'] == '2023-10-16'
        
        # Проверяем статистику (примерные значения)
        assert 'total_entries' in context['week_statistics']
        assert context['week_statistics']['streak_days_current'] >= 0 # Может быть любым неотрицательным


    @pytest.mark.asyncio
    async def test_create_or_update_weekly_analysis(self, user_with_data):
        """Тест создания объекта WeeklyAnalysis."""
        week_start = date(2023, 10, 23)
        
        parsed_result = {
            "summary_text": "Test summary",
            "progress_insights": {"mood_trend": "stable"},
            "user_profile_updates": {"personality_traits": {"openness": 0.75}},
            "statistics": {"total_entries": 5},
            "comparison_with_previous": {"progress_comment": "Stable"}
        }
        api_result = {"raw_response": "test"}
        context = {"user_profile": user_with_data.get_profile_data()} # Минимальный контекст

        weekly_analysis_obj = await weekly_analysis_service._create_or_update_weekly_analysis(
            user_with_data, week_start, parsed_result, api_result, context
        )

        assert weekly_analysis_obj.user == user_with_data
        assert weekly_analysis_obj.week_start_date == week_start
        assert weekly_analysis_obj.summary_text == "Test summary"
        assert weekly_analysis_obj.api_response == api_result


    @pytest.mark.asyncio
    async def test_update_user_profile(self, user_with_data):
        """Тест обновления профиля пользователя."""
        profile_updates = {
            "personality_traits": {"openness": 0.9, "conscientiousness": 0.8},
            "life_facts": ["Fact 1", {"remove": "I live in Moscow"}, "Fact 2"],
            "hobbies": ["reading", "swimming"]
        }

        success = await weekly_analysis_service._update_user_profile(user_with_data, profile_updates)
        
        assert success is True
        user_with_data.refresh_from_db()
        
        # Проверяем обновление словаря
        assert user_with_data.personality_traits["openness"] == 0.9
        assert user_with_data.personality_traits["conscientiousness"] == 0.8
        
        # Проверяем обновление списков
        assert "Fact 1" in user_with_data.life_facts
        assert "Fact 2" in user_with_data.life_facts
        assert "I live in Moscow" not in user_with_data.life_facts # Удалено
        
        assert "swimming" in user_with_data.hobbies


    @pytest.mark.asyncio
    async def test_get_weekly_analysis_for_week(self, user_with_data, previous_week_analysis):
        """Тест получения анализа недели."""
        week_start = date(2023, 10, 16)
        
        analysis = await weekly_analysis_service._get_weekly_analysis_for_week(user_with_data, week_start)
        
        assert analysis is not None
        assert analysis.id == previous_week_analysis.id
        assert analysis.week_start_date == week_start


    @pytest.mark.asyncio
    async def test_perform_weekly_analysis_already_exists(self, user_with_data, populate_week_data, previous_week_analysis):
        """Тест выполнения анализа, если он уже существует."""
        # Создаем анализ для тестируемой недели
        existing_analysis = baker.make(
            WeeklyAnalysis,
            user=user_with_data,
            week_start_date=date(2023, 10, 23),
            summary_text="Already exists"
        )
        
        test_date_in_user_tz = date(2023, 10, 30)
        with patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0))):
            
            result = await weekly_analysis_service.perform_weekly_analysis(user_with_data)

            assert result['success'] is True
            assert result['message'] == "Анализ для этой недели уже существует."
            assert result['weekly_analysis'].id == existing_analysis.id
