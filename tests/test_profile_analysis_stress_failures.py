from datetime import date, timedelta

import pytest
from asgiref.sync import async_to_sync
from model_bakery import baker

from diary.models import WeeklyAnalysis
from diary.services.user_profile_analysis_service import user_profile_analysis_service
from diary.services.user_profile_change_analysis_service import (
    user_profile_change_analysis_service,
)
from users.models import User, UserProfileHistory


pytestmark = pytest.mark.django_db


def _build_large_compressed_profile(seed: str = "x"):
    return {
        "psych_summary": ("summary-" + seed + " ") * 300,
        "core_patterns": [f"pattern-{i}-{seed}" for i in range(40)],
        "emotional_style": ("style-" + seed + " ") * 120,
        "main_triggers": [f"trigger-{i}-{seed}" for i in range(40)],
        "coping_style": ("coping-" + seed + " ") * 120,
        "current_focus": ("focus-" + seed + " ") * 120,
    }


def _make_weekly_analysis(user: User, week_start_date: date):
    return baker.make(
        WeeklyAnalysis,
        user=user,
        week_start_date=week_start_date,
        summary_text="weekly summary",
        progress_insights={"mood": "stable"},
        consolidated_user_profile={},
        statistics={"entries": 1},
        comparison_with_previous={},
        api_response={},
        profile_changes_summary={"initial": True},
    )


