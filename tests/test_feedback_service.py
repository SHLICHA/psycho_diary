"""
Тесты для feedback_service.py
"""
import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings

from core.services.feedback_service import feedback_service, FeedbackService, FeedbackDisplayData
from users.models import Feedback, User


# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
from model_bakery import baker
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


# --- Helpers for async DB operations ---
async def _create_feedback(**kwargs):
    return await sync_to_async(Feedback.objects.create)(**kwargs)

async def _count_feedback():
    return await sync_to_async(Feedback.objects.count)()


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceIsDeveloper:
    """Тесты для is_developer."""

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_developer_correct_id(self):
        assert feedback_service.is_developer(12345) is True

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_developer_wrong_id(self):
        assert feedback_service.is_developer(99999) is False

    @override_settings(DEVELOPER_CHAT_ID='')
    def test_is_developer_no_setting(self):
        assert feedback_service.is_developer(12345) is False

    @override_settings(DEVELOPER_CHAT_ID='invalid')
    def test_is_developer_invalid_value(self):
        assert feedback_service.is_developer(12345) is False


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceCreateFeedback:
    """Тесты для create_feedback."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=11111)

    @pytest.mark.asyncio
    async def test_create_feedback_text_only(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="Тестовое сообщение"
        )
        assert feedback is not None
        assert feedback.message == "Тестовое сообщение"
        assert feedback.is_voice is False
        assert feedback.is_photo is False
        assert feedback.status == 'new'

    @pytest.mark.asyncio
    async def test_create_feedback_with_voice(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="Голосовое",
            voice_data=b'fake_voice_data'
        )
        assert feedback.is_voice is True
        assert feedback.message == "Голосовое"

    @pytest.mark.asyncio
    async def test_create_feedback_with_photo_data(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="С фото",
            photo_data=b'fake_photo_data'
        )
        assert feedback.is_photo is True

    @pytest.mark.asyncio
    async def test_create_feedback_with_photo_file_id(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="С photo_file_id",
            photo_file_id="AgACAgIA..."
        )
        assert feedback.is_photo is True
        assert feedback.photo_file_id == "AgACAgIA..."

    @pytest.mark.asyncio
    async def test_create_feedback_empty_message_text_with_voice(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="",
            voice_data=b'voice'
        )
        assert feedback.message == "Голосовое сообщение"

    @pytest.mark.asyncio
    async def test_create_feedback_empty_message_text_with_photo(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text="",
            photo_data=b'photo'
        )
        assert feedback.message == "Фото"

    @pytest.mark.asyncio
    async def test_create_feedback_empty_everything(self, test_user):
        feedback = await feedback_service.create_feedback(
            user=test_user,
            message_text=""
        )
        assert feedback.message == "Сообщение"


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceGetUnprocessed:
    """Тесты для get_unprocessed_feedbacks."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=22222)

    @pytest.mark.asyncio
    async def test_get_unprocessed_returns_new(self, test_user):
        await _create_feedback(user=test_user, message="Новое 1", status='new')
        await _create_feedback(user=test_user, message="Новое 2", status='new')
        feedbacks = await feedback_service.get_unprocessed_feedbacks()
        assert len(feedbacks) == 2
        for fb in feedbacks:
            assert fb.status == 'new'

    @pytest.mark.asyncio
    async def test_get_unprocessed_excludes_processed(self, test_user):
        await _create_feedback(user=test_user, message="Новое", status='new')
        await _create_feedback(user=test_user, message="Обработанное", status='processed')
        await _create_feedback(user=test_user, message="Ответ отправлен", status='replied')
        feedbacks = await feedback_service.get_unprocessed_feedbacks()
        assert len(feedbacks) == 1
        assert feedbacks[0].message == "Новое"

    @pytest.mark.asyncio
    async def test_get_unprocessed_empty(self, test_user):
        feedbacks = await feedback_service.get_unprocessed_feedbacks()
        assert len(feedbacks) == 0

    @pytest.mark.asyncio
    async def test_get_unprocessed_respects_limit(self, test_user):
        for i in range(10):
            await _create_feedback(user=test_user, message=f"Новое {i}", status='new')
        feedbacks = await feedback_service.get_unprocessed_feedbacks(limit=3)
        assert len(feedbacks) <= 3


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceGetById:
    """Тесты для get_feedback_by_id."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=33333)

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_exists(self, test_user):
        fb = await _create_feedback(user=test_user, message="Тест", status='new')
        result = await feedback_service.get_feedback_by_id(fb.id)
        assert result is not None
        assert result.message == "Тест"

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_not_exists(self):
        result = await feedback_service.get_feedback_by_id(99999)
        assert result is None


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceFormatForDisplay:
    """Тесты для format_feedback_for_display."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=44444, username="testuser")

    @pytest.mark.asyncio
    async def test_format_feedback_basic(self, test_user):
        fb = await _create_feedback(
            user=test_user, message="Короткое сообщение", status='new',
            is_voice=False, is_photo=False
        )
        data = await feedback_service.format_feedback_for_display(fb)
        assert isinstance(data, FeedbackDisplayData)
        assert data.feedback_id == fb.id
        assert data.username == "testuser"
        assert data.is_voice is False
        assert data.is_photo is False
        assert data.message_preview == "Короткое сообщение"

    @pytest.mark.asyncio
    async def test_format_feedback_long_message_truncated(self, test_user):
        long_msg = "A" * 300
        fb = await _create_feedback(user=test_user, message=long_msg, status='new')
        data = await feedback_service.format_feedback_for_display(fb, include_full_message=False)
        assert len(data.message_preview) <= 203  # 200 + "..."
        assert data.message_preview.endswith("...")

    @pytest.mark.asyncio
    async def test_format_feedback_long_message_full(self, test_user):
        long_msg = "A" * 300
        fb = await _create_feedback(user=test_user, message=long_msg, status='new')
        data = await feedback_service.format_feedback_for_display(fb, include_full_message=True)
        assert data.full_message == long_msg
        assert data.message_preview == long_msg

    @pytest.mark.asyncio
    async def test_format_feedback_voice(self, test_user):
        fb = await _create_feedback(user=test_user, message="Голосовое", status='new', is_voice=True)
        data = await feedback_service.format_feedback_for_display(fb)
        assert data.is_voice is True

    @pytest.mark.asyncio
    async def test_format_feedback_with_photo(self, test_user):
        fb = await _create_feedback(
            user=test_user, message="С фото", status='new', is_photo=True,
            photo_file_id="AgACAgIA..."
        )
        data = await feedback_service.format_feedback_for_display(fb)
        assert data.is_photo is True
        assert data.photo_file_id == "AgACAgIA..."

    @pytest.mark.asyncio
    async def test_format_feedback_no_username(self):
        user = await sync_to_async(baker.make)(User, telegram_id=44445, username="")
        fb = await _create_feedback(user=user, message="Тест", status='new')
        data = await feedback_service.format_feedback_for_display(fb)
        assert data.username == f"user_{user.telegram_id}"


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceBuildDescription:
    """Тесты для build_description_text."""

    def test_build_description_text_voice(self):
        data = FeedbackDisplayData(
            feedback_id=1, username="testuser", created_at="01.01.2026 12:00",
            is_voice=True, is_photo=False, message_preview="Тест",
            full_message="Тест", photo_file_id=None, status='new'
        )
        text = feedback_service.build_description_text(data)
        assert "📬 Обращение #1" in text
        assert "Тип: голосовое" in text
        assert "Фото: нет" in text

    def test_build_description_text_photo(self):
        data = FeedbackDisplayData(
            feedback_id=2, username="photouser", created_at="02.01.2026 15:00",
            is_voice=False, is_photo=True, message_preview="Фото сообщение",
            full_message="Фото сообщение", photo_file_id="abc123", status='new'
        )
        text = feedback_service.build_description_text(data)
        assert "📬 Обращение #2" in text
        assert "Тип: текстовое" in text
        assert "Фото: да" in text


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceReplyToFeedback:
    """Тесты для reply_to_feedback."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=55555)

    @pytest.mark.asyncio
    async def test_reply_to_feedback_success(self, test_user):
        fb = await _create_feedback(user=test_user, message="Нужна помощь", status='new')
        result = await feedback_service.reply_to_feedback(fb.id, "Мы помогли!")
        assert result is not None
        assert result.status == 'replied'
        assert result.admin_response == "Мы помогли!"

    @pytest.mark.asyncio
    async def test_reply_to_feedback_not_exists(self):
        result = await feedback_service.reply_to_feedback(99999, "Ответ")
        assert result is None


@pytest.mark.django_db(transaction=True)
class TestFeedbackServiceCanReply:
    """Тесты для can_reply_to_feedback."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=66666)

    @pytest.mark.asyncio
    async def test_can_reply_status_new(self, test_user):
        fb = await _create_feedback(user=test_user, message="Новое", status='new')
        can, feedback = await feedback_service.can_reply_to_feedback(fb.id)
        assert can is True
        assert feedback is not None

    @pytest.mark.asyncio
    async def test_can_reply_status_processed(self, test_user):
        fb = await _create_feedback(user=test_user, message="Обработанное", status='processed')
        can, feedback = await feedback_service.can_reply_to_feedback(fb.id)
        assert can is True

    @pytest.mark.asyncio
    async def test_can_reply_status_replied(self, test_user):
        fb = await _create_feedback(user=test_user, message="Отвечено", status='replied')
        can, feedback = await feedback_service.can_reply_to_feedback(fb.id)
        assert can is False

    @pytest.mark.asyncio
    async def test_can_reply_not_exists(self):
        can, feedback = await feedback_service.can_reply_to_feedback(99999)
        assert can is False
        assert feedback is None


