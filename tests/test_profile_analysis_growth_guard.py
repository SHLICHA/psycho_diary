"""
Тесты anti-growth guard и replace-политики list-полей в UserProfileAnalysisService.

Охватываемые сценарии:
- Pre-cleanup: parse-fail => no-op, поле не меняется
- Pre-cleanup: валидный ответ => replace (не union), размер <= исходного
- Основной апдейт: рост per-field отклоняется
- Основной апдейт: total-рост отклоняет все list-обновления
- _normalize_cleaned_items: сохраняет added_at из оригинала
"""

import re
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from diary.services.user_profile_analysis_service import UserProfileAnalysisService


def make_item(value: str, weight: float = 0.5, frequency: int = 1, added_at: str = "2026-01-01") -> Dict[str, Any]:
    return {
        "value": value,
        "weight": weight,
        "frequency": frequency,
        "added_at": added_at,
        "last_seen": "2026-04-01",
        "is_stale": False,
    }


class TestPrecleanupNoopOnFailure:
    """Pre-cleanup: при любой ошибке поле остается без изменений."""

    @pytest.mark.asyncio
    async def test_parse_fail_returns_original_items(self):
        service = UserProfileAnalysisService()
        original = [make_item("триггер 1"), make_item("триггер 2")]

        failed_api_result = {"success": False, "error": "response_parse_failed", "result": {}, "raw_response": ""}

        semaphore = __import__("asyncio").Semaphore(1)
        mock_api = AsyncMock(return_value=failed_api_result)

        with patch("diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse", mock_api):
            result = await service._precleanup_single_field(
                field_name="triggers",
                raw_items=original,
                language="ru",
                semaphore=semaphore,
            )

        assert result["used_fallback"] is True
        assert result["updated"] is False
        # Значения поля не изменились
        result_values = {i["value"] for i in result["cleaned_items"]}
        original_values = {i["value"] for i in original}
        assert result_values == original_values

    @pytest.mark.asyncio
    async def test_valid_cleanup_does_not_grow_field(self):
        service = UserProfileAnalysisService()
        original = [make_item(f"элемент {i}") for i in range(10)]

        # AI возвращает очищенный список — меньше исходного
        ai_cleaned = [
            {"value": f"элемент {i}", "weight": 0.5, "frequency": 1, "is_stale": False}
            for i in range(6)
        ]
        api_result = {"success": True, "result": {"cleaned_items": ai_cleaned}, "raw_response": "..."}

        semaphore = __import__("asyncio").Semaphore(1)
        mock_api = AsyncMock(return_value=api_result)

        with patch("diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse", mock_api):
            result = await service._precleanup_single_field(
                field_name="practical_patterns",
                raw_items=original,
                language="ru",
                semaphore=semaphore,
            )

        assert result["used_fallback"] is False
        assert len(result["cleaned_items"]) <= len(original)

    @pytest.mark.asyncio
    async def test_cleanup_growth_rejected(self):
        """Если AI вернул больше элементов, чем пришло — no-op."""
        service = UserProfileAnalysisService()
        original = [make_item("a"), make_item("b")]

        # AI возвращает больше элементов — должно быть отклонено
        ai_cleaned = [
            {"value": v, "weight": 0.5, "frequency": 1, "is_stale": False}
            for v in ["a", "b", "c", "d"]
        ]
        api_result = {"success": True, "result": {"cleaned_items": ai_cleaned}, "raw_response": "..."}

        semaphore = __import__("asyncio").Semaphore(1)
        mock_api = AsyncMock(return_value=api_result)

        with patch("diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse", mock_api):
            result = await service._precleanup_single_field(
                field_name="practical_patterns",
                raw_items=original,
                language="ru",
                semaphore=semaphore,
            )

        assert result["used_fallback"] is True
        assert "cleanup_growth_rejected" in (result["error"] or "")
        # Поле не выросло
        assert len(result["cleaned_items"]) <= len(original)


