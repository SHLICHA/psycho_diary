"""Unified monitoring service for application-level metrics."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MonitoringService:
    """In-memory monitoring counters used as a safe baseline implementation."""

    def __init__(self) -> None:
        self._counters: Dict[str, Any] = {
            "use_cases": {},
            "ai_calls": {},
            "transport": {},
            "totals": {
                "success": 0,
                "failure": 0,
            },
        }

    def _record_bucket_event(
        self,
        bucket_name: str,
        event_name: str,
        success: bool,
        duration_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        bucket = self._counters[bucket_name].setdefault(
            event_name,
            {
                "count": 0,
                "success": 0,
                "failure": 0,
                "last_duration_ms": 0.0,
                "last_metadata": {},
            },
        )
        bucket["count"] += 1
        if success:
            bucket["success"] += 1
            self._counters["totals"]["success"] += 1
        else:
            bucket["failure"] += 1
            self._counters["totals"]["failure"] += 1

        bucket["last_duration_ms"] = float(duration_ms)
        bucket["last_metadata"] = dict(metadata or {})

    async def record_use_case_event(
        self,
        use_case: str,
        success: bool,
        duration_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a use-case execution metric in memory."""
        try:
            self._record_bucket_event(
                bucket_name="use_cases",
                event_name=use_case,
                success=success,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("[monitoring_service] Failed to record use-case metric: %s", exc, exc_info=True)

    async def record_ai_call_event(
        self,
        flow: str,
        success: bool,
        duration_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record AI provider call metrics in memory."""
        try:
            self._record_bucket_event(
                bucket_name="ai_calls",
                event_name=flow,
                success=success,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("[monitoring_service] Failed to record ai-call metric: %s", exc, exc_info=True)

    async def record_transport_event(
        self,
        transport_event: str,
        success: bool,
        duration_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record transport-level event metrics (middleware layer)."""
        try:
            self._record_bucket_event(
                bucket_name="transport",
                event_name=transport_event,
                success=success,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("[monitoring_service] Failed to record transport metric: %s", exc, exc_info=True)

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a deep copy of in-memory counters."""
        return deepcopy(self._counters)

    def reset(self) -> None:
        """Reset all in-memory counters (primarily for tests)."""
        self._counters = {
            "use_cases": {},
            "ai_calls": {},
            "transport": {},
            "totals": {
                "success": 0,
                "failure": 0,
            },
        }


monitoring_service = MonitoringService()
