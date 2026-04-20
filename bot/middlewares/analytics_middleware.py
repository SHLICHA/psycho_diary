"""Middleware for lightweight analytics hooks."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware

from core.services.monitoring_service import monitoring_service


class AnalyticsMiddleware(BaseMiddleware):
    """Records lightweight transport-level metrics for incoming events."""

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        started_at = time.perf_counter()
        event_type = type(event).__name__
        handler_name = getattr(handler, "__name__", "unknown_handler")
        success = False
        metadata = {
            "event_type": event_type,
            "handler": handler_name,
        }

        try:
            result = await handler(event, data)
            success = True
            return result
        except Exception as exc:
            metadata["error"] = exc.__class__.__name__
            raise
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            await monitoring_service.record_transport_event(
                transport_event=f"telegram.{event_type}",
                success=success,
                duration_ms=duration_ms,
                metadata=metadata,
            )
