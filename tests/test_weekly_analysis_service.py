"""
Тесты для WeeklyAnalysisService.
"""

from datetime import date, datetime, time

import pytest
from asgiref.sync import async_to_sync
from model_bakery import baker

from bot.services.deepseek_api import deepseek_api_service
from diary.models import WeeklyAnalysis
from diary.services.weekly_analysis_service import weekly_analysis_service
from users.models import User


@pytest.mark.django_db
class TestWeeklyAnalysisService:
    """Тесты для сервиса еженедельного анализа."""

    @pytest.fixture
    def user_with_data(self, db):
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
            areas_for_growth=["public speaking"],
            compressed_psych_profile={
                "psych_summary": "User summary",
                "core_patterns": ["reflection", "growth"],
                "emotional_style": "stable",
                "main_triggers": ["loud noises"],
                "coping_style": "journaling",
                "current_focus": "self-development",
            },
        )

    def test_perform_weekly_analysis_success(self, user_with_data, mocker):
        test_date_in_user_tz = date(2023, 10, 30)
        mock_weekly_analysis = mocker.MagicMock(spec=WeeklyAnalysis)
        mock_weekly_analysis.id = 101

        mock_context = {
            'has_data': True,
            'daily_analyses': [{"date": "2023-10-23", "mood_trend": "stable"}],
            'previous_weekly_analysis': None,
            'week_statistics': {"avg_mood_score": 6.0},
        }
        mock_api_response = {
            'success': True,
            'result': {
                "summary_text": "Great week!",
                "progress_insights": {"mood_trend": "improving"},
                "statistics": {"avg_mood_score": 6.0},
                "comparison_with_previous": {},
            },
        }

        mocker.patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0)))
        mocker.patch.object(weekly_analysis_service, '_get_weekly_analysis_for_week', new=mocker.AsyncMock(return_value=None))
        mocker.patch.object(weekly_analysis_service, '_gather_weekly_context', new=mocker.AsyncMock(return_value=mock_context))
        mocker.patch.object(deepseek_api_service, 'send_prompt_and_parse', new=mocker.AsyncMock(return_value=mock_api_response))
        create_mock = mocker.patch.object(
            weekly_analysis_service,
            '_create_or_update_weekly_analysis',
            new=mocker.AsyncMock(return_value=mock_weekly_analysis),
        )

        result = async_to_sync(weekly_analysis_service.perform_weekly_analysis)(user_with_data)

        assert result['success'] is True
        assert result['weekly_analysis'] is mock_weekly_analysis
        create_mock.assert_awaited_once()

    def test_perform_weekly_analysis_no_data(self, user_with_data, mocker):
        test_date_in_user_tz = date(2023, 11, 6)

        mocker.patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0)))
        mocker.patch.object(weekly_analysis_service, '_get_weekly_analysis_for_week', new=mocker.AsyncMock(return_value=None))
        mocker.patch.object(
            weekly_analysis_service,
            '_gather_weekly_context',
            new=mocker.AsyncMock(return_value={'has_data': False}),
        )

        result = async_to_sync(weekly_analysis_service.perform_weekly_analysis)(user_with_data)

        assert result['success'] is False
        assert result['error'] == 'no_data'
        assert result['weekly_analysis'] is None

    def test_perform_weekly_analysis_api_error(self, user_with_data, mocker):
        test_date_in_user_tz = date(2023, 10, 30)
        mock_weekly_analysis = mocker.MagicMock(spec=WeeklyAnalysis)
        mock_weekly_analysis.id = 202

        mocker.patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0)))
        mocker.patch.object(weekly_analysis_service, '_get_weekly_analysis_for_week', new=mocker.AsyncMock(return_value=None))
        mocker.patch.object(
            weekly_analysis_service,
            '_gather_weekly_context',
            new=mocker.AsyncMock(return_value={'has_data': True, 'daily_analyses': [], 'previous_weekly_analysis': None, 'week_statistics': {}}),
        )
        mocker.patch.object(
            deepseek_api_service,
            'send_prompt_and_parse',
            new=mocker.AsyncMock(return_value={'success': False, 'error': 'api_timeout', 'message': 'Request timed out'}),
        )
        create_mock = mocker.patch.object(
            weekly_analysis_service,
            '_create_or_update_weekly_analysis',
            new=mocker.AsyncMock(return_value=mock_weekly_analysis),
        )

        result = async_to_sync(weekly_analysis_service.perform_weekly_analysis)(user_with_data)

        assert result['success'] is False
        assert result['error'] == 'api_timeout'
        assert result['weekly_analysis'] is mock_weekly_analysis
        create_mock.assert_awaited_once()

    def test_create_lite_profile(self):
        full_profile = {
            'psych_summary': 'Sentence one. Sentence two. Sentence three. ' * 20,
            'core_patterns': ['p1', 'p2', 'p3'],
            'emotional_style': 'stable',
            'main_triggers': ['t1', 't2', 't3', 't4'],
            'coping_style': 'journaling',
            'current_focus': 'growth',
        }

        lite = weekly_analysis_service._create_lite_profile(full_profile)

        assert len(lite['psych_summary']) <= 201
        assert lite['core_patterns'] == ['p1', 'p2']
        assert lite['main_triggers'] == ['t1', 't2', 't3']
        assert lite['emotional_style'] == 'stable'
        assert lite['coping_style'] == 'journaling'
        assert lite['current_focus'] == 'growth'

    def test_create_or_update_weekly_analysis(self, user_with_data, mocker):
        week_start = date(2023, 10, 23)
        parsed_result = {
            "summary_text": "Test summary",
            "progress_insights": {"mood_trend": "stable"},
            "statistics": {"total_entries": 5},
            "comparison_with_previous": {"progress_comment": "Stable"},
            "awareness_level_adjustment": {"new_level": 6},
        }
        api_result = {"raw_response": "test"}
        context = {"week_statistics": {"total_entries": 5}}

        mocker.patch(
            'diary.services.full_profile_service.full_profile_service.generate_for_user',
            return_value={"summary": "profile"},
        )

        weekly_analysis_obj = async_to_sync(weekly_analysis_service._create_or_update_weekly_analysis)(
            user_with_data,
            week_start,
            parsed_result,
            api_result,
            context,
        )

        assert weekly_analysis_obj.user == user_with_data
        assert weekly_analysis_obj.week_start_date == week_start
        assert weekly_analysis_obj.summary_text == "Test summary"
        assert weekly_analysis_obj.api_response == api_result

        user_with_data.refresh_from_db()
        assert user_with_data.full_psych_profile == {"summary": "profile"}

    def test_get_weekly_analysis_for_week(self, user_with_data):
        analysis = baker.make(
            WeeklyAnalysis,
            user=user_with_data,
            week_start_date=date(2023, 10, 16),
            summary_text="Previous week summary",
        )

        result = async_to_sync(weekly_analysis_service._get_weekly_analysis_for_week)(
            user_with_data,
            date(2023, 10, 16),
        )

        assert result is not None
        assert result.id == analysis.id

    def test_perform_weekly_analysis_already_exists(self, user_with_data, mocker):
        existing_analysis = mocker.MagicMock(spec=WeeklyAnalysis)
        existing_analysis.id = 303
        test_date_in_user_tz = date(2023, 10, 30)

        mocker.patch.object(User, 'get_local_datetime', return_value=datetime.combine(test_date_in_user_tz, time(3, 0)))
        get_mock = mocker.patch.object(
            weekly_analysis_service,
            '_get_weekly_analysis_for_week',
            new=mocker.AsyncMock(return_value=existing_analysis),
        )

        result = async_to_sync(weekly_analysis_service.perform_weekly_analysis)(user_with_data)

        assert result['success'] is True
        assert result['message'] == "Анализ для этой недели уже существует."
        assert result['weekly_analysis'] is existing_analysis
        get_mock.assert_awaited_once()
