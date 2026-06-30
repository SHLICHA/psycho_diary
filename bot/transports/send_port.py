"""Unified send port interface for outbound transport delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import NormalizedOutput


@dataclass(slots=True)
class SendResult:
    success: bool
    reason: str


class SendPort(Protocol):
    async def send(self, *, platform: str, recipient_id: int, output: NormalizedOutput) -> SendResult:
        ...
