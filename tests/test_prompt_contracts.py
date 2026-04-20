"""Тесты контрактов промптов (placeholders и рендер)."""

import pytest

from prompts.get_prompt import get_prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_full_day_analysis_renders_with_compressed_profile(language):
    prompt = get_prompt(
        key="full_day_analysis",
        language=language,
        compressed_psych_profile_json="{}",
        all_entries_combined_text="entry text",
        entry_analyses="[]",
        daily_mood_scores="[5, 6]",
        completed_tasks="[]",
    )

    assert isinstance(prompt, str)
    assert "{compressed_psych_profile_json}" not in prompt
    assert "{all_entries_combined_text}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_task_effect_analysis_renders_with_changed_format_payload(language):
    prompt = get_prompt(
        key="task_effect_analysis",
        language=language,
        compressed_psych_profile_json="{}",
        personal_fields_json="{}",
        assigned_date="2026-01-01",
        assigned_day_text="assigned day",
        assigned_day_analysis="{}",
        completion_date="2026-01-02",
        completion_day_text="completion day",
        completion_day_analysis="{}",
        task_title="Task",
        task_description="Description",
        task_complexity="medium",
        completion_text="Did it",
        feelings_text="Felt better",
    )

    assert isinstance(prompt, str)
    assert "{personal_fields_json}" not in prompt
    assert "{compressed_psych_profile_json}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_clarification_analysis_renders_with_changed_format_payload(language):
    prompt = get_prompt(
        key="clarification_analysis",
        language=language,
        original_text="Original",
        clarification_questions="Q1",
        clarification_answers="A1",
        ai_state_data="{}",
        compressed_psych_profile_json="{}",
        personal_fields_json="{}",
    )

    assert isinstance(prompt, str)
    assert "{compressed_psych_profile_json}" not in prompt
    assert "{personal_fields_json}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_comment_analysis_renders_with_changed_format_payload(language):
    prompt = get_prompt(
        key="comment_analysis",
        language=language,
        original_text="Original",
        previous_comment="Prev comment",
        previous_recommendation="Prev rec",
        previous_analysis="Prev analysis",
        user_comment="User comment",
        compressed_psych_profile_json="{}",
        personal_fields_json="{}",
        clarification_questions="None",
        clarification_answers="None",
    )

    assert isinstance(prompt, str)
    assert "{compressed_psych_profile_json}" not in prompt
    assert "{personal_fields_json}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_incremental_day_analysis_lite_v2_renders_with_weighted_user_fields(language):
    prompt = get_prompt(
        key="incremental_day_analysis_lite_v2",
        language=language,
        user_plan="free",
        first_name="User",
        awareness_level=5,
        entries_count=12,
        compressed_psych_profile_json="{}",
        day_context_summary_json="{}",
        user_personality_traits='[{"value":"resilience","weight":0.9,"frequency":5}]',
        user_triggers='[{"value":"criticism","weight":0.8,"frequency":4}]',
        user_strengths='[{"value":"self-reflection","weight":0.85,"frequency":6}]',
        new_entry_text="Entry",
        new_entry_creation_time_local="19.04.2026 10:00",
        ai_state_data="{}",
    )

    assert isinstance(prompt, str)
    assert "{user_personality_traits}" not in prompt
    assert "{user_triggers}" not in prompt
    assert "{user_strengths}" not in prompt
    assert "{compressed_psych_profile_json}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_user_profile_analysis_renders_with_unified_profile_payload(language):
    prompt = get_prompt(
        key="user_profile_analysis",
        language=language,
        personality_description="Current description",
        compressed_psych_profile_json="{}",
        personal_fields_json="{}",
        recent_weekly_analyses="[]",
    )

    assert isinstance(prompt, str)
    assert "{personality_description}" not in prompt
    assert "{compressed_psych_profile_json}" not in prompt
    assert "{personal_fields_json}" not in prompt
    assert "selected_task_completion_analyses" not in prompt
    assert "TaskCompletionAnalysis" not in prompt
    assert "completed_tasks" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_profile_change_analysis_renders_with_unified_snapshots_payload(language):
    prompt = get_prompt(
        key="profile_change_analysis",
        language=language,
        current_personality_description="Current description",
        current_compressed_psych_profile_json="{}",
        current_personal_fields_json="{}",
        historical_snapshots_json="[]",
        num_snapshots=3,
    )

    assert isinstance(prompt, str)
    assert "{current_personality_description}" not in prompt
    assert "{current_compressed_psych_profile_json}" not in prompt
    assert "{current_personal_fields_json}" not in prompt
    assert "{historical_snapshots_json}" not in prompt


@pytest.mark.parametrize("language", ["ru", "en"])
def test_profile_field_cleanup_renders_with_block_payload(language):
    prompt = get_prompt(
        key="profile_field_cleanup",
        language=language,
        field_name="life_facts",
        field_items_json='[{"value":"foo","weight":0.7,"frequency":2,"is_stale":false}]',
    )

    assert isinstance(prompt, str)
    assert "{field_name}" not in prompt
    assert "{field_items_json}" not in prompt
