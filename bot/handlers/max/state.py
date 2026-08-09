"""FSM-like state helpers for MAX users (cache-backed)."""

from __future__ import annotations

from typing import Any, Optional

from bot.states.onboarding_states import OnboardingStates
from bot.states.settings_states import SettingsStates
from bot.transports.max.state_store import MaxStateStore

_store = MaxStateStore()

# Canonical state strings (aiogram State.state)
STATE_AGREEMENT_1 = OnboardingStates.waiting_for_agreement_1.state
STATE_AGREEMENT_2 = OnboardingStates.waiting_for_agreement_2.state
STATE_TIMEZONE = OnboardingStates.waiting_for_timezone_confirmation.state
STATE_FIRST_ENTRY = OnboardingStates.waiting_for_first_entry.state
STATE_CITY_INPUT = SettingsStates.waiting_for_city_input.state
STATE_LANGUAGE = SettingsStates.waiting_for_language_choice.state


def get_raw_state(max_id: int) -> dict:
    return _store.get_state(max_id) or {}


def get_fsm_state(max_id: int) -> Optional[str]:
    raw = get_raw_state(max_id)
    value = raw.get('fsm_state')
    return str(value) if value else None


def set_fsm_state(max_id: int, fsm_state: Any, **extra) -> None:
    """Persist FSM state string (State | str | None)."""
    raw = get_raw_state(max_id)
    if fsm_state is None:
        raw.pop('fsm_state', None)
    else:
        raw['fsm_state'] = getattr(fsm_state, 'state', None) or str(fsm_state)
    for key, value in extra.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    _store.set_state(max_id, raw)


def update_state_data(max_id: int, **extra) -> None:
    raw = get_raw_state(max_id)
    raw.update({k: v for k, v in extra.items() if v is not None})
    _store.set_state(max_id, raw)


def clear_fsm_state(max_id: int) -> None:
    _store.clear_state(max_id)


def matches_state(max_id: int, expected) -> bool:
    current = get_fsm_state(max_id)
    expected_str = getattr(expected, 'state', None) or str(expected)
    return current == expected_str
