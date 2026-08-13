"""
Тесты для task_display_service.py
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings
from django.utils import timezone
from aiogram.types import InlineKeyboardMarkup

from diary.services.task_display_service import task_display_service, TaskAnalysisNotification, TaskHistoryDetail
from diary.models import TherapyTask, TaskCompletion, TaskCompletionAnalysis
from users.models import User


# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
from model_bakery import baker
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


# --- Helpers for async DB operations ---
async def _create_task(**kwargs):
    return await sync_to_async(TherapyTask.objects.create)(**kwargs)


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceBuildInvalidKeyboard:
    """Тесты для build_task_completion_invalid_keyboard."""

    def test_build_invalid_keyboard_has_buttons(self):
        keyboard = task_display_service.build_task_completion_invalid_keyboard(42, 'ru')
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) == 3  # Try again, Skip, Back
        # First button callback contains task id
        first_btn = keyboard.inline_keyboard[0][0]
        assert "complete_task:42" in first_btn.callback_data


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceFormatMoodImpact:
    """Тесты для _format_mood_impact."""

    def test_positive_impact(self):
        assert task_display_service._format_mood_impact(3) == "🔺 +3"

    def test_negative_impact(self):
        assert task_display_service._format_mood_impact(-2) == "🔻 -2"

    def test_zero_impact(self):
        assert task_display_service._format_mood_impact(0) == "➡️ 0"

    def test_none_impact(self):
        assert task_display_service._format_mood_impact(None) == "N/A"

    def test_string_impact_valid(self):
        assert task_display_service._format_mood_impact("5") == "🔺 +5"

    def test_string_impact_invalid(self):
        assert task_display_service._format_mood_impact("abc") == "N/A"


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceFormatTaskAnalysisNotification:
    """Тесты для format_task_analysis_notification."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=10001, language='ru')

    @pytest.fixture
    def test_task(self, test_user):
        return baker.make(
            TherapyTask, user=test_user, title="Тестовое задание",
            description="Описание", status='active'
        )

    @pytest.fixture
    def test_completion(self, test_task):
        return baker.make(
            TaskCompletion, task=test_task,
            completion_text="Выполнено", feelings_text="Хорошо"
        )

    @pytest.mark.asyncio
    async def test_notification_invalid_result(self, test_user, test_completion):
        analysis_result = {
            'invalid': True,
            'validation_comment': "Недостаточно информации"
        }
        notification = await task_display_service.format_task_analysis_notification(
            analysis_result, test_user, test_completion
        )
        assert isinstance(notification, TaskAnalysisNotification)
        assert "Недостаточно информации" in notification.text

    @pytest.mark.asyncio
    async def test_notification_error_result(self, test_user, test_completion):
        analysis_result = None
        notification = await task_display_service.format_task_analysis_notification(
            analysis_result, test_user, test_completion
        )
        assert isinstance(notification, TaskAnalysisNotification)
        # Falls through to error case
        assert notification.keyboard is not None

    @pytest.mark.asyncio
    async def test_notification_successful_analysis(self, test_user, test_completion):
        # Mock the _format_successful_analysis path
        mock_analysis = MagicMock()
        mock_analysis.id = 1
        mock_analysis.api_response = {'result': {'formatted_message': "Отличный анализ!"}}
        mock_analysis.tokens_awarded = 0

        with patch.object(
            task_display_service, '_format_successful_analysis',
            new_callable=AsyncMock
        ) as mock_format:
            mock_format.return_value = TaskAnalysisNotification(
                text="Отличный анализ!",
                keyboard=MagicMock()
            )
            notification = await task_display_service.format_task_analysis_notification(
                mock_analysis, test_user, test_completion
            )
            assert notification.text == "Отличный анализ!"
            mock_format.assert_called_once()


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceFormatTaskHistoryDetail:
    """Тесты для format_task_history_detail."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=20001, language='ru')

    @pytest.fixture
    def test_task(self, test_user):
        return baker.make(
            TherapyTask, user=test_user, title="Тестовое задание",
            description="Описание задания", status='completed',
            complexity='medium', assigned_at=timezone.now()
        )

    @pytest.mark.asyncio
    async def test_format_detail_without_completion(self, test_task):
        detail = await task_display_service.format_task_history_detail(test_task, 'ru')
        assert isinstance(detail, TaskHistoryDetail)
        assert "Тестовое задание" in detail.text

    @pytest.mark.asyncio
    async def test_format_detail_with_completion(self, test_task):
        completion = await sync_to_async(TaskCompletion.objects.create)(
            task=test_task,
            completion_text="Я выполнил задание",
            feelings_text="Чувствую себя лучше"
        )
        detail = await task_display_service.format_task_history_detail(test_task, 'ru')
        assert isinstance(detail, TaskHistoryDetail)
        assert "Я выполнил задание" in detail.text
        assert "Чувствую себя лучше" in detail.text

    @pytest.mark.asyncio
    async def test_format_detail_error_handling(self, test_task):
        # Force an error by mocking TaskCompletion.objects.aget to raise
        mock_aget = AsyncMock(side_effect=Exception("DB error"))
        with patch.object(TaskCompletion.objects, 'aget', mock_aget):
            detail = await task_display_service.format_task_history_detail(test_task, 'ru')
            assert isinstance(detail, TaskHistoryDetail)
            # Should fall back to error messages (localized text)
            assert "Ошибка" in detail.text  # Russian "Error"


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceGetTaskAnalysisDetail:
    """Тесты для get_task_analysis_detail."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=30001, language='ru', token_balance=100)

    @pytest.fixture
    def test_task(self, test_user):
        return baker.make(
            TherapyTask, user=test_user, title="Анализируемое задание",
            description="Описание", status='completed',
            complexity='high', assigned_at=timezone.now()
        )

    @pytest.fixture
    def test_completion(self, test_task):
        return baker.make(
            TaskCompletion, task=test_task,
            completion_text="Выполнено", feelings_text="Хорошо"
        )

    @pytest.mark.asyncio
    async def test_detail_task_not_found(self, test_user):
        result = await task_display_service.get_task_analysis_detail(test_user, 99999)
        assert result['success'] is False
        assert result['error'] == 'task_not_found'

    @pytest.mark.asyncio
    async def test_detail_task_not_completed(self, test_task):
        # Task status is 'completed' but let's test a different status
        test_task.status = 'active'
        await sync_to_async(test_task.save)()
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is False
        assert result['error'] == 'not_completed'

    @pytest.mark.asyncio
    async def test_detail_completion_not_found(self, test_task):
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is False
        assert result['error'] == 'completion_not_found'

    @pytest.mark.asyncio
    async def test_detail_analysis_not_found(self, test_task, test_completion):
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is False
        assert result['error'] == 'analysis_not_found'

    @pytest.mark.asyncio
    async def test_detail_with_analysis_no_details(self, test_task, test_completion):
        # Create analysis without detailed_analysis
        analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
            completion=test_completion,
            effect_description="Эффект есть",
            mood_impact_score=2,
            comment="Хорошая работа",
            recommendation="Продолжайте",
            tokens_awarded=5,
            api_response={'result': {}},
            detailed_analysis=''
        )
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is True
        assert result['text'] is not None
        assert result['keyboard'] is not None

    @pytest.mark.asyncio
    async def test_detail_with_detailed_analysis(self, test_task, test_completion):
        # Create analysis with detailed_analysis
        analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
            completion=test_completion,
            effect_description="Значительный эффект",
            mood_impact_score=3,
            comment="Отличная работа!",
            recommendation="Рекомендуем продолжить",
            tokens_awarded=10,
            api_response={'result': {}},
            detailed_analysis="Подробный анализ показывает положительную динамику."
        )
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is True
        assert "Подробный анализ показывает" in result['text']
        assert result['keyboard'] is not None

    @pytest.mark.asyncio
    async def test_detail_with_tokens_awarded(self, test_task, test_completion):
        analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
            completion=test_completion,
            effect_description="Эффект",
            mood_impact_score=1,
            comment="Ок",
            recommendation="Ок",
            tokens_awarded=15,
            api_response={'result': {}},
            detailed_analysis="Детали"
        )
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is True
        # Token info should be in text
        assert "15" in result['text']

    @pytest.mark.asyncio
    async def test_detail_analysis_without_detailed_text(self, test_task, test_completion):
        analysis = await sync_to_async(TaskCompletionAnalysis.objects.create)(
            completion=test_completion,
            effect_description="Эффект",
            mood_impact_score=0,
            comment="Комментарий",
            recommendation="Рекомендация",
            tokens_awarded=0,
            api_response={'result': {}},
            detailed_analysis=''
        )
        result = await task_display_service.get_task_analysis_detail(test_task.user, test_task.id)
        assert result['success'] is True
        assert result['text'] is not None


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceGetBackKeyboard:
    """Тесты для _get_back_keyboard."""

    def test_back_keyboard_returns_markup(self):
        keyboard = task_display_service._get_back_keyboard('ru')
        assert isinstance(keyboard, InlineKeyboardMarkup)


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceSuccessfulAnalysis:
    """Тесты для _format_successful_analysis."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=40001, language='ru', token_balance=50)

    @pytest.fixture
    def test_task(self, test_user):
        return baker.make(
            TherapyTask, user=test_user, title="Задание",
            description="Описание", status='completed'
        )

    @pytest.fixture
    def test_completion(self, test_task):
        return baker.make(
            TaskCompletion, task=test_task,
            completion_text="Выполнено", feelings_text="Хорошо"
        )

    @pytest.mark.asyncio
    async def test_analysis_with_formatted_message(self, test_user, test_completion):
        mock_analysis = MagicMock()
        mock_analysis.id = 1
        mock_analysis.api_response = {'result': {'formatted_message': "Готовый анализ"}}
        mock_analysis.tokens_awarded = 0

        notification = await task_display_service._format_successful_analysis(
            mock_analysis, test_user, test_completion
        )
        assert notification.text == "Готовый анализ"

    @pytest.mark.asyncio
    async def test_analysis_with_formatted_message_and_tokens(self, test_user, test_completion):
        mock_analysis = MagicMock()
        mock_analysis.id = 2
        mock_analysis.api_response = {'result': {'formatted_message': "Анализ"}}
        mock_analysis.tokens_awarded = 10

        with patch.object(task_display_service, '_reload_user', new_callable=AsyncMock) as mock_reload:
            mock_user = MagicMock()
            mock_user.token_balance = 60
            mock_reload.return_value = mock_user

            notification = await task_display_service._format_successful_analysis(
                mock_analysis, test_user, test_completion
            )
            assert "10" in notification.text


@pytest.mark.django_db(transaction=True)
class TestTaskDisplayServiceBuildDetailedAnalysisText:
    """Тесты для _build_detailed_analysis_text."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=50001, language='ru', token_balance=100)

    @pytest.mark.asyncio
    async def test_build_detailed_text_without_tokens(self, test_user):
        mock_analysis = MagicMock()
        mock_analysis.effect_description = "Положительный эффект"
        mock_analysis.mood_impact_score = 3
        mock_analysis.comment = "Хорошо"
        mock_analysis.recommendation = "Продолжайте"
        mock_analysis.detailed_analysis = "Подробности"

        text = await task_display_service._build_detailed_analysis_text(
            mock_analysis, test_user, tokens_awarded=0
        )
        assert "Положительный эффект" in text

    @pytest.mark.asyncio
    async def test_build_detailed_text_with_tokens(self, test_user):
        mock_analysis = MagicMock()
        mock_analysis.effect_description = "Эффект"
        mock_analysis.mood_impact_score = 2
        mock_analysis.comment = "Комментарий"
        mock_analysis.recommendation = "Рекомендация"
        mock_analysis.detailed_analysis = ""

        with patch.object(task_display_service, '_reload_user', new_callable=AsyncMock) as mock_reload:
            mock_user = MagicMock()
            mock_user.token_balance = 120
            mock_reload.return_value = mock_user

            text = await task_display_service._build_detailed_analysis_text(
                mock_analysis, test_user, tokens_awarded=20
            )
            assert "20" in text

    @pytest.mark.asyncio
    async def test_build_detailed_text_with_tokens_for_max_user(self):
        max_user = baker.make(User, telegram_id=None, max_id=900501, language='ru', token_balance=135)
        mock_analysis = MagicMock()
        mock_analysis.effect_description = "Эффект"
        mock_analysis.mood_impact_score = 2
        mock_analysis.comment = "Комментарий"
        mock_analysis.recommendation = "Рекомендация"
        mock_analysis.detailed_analysis = ""

        text = await task_display_service._build_detailed_analysis_text(
            mock_analysis, max_user, tokens_awarded=20
        )

        assert "20" in text

    @pytest.mark.asyncio
    async def test_build_detailed_text_defaults(self, test_user):
        mock_analysis = MagicMock()
        mock_analysis.effect_description = None
        mock_analysis.mood_impact_score = None
        mock_analysis.comment = None
        mock_analysis.recommendation = None
        mock_analysis.detailed_analysis = None

        text = await task_display_service._build_detailed_analysis_text(
            mock_analysis, test_user, tokens_awarded=0
        )
        assert text is not None
        assert isinstance(text, str)
