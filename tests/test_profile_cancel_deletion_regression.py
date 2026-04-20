"""Regression tests for account deletion cancel flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import profile as profile_handlers


@pytest.mark.asyncio
async def test_cancel_account_deletion_returns_to_main_menu(monkeypatch):
    """Cancel deletion should safely return user to main menu without fallback errors."""
    callback = SimpleNamespace(
        message=SimpleNamespace(
            answer=AsyncMock(),
            text="old text",
        )
    )
    user = SimpleNamespace(telegram_id=399096554)
    state = SimpleNamespace()

    edit_calls = []

    async def fake_safe_edit_message_text(message, text, reply_markup=None):
        edit_calls.append({"text": text, "reply_markup": reply_markup})
        return True

    menu_data_spy = AsyncMock(
        return_value={
            "message_text": "MAIN MENU",
            "keyboard": object(),
        }
    )

    clear_state_spy = AsyncMock()
    answer_callback_spy = AsyncMock()

    monkeypatch.setattr(
        profile_handlers,
        "safe_edit_message_text",
        fake_safe_edit_message_text,
    )
    monkeypatch.setattr(profile_handlers, "build_main_menu_data", menu_data_spy)
    monkeypatch.setattr(profile_handlers.state_manager, "clear_state", clear_state_spy)
    monkeypatch.setattr(profile_handlers, "safe_answer_callback", answer_callback_spy)
    monkeypatch.setattr(profile_handlers.asyncio, "sleep", AsyncMock())

    # Bypass decorator side effects (activity logging) and test handler logic directly.
    await profile_handlers.cancel_account_deletion.__wrapped__(
        callback=callback,
        user=user,
        language="ru",
        state=state,
    )

    menu_data_spy.assert_awaited_once_with(user=user, language="ru")
    clear_state_spy.assert_awaited_once_with(state)
    answer_callback_spy.assert_awaited_once()

    assert len(edit_calls) == 2
    assert edit_calls[0]["text"]
    assert edit_calls[1]["text"] == "MAIN MENU"
    callback.message.answer.assert_not_awaited()