class TestNormalizeCleanedItems:
    """_normalize_cleaned_items: сохраняет added_at из оригинала."""

    def test_preserves_added_at_for_matching_value(self):
        service = UserProfileAnalysisService()
        original = [make_item("стресс", added_at="2025-06-15")]
        ai_items = [{"value": "стресс", "weight": 0.7, "frequency": 2, "is_stale": False}]

        result = service._normalize_cleaned_items(ai_items, original)
        assert result[0]["added_at"] == "2025-06-15"

    def test_sets_today_for_new_items(self):
        service = UserProfileAnalysisService()
        original = [make_item("старый")]
        ai_items = [{"value": "совсем новый", "weight": 0.5, "frequency": 1, "is_stale": False}]

        today = timezone.now().date().isoformat()
        result = service._normalize_cleaned_items(ai_items, original)
        assert result[0]["added_at"] == today

    def test_sets_last_seen_to_today(self):
        service = UserProfileAnalysisService()
        original = [make_item("x", added_at="2025-01-01")]
        ai_items = [{"value": "x", "weight": 0.5, "frequency": 1, "last_seen": "2025-01-01", "is_stale": False}]

        today = timezone.now().date().isoformat()
        result = service._normalize_cleaned_items(ai_items, original)
        assert result[0]["last_seen"] == today


class TestMainUpdateGrowthGuard:
    """Основной апдейт list-полей: per-field и total-guard."""

    def _make_user(self, field_items: Dict[str, List]) -> MagicMock:
        user = MagicMock()
        user.telegram_id = 999
        user.language = "ru"
        list_fields = ["life_facts", "hobbies", "core_values", "triggers", "strengths",
                       "areas_for_growth", "practical_patterns", "aspirations"]
        for f in list_fields:
            setattr(user, f, field_items.get(f, []))
        user.personality_traits = {}
        user.personality_insights = {}
        user.personality_description = ""
        return user

    @pytest.mark.asyncio
    async def test_per_field_growth_blocked(self):
        """Per-field guard: если после replace поле выросло — обновление отклоняется."""
        service = UserProfileAnalysisService()
        # 2 элемента в triggers
        user = self._make_user({"triggers": [make_item("a"), make_item("b")]})

        # AI присылает 5 элементов — рост, должно быть отклонено
        parsed_result = {
            "triggers": [
                {"value": v, "weight": 0.5, "frequency": 1, "is_stale": False}
                for v in ["a", "b", "c", "d", "e"]
            ]
        }

        result = await service._update_user_profile_from_analysis(user, parsed_result)
        assert result is True
        # triggers не должен быть обновлён
        assert user.triggers == [make_item("a"), make_item("b")]

    @pytest.mark.asyncio
    async def test_empty_ai_list_not_applied(self):
        """Если AI вернул пустой список для поля — не применять."""
        service = UserProfileAnalysisService()
        user = self._make_user({"practical_patterns": [make_item("бег"), make_item("чтение")]})
        parsed_result = {"practical_patterns": []}

        result = await service._update_user_profile_from_analysis(user, parsed_result)
        assert result is True
        assert user.practical_patterns == [make_item("бег"), make_item("чтение")]

    @pytest.mark.asyncio
    async def test_valid_replace_applies(self):
        """При сжатии (меньше элементов) guard пропускает — ошибки не должно быть до сохранения."""
        service = UserProfileAnalysisService()
        user = self._make_user({"strengths": [make_item(f"навык {i}") for i in range(5)]})

        # AI возвращает 3 — сжатие допустимо
        parsed_result = {
            "strengths": [
                {"value": f"навык {i}", "weight": 0.6, "frequency": 2, "is_stale": False}
                for i in range(3)
            ]
        }

        save_called = []

        async def fake_save():
            save_called.append(True)

        # Мокируем sync_to_async чтобы сохранение вернуло dummy-корутину
        with patch("diary.services.user_profile_analysis_service.sync_to_async", side_effect=lambda fn: lambda: fake_save()):
            result = await service._update_user_profile_from_analysis(user, parsed_result)

        assert result is True
        assert save_called  # save был вызван
