"""Presenter utilities for diary handler flows."""

from typing import Any, Dict

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from messages import get_message, get_button_text
from bot.keyboards import get_single_button_keyboard


def build_analysis_result_payload(service_result: Dict[str, Any]) -> Dict[str, Any]:
    """Build normalized successful payload for handler analysis processing."""
    analysis_obj = service_result["analysis"]
    return {
        "success": True,
        "result": {
            "mood_score": analysis_obj.mood_score,
            "comment": analysis_obj.comment,
            "recommendation": analysis_obj.recommendation,
            "analysis": service_result.get("formatted_message_ai", ""),
        },
    }


def build_analysis_error_payload(message: str, error_type: str = "service_error") -> Dict[str, Any]:
    """Build normalized failed payload for handler analysis processing."""
    return {
        "success": False,
        "error": error_type,
        "message": message,
    }


def build_new_entry_validation_failure_view(result: Dict[str, Any], language: str) -> Dict[str, Any]:
    """Build message and retry keyboard for new-entry validation failure."""
    formatted_message_ai = result.get("formatted_message_ai", "")
    validation_comment_ai = result.get("validation_comment_ai", "")

    if formatted_message_ai:
        final_message_text = formatted_message_ai
    else:
        final_message_text = "❌ <b>Ваша запись не прошла валидацию</b>\n"
        if validation_comment_ai:
            final_message_text += f"💬 <i>{validation_comment_ai}</i>\n"
        else:
            final_message_text += f"📝 <i>{get_message('entry_not_validated_generic', language)}</i>\n"
        final_message_text += "🔍 Пожалуйста, попробуйте снова."

    retry_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("btn_retry_entry", language), callback_data="new_entry")],
        [InlineKeyboardButton(text=get_button_text("btn_main_menu", language), callback_data="main_menu")],
    ])

    return {
        "text": final_message_text,
        "reply_markup": retry_keyboard,
    }


def build_new_entry_success_text(
    analysis_obj: Any,
    suggested_task_obj: Any,
    streak_bonus_info: Dict[str, Any],
    language: str,
) -> str:
    """Build final success text for new entry flow."""
    task_info = ""
    if suggested_task_obj:
        preview = (
            suggested_task_obj.description[:150] + "..."
            if len(suggested_task_obj.description) > 150
            else suggested_task_obj.description
        )
        task_info = get_message(
            "task_assigned",
            language,
            title=suggested_task_obj.title,
            description=preview,
        )

    final_text = get_message(
        "entry_saved",
        language,
        score=analysis_obj.mood_score,
        mood=get_message(f"mood_{analysis_obj.mood_score}", language),
        comment=analysis_obj.comment,
        recommendation=analysis_obj.recommendation,
    ) + task_info

    if streak_bonus_info.get("awarded"):
        rewards = streak_bonus_info.get("rewards", [])
        reward_strings = [
            get_message("streak_bonus_earned", language, days=streak, tokens=tokens)
            for streak, tokens in rewards
        ]
        final_text += f"\n{' '.join(reward_strings)}"

    return final_text


def build_clarification_questions_view(clarification_questions: Any, language: str) -> Dict[str, Any]:
    """Build clarification prompt text and keyboard for handler output."""
    questions_text = "\n".join([
        f"{index + 1}. {question}" for index, question in enumerate(clarification_questions or [])
    ])
    return {
        "text": f"{get_message('clarification_needed', language)}\n{questions_text}",
        "reply_markup": get_single_button_keyboard(language, "main_menu", "btn_cancel"),
    }


async def build_entry_saved_view(
    entry: Any,
    analysis: Any,
    user: Any,
    language: str,
    task: Any = None,
) -> Dict[str, Any]:
    """
    Build text + keyboard for already-persisted entry analysis.

    Domain persistence must happen in services/use cases; presenter only formats output.
    """
    from diary.services.diary_display_service import diary_display_service

    if analysis is not None:
        text = get_message(
            "entry_saved",
            language,
            score=analysis.mood_score,
            mood=get_message(f"mood_{analysis.mood_score}", language),
            comment=analysis.comment,
            recommendation=analysis.recommendation,
        )
        reply_markup = await diary_display_service.build_entry_result_keyboard(
            entry, analysis, user, language, task=task
        )
    else:
        text = get_message("error_processing", language)
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("btn_back", language), callback_data="main_menu")]
            ]
        )

    return {
        "text": text,
        "reply_markup": reply_markup,
        "should_clear_state": True,
    }


async def build_new_entry_outcome_view(
    response: Any,
    user: Any,
    language: str,
) -> Dict[str, Any]:
    """
    Build handler view for new-entry use-case outcome (failure / success / clarification).

    Returns text, keyboard, and FSM orchestration hints for transport handlers.
    """
    from diary.services.diary_display_service import diary_display_service

    success = getattr(response, "success", None)
    if success is None and isinstance(response, dict):
        success = response.get("success")

    if not success:
        result = getattr(response, "data", None) or {}
        if isinstance(response, dict):
            result = response.get("data") or result
        failure_view = build_new_entry_validation_failure_view(result or {}, language)
        return {
            "mode": "failure",
            "text": failure_view["text"],
            "reply_markup": failure_view["reply_markup"],
            "fsm_action": "clear",
        }

    result = getattr(response, "data", None) or {}
    if isinstance(response, dict):
        result = response.get("data") or result

    diary_entry = result["entry"]
    analysis_obj = result["analysis"]
    needs_clarification = result.get("needs_clarification")
    clarification_questions = result.get("clarification_questions") or []
    suggested_task_obj = result.get("suggested_task")
    streak_bonus_info = result.get("streak_bonus_info") or {}

    if needs_clarification and clarification_questions:
        clarification_view = build_clarification_questions_view(clarification_questions, language)
        return {
            "mode": "clarification",
            "text": clarification_view["text"],
            "reply_markup": clarification_view["reply_markup"],
            "fsm_action": "clarification",
            "clarifying_entry_id": diary_entry.id,
            "clarification_questions": clarification_questions,
        }

    final_text = build_new_entry_success_text(
        analysis_obj=analysis_obj,
        suggested_task_obj=suggested_task_obj,
        streak_bonus_info=streak_bonus_info,
        language=language,
    )
    reply_markup = await diary_display_service.build_entry_result_keyboard(
        diary_entry, analysis_obj, user, language, task=suggested_task_obj
    )
    return {
        "mode": "success",
        "text": final_text,
        "reply_markup": reply_markup,
        "fsm_action": "clear",
        "should_trigger_prompt": True,
        "entry": diary_entry,
    }


def build_delete_entire_day_confirm_view(target_date: Any, language: str) -> Dict[str, Any]:
    """Build confirmation prompt for deleting all entries on a day."""
    confirm_msg = get_message("confirm_delete_entire_day_prompt", language).format(
        date=target_date.strftime("%d.%m.%Y")
    )
    confirm_buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text("btn_confirm_delete_day", language),
                callback_data=f"confirm_delete_entire_day:{target_date.isoformat()}",
            ),
            InlineKeyboardButton(
                text=get_button_text("btn_cancel", language),
                callback_data="archive",
            ),
        ]
    ]
    return {
        "text": confirm_msg,
        "keyboard": InlineKeyboardMarkup(inline_keyboard=confirm_buttons),
    }