class TestProfileAnalysisStressFailures:
    def test_user_profile_analysis_order_precleanup_then_snapshot_then_main_context(self, mocker):
        user = baker.make(
            User,
            telegram_id=910000,
            username="order_user",
            language="ru",
            personality_description="before",
        )

        call_order = []

        async def _precleanup(_user):
            call_order.append("precleanup")
            return {}

        async def _snapshot(_user):
            call_order.append("snapshot")
            return None

        async def _gather(_user):
            call_order.append("gather")
            return {
                "has_data": True,
                "personality_description": "before",
                "compressed_psych_profile_json": "{}",
                "personal_fields_json": "{}",
                "recent_weekly_analyses": "[]",
            }

        mocker.patch.object(
            user_profile_analysis_service,
            "_run_profile_field_precleanup",
            new=mocker.AsyncMock(side_effect=_precleanup),
        )
        mocker.patch.object(
            user_profile_analysis_service,
            "_create_profile_snapshot",
            new=mocker.AsyncMock(side_effect=_snapshot),
        )
        mocker.patch.object(
            user_profile_analysis_service,
            "_gather_user_context",
            new=mocker.AsyncMock(side_effect=_gather),
        )
        mocker.patch(
            "diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=mocker.AsyncMock(return_value={"success": True, "result": {"personality_description": "after"}}),
        )
        mocker.patch.object(
            user_profile_analysis_service,
            "_update_user_profile_from_analysis",
            new=mocker.AsyncMock(return_value=True),
        )

        result = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)(user)

        assert result["success"] is True
        assert call_order[:3] == ["precleanup", "snapshot", "gather"]

    def test_create_profile_snapshot_removes_technical_keys(self):
        user = baker.make(
            User,
            telegram_id=910006,
            username="snapshot_cleanup_user",
            personality_description="  clean me  ",
            personality_traits={"эмпатия": 0.8, "_debug": 1.0, "metadata": 0.3},
            personality_insights={"coping": "works", "_meta": "x", "documentation": "tech"},
            life_facts=[
                {
                    "value": "Живу в Москве",
                    "weight": 0.7,
                    "frequency": 2,
                    "is_stale": False,
                    "added_at": "2026-01-01T00:00:00+00:00",
                    "last_seen": "2026-01-02T00:00:00+00:00",
                    "source": "system",
                }
            ],
        )

        snapshot = async_to_sync(user_profile_analysis_service._create_profile_snapshot)(user)
        snapshot.refresh_from_db()

        assert snapshot is not None
        assert snapshot.personality_description == "clean me"
        assert set(snapshot.personality_traits.keys()) == {"эмпатия"}
        assert set(snapshot.personality_insights.keys()) == {"coping"}
        assert isinstance(snapshot.life_facts, list)
        assert len(snapshot.life_facts) == 1
        assert set(snapshot.life_facts[0].keys()) == {"value", "weight", "frequency", "is_stale"}

    def test_profile_precleanup_partial_failure_uses_fallback(self, mocker):
        user = baker.make(
            User,
            telegram_id=910007,
            username="precleanup_fallback_user",
            language="ru",
            life_facts=[
                {"value": "Факт 1", "weight": 0.7, "frequency": 2, "is_stale": False},
                {"value": "факт 1", "weight": 0.8, "frequency": 3, "is_stale": False},
            ],
            hobbies=[
                {"value": "Бег", "weight": 0.6, "frequency": 1, "is_stale": False},
                {"value": "бег", "weight": 0.9, "frequency": 5, "is_stale": False},
            ],
        )

        mocker.patch(
            "diary.services.user_profile_analysis_service.local_profile_cluster_service.cluster_items",
            side_effect=[
                {
                    "field_name": "life_facts",
                    "cleaned_items": [
                        {"value": "Факт 1", "weight": 0.95, "frequency": 7, "is_stale": False}
                    ],
                    "used_fallback": False,
                    "error": None,
                    "strategy": "sentence_transformers",
                },
                RuntimeError("local model unavailable"),
            ],
        )

        mocker.patch(
            "diary.services.user_profile_analysis_service.get_prompt",
            side_effect=lambda key, language, **kwargs: f"{key}:{kwargs.get('field_name', '')}",
        )

        async def _api_side_effect(prompt, **kwargs):
            if prompt.endswith("hobbies"):
                return {"success": False, "error": "timeout"}
            return {
                "success": True,
                "result": {
                    "cleaned_items": [
                        {"value": "Факт 1", "weight": 0.95, "frequency": 7, "is_stale": False}
                    ]
                },
            }

        mocker.patch(
            "diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=mocker.AsyncMock(side_effect=_api_side_effect),
        )

        stats = async_to_sync(user_profile_analysis_service._run_profile_field_precleanup)(user)
        user.refresh_from_db()

        assert stats["processed_fields"] == 2
        assert "hobbies" in stats["fallback_fields"]
        assert "life_facts" in stats["updated_fields"]
        assert isinstance(user.hobbies, list)
        assert len(user.hobbies) == 2

    def test_gather_change_context_uses_latest_n_snapshots_with_oversized_payload(self):
        user = baker.make(
            User,
            telegram_id=910001,
            username="stress_change_user",
            personality_description="base profile",
            compressed_psych_profile=_build_large_compressed_profile("current"),
            life_facts=[{"value": f"fact-{i}", "weight": 0.5, "frequency": 1} for i in range(80)],
            triggers=[{"value": f"trigger-{i}", "weight": 0.5, "frequency": 1} for i in range(80)],
            strengths=[{"value": f"strength-{i}", "weight": 0.5, "frequency": 1} for i in range(80)],
        )

        # Create 5 snapshots and force deterministic created_at ordering.
        created = []
        for idx in range(5):
            snapshot = baker.make(
                UserProfileHistory,
                user=user,
                awareness_level=idx + 1,
                personality_traits={"trait": idx},
                life_facts=[f"life-{idx}"],
                hobbies=[f"hobby-{idx}"],
                core_values=[f"value-{idx}"],
                triggers=[f"trig-{idx}"],
                strengths=[f"strong-{idx}"],
                areas_for_growth=[f"growth-{idx}"],
                personality_insights={"insight": idx},
                practical_patterns=[f"habit-{idx}", f"skill-{idx}"],
                aspirations=[f"asp-{idx}"],
                personality_description={"text": f"snapshot-{idx}"},
            )
            forced_ts = date(2026, 1, 1) + timedelta(days=idx)
            UserProfileHistory.objects.filter(pk=snapshot.pk).update(
                created_at=f"{forced_ts.isoformat()}T00:00:00+00:00"
            )
            snapshot.refresh_from_db()
            created.append(snapshot)

        context = async_to_sync(user_profile_change_analysis_service._gather_change_context)(
            user,
            3,
        )

        assert len(context["historical_snapshots"]) == 3
        assert context["historical_snapshots_str"].startswith("[")
        assert context["current_compressed_psych_profile_json"].startswith("{")

        snapshot_dates = [item["created_at"] for item in context["historical_snapshots"]]
        assert snapshot_dates == sorted(snapshot_dates)
        assert all("T" not in dt for dt in snapshot_dates)

    def test_profile_change_analysis_handles_context_overflow_and_clears_summary(self, mocker):
        user = baker.make(
            User,
            telegram_id=910002,
            username="overflow_user",
            personality_description="current profile",
            compressed_psych_profile=_build_large_compressed_profile("overflow"),
        )
        weekly = _make_weekly_analysis(user, date(2026, 4, 14))
        baker.make(
            UserProfileHistory,
            user=user,
            awareness_level=5,
            personality_traits={"trait": 1},
            life_facts=["life"],
            hobbies=["hobby"],
            core_values=["value"],
            triggers=["trigger"],
            strengths=["strength"],
            areas_for_growth=["growth"],
            personality_insights={"insight": "v"},
            practical_patterns=["habit", "skill"],
            aspirations=["aspiration"],
            personality_description={"text": "snapshot"},
        )

        mocker.patch(
            "diary.services.user_profile_change_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=mocker.AsyncMock(
                return_value={
                    "success": False,
                    "error": "context_length_exceeded",
                    "message": "prompt too long",
                }
            ),
        )

        result = async_to_sync(user_profile_change_analysis_service.perform_profile_change_analysis)(
            user,
            weekly,
            3,
        )

        weekly.refresh_from_db()
        assert result["success"] is False
        assert result["error"] == "context_length_exceeded"
        assert weekly.profile_changes_summary == {}

    def test_profile_change_analysis_handles_parse_failure_and_returns_error(self, mocker):
        user = baker.make(
            User,
            telegram_id=910003,
            username="parse_fail_user",
            personality_description="current profile",
            compressed_psych_profile=_build_large_compressed_profile("parse"),
        )
        weekly = _make_weekly_analysis(user, date(2026, 4, 21))
        baker.make(
            UserProfileHistory,
            user=user,
            awareness_level=5,
            personality_traits={"trait": 1},
            life_facts=["life"],
            hobbies=["hobby"],
            core_values=["value"],
            triggers=["trigger"],
            strengths=["strength"],
            areas_for_growth=["growth"],
            personality_insights={"insight": "v"},
            practical_patterns=["habit", "skill"],
            aspirations=["aspiration"],
            personality_description={"text": "snapshot"},
        )

        mocker.patch(
            "diary.services.user_profile_change_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=mocker.AsyncMock(
                return_value={
                    "success": False,
                    "error": "response_parse_failed",
                    "message": "json parse failed",
                }
            ),
        )

        result = async_to_sync(user_profile_change_analysis_service.perform_profile_change_analysis)(
            user,
            weekly,
            3,
        )

        assert result["success"] is False
        assert result["error"] == "response_parse_failed"

    def test_user_profile_analysis_timeout_on_oversized_context(self, mocker):
        user = baker.make(
            User,
            telegram_id=910004,
            username="timeout_user",
            language="ru",
            personality_description="before timeout",
            compressed_psych_profile=_build_large_compressed_profile("timeout"),
            life_facts=[{"value": f"fact-{i}", "weight": 0.6, "frequency": 2} for i in range(120)],
            triggers=[{"value": f"trigger-{i}", "weight": 0.6, "frequency": 2} for i in range(120)],
            strengths=[{"value": f"strength-{i}", "weight": 0.6, "frequency": 2} for i in range(120)],
        )
        _make_weekly_analysis(user, date.today() - timedelta(days=7))

        mocker.patch(
            "diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=mocker.AsyncMock(
                return_value={
                    "success": False,
                    "error": "timeout",
                    "message": "timeout exceeded",
                }
            ),
        )

        result = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)(user)

        user.refresh_from_db()
        assert result["success"] is False
        assert result["error"] == "timeout"
        assert user.personality_description == "before timeout"

    def test_user_profile_analysis_runs_field_precleanup_before_main_prompt(self, mocker):
        user = baker.make(
            User,
            telegram_id=910005,
            username="precleanup_user",
            language="ru",
            personality_description="before",
            compressed_psych_profile=_build_large_compressed_profile("precleanup"),
            life_facts=[
                {"value": "Живу в Москве", "weight": 0.6, "frequency": 2, "is_stale": False},
                {"value": "живу  в  москве", "weight": 0.8, "frequency": 3, "is_stale": False},
            ],
        )
        _make_weekly_analysis(user, date.today() - timedelta(days=7))

        mocker.patch(
            "diary.services.user_profile_analysis_service.local_profile_cluster_service.cluster_items",
            return_value={
                "field_name": "life_facts",
                "cleaned_items": [
                    {
                        "value": "Живу в Москве",
                        "weight": 0.9,
                        "frequency": 5,
                        "is_stale": False,
                    }
                ],
                "used_fallback": False,
                "error": None,
                "strategy": "sentence_transformers",
            },
        )

        async_mock = mocker.AsyncMock(
            return_value={
                "success": True,
                "result": {
                    "personality_description": "after",
                },
            }
        )
        mocker.patch(
            "diary.services.user_profile_analysis_service.deepseek_api_service.send_prompt_and_parse",
            new=async_mock,
        )

        result = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)(user)

        user.refresh_from_db()
        assert result["success"] is True
        assert async_mock.await_count == 1
        assert isinstance(user.life_facts, list)
        assert len(user.life_facts) == 1
        assert user.life_facts[0]["value"] == "Живу в Москве"

    def test_precleanup_preserves_frequency_and_history_dates(self, mocker):
        user = baker.make(
            User,
            telegram_id=910008,
            username="history_preserve_user",
            language="ru",
            life_facts=[
                {
                    "value": "Живу в Москве",
                    "weight": 0.6,
                    "frequency": 2,
                    "added_at": "2026-03-01T08:00:00+00:00",
                    "last_seen": "2026-04-10T10:00:00+00:00",
                    "is_stale": False,
                },
                {
                    "value": "живу в москве",
                    "weight": 0.8,
                    "frequency": 3,
                    "added_at": "2026-03-05T08:00:00+00:00",
                    "last_seen": "2026-04-20T12:00:00+00:00",
                    "is_stale": False,
                },
            ],
        )

        mocker.patch(
            "diary.services.user_profile_analysis_service.local_profile_cluster_service.cluster_items",
            return_value={
                "field_name": "life_facts",
                "cleaned_items": [
                    {
                        "value": "Живу в Москве",
                        "weight": 0.8,
                        "frequency": 5,
                        "added_at": "2026-03-01T08:00:00+00:00",
                        "last_seen": "2026-04-20T12:00:00+00:00",
                        "is_stale": False,
                    }
                ],
                "used_fallback": False,
                "error": None,
                "strategy": "sentence_transformers",
            },
        )

        stats = async_to_sync(user_profile_analysis_service._run_profile_field_precleanup)(user)
        user.refresh_from_db()

        assert "life_facts" in stats["updated_fields"]
        assert len(user.life_facts) == 1
        assert user.life_facts[0]["frequency"] == 5
        assert user.life_facts[0]["added_at"].startswith("2026-03-01T08:00:00")
        assert user.life_facts[0]["last_seen"].startswith("2026-04-20T12:00:00")
