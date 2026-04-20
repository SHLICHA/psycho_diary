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
