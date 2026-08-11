"""Runtime coordinator для MAX transport (polling/webhook mode)."""

from __future__ import annotations

import asyncio
import logging
import time

from django.conf import settings
from core.services.monitoring_service import monitoring_service

from .client import MaxClient
from .inbound import aprocess_max_update
from .preflight import collect_preflight_errors, normalize_transport_mode


logger = logging.getLogger(__name__)


class MaxTransportCoordinator:
    """Координирует runtime поведение MAX в режимах polling/webhook."""

    def __init__(self, client: MaxClient | None = None):
        self.client = client or MaxClient(
            api_token=settings.MAX_BOT_TOKEN,
            base_url=settings.MAX_API_BASE_URL,
            timeout_seconds=settings.MAX_API_TIMEOUT_SECONDS,
            rate_limit_rps=getattr(settings, 'MAX_RATE_LIMIT_RPS', 10),
            rate_limit_burst=getattr(settings, 'MAX_RATE_LIMIT_BURST', 50),
            max_message_length=getattr(settings, 'MAX_MESSAGE_MAX_LENGTH', 3500),
        )

    async def _record_runtime_metric(
        self,
        event_name: str,
        success: bool,
        duration_ms: float,
        metadata: dict | None = None,
    ) -> None:
        await monitoring_service.record_transport_event(
            transport_event=event_name,
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

    async def _run_webhook_mode(self, stop_event: asyncio.Event) -> None:
        webhook_url = (getattr(settings, 'MAX_WEBHOOK_URL', '') or '').strip()
        if webhook_url:
            started_at = time.perf_counter()
            try:
                registered = await self.client.register_webhook(
                    webhook_url=webhook_url,
                    update_types=['message_created', 'bot_started', 'message_callback'],
                )
                duration_ms = (time.perf_counter() - started_at) * 1000
                await self._record_runtime_metric(
                    event_name='max_runtime_webhook_register',
                    success=bool(registered),
                    duration_ms=duration_ms,
                    metadata={
                        'mode': 'webhook',
                        'outcome': 'success' if registered else 'failure',
                    },
                )
            except Exception as exc:
                duration_ms = (time.perf_counter() - started_at) * 1000
                await self._record_runtime_metric(
                    event_name='max_runtime_webhook_register',
                    success=False,
                    duration_ms=duration_ms,
                    metadata={
                        'mode': 'webhook',
                        'outcome': 'failure',
                        'error_type': type(exc).__name__,
                    },
                )
                raise
        else:
            logger.info('[MAX Runtime] webhook mode active without registration (MAX_WEBHOOK_URL empty)')

        await stop_event.wait()

    async def _run_polling_mode(self, stop_event: asyncio.Event) -> None:
        marker: str | None = None
        polling_timeout = int(getattr(settings, 'MAX_POLLING_TIMEOUT_SECONDS', 30))
        # После пустого long-poll сразу начинаем следующий — sleep только на ошибках.
        idle_sleep = float(getattr(settings, 'MAX_POLLING_IDLE_SLEEP_SECONDS', 0))
        error_sleep = max(idle_sleep, 1.0)
        update_types = ['message_created', 'bot_started', 'message_callback']

        while not stop_event.is_set():
            iteration_started_at = time.perf_counter()
            try:
                updates, marker = await self.client.fetch_updates(
                    marker=marker,
                    timeout_seconds=polling_timeout,
                    update_types=update_types,
                )
                if not updates:
                    if idle_sleep > 0:
                        await asyncio.sleep(idle_sleep)
                    continue

                # Не делаем notification-only fast-ack здесь: он «сжигает» callback_id,
                # а клиент MAX снимает ошибку на кнопке только при /answers с message.
                # Передаём прогретый client в dispatcher — первый send_func ответит через /answers.
                for update in updates:
                    if stop_event.is_set():
                        break
                    # Не трогаем MaxStateStore здесь: set_state перезаписывает весь ключ
                    # и стирает fsm_state онбординга → error_generic на кнопке «Далее».
                    await aprocess_max_update(
                        update,
                        max_client=self.client,
                        callback_already_answered=False,
                    )

                duration_ms = (time.perf_counter() - iteration_started_at) * 1000
                await self._record_runtime_metric(
                    event_name='max_runtime_polling_iteration',
                    success=True,
                    duration_ms=duration_ms,
                    metadata={'mode': 'polling', 'updates_count': len(updates)},
                )
            except Exception as exc:
                duration_ms = (time.perf_counter() - iteration_started_at) * 1000
                await self._record_runtime_metric(
                    event_name='max_runtime_polling_iteration',
                    success=False,
                    duration_ms=duration_ms,
                    metadata={'mode': 'polling', 'error_type': type(exc).__name__},
                )
                logger.error('[MAX Runtime] polling iteration failed: %s', exc, exc_info=True)
                await asyncio.sleep(error_sleep)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Точка входа runtime coordinator с graceful shutdown."""
        if not getattr(settings, 'MAX_TRANSPORT_ENABLED', False):
            logger.info('[MAX Runtime] skipped: MAX_TRANSPORT_ENABLED=false')
            return

        mode = normalize_transport_mode(getattr(settings, 'MAX_TRANSPORT_MODE', 'polling'))
        logger.info('[MAX Runtime] starting in mode=%s', mode)

        preflight_errors = collect_preflight_errors(settings, mode=mode)
        if preflight_errors:
            logger.error('[MAX Runtime] preflight failed: %s', '; '.join(preflight_errors))
            await self._record_runtime_metric(
                event_name='max_runtime_preflight',
                success=False,
                duration_ms=0,
                metadata={'mode': mode, 'errors': preflight_errors},
            )
            return

        await self._record_runtime_metric(
            event_name='max_runtime_preflight',
            success=True,
            duration_ms=0,
            metadata={'mode': mode},
        )

        try:
            if mode == 'webhook':
                await self._run_webhook_mode(stop_event)
            else:
                await self._run_polling_mode(stop_event)
        finally:
            await self.client.close()
            logger.info('[MAX Runtime] stopped')
