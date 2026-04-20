"""
Тесты для admin_service.py
"""
import pytest
from datetime import timedelta
from model_bakery import baker
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.test import override_settings

from core.services.admin_service import admin_service
from diary.models import DiaryEntry, AnalysisRating, PsychoAnalysis
from users.models import User, Payment

# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


@pytest.mark.django_db
class TestAdminService:
    """Тесты для AdminService."""

    # === is_admin ===

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_admin_correct_id(self):
        """Тест: правильный ID администратора."""
        assert admin_service.is_admin(12345) is True

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_admin_wrong_id(self):
        """Тест: неправильный ID."""
        assert admin_service.is_admin(99999) is False

    @override_settings(DEVELOPER_CHAT_ID='')
    def test_is_admin_no_setting(self):
        """Тест: настройка DEVELOPER_CHAT_ID не установлена."""
        assert admin_service.is_admin(12345) is False

    @override_settings(DEVELOPER_CHAT_ID='invalid')
    def test_is_admin_invalid_setting(self):
        """Тест: некорректное значение DEVELOPER_CHAT_ID."""
        assert admin_service.is_admin(12345) is False

    # === get_users_for_broadcast ===

    @pytest.fixture
    def active_user_with_notifications(self):
        return baker.make(User, telegram_id=100, is_blocked=False, deletion_status='active',
                         deleted_at=None, notifications_enabled=True, language='ru')

    @pytest.fixture
    def active_user_without_notifications(self):
        return baker.make(User, telegram_id=101, is_blocked=False, deletion_status='active',
                         deleted_at=None, notifications_enabled=False, language='en')

    @pytest.fixture
    def blocked_user(self):
        return baker.make(User, telegram_id=102, is_blocked=True, deletion_status='active',
                         deleted_at=None, notifications_enabled=True, language='ru')

    @pytest.mark.asyncio
    async def test_get_users_for_broadcast_important(self, active_user_with_notifications,
                                                      active_user_without_notifications, blocked_user):
        """Тест: важная рассылка - все активные пользователи."""
        users = await admin_service.get_users_for_broadcast(is_important=True)

        user_ids = [u[0] for u in users]
        assert 100 in user_ids  # С уведомлениями
        assert 101 in user_ids  # Без уведомлений
        assert 102 not in user_ids  # Заблокирован

    @pytest.mark.asyncio
    async def test_get_users_for_broadcast_regular(self, active_user_with_notifications,
                                                    active_user_without_notifications, blocked_user):
        """Тест: обычная рассылка - только с уведомлениями."""
        users = await admin_service.get_users_for_broadcast(is_important=False)

        user_ids = [u[0] for u in users]
        assert 100 in user_ids  # С уведомлениями
        assert 101 not in user_ids  # Без уведомлений
        assert 102 not in user_ids  # Заблокирован

    # === get_admin_stats ===

    @pytest.fixture
    def stats_users(self):
        """Создает пользователей для статистики."""
        return [
            baker.make(User, telegram_id=200, is_blocked=False, deletion_status='active',
                      deleted_at=None, token_balance=100, auto_analysis_enabled=True,
                      is_onboarding_completed=True, language='ru'),
            baker.make(User, telegram_id=201, is_blocked=False, deletion_status='active',
                      deleted_at=None, token_balance=0, auto_analysis_enabled=False,
                      is_onboarding_completed=False, language='en'),
            baker.make(User, telegram_id=202, is_blocked=True, deletion_status='active',
                      deleted_at=None, token_balance=50, language='ru'),
        ]

    @pytest.mark.asyncio
    async def test_get_admin_stats_basic(self, stats_users):
        """Тест: базовая статистика пользователей."""
        stats = await admin_service.get_admin_stats()

        assert stats['total_users'] >= 2  # Не считаем superuser
        assert stats['active_users'] >= 2
        assert stats['blocked_users'] >= 1
        assert 'top_timezones' in stats
        assert 'rating_distribution' in stats

    @pytest.fixture
    def diary_entries_for_stats(self, stats_users):
        """Создает записи для статистики."""
        entries = []
        for i, user in enumerate(stats_users[:2]):  # Только активные
            entry = baker.make(DiaryEntry, user=user, text=f"Запись {i}", language='ru', word_count=2)
            entries.append(entry)
        return entries

    @pytest.mark.asyncio
    async def test_get_admin_stats_with_entries(self, stats_users, diary_entries_for_stats):
        """Тест: статистика с записями."""
        stats = await admin_service.get_admin_stats()

        assert stats['users_with_entries'] >= 2
        assert stats['total_entries'] >= 2
        assert stats['real_entries'] >= 2

    @pytest.fixture
    def ratings_for_stats(self, diary_entries_for_stats):
        """Создает рейтинги для статистики."""
        ratings = []
        for i, entry in enumerate(diary_entries_for_stats):
            analysis = baker.make(
                PsychoAnalysis,
                entry=entry,
                mood_score=7,
                comment="Хорошо",
                recommendation="1",
                processing_time=1.0,
                analysis_text="Тест"
            )
            rating = baker.make(AnalysisRating, user=entry.user, analysis=analysis, rating=i+1)
            ratings.append(rating)
        return ratings

    @pytest.mark.asyncio
    async def test_get_admin_stats_with_ratings(self, stats_users, diary_entries_for_stats, ratings_for_stats):
        """Тест: статистика с рейтингами."""
        from diary.models import PsychoAnalysis

        stats = await admin_service.get_admin_stats()

        assert stats['total_ratings'] >= 2
        assert 1 in stats['rating_distribution']
        assert 2 in stats['rating_distribution']

    @pytest.fixture
    def payments_for_stats(self, stats_users):
        """Создает платежи для статистики."""
        payments = []
        for user in stats_users[:1]:
            payment = baker.make(
                Payment,
                user=user,
                status='succeeded',
                payment_type='subscription_month',
                amount_rub=199,
                yookassa_payment_id=f"test_{user.telegram_id}"
            )
            payments.append(payment)
        return payments

    @pytest.mark.asyncio
    async def test_get_admin_stats_with_payments(self, stats_users, payments_for_stats):
        """Тест: статистика с платежами."""
        stats = await admin_service.get_admin_stats()

        assert stats['subscriptions_30_count'] >= 1
        assert stats['subscriptions_year_count'] >= 0


@pytest.mark.django_db
class TestAdminServiceIntegration:
    """Интеграционные тесты для admin_service."""

    @pytest.mark.asyncio
    async def test_full_stats_flow(self):
        """Тест: полный поток сбора статистики."""
        # Создаем пользователей
        user1 = await sync_to_async(baker.make)(
            User,
            telegram_id=300,
            is_blocked=False,
            deletion_status='active',
            deleted_at=None,
            token_balance=100,
            language='ru',
            timezone='Europe/Moscow'
        )
        user2 = await sync_to_async(baker.make)(
            User,
            telegram_id=301,
            is_blocked=False,
            deletion_status='active',
            deleted_at=None,
            token_balance=0,
            language='en',
            timezone='UTC'
        )

        # Создаем записи
        await sync_to_async(baker.make)(DiaryEntry, user=user1, text="Запись", language='ru', word_count=2)

        # Получаем статистику
        stats = await admin_service.get_admin_stats()

        # Проверяем
        assert stats['total_users'] >= 2
        assert stats['active_users'] >= 2
        assert stats['users_with_entries'] >= 1
        assert len(stats['top_timezones']) > 0