class TestFeedbackServiceValidatePhotoSize:
    """Тесты для validate_photo_size."""

    def test_valid_photo_size(self):
        assert feedback_service.validate_photo_size(10 * 1024 * 1024) is True

    def test_max_photo_size(self):
        assert feedback_service.validate_photo_size(20 * 1024 * 1024) is True

    def test_photo_too_large(self):
        assert feedback_service.validate_photo_size(21 * 1024 * 1024) is False

    def test_zero_size(self):
        assert feedback_service.validate_photo_size(0) is True


@pytest.mark.django_db(transaction=True)
class TestFeedbackServicePagination:
    """Тесты для get_feedbacks_with_pagination."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=77777)

    @pytest.mark.asyncio
    async def test_pagination_first_page(self, test_user):
        for i in range(5):
            await _create_feedback(user=test_user, message=f"Сообщение {i}", status='new')
        result = await feedback_service.get_feedbacks_with_pagination(page=1, page_size=2)
        assert result['page'] == 1
        assert result['page_size'] == 2
        assert len(result['feedbacks']) == 2
        assert result['has_next'] is True
        assert result['has_prev'] is False

    @pytest.mark.asyncio
    async def test_pagination_last_page(self, test_user):
        for i in range(5):
            await _create_feedback(user=test_user, message=f"Сообщение {i}", status='new')
        result = await feedback_service.get_feedbacks_with_pagination(page=3, page_size=2)
        assert len(result['feedbacks']) == 1
        assert result['has_next'] is False
        assert result['has_prev'] is True

    @pytest.mark.asyncio
    async def test_pagination_empty(self, test_user):
        result = await feedback_service.get_feedbacks_with_pagination(page=1, page_size=5)
        assert result['total'] == 0
        assert result['feedbacks'] == []
        assert result['has_next'] is False
        assert result['has_prev'] is False
