"""Shared transport contracts for normalized input/output payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedActor:
    """Unified actor identity across transport adapters."""

    platform: str
    user_id: str
    chat_id: str | None = None
    language: str = 'ru'


@dataclass(slots=True)
class NormalizedInput:
    """Transport-agnostic inbound command envelope."""

    actor: NormalizedActor
    command: str
    payload: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedButton:
    """Normalized callback button used by all transport adapters."""

    text: str
    callback_data: str


@dataclass(slots=True)
class NormalizedAttachment:
    """Normalized outgoing attachment descriptor."""

    kind: str
    value: str


@dataclass(slots=True)
class StateTransition:
    """Optional state transition for output pipelines."""

    state: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedOutput:
    """Transport-agnostic outbound response envelope."""

    text: str
    buttons: list[list[NormalizedButton]] = field(default_factory=list)
    attachments: list[NormalizedAttachment] = field(default_factory=list)
    state_transition: StateTransition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
