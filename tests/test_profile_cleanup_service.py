"""Тесты для TTL-очистки профиля пользователя."""

from asgiref.sync import async_to_sync
from django.utils import timezone
from model_bakery import baker
import pytest

from diary.services.profile_cleanup_service import profile_cleanup_service
from users.models import User


@pytest.mark.django_db
class TestProfileCleanupService:
    def test_removes_old_low_frequency_items_and_rebuilds_compressed_profile(self, mocker):
        user = baker.make(
            User,
            telegram_id=300001,
            triggers=[
                {
                    "value": "старый триггер",
                    "weight": 0.2,
                    "frequency": 1,
                    "added_at": "2025-12-01T00:00:00Z",
                    "last_seen": "2026-01-01T00:00:00Z",
                    "is_stale": True,
                },
                {
                    "value": "актуальный триггер",
                    "weight": 0.7,
                    "frequency": 4,
                    "added_at": "2026-04-10T00:00:00Z",
                    "last_seen": timezone.now().isoformat(),
                    "is_stale": False,
                },
            ],
        )
        mock_rebuild = mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.generate_for_user',
            return_value={
                'psych_summary': 'summary',
                'core_patterns': [],
                'emotional_style': 'style',
                'main_triggers': ['актуальный триггер'],
                'coping_style': 'coping',
                'current_focus': 'focus',
            },
        )
        mock_save = mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.save_for_user_async',
            new=mocker.AsyncMock(return_value=True),
        )

        result = async_to_sync(profile_cleanup_service.cleanup_user_profile)(user)

        user.refresh_from_db()
        assert result['success'] is True
        assert result['changed'] is True
        assert result['changed_fields_count'] == 1
        assert result['inspected_items'] == 2
        assert result['remaining_items'] == 1
        assert result['removed_items'] == 1
        assert result['compressed_profile_action'] == 'rebuilt'
        assert user.triggers == [
            {
                "value": "актуальный триггер",
                "weight": 0.7,
                "frequency": 4,
                "added_at": "2026-04-10T00:00:00Z",
                "last_seen": user.triggers[0]['last_seen'],
                "is_stale": False,
            }
        ]
        mock_rebuild.assert_called_once_with(user)
        mock_save.assert_awaited_once()

    def test_keeps_high_frequency_stale_items(self, mocker):
        user = baker.make(
            User,
            telegram_id=300002,
            strengths=[
                {
                    "value": "стойкость",
                    "weight": 0.9,
                    "frequency": 5,
                    "added_at": "2025-12-01T00:00:00Z",
                    "last_seen": "2026-01-01T00:00:00Z",
                    "is_stale": False,
                }
            ],
        )
        mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.generate_for_user',
            return_value={
                'psych_summary': 'summary',
                'core_patterns': [],
                'emotional_style': 'style',
                'main_triggers': [],
                'coping_style': 'coping',
                'current_focus': 'focus',
            },
        )
        mock_save = mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.save_for_user_async',
            new=mocker.AsyncMock(return_value=True),
        )

        result = async_to_sync(profile_cleanup_service.cleanup_user_profile)(user)

        user.refresh_from_db()
        assert result['success'] is True
        assert result['changed'] is True
        assert result['stale_items'] == 1
        assert result['removed_items'] == 0
        assert result['compressed_profile_action'] == 'rebuilt'
        assert user.strengths[0]['value'] == 'стойкость'
        assert user.strengths[0]['is_stale'] is True
        mock_save.assert_awaited_once()

    def test_skips_rebuild_when_no_changes(self, mocker):
        user = baker.make(
            User,
            telegram_id=300003,
            practical_patterns=[
                {
                    "value": "дневник",
                    "weight": 0.8,
                    "frequency": 3,
                    "added_at": "2026-04-01T00:00:00Z",
                    "last_seen": timezone.now().isoformat(),
                    "is_stale": False,
                }
            ],
        )
        mock_generate = mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.generate_for_user'
        )

        result = async_to_sync(profile_cleanup_service.cleanup_user_profile)(user)

        assert result['success'] is True
        assert result['changed'] is False
        assert result['compressed_profile_rebuilt'] is False
        assert result['compressed_profile_action'] == 'skipped'
        mock_generate.assert_not_called()

    def test_clears_compressed_profile_when_generation_returns_none(self, mocker):
        user = baker.make(
            User,
            telegram_id=300004,
            compressed_psych_profile={'psych_summary': 'old'},
            triggers=[
                {
                    "value": "разовый триггер",
                    "weight": 0.2,
                    "frequency": 1,
                    "added_at": "2025-12-01T00:00:00Z",
                    "last_seen": "2026-01-01T00:00:00Z",
                    "is_stale": True,
                }
            ],
        )
        mocker.patch(
            'diary.services.profile_cleanup_service.compressed_profile_service.generate_for_user',
            return_value=None,
        )

        result = async_to_sync(profile_cleanup_service.cleanup_user_profile)(user)

        user.refresh_from_db()
        assert result['success'] is True
        assert result['compressed_profile_rebuilt'] is True
        assert result['compressed_profile_action'] == 'cleared'
        assert user.triggers == []
        assert user.compressed_psych_profile == {}