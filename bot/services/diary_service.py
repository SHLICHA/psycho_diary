"""
Сервис для работы с записями дневника
"""
import pytz
import logging
import time
import json

from asgiref.sync import sync_to_async
from typing import List, Dict, Any, Optional
from datetime import datetime, date, time as dtime
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.core.cache import cache
from typing import Dict, Any, List

from bot.utils.decorators import async_error_handler, database_retry
from bot.utils.api_utils import format_api_error_for_analysis
from bot.utils.diary_utils import check_and_award_streak_bonus
from bot.services.deepseek_api import deepseek_api_service
from bot.services.psycho_analysis_service import psycho_analysis_service
from diary.models import DiaryEntry, PsychoAnalysis, CombinedDiaryEntry, TherapyTask
from diary.services.daily_state_service import (
    get_daily_state,
    get_or_create_daily_state,
    update_daily_state,
    update_daily_state_text_and_count,
    create_daily_state_from_entry
)
from diary.services.task_management_service import assign_task
from users.models import User
from prompts import get_prompt
from diary.services.daily_state_service import daily_state_service
from asgiref.sync import sync_to_async
from messages import get_message
from core.service_response import ServiceResponse
from core.profile_field_utils import (
    build_personal_fields_payload_for_ai,
    normalize_compressed_profile_for_prompt,
)
from core.services.monitoring_service import monitoring_service
from diary.services.compressed_profile_service import compressed_profile_service

logger = logging.getLogger(__name__)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _top_profile_items_for_prompt(items: Any, limit: int) -> List[Dict[str, Any]]:
    """Return top-N weighted items for prompt payload, preferring non-stale and higher weight/frequency."""
    if not isinstance(items, list) or limit <= 0:
        return []

    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        if not value:
            continue
        normalized.append({
            "value": value,
            "weight": _to_float(item.get("weight"), 0.5),
            "frequency": _to_int(item.get("frequency"), 1),
            "is_stale": bool(item.get("is_stale", False)),
        })

    normalized.sort(
        key=lambda x: (
            bool(x.get("is_stale", False)),
            -_to_float(x.get("weight"), 0.0),
            -_to_int(x.get("frequency"), 0),
            x.get("value", ""),
        )
    )
    return normalized[:limit]


def _truncate_text_for_prompt(value: Any, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def _trim_list_for_prompt(values: Any, limit: int) -> List[Any]:
    if not isinstance(values, list) or limit <= 0:
        return []
    return values[:limit]


def _format_entry_datetime_for_prompt(dt, language: str = 'ru') -> str:
    """Возвращает обогащённую строку даты/времени записи: день недели, дата, время, сезон."""
    _seasons_ru = {1: 'зима', 2: 'зима', 3: 'весна', 4: 'весна', 5: 'весна',
                   6: 'лето', 7: 'лето', 8: 'лето', 9: 'осень', 10: 'осень',
                   11: 'осень', 12: 'зима'}
    _seasons_en = {1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
                   6: 'summer', 7: 'summer', 8: 'summer', 9: 'autumn', 10: 'autumn',
                   11: 'autumn', 12: 'winter'}
    _weekdays_ru = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
    try:
        if language == 'ru':
            weekday = _weekdays_ru[dt.weekday()]
            season = _seasons_ru[dt.month]
            return dt.strftime(f'{weekday}, %d.%m.%Y, %H:%M ({season})')
        else:
            season = _seasons_en[dt.month]
            return dt.strftime(f'%A, %B %d %Y, %H:%M ({season})')
    except Exception:
        return dt.strftime('%Y-%m-%d %H:%M')


class DiaryService:
    """Сервис для работы с записями дневника"""

    async def _record_use_case_metric(
        self,
        use_case: str,
        success: bool,
        started_at: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record unified use-case metric without affecting business flow."""
        duration_ms = (time.perf_counter() - started_at) * 1000
        await monitoring_service.record_use_case_event(
            use_case=use_case,
            success=success,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    async def _call_deepseek_with_metrics(
        self,
        flow: str,
        prompt: str,
        language: str,
        metadata: Optional[Dict[str, Any]] = None,
        **api_kwargs: Any,
    ) -> Dict[str, Any]:
        """Call DeepSeek API and record AI-call metrics without altering behavior."""
        started_at = time.perf_counter()
        base_metadata = dict(metadata or {})
        base_metadata["provider"] = "deepseek"

        try:
            result = await deepseek_api_service.send_prompt_and_parse(
                prompt,
                language,
                **api_kwargs,
            )
        except Exception as exc:
            await monitoring_service.record_ai_call_event(
                flow=flow,
                success=False,
                duration_ms=(time.perf_counter() - started_at) * 1000,
                metadata={
                    **base_metadata,
                    "error": exc.__class__.__name__,
                },
            )
            raise

        result_success = bool(result.get("success"))
        event_metadata = dict(base_metadata)
        if not result_success:
            event_metadata["error"] = result.get("error", "unknown")

        await monitoring_service.record_ai_call_event(
            flow=flow,
            success=result_success,
            duration_ms=(time.perf_counter() - started_at) * 1000,
            metadata=event_metadata,
        )
        return result

    async def process_new_entry_use_case(
        self,
        user: User,
        entry_text: str,
        language: str,
        entry_datetime: datetime = None
    ) -> ServiceResponse:
        """
        Универсальный use-case обработки новой записи.

        Возвращает ServiceResponse, чтобы один и тот же контракт можно было
        переиспользовать из Telegram handler и будущего API слоя.
        Базовая бизнес-логика пока остается в process_new_entry_logic.
        """
        started_at = time.perf_counter()
        success = False
        response: ServiceResponse
        try:
            result = await self.process_new_entry_logic(
                user=user,
                entry_text=entry_text,
                language=language,
                entry_datetime=entry_datetime,
            )
        except Exception as exc:
            logger.error(
                f"[process_new_entry_use_case] Ошибка обработки записи для {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='entry_processing_exception',
                message=get_message('error_processing', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_new_entry_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'entry_processing_exception'},
            )
            return response

        if result.get('success'):
            success = True
            response = ServiceResponse.ok(
                data=result,
                needs_clarification=bool(result.get('needs_clarification')),
                has_suggested_task=bool(result.get('suggested_task')),
            )
            await self._record_use_case_metric(
                use_case='diary.process_new_entry_use_case',
                success=success,
                started_at=started_at,
            )
            return response

        error_code = 'entry_validation_failed'
        if not result.get('formatted_message_ai') and not result.get('validation_comment_ai'):
            error_code = result.get('error') or 'entry_processing_failed'

        response = ServiceResponse.fail(
            error=error_code,
            message=result.get('validation_comment_ai') or result.get('formatted_message_ai'),
            data=result,
        )
        await self._record_use_case_metric(
            use_case='diary.process_new_entry_use_case',
            success=success,
            started_at=started_at,
            metadata={'error': error_code},
        )
        return response

    async def process_first_onboarding_entry_use_case(
        self,
        user: User,
        entry_text: str,
        language: str,
        entry_datetime: datetime = None
    ) -> ServiceResponse:
        """
        Универсальный use-case обработки первой записи в онбординге.

        Использует существующую бизнес-логику, но возвращает стандартизированный
        ServiceResponse для переиспользования из Telegram и будущего API.
        """
        started_at = time.perf_counter()
        success = False
        response: ServiceResponse
        try:
            result = await self.process_first_onboarding_entry_logic(
                user=user,
                entry_text=entry_text,
                language=language,
                entry_datetime=entry_datetime,
            )
        except Exception as exc:
            logger.error(
                f"[process_first_onboarding_entry_use_case] Ошибка обработки первой записи для {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='onboarding_entry_processing_exception',
                message=get_message('error_processing', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_first_onboarding_entry_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'onboarding_entry_processing_exception'},
            )
            return response

        if result.get('success'):
            success = True
            response = ServiceResponse.ok(
                data=result,
                onboarding_completed=False,
            )
            await self._record_use_case_metric(
                use_case='diary.process_first_onboarding_entry_use_case',
                success=success,
                started_at=started_at,
            )
            return response

        error_code = result.get('error') or 'onboarding_entry_validation_failed'
        response = ServiceResponse.fail(
            error=error_code,
            message=result.get('formatted_message_ai') or get_message('error_processing', language),
            data=result,
        )
        await self._record_use_case_metric(
            use_case='diary.process_first_onboarding_entry_use_case',
            success=success,
            started_at=started_at,
            metadata={'error': error_code},
        )
        return response

    async def process_clarification_answers_use_case(
        self,
        user: User,
        diary_entry: DiaryEntry,
        clarification_answers_dict: Dict[str, str],
        language: str
    ) -> ServiceResponse:
        """
        Универсальный use-case обработки ответов на уточняющие вопросы.
        """
        started_at = time.perf_counter()
        success = False
        response: ServiceResponse
        try:
            result = await self.process_clarification_answers_logic(
                user=user,
                diary_entry=diary_entry,
                clarification_answers_dict=clarification_answers_dict,
                language=language,
            )
        except Exception as exc:
            logger.error(
                f"[process_clarification_answers_use_case] Ошибка для {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='clarification_processing_exception',
                message=get_message('error_processing', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_clarification_answers_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'clarification_processing_exception'},
            )
            return response

        if result.get('success'):
            success = True
            response = ServiceResponse.ok(
                data=result,
                entry_id=getattr(result.get('entry'), 'id', None),
            )
            await self._record_use_case_metric(
                use_case='diary.process_clarification_answers_use_case',
                success=success,
                started_at=started_at,
            )
            return response

        error_code = result.get('error') or 'clarification_processing_failed'
        response = ServiceResponse.fail(
            error=error_code,
            message=result.get('message') or get_message('error_processing', language),
            data=result,
        )
        await self._record_use_case_metric(
            use_case='diary.process_clarification_answers_use_case',
            success=success,
            started_at=started_at,
            metadata={'error': error_code},
        )
        return response

    async def process_user_comment_use_case(
        self,
        user: User,
        diary_entry: DiaryEntry,
        user_comment_text: str,
        language: str
    ) -> ServiceResponse:
        """
        Универсальный use-case обработки комментария пользователя к записи.
        """
        started_at = time.perf_counter()
        success = False
        response: ServiceResponse
        try:
            result = await self.process_user_comment_logic(
                user=user,
                diary_entry=diary_entry,
                user_comment_text=user_comment_text,
                language=language,
            )
        except Exception as exc:
            logger.error(
                f"[process_user_comment_use_case] Ошибка для {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='comment_processing_exception',
                message=get_message('error_processing', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_user_comment_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'comment_processing_exception'},
            )
            return response

        if result.get('success'):
            success = True
            response = ServiceResponse.ok(
                data=result,
                entry_id=getattr(result.get('entry'), 'id', None),
            )
            await self._record_use_case_metric(
                use_case='diary.process_user_comment_use_case',
                success=success,
                started_at=started_at,
            )
            return response

        error_code = result.get('error') or 'comment_processing_failed'
        response = ServiceResponse.fail(
            error=error_code,
            message=result.get('message') or get_message('error_processing', language),
            data=result,
        )
        await self._record_use_case_metric(
            use_case='diary.process_user_comment_use_case',
            success=success,
            started_at=started_at,
            metadata={'error': error_code},
        )
        return response

    async def process_entry_edit_use_case(
        self,
        user: User,
        entry_id: int,
        new_text: str,
        language: str,
        target_date_iso: Optional[str] = None,
    ) -> ServiceResponse:
        """Универсальный use-case редактирования записи и подготовки payload отображения дня."""
        started_at = time.perf_counter()
        success = False

        try:
            updated = await self.update_entry_text(entry_id, user, new_text)
            if not updated:
                response = ServiceResponse.fail(
                    error='entry_update_failed',
                    message=get_message('error_processing', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_entry_edit_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'entry_update_failed', 'entry_id': entry_id},
                )
                return response

            entry = await self.get_user_entry_by_id(user, entry_id)
            if not entry:
                response = ServiceResponse.fail(
                    error='entry_not_found_after_update',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_entry_edit_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'entry_not_found_after_update', 'entry_id': entry_id},
                )
                return response

            if target_date_iso:
                try:
                    target_date = date.fromisoformat(target_date_iso)
                except ValueError:
                    response = ServiceResponse.fail(
                        error='invalid_target_date',
                        message=get_message('error_generic', language),
                    )
                    await self._record_use_case_metric(
                        use_case='diary.process_entry_edit_use_case',
                        success=success,
                        started_at=started_at,
                        metadata={'error': 'invalid_target_date', 'entry_id': entry_id},
                    )
                    return response
            else:
                target_date = await entry.aentry_date()

            from diary.services.diary_display_service import diary_display_service

            day_view = await diary_display_service.build_day_entries_view(user, target_date, language)
            if not day_view.get('success'):
                response = ServiceResponse.fail(
                    error='day_view_build_failed',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_entry_edit_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'day_view_build_failed', 'entry_id': entry_id},
                )
                return response

            success = True
            response = ServiceResponse.ok(
                data={'day_view': day_view, 'target_date': target_date},
                entry_id=entry_id,
            )
            await self._record_use_case_metric(
                use_case='diary.process_entry_edit_use_case',
                success=success,
                started_at=started_at,
                metadata={'entry_id': entry_id},
            )
            return response
        except Exception as exc:
            logger.error(
                f"[process_entry_edit_use_case] Ошибка редактирования записи {entry_id} пользователя {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='entry_edit_exception',
                message=get_message('error_processing', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_entry_edit_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'entry_edit_exception', 'entry_id': entry_id},
            )
            return response

    async def process_delete_specific_entry_use_case(
        self,
        user: User,
        entry_id: int,
        language: str,
        target_date_iso: str,
    ) -> ServiceResponse:
        """Универсальный use-case подтверждения удаления записи и подготовки payload отображения дня."""
        started_at = time.perf_counter()
        success = False

        try:
            try:
                target_date = date.fromisoformat(target_date_iso)
            except ValueError:
                response = ServiceResponse.fail(
                    error='invalid_target_date',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_delete_specific_entry_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'invalid_target_date', 'entry_id': entry_id},
                )
                return response

            deleted = await self.delete_entry_and_update_combined(entry_id, user)
            alert_message = (
                get_message('entry_deleted_success', language)
                if deleted
                else get_message('error_processing', language)
            )

            from diary.services.diary_display_service import diary_display_service

            day_view = await diary_display_service.build_day_entries_view(user, target_date, language)
            if not day_view.get('success'):
                response = ServiceResponse.fail(
                    error='day_view_build_failed',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_delete_specific_entry_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'day_view_build_failed', 'entry_id': entry_id},
                )
                return response

            success = True
            response = ServiceResponse.ok(
                data={'day_view': day_view, 'alert_message': alert_message, 'deleted': deleted},
                entry_id=entry_id,
            )
            await self._record_use_case_metric(
                use_case='diary.process_delete_specific_entry_use_case',
                success=success,
                started_at=started_at,
                metadata={'entry_id': entry_id, 'deleted': deleted},
            )
            return response
        except Exception as exc:
            logger.error(
                f"[process_delete_specific_entry_use_case] Ошибка удаления записи {entry_id} пользователя {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='delete_entry_exception',
                message=get_message('error_generic', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_delete_specific_entry_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'delete_entry_exception', 'entry_id': entry_id},
            )
            return response

    async def process_cancel_delete_specific_entry_use_case(
        self,
        user: User,
        language: str,
        target_date_iso: str,
    ) -> ServiceResponse:
        """Универсальный use-case отмены удаления записи и подготовки payload отображения дня."""
        started_at = time.perf_counter()
        success = False

        try:
            try:
                target_date = date.fromisoformat(target_date_iso)
            except ValueError:
                response = ServiceResponse.fail(
                    error='invalid_target_date',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_cancel_delete_specific_entry_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'invalid_target_date'},
                )
                return response

            from diary.services.diary_display_service import diary_display_service

            day_view = await diary_display_service.build_day_entries_view(user, target_date, language)
            if not day_view.get('success'):
                response = ServiceResponse.fail(
                    error='day_view_build_failed',
                    message=get_message('error_generic', language),
                )
                await self._record_use_case_metric(
                    use_case='diary.process_cancel_delete_specific_entry_use_case',
                    success=success,
                    started_at=started_at,
                    metadata={'error': 'day_view_build_failed'},
                )
                return response

            success = True
            response = ServiceResponse.ok(data={'day_view': day_view})
            await self._record_use_case_metric(
                use_case='diary.process_cancel_delete_specific_entry_use_case',
                success=success,
                started_at=started_at,
            )
            return response
        except Exception as exc:
            logger.error(
                f"[process_cancel_delete_specific_entry_use_case] Ошибка отмены удаления для пользователя {user.telegram_id}: {exc}",
                exc_info=True,
            )
            response = ServiceResponse.fail(
                error='cancel_delete_exception',
                message=get_message('error_generic', language),
            )
            await self._record_use_case_metric(
                use_case='diary.process_cancel_delete_specific_entry_use_case',
                success=success,
                started_at=started_at,
                metadata={'error': 'cancel_delete_exception'},
            )
            return response

    @async_error_handler('diary_service')
    @database_retry(max_retries=3)
    async def create_text_entry(
        self, 
        user: User, 
        text: str, 
        language: str = 'ru',
        entry_datetime: datetime = None
    ) -> DiaryEntry:
        """
        Асинхронное создание текстовой записи - ОПТИМИЗИРОВАНО
        """
        try:
            @sync_to_async
            def _create_entry():
                with transaction.atomic():
                    entry_created_at = entry_datetime or datetime.now()
                    diary_entry = DiaryEntry.objects.create(
                        user=user,
                        text=text,
                        language=language,
                        word_count=len(text.split()),
                        is_processed=False,
                        created_at=entry_created_at,
                        creator_timezone=user.timezone or 'UTC'
                    )
                    user.last_entry = entry_created_at
                    user.last_activity = entry_created_at
                    user.save(update_fields=['last_entry', 'last_activity'])
                    return diary_entry
            diary_entry = await _create_entry()
            logger.debug(f"Текстовая запись создана: Entry ID {diary_entry.id}")
            entry_date = await diary_entry.aentry_date()
            cache.delete_many([
                f'user_{user.id}_entries_{entry_date}',
                f'user_{user.id}_calendar_{entry_date.year}_{entry_date.month}'
            ])
            return diary_entry
        except Exception as e:
            logger.error(f"Ошибка при создании текстовой записи: {e}")
            raise
    
    async def update_entry_text(self, entry_id: int, user: User, new_text: str) -> bool:
        """
        Асинхронное обновление текста записи и соответствующего CombinedDiaryEntry.

        Args:
            entry_id: ID записи.
            user: Пользователь.
            new_text: Новый текст записи.

        Returns:
            bool: True, если успешно, иначе False.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            target_date = entry.entry_date
            @sync_to_async
            def _update_entry_and_related():
                with transaction.atomic():
                    entry.text = new_text
                    entry.word_count = len(new_text.split())
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                    entry.is_processed = False
                    entry.processing_error = ""
                    entry.save(update_fields=['text', 'word_count', 'is_processed', 'processing_error'])
                    return True
            await _update_entry_and_related()
            @sync_to_async
            def _update_or_create_combined_entry():
                with transaction.atomic():
                    try:
                        combined_entry = CombinedDiaryEntry.objects.select_for_update().get(user=user, date=target_date) 
                        all_entries_for_day = list(DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at'))
                        if not all_entries_for_day:
                             logger.error(f"[Сервис] Критическая ошибка: Запись {entry_id} существует, но записей за день {target_date} нет!")
                             texts = [entry.text]
                             new_combined_text = "\n\n---\n\n".join(texts)
                             new_entry_count = 1
                             combined_entry = CombinedDiaryEntry.objects.create(
                                 user=user,
                                 date=target_date,
                                 text=new_combined_text,
                                 entry_count=new_entry_count,
                                 ai_state_data='',
                                 is_analyzed=False,
                             )
                        else:
                             texts = [e.text for e in all_entries_for_day]
                             new_combined_text = "\n\n---\n\n".join(texts)
                             new_entry_count = len(all_entries_for_day) 
                             combined_entry.text = new_combined_text
                             combined_entry.entry_count = new_entry_count
                             combined_entry.reset_analysis_flag()
                             combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed'])
                    except CombinedDiaryEntry.DoesNotExist:
                        all_entries_for_day = list(DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at'))
                        if not all_entries_for_day:
                            logger.warning(f"[Сервис] CombinedDiaryEntry и записи за день {target_date} не найдены при обновлении. Создаем новый CombinedDiaryEntry с текущей записью.")
                            texts = [entry.text] 
                            new_entry_count = 1
                        else:
                            texts = [e.text for e in all_entries_for_day]
                            new_entry_count = len(all_entries_for_day)                   
                        new_combined_text = "\n\n---\n\n".join(texts)
                        combined_entry = CombinedDiaryEntry.objects.create(
                            user=user,
                            date=target_date,
                            text=new_combined_text,
                            entry_count=new_entry_count,
                            ai_state_data='',
                            is_analyzed=False,
                        )
                    return True
            await _update_or_create_combined_entry()
            return True
        except DiaryEntry.DoesNotExist:
            logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id} (внешний блок)")
            return False
        except Exception as e:
            logger.error(f"Ошибка в асинхронном обновлении текста записи {entry_id}: {e}", exc_info=True)
            try:
                @sync_to_async
                def _set_error_flag():
                     DiaryEntry.objects.filter(id=entry_id, user=user).update(is_processed=False, processing_error=str(e)[:255])
                await _set_error_flag()
            except Exception as flag_error:
                 logger.error(f"Не удалось установить флаг ошибки для записи {entry_id}: {flag_error}")
            return False

    async def delete_entry_and_update_combined(self, entry_id: int, user: User) -> bool:
        """
        Асинхронное удаление записи и обновление/удаление связанного CombinedDiaryEntry.

        Args:
            entry_id: ID записи.
            user: Пользователь.

        Returns:
            bool: True, если успешно, иначе False.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            entry_date = entry.entry_date
            @sync_to_async
            def _delete_related_and_entry():
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                    if hasattr(entry, 'voicetotext'):
                        entry.voicetotext.delete()             
                    TherapyTask.objects.filter(related_entry=entry).delete()
                    entry.delete() 
            await _delete_related_and_entry()
            try:
                combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=entry_date)
                @sync_to_async
                def _get_remaining_entries():
                    return list(DiaryEntry.objects.filter(user=user, created_at__date=entry_date).order_by('created_at'))
                remaining_entries = await _get_remaining_entries()
                if remaining_entries:
                    texts = [e.text for e in remaining_entries]
                    new_combined_text = "\n\n---\n\n".join(texts)
                    new_entry_count = len(remaining_entries)
                    combined_entry.text = new_combined_text
                    combined_entry.entry_count = new_entry_count
                    combined_entry.reset_analysis_flag()
                    await combined_entry.asave(update_fields=['text', 'entry_count', 'is_analyzed'])
                    logger.debug(f"CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                else:
                    await combined_entry.adelete()                 
            except CombinedDiaryEntry.DoesNotExist:
                logger.warning(f"CombinedDiaryEntry для {entry_date} не найден при удалении записи {entry_id}. Возможно, он уже был удален.")
            cache_key = f'user_{user.id}_entries_{entry_date}'
            cache.delete(cache_key)
            logger.debug(f"Кэш для записей пользователя {user.telegram_id} за {entry_date} удалён после удаления записи {entry_id}.")
            return True
        except Exception as e:
            logger.error(f"Ошибка в асинхронном удалении записи {entry_id} и обновлении CombinedDiaryEntry: {e}", exc_info=True)
            return False

    async def get_or_update_daily_state_with_entries(
        self,
        user: User,
        diary_entry: DiaryEntry
    ) -> tuple[CombinedDiaryEntry, bool]:
        """
        Получает или создаёт CombinedDiaryEntry и обновляет его текст и счётчик.
        Возвращает объект и флаг is_first_entry_of_day.
        """
        entry_date = diary_entry.entry_date
        combined_entry = await self.get_daily_state(user, entry_date)
        if combined_entry is None:
            combined_entry = await self.create_daily_state_from_entry(diary_entry)
            return combined_entry, True
        entries = await self.get_user_entries_for_date(user, entry_date)
        combined_text = await self.get_combined_entry_text(user, entry_date, entries_list=entries)
        await self.update_daily_state_text_and_count(
            combined_entry, combined_text, len(entries)
        )
        return combined_entry, False

    @async_error_handler('diary_service')
    async def get_user_entries_for_date(
        self, 
        user: User, 
        target_date: date
    ) -> List[DiaryEntry]:
        """
        Асинхронное получение записей за дату - С КЭШИРОВАНИЕМ
        """
        cache_key = f'user_{user.id}_entries_{target_date}'
        cached_entries = cache.get(cache_key)
        if cached_entries is not None:
            return cached_entries
        try:
            user_timezone_str = user.timezone or 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            start_of_day_user_tz = user_tz.localize(
                datetime.combine(target_date, dtime.min)
            )
            end_of_day_user_tz = user_tz.localize(
                datetime.combine(target_date, dtime.max)
            )
            start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
            end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)
            entries = await sync_to_async(list)(
                DiaryEntry.objects
                .select_related('user')
                .filter(
                    user=user,
                    created_at__gte=start_of_day_utc,
                    created_at__lte=end_of_day_utc,
                    is_recovered_streak=False
                )
                .order_by('created_at')
            )
            if entries:
                cache.set(cache_key, entries, timeout=300)
            logger.debug(f"Найдено {len(entries)} записей за {target_date}")
            return entries
        except Exception as e:
            logger.error(f"Ошибка при получении записей за дату: {e}")
            return []

    async def get_user_entry_by_id(self, user: User, entry_id: int) -> Optional[DiaryEntry]:
        """Получение записи пользователя по ID."""
        try:
            return await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении записи {entry_id} пользователя {user.telegram_id}: {e}", exc_info=True)
            return None

    async def get_combined_entry_with_analysis_for_date(
        self,
        user: User,
        target_date: date,
    ) -> Optional[CombinedDiaryEntry]:
        """Получение CombinedDiaryEntry за дату с prefetch daily_analysis."""
        try:
            return await CombinedDiaryEntry.objects.select_related('daily_analysis').aget(user=user, date=target_date)
        except CombinedDiaryEntry.DoesNotExist:
            return None
        except Exception as e:
            logger.error(
                f"Ошибка при получении CombinedDiaryEntry за {target_date} пользователя {user.telegram_id}: {e}",
                exc_info=True,
            )
            return None

    async def get_analysis_for_entry(self, entry: DiaryEntry) -> Optional[PsychoAnalysis]:
        """Получение анализа для конкретной записи."""
        try:
            return await PsychoAnalysis.objects.aget(entry=entry)
        except PsychoAnalysis.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении анализа для записи {entry.id}: {e}", exc_info=True)
            return None

    async def get_combined_entry_text(
        self, 
        user: User, 
        target_date: date, 
        entries_list: Optional[List[DiaryEntry]] = None
    ) -> str:
        """
        Асинхронное получение объединенного текста всех записей пользователя за конкретную дату,
        с учетом часового пояса пользователя.

        Args:
            user: Пользователь.
            target_date: Целевая дата (в терминах пользователя).
            entries_list: (Опционально) Список уже полученных записей DiaryEntry за эту дату.
                        Если предоставлен, будет использован вместо нового запроса к БД.

        Returns:
            str: Объединенный текст всех записей дня. Пустая строка, если записей нет или произошла ошибка.
        """
        try:
            if entries_list is not None:
                entries = entries_list
            else:
                entries = await self.get_user_entries_for_date(user, target_date) 
            if not entries:
                return ""
            texts = [entry.text for entry in entries]
            combined_text = "\n\n---\n\n".join(texts)
            return combined_text
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении объединенного текста за {target_date} для пользователя {user.telegram_id} (с учетом часового пояса): {e}", exc_info=True)
            return ""

    async def delete_entry(self, entry_id: int, user: User) -> bool:
        """
        Асинхронное удаление записи дневника и всех связанных объектов.

        Args:
            entry_id: ID записи.
            user: Пользователь (для проверки прав доступа).

        Returns:
            bool: True, если запись была успешно удалена или не существовала, False в случае ошибки.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return True
            entry_date = await entry.aentry_date()
            @sync_to_async
            def _delete_entry_atomic():
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        try:
                            entry.analysis.delete() 
                        except Exception as analysis_delete_error:
                            logger.warning(f"Ошибка при удалении связанного PsychoAnalysis для записи {entry_id}: {analysis_delete_error}")
                    entry.delete()
                    logger.debug(f"Запись дневника {entry_id} успешно удалена для пользователя {user.telegram_id}.")
            cache_key = f'user_{user.id}_entries_{entry_date}'
            cache.delete(cache_key)
            logger.debug(f"Кэш для записей пользователя {user.telegram_id} за {entry_date} удалён после удаления записи {entry_id}.")
            await _delete_entry_atomic()
            return True
        except Exception as e:
            logger.error(f"Ошибка при асинхронном удалении записи {entry_id} для пользователя {user.telegram_id}: {e}", exc_info=True)
            return False
    
    @async_error_handler('diary_service')
    async def get_days_with_entries(self, user: User, year: int, month: int) -> set:
        """
        Получение дней с записями - С КЭШИРОВАНИЕМ
        """
        cache_key = f'user_{user.id}_calendar_{year}_{month}'
        cached_days = cache.get(cache_key)
        if cached_days:
            return cached_days
        
        try:
            @sync_to_async
            def _get_days():
                return set(
                    DiaryEntry.objects
                    .filter(user=user, created_at__year=year, created_at__month=month)
                    .annotate(day=F('created_at__day'))
                    .values_list('day', flat=True)
                    .distinct()
                )
            days_with_entries = await _get_days()
            cache.set(cache_key, days_with_entries, timeout=3600)
            return days_with_entries
        except Exception as e:
            logger.error(f"Ошибка при получении дней с записями: {e}")
            return set()

    async def get_daily_state(self, user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
        """
        Асинхронно получает CombinedDiaryEntry для пользователя и даты.
        Делегирует вызов DailyStateService.

        Args:
            user: Пользователь.
            target_date: Целевая дата.

        Returns:
            CombinedDiaryEntry: Объект состояния дня или None, если не найден.
        """
        return await get_daily_state(user, target_date)

    async def get_or_create_daily_state(self, user: User, target_date: date, initial_text: str) -> CombinedDiaryEntry:
        """
        Асинхронно получает или создает CombinedDiaryEntry для пользователя и даты.
        Делегирует вызов DailyStateService.

        Args:
            user: Пользователь.
            target_date: Целевая дата.
            initial_text: Начальный объединенный текст для создания записи.

        Returns:
            CombinedDiaryEntry: Существующий или новый объект состояния дня.
        """
        return await get_or_create_daily_state(user, target_date, initial_text)

    async def update_daily_state(self, combined_entry: CombinedDiaryEntry, new_ai_state_data: str) -> bool:
        """
        Асинхронно обновляет существующий CombinedDiaryEntry с новым состоянием от ИИ.
        Делегирует вызов DailyStateService.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_ai_state_data: Новое текстовое состояние дня от ИИ.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        return await update_daily_state(combined_entry, new_ai_state_data)

    async def update_daily_state_text_and_count(
        self, combined_entry: CombinedDiaryEntry, new_text: str, new_entry_count: int
    ) -> bool:
        """
        Асинхронно обновляет текст и счетчик записей в CombinedDiaryEntry.
        Делегирует вызов DailyStateService.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_text: Новый объединенный текст.
            new_entry_count: Новое количество записей.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        return await update_daily_state_text_and_count(combined_entry, new_text, new_entry_count)

    async def create_daily_state_from_entry(self, diary_entry: DiaryEntry) -> Optional[CombinedDiaryEntry]:
        """
        Создает новый CombinedDiaryEntry на основе одной DiaryEntry.
        Делегирует вызов DailyStateService.

        Args:
            diary_entry: Объект DiaryEntry.

        Returns:
            CombinedDiaryEntry: Созданный объект состояния дня или None при ошибке.
        """
        return await create_daily_state_from_entry(diary_entry)
    
    async def delete_all_entries_for_day(self, user: User, target_date: date) -> bool:
        """
        Асинхронно удаляет все записи DiaryEntry за указанный день для пользователя,
        а также все связанные объекты и TherapyTask, созданные для этих записей.
        Также удаляет CombinedDiaryEntry за этот день.
        """
        logger.debug(f"[Сервис] Удаление всех записей за {target_date} для пользователя {user.telegram_id}")
        try:
            @sync_to_async
            def _delete_sync():
                with transaction.atomic():
                    entries = DiaryEntry.objects.filter(user=user, created_at__date=target_date)
                    entry_ids = list(entries.values_list('id', flat=True))
                    if not entry_ids:
                        CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                        return True
                    PsychoAnalysis.objects.filter(entry_id__in=entry_ids).delete()
                    TherapyTask.objects.filter(related_entry_id__in=entry_ids).delete()
                    entries.delete()
                    CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                return True
            result = await _delete_sync()
            if result: # Удаляем кэш только если удаление прошло успешно
                cache_key = f'user_{user.id}_entries_{target_date}'
                cache.delete(cache_key)
                logger.debug(f"Кэш для записей пользователя {user.telegram_id} за {target_date} удалён после удаления всех записей за день.")
                logger.debug(f"[Сервис] Удаление записей за {target_date} завершено успешно: {result}")
            return result
        except Exception as e:
            logger.error(f"[Сервис] Ошибка при удалении записей за {target_date}: {e}")
            return False

    async def process_new_entry_logic(
        self,
        user: User,
        entry_text: str,
        language: str,
        entry_datetime: datetime = None
    ) -> Dict[str, Any]:
        """
        Выполняет полную бизнес-логику обработки новой текстовой записи:
        - Создание DiaryEntry
        - Обновление/создание CombinedDiaryEntry
        - Вызов ИИ для анализа
        - Обработка результата ИИ (в т.ч. валидация, уточнения, PsychoAnalysis, обновление состояния дня, задания, серия)
        - Возвращает структурированный результат для дальнейшего использования в хендлере.

        Args:
            user (User): Пользователь.
            entry_text (str): Текст записи.
            language (str): Язык.
            entry_datetime (datetime, optional): Время создания записи. Defaults to None.

        Returns:
            Dict[str, Any]: Результат обработки. Содержит:
                - 'success' (bool): Успешность основной операции (после валидации ИИ).
                - 'entry' (DiaryEntry): Созданная запись.
                - 'analysis' (PsychoAnalysis): Созданный/обновленный анализ.
                - 'needs_clarification' (bool): Требуются ли уточнения.
                - 'clarification_questions' (list): Список уточняющих вопросов, если требуются.
                - 'suggested_task' (TherapyTask): Созданное задание, если было предложено ИИ.
                - 'streak_bonus_info' (dict): Информация о награде за серию.
                - 'formatted_message_ai' (str): Форматированное сообщение от ИИ, если запись не прошла валидацию.
                - 'validation_comment_ai' (str): Комментарий ИИ при невалидной записи.
        """
        # 1. Создание DiaryEntry
        diary_entry = await self.create_text_entry(
            user=user,
            text=entry_text,
            language=language,
            entry_datetime=entry_datetime
        )
        logger.debug(f"[process_new_entry_logic] Создана запись ID {diary_entry.id} для пользователя {user.telegram_id}")

        # 2. Обновление/создание CombinedDiaryEntry
        combined_entry, _ = await self.get_or_update_daily_state_with_entries(user, diary_entry)
        entry_date = await diary_entry.aentry_date()
        all_entries_text = await self.get_combined_entry_text(user, entry_date)
        logger.debug(f"[process_new_entry_logic] Обновлен CombinedDiaryEntry ID {combined_entry.id} для пользователя {user.telegram_id}")

        # 3. Подготовка данных и вызов ИИ
        ai_state_data = combined_entry.ai_state_data if combined_entry else ""
        base_user_profile = await user.aget_profile_data()

        # Проверяем активную подписку для выбора промпта
        is_premium_active = await sync_to_async(user.is_premium_active)()

        extended_user_context = {
            "first_name": base_user_profile.get('first_name', 'Пользователь'),
            "awareness_level": base_user_profile.get('awareness_level', 1),
            "is_premium": is_premium_active,
            "entries_count": base_user_profile.get('entries_count', 0),
            "personality_traits": user.personality_traits,
            "life_facts": user.life_facts,
            "hobbies": user.hobbies,
            "core_values": user.core_values,
            "triggers": user.triggers,
            "strengths": user.strengths,
            "areas_for_growth": user.areas_for_growth,
            "practical_patterns": user.practical_patterns,
            "aspirations": user.aspirations
        }

        personal_fields_payload = build_personal_fields_payload_for_ai(user)
        premium_top_personality_traits = _top_profile_items_for_prompt(
            personal_fields_payload.get("personality_traits", []),
            limit=20,
        )
        premium_top_triggers = _top_profile_items_for_prompt(
            personal_fields_payload.get("triggers", []),
            limit=20,
        )
        premium_top_strengths = _top_profile_items_for_prompt(
            personal_fields_payload.get("strengths", []),
            limit=20,
        )

        try:
            user_tz_str = user.timezone if user.timezone else 'UTC'
            user_tz = pytz.timezone(user_tz_str)
            created_at = diary_entry.created_at
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            localized_time = created_at.astimezone(user_tz)
            new_entry_creation_time_local = _format_entry_datetime_for_prompt(localized_time, language)
            logger.debug(f"[process_new_entry_logic] Локализованное время создания записи {diary_entry.id}: {new_entry_creation_time_local}")
        except Exception as e:
            logger.error(f"[process_new_entry_logic] Ошибка при определении локального времени для записи {diary_entry.id}: {e}")
            new_entry_creation_time_local = _format_entry_datetime_for_prompt(diary_entry.created_at, language)

        # Выбираем промпт: полный для premium, сокращённый для обычных
        prompt_mode = "unknown"
        if is_premium_active:
            prompt_key = 'incremental_day_analysis'
            prompt_mode = "premium"
            prompt = get_prompt(
                key=prompt_key,
                language=language,
                all_entries_combined=all_entries_text,
                new_entry_text=entry_text,
                new_entry_creation_time_local=new_entry_creation_time_local,
                ai_state_data=ai_state_data,
                first_name=extended_user_context["first_name"],
                awareness_level=extended_user_context["awareness_level"],
                is_premium=extended_user_context["is_premium"],
                user_personality_traits=json.dumps(
                    premium_top_personality_traits,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                user_life_facts=extended_user_context["life_facts"],
                user_hobbies=extended_user_context["hobbies"],
                user_core_values=extended_user_context["core_values"],
                user_triggers=json.dumps(
                    premium_top_triggers,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                user_strengths=json.dumps(
                    premium_top_strengths,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                user_areas_for_growth=extended_user_context["areas_for_growth"],
                entries_count=extended_user_context["entries_count"],
            )
            logger.debug(f"[process_new_entry_logic] Используется ПОЛНЫЙ промпт (premium) для пользователя {user.telegram_id}")
        else:
            # Проверяем возможность использования LITE v2
            from django.conf import settings
            use_lite_v2 = (
                settings.USE_LITE_V2 and 
                user.compressed_psych_profile and 
                combined_entry and combined_entry.day_context_summary
            )
            
            if use_lite_v2:
                # LITE v2: использует compressed_psych_profile + day_context_summary
                prompt_key = 'incremental_day_analysis_lite_v2'
                prompt_mode = "lite_v2"
                compressed_profile = normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {})
                compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))
                day_context_json = json.dumps(combined_entry.day_context_summary or {}, ensure_ascii=False, separators=(",", ":"))
                free_top_personality_traits = _top_profile_items_for_prompt(
                    personal_fields_payload.get("personality_traits", []),
                    limit=10,
                )
                free_top_triggers = _top_profile_items_for_prompt(
                    personal_fields_payload.get("triggers", []),
                    limit=10,
                )
                free_top_strengths = _top_profile_items_for_prompt(
                    personal_fields_payload.get("strengths", []),
                    limit=10,
                )
                lite_v2_personality_traits_json = json.dumps(
                    free_top_personality_traits,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                lite_v2_triggers_json = json.dumps(
                    free_top_triggers,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                lite_v2_strengths_json = json.dumps(
                    free_top_strengths,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                
                prompt = get_prompt(
                    key=prompt_key,
                    language=language,
                    user_plan='free',
                    first_name=extended_user_context["first_name"],
                    awareness_level=extended_user_context["awareness_level"],
                    entries_count=extended_user_context["entries_count"],
                    compressed_psych_profile_json=compressed_profile_json,
                    day_context_summary_json=day_context_json,
                    user_personality_traits=lite_v2_personality_traits_json,
                    user_triggers=lite_v2_triggers_json,
                    user_strengths=lite_v2_strengths_json,
                    new_entry_text=entry_text,
                    new_entry_creation_time_local=new_entry_creation_time_local,
                    ai_state_data=ai_state_data,
                )
                logger.debug(f"[process_new_entry_logic] Используется LITE v2 промпт для пользователя {user.telegram_id}")
                
                # Логирование для мониторинга
                logger.info(
                    f"[LiteV2] User {user.telegram_id}: using lite_v2_incremental, "
                    f"compressed={bool(user.compressed_psych_profile)}, "
                    f"day_context={bool(combined_entry and combined_entry.day_context_summary)}, "
                    f"prompt_length={len(prompt)}"
                )
            else:
                # LITE v1: используем compressed_psych_profile
                prompt_key = 'incremental_day_analysis_lite'
                prompt_mode = "lite_v1"
                compressed_profile = normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {})
                compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))
                
                prompt = get_prompt(
                    key=prompt_key,
                    language=language,
                    all_entries_combined=all_entries_text,
                    new_entry_text=entry_text,
                    new_entry_creation_time_local=new_entry_creation_time_local,
                    ai_state_data=ai_state_data,
                    first_name=extended_user_context["first_name"],
                    compressed_psych_profile_json=compressed_profile_json,
                )
                logger.debug(f"[process_new_entry_logic] Используется LITE v1 промпт (без подписки) для пользователя {user.telegram_id}")
                
                # Логирование для мониторинга
                logger.info(
                    f"[LiteV2] User {user.telegram_id}: fallback to lite_v1, "
                    f"compressed={bool(user.compressed_psych_profile)}, "
                    f"day_context={bool(combined_entry and combined_entry.day_context_summary)}, "
                    f"USE_LITE_V2={settings.USE_LITE_V2}"
                )

        api_start_time = time.time()
        analysis_result = await self._call_deepseek_with_metrics(
            flow='diary.process_new_entry_logic',
            prompt=prompt,
            language=language,
            metadata={'prompt_mode': prompt_mode, 'attempt': 'primary'},
        )

        if (not analysis_result.get('success')) and analysis_result.get('error') == 'context_length_exceeded':
            logger.warning(
                f"[process_new_entry_logic] context_length_exceeded для {user.telegram_id}, "
                f"режим={prompt_mode}. Пробуем fallback prompt."
            )

            fallback_prompt = None
            if prompt_mode == "lite_v2":
                fallback_compressed_profile_json = json.dumps(
                    normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {}),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                fallback_traits = _top_profile_items_for_prompt(
                    personal_fields_payload.get("personality_traits", []),
                    limit=3,
                )
                fallback_strengths = _top_profile_items_for_prompt(
                    personal_fields_payload.get("strengths", []),
                    limit=3,
                )
                fallback_prompt = get_prompt(
                    key='incremental_day_analysis_lite_v2',
                    language=language,
                    user_plan='free',
                    first_name=extended_user_context["first_name"],
                    awareness_level=extended_user_context["awareness_level"],
                    entries_count=extended_user_context["entries_count"],
                    compressed_psych_profile_json=fallback_compressed_profile_json,
                    day_context_summary_json='{}',
                    user_personality_traits=json.dumps(fallback_traits, ensure_ascii=False, separators=(",", ":")),
                    user_triggers='[]',
                    user_strengths=json.dumps(fallback_strengths, ensure_ascii=False, separators=(",", ":")),
                    new_entry_text=entry_text,
                    new_entry_creation_time_local=new_entry_creation_time_local,
                    ai_state_data=_truncate_text_for_prompt(ai_state_data, 2000),
                )

            elif prompt_mode == "premium":
                fallback_prompt = get_prompt(
                    key='incremental_day_analysis',
                    language=language,
                    all_entries_combined=_truncate_text_for_prompt(all_entries_text, 12000),
                    new_entry_text=entry_text,
                    new_entry_creation_time_local=new_entry_creation_time_local,
                    ai_state_data=_truncate_text_for_prompt(ai_state_data, 3000),
                    first_name=extended_user_context["first_name"],
                    awareness_level=extended_user_context["awareness_level"],
                    is_premium=extended_user_context["is_premium"],
                    user_personality_traits=json.dumps(
                        _top_profile_items_for_prompt(personal_fields_payload.get("personality_traits", []), limit=10),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    user_life_facts=_trim_list_for_prompt(extended_user_context["life_facts"], 10),
                    user_hobbies=_trim_list_for_prompt(extended_user_context["hobbies"], 10),
                    user_core_values=_trim_list_for_prompt(extended_user_context["core_values"], 10),
                    user_triggers=json.dumps(
                        _top_profile_items_for_prompt(personal_fields_payload.get("triggers", []), limit=10),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    user_strengths=json.dumps(
                        _top_profile_items_for_prompt(personal_fields_payload.get("strengths", []), limit=10),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    user_areas_for_growth=_trim_list_for_prompt(extended_user_context["areas_for_growth"], 10),
                    entries_count=extended_user_context["entries_count"],
                )

            elif prompt_mode == "lite_v1":
                fallback_prompt = get_prompt(
                    key='incremental_day_analysis_lite',
                    language=language,
                    all_entries_combined=_truncate_text_for_prompt(all_entries_text, 12000),
                    new_entry_text=entry_text,
                    new_entry_creation_time_local=new_entry_creation_time_local,
                    ai_state_data=_truncate_text_for_prompt(ai_state_data, 3000),
                    first_name=extended_user_context["first_name"],
                    compressed_psych_profile_json=json.dumps(
                        normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )

            if fallback_prompt:
                analysis_result = await self._call_deepseek_with_metrics(
                    flow='diary.process_new_entry_logic',
                    prompt=fallback_prompt,
                    language=language,
                    metadata={'prompt_mode': prompt_mode, 'attempt': 'fallback'},
                    max_retries=1,
                    timeout_per_attempt=90,
                )

        total_api_time = time.time() - api_start_time
        logger.debug(f"[process_new_entry_logic] 🕒 Полное время API запроса: {total_api_time:.3f} секунд")

        # 4. Обработка результата ИИ
        result_data = analysis_result.get('result', {})
        is_valid_ai = result_data.get('is_valid', True)
        validation_comment_ai = result_data.get('validation_comment', '')
        formatted_message_ai = result_data.get('formatted_message', '')

        # 4.1. Проверка валидации ИИ
        if not is_valid_ai:
            # Удаляем невалидную запись и CombinedDiaryEntry
            success = await self.delete_entry_and_update_combined(diary_entry.id, user)
            if not success:
                logger.warning(f"[process_new_entry_logic] Не удалось удалить невалидную запись {diary_entry.id} для пользователя {user.telegram_id}")
            # Возвращаем информацию о невалидности
            return {
                'success': False,
                'entry': None, # Запись удалена
                'analysis': None,
                'needs_clarification': False,
                'suggested_task': None,
                'streak_bonus_info': None,
                'formatted_message_ai': formatted_message_ai,
                'validation_comment_ai': validation_comment_ai
            }

        # 4.2. Обработка основного результата (если валидна)
        mood_score = result_data.get('mood_score', 5)
        comment = result_data.get('comment', 'Анализ записан')
        recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
        analysis_text = result_data.get('analysis', 'Текст проанализирован.')
        suggested_task_data = result_data.get('suggested_task')
        needs_clarification = result_data.get('needs_clarification', False)
        clarification_questions = result_data.get('clarification_questions', [])

        # 4.3. Создание/обновление PsychoAnalysis
        finalize_now = not needs_clarification
        analysis_obj = await psycho_analysis_service.create_or_update_analysis(
            entry=diary_entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {}),
            processing_time=total_api_time,
            finalize_processing=finalize_now
        )
        logger.debug(f"[process_new_entry_logic] Создан/обновлен PsychoAnalysis ID {analysis_obj.id} для записи {diary_entry.id}")

        # 4.4. Обновление CombinedDiaryEntry с новым состоянием ИИ
        # Используем новый структурированный формат
        from diary.services.daily_state_service import update_ai_state_from_analysis
        
        current_ai_state = combined_entry.ai_state_data if combined_entry else ""
        
        if 'updated_ai_state_data' in result_data:
            # AI already returns structured data in v2 prompts, or text in v1
            # Try to parse as JSON first, if fails - use old format conversion
            new_state_raw = result_data['updated_ai_state_data']
            try:
                parsed = json.loads(new_state_raw)
                if isinstance(parsed, dict) and 'current_mood' in parsed:
                    # Already structured - use as is
                    new_state = json.dumps(parsed, ensure_ascii=False)
                else:
                    # Text format from v1 - convert to structured
                    new_state = update_ai_state_from_analysis(
                        current_ai_state=current_ai_state,
                        new_mood_score=mood_score,
                        comment=result_data.get('comment', ''),
                        day_context_summary=None
                    )
            except (json.JSONDecodeError, TypeError):
                # Not JSON - convert text to structured format
                new_state = update_ai_state_from_analysis(
                    current_ai_state=current_ai_state,
                    new_mood_score=mood_score,
                    comment=new_state_raw,
                    day_context_summary=None
                )
        else:
            # Fallback: create from analysis
            new_state = update_ai_state_from_analysis(
                current_ai_state=current_ai_state,
                new_mood_score=mood_score,
                comment=result_data.get('comment', ''),
                day_context_summary=None
            )
        
        await daily_state_service.update_daily_state(
            combined_entry=combined_entry,
            new_ai_state_data=new_state,
            latest_mood_score=mood_score
        )
        logger.debug(f"[process_new_entry_logic] Обновлен CombinedDiaryEntry ID {combined_entry.id} с новым состоянием (структурированный формат)")

        # 4.5. Создание задания от ИИ (если предложено и лимит не превышен)
        suggested_task_obj = None
        if suggested_task_data and isinstance(suggested_task_data, dict):
            @sync_to_async
            def check_ai_tasks_limit_sync():
                # Лимит проверяется на количество заданий, назначенных сегодня
                from diary.models import TherapyTask
                from django.utils import timezone
                import pytz
                user_timezone_str = user.timezone if user.timezone else 'UTC'
                user_tz = pytz.timezone(user_timezone_str)
                today_start = timezone.now().astimezone(user_tz).date()
                count = TherapyTask.objects.filter(
                    user=user,
                    assigned_at__date=today_start # Проверяем по дате назначения, а не по дате записи
                ).count()
                return count < user.max_ai_tasks_per_day

            limit_not_exceeded = await check_ai_tasks_limit_sync()
            if limit_not_exceeded:
                try:
                    suggested_task_obj = await self._create_task_from_suggested_data(user, suggested_task_data, entry_date, diary_entry)
                    logger.debug(f"[process_new_entry_logic] Задание от ИИ создано: {suggested_task_obj.id if suggested_task_obj else 'None'}")
                except Exception as task_creation_error:
                    logger.error(f"[process_new_entry_logic] Ошибка при создании задания от ИИ для пользователя {user.telegram_id}: {task_creation_error}")

        # 4.6. Награда за серию
        streak_bonus_info = await check_and_award_streak_bonus(user)

        # 4.7. Возврат результата
        return {
            'success': True,
            'entry': diary_entry,
            'analysis': analysis_obj,
            'needs_clarification': needs_clarification,
            'clarification_questions': clarification_questions,
            'suggested_task': suggested_task_obj,
            'streak_bonus_info': streak_bonus_info,
            'formatted_message_ai': None, # Не используется, если запись валидна
            'validation_comment_ai': None # Не используется, если запись валидна
        }

    # --- Вспомогательная функция для создания задания ---
    async def _create_task_from_suggested_data(self, user, task_data, entry_date, related_entry):
        """Создаёт задание из данных ИИ."""
        from core.constants import TASK_TYPES
        valid_types = [t[0] for t in TASK_TYPES]
        task_type = task_data.get('type', 'daily')
        if task_type not in valid_types:
            task_type = 'daily'
        complexity = task_data.get('priority', 'medium').lower()
        if complexity not in ['low', 'medium', 'high']:
            complexity = 'medium'
        return await assign_task(
            user=user,
            title=task_data.get('title', 'Задание от ИИ'),
            description=task_data.get('description', 'Выполните задание.'),
            task_type=task_type,
            complexity=complexity,
            related_entry=related_entry
        )

    async def process_clarification_answers_logic(
        self,
        user: User,
        diary_entry: DiaryEntry,
        clarification_answers_dict: Dict[str, str],
        language: str
    ) -> Dict[str, Any]:
        """
        Выполняет бизнес-логику обработки ответов на уточняющие вопросы:
        - Сохранение ответов в DiaryEntry
        - Вызов ИИ для анализа уточнений
        - Обновление PsychoAnalysis
        - Обновление CombinedDiaryEntry
        - Возврат результата для хендлера.

        Args:
            user (User): Пользователь.
            diary_entry (DiaryEntry): Запись, к которой относятся уточнения.
            clarification_answers_dict (Dict[str, str]): Словарь ответов на уточнения.
            language (str): Язык.

        Returns:
            Dict[str, Any]: Результат обработки.
        """
        # 1. Сохранение ответов
        diary_entry.clarification_answers = clarification_answers_dict
        await sync_to_async(diary_entry.save)(update_fields=['clarification_answers'])

        # 2. Подготовка данных и вызов ИИ
        personal_fields_payload = build_personal_fields_payload_for_ai(user)
        compressed_profile = user.compressed_psych_profile or {}
        if not compressed_profile:
            generated_profile = compressed_profile_service.generate_for_user(user)
            compressed_profile = generated_profile or {}
        compressed_profile = normalize_compressed_profile_for_prompt(compressed_profile)

        personal_fields_json = json.dumps(personal_fields_payload, ensure_ascii=False, separators=(",", ":"))
        compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))

        entry_date = await diary_entry.aentry_date()
        combined_entry = await daily_state_service.get_daily_state(user, entry_date)
        ai_state_data = combined_entry.ai_state_data if combined_entry else ""

        clarification_questions = diary_entry.clarification_questions_asked
        prompt = get_prompt(
            key='clarification_analysis',
            language=language,
            original_text=diary_entry.text,
            clarification_questions="\n".join(clarification_questions),
            clarification_answers="\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]),
            ai_state_data=ai_state_data,
            compressed_psych_profile_json=compressed_profile_json,
            personal_fields_json=personal_fields_json,
        )

        api_start_time = time.time()
        analysis_result = await self._call_deepseek_with_metrics(
            flow='diary.process_clarification_answers_logic',
            prompt=prompt,
            language=language,
        )
        total_api_time = time.time() - api_start_time

        # 3. Обработка результата ИИ
        # Инициализируем result_data и finalize_now значением по умолчанию
        result_data = {}
        # Переменная finalize_now определяет, нужно ли завершать анализ (установить is_processed = True)
        # В случае ошибки API, анализ не завершается, чтобы не оставлять запись в "висячем" состоянии
        finalize_now = False

        if not analysis_result.get('success'):
            # Обработка ошибки API
            comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, is_final=True)
            mood_score = 5
            # result_data остается пустым, как инициализировано выше
            # finalize_now остается False, анализ не завершается
        else:
            result_data = analysis_result.get('result', {})
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')
            # Успешный ответ ИИ - анализ можно завершить
            finalize_now = True

        # 4. Обновление PsychoAnalysis
        await psycho_analysis_service.create_or_update_analysis(
            entry=diary_entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {}),
            processing_time=total_api_time,
            finalize_processing=finalize_now # Используем переменную, определённую выше
        )

        # 5. Обновление CombinedDiaryEntry с новым состоянием ИИ
        # Используем новый структурированный формат
        from diary.services.daily_state_service import update_ai_state_from_analysis
        
        current_ai_state = combined_entry.ai_state_data if combined_entry else ""
        
        if 'updated_ai_state_data' in result_data:
            new_state_raw = result_data['updated_ai_state_data']
            try:
                parsed = json.loads(new_state_raw)
                if isinstance(parsed, dict) and 'current_mood' in parsed:
                    new_ai_state_data = json.dumps(parsed, ensure_ascii=False)
                else:
                    new_ai_state_data = update_ai_state_from_analysis(
                        current_ai_state=current_ai_state,
                        new_mood_score=mood_score,
                        comment=result_data.get('comment', ''),
                        day_context_summary=None
                    )
            except (json.JSONDecodeError, TypeError):
                new_ai_state_data = update_ai_state_from_analysis(
                    current_ai_state=current_ai_state,
                    new_mood_score=mood_score,
                    comment=new_state_raw,
                    day_context_summary=None
                )
            
            await daily_state_service.update_daily_state(
                combined_entry=combined_entry,
                new_ai_state_data=new_ai_state_data,
                latest_mood_score=mood_score
            )
            logger.debug(f"[process_clarification_answers_logic] Обновлен CombinedDiaryEntry ID {combined_entry.id} с новым состоянием (структурированный формат).")
        else:
            logger.debug(f"[process_clarification_answers_logic] Поле 'updated_ai_state_data' отсутствует в ответе ИИ. CombinedDiaryEntry ID {combined_entry.id} не обновляется.")

        # 6. Сброс флага ожидания уточнений и времени анализа
        diary_entry.clarification_asked_at = None
        diary_entry.clarification_reminder_due_at = None
        diary_entry.clarification_force_process_at = None
        diary_entry.last_reminder_sent_at = None
        diary_entry.analysis_processed_at = timezone.now() # Фиксируем время завершения анализа
        update_fields = ['clarification_asked_at', 'clarification_reminder_due_at', 'clarification_force_process_at', 'last_reminder_sent_at', 'analysis_processed_at']
        # Добавляем is_processed только если finalize_now = True
        if finalize_now:
            diary_entry.is_processed = True
            update_fields.append('is_processed')
        await sync_to_async(diary_entry.save)(update_fields=update_fields)
        logger.debug(f"[process_clarification_answers_logic] analysis_processed_at (и is_processed={finalize_now}) установлен для записи {diary_entry.id}")

        # 7. Возврат результата
        return {
            'success': True, # В данном случае, если ИИ не вернул ошибку, считаем успехом
            'entry': diary_entry,
            'analysis': await sync_to_async(lambda: diary_entry.analysis)(), # Получаем обновленный объект
            'formatted_message_ai': analysis_text, # Текст для отправки пользователю
        }

    async def process_user_comment_logic(
        self,
        user: User,
        diary_entry: DiaryEntry,
        user_comment_text: str,
        language: str
    ) -> Dict[str, Any]:
        """
        Выполняет бизнес-логику обработки комментария пользователя:
        - Сохранение комментария в DiaryEntry
        - Сброс флага анализа дня
        - Вызов ИИ для анализа комментария
        - Обновление PsychoAnalysis
        - Возврат результата для хендлера.

        Args:
            user (User): Пользователь.
            diary_entry (DiaryEntry): Запись, к которой добавляется комментарий.
            user_comment_text (str): Текст комментария.
            language (str): Язык.

        Returns:
            Dict[str, Any]: Результат обработки.
        """
        # 1. Сохранение комментария
        diary_entry.user_comment = user_comment_text
        await sync_to_async(diary_entry.save)(update_fields=['user_comment'])
        logger.debug(f"[process_user_comment_logic] Комментарий сохранён для записи {diary_entry.id}, пользователь {user.telegram_id}")

        # 2. Сброс флага анализа дня
        combined_entry_for_day = await daily_state_service.get_daily_state(user, await diary_entry.aentry_date())
        if combined_entry_for_day:
            combined_entry_for_day.reset_analysis_flag()
            await sync_to_async(combined_entry_for_day.save)(update_fields=['is_analyzed'])
            logger.debug(f"[process_user_comment_logic] Флаг is_analyzed сброшен для CombinedDiaryEntry ID {combined_entry_for_day.id}")
        else:
            logger.warning(f"[process_user_comment_logic] CombinedDiaryEntry не найден для даты {await diary_entry.aentry_date()}")

        # 3. Подготовка данных для промпта
        try:
            previous_analysis = await PsychoAnalysis.objects.aget(entry=diary_entry)
            previous_comment = previous_analysis.comment or "Нет комментария"
            previous_recommendation = previous_analysis.recommendation or "Нет рекомендации"
            previous_analysis_text = previous_analysis.analysis_text or "Анализ не предоставлен"
        except PsychoAnalysis.DoesNotExist:
            logger.warning(f"[process_user_comment_logic] Предыдущий анализ не найден для записи {diary_entry.id}")
            previous_comment = "Нет комментария"
            previous_recommendation = "Нет рекомендации"
            previous_analysis_text = "Анализ не предоставлен"

        clarification_questions = "\n".join(diary_entry.clarification_questions_asked) if diary_entry.clarification_questions_asked else "Нет уточняющих вопросов."
        clarification_answers_dict = diary_entry.clarification_answers
        clarification_answers_str = "\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]) if clarification_answers_dict else "Нет ответов на уточнения."

        personal_fields_payload = build_personal_fields_payload_for_ai(user)
        compressed_profile = user.compressed_psych_profile or {}
        if not compressed_profile:
            generated_profile = compressed_profile_service.generate_for_user(user)
            compressed_profile = generated_profile or {}
        compressed_profile = normalize_compressed_profile_for_prompt(compressed_profile)

        personal_fields_json = json.dumps(personal_fields_payload, ensure_ascii=False, separators=(",", ":"))
        compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))

        # 4. Генерация промпта и вызов ИИ
        prompt = get_prompt(
            key='comment_analysis',
            language=language,
            original_text=diary_entry.text,
            previous_comment=previous_comment,
            previous_recommendation=previous_recommendation,
            previous_analysis=previous_analysis_text,
            user_comment=user_comment_text,
            compressed_psych_profile_json=compressed_profile_json,
            personal_fields_json=personal_fields_json,
            clarification_questions=clarification_questions,
            clarification_answers=clarification_answers_str,
        )

        api_start_time = time.time()
        analysis_result = await self._call_deepseek_with_metrics(
            flow='diary.process_user_comment_logic',
            prompt=prompt,
            language=language,
        )
        total_api_time = time.time() - api_start_time

        # 5. Обработка результата ИИ
        if not analysis_result.get('success'):
            comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, is_final=True)
            mood_score = 5
        else:
            result_data = analysis_result.get('result', {})
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')

        # 6. Обновление PsychoAnalysis
        await psycho_analysis_service.create_or_update_analysis(
            entry=diary_entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {}),
            processing_time=total_api_time,
            finalize_processing=True
        )

        # 7. Возврат результата
        return {
            'success': True, # В данном случае, если ИИ не вернул ошибку, считаем успехом
            'entry': diary_entry,
            'analysis': await sync_to_async(lambda: diary_entry.analysis)(), # Получаем обновленный объект
            'formatted_message_ai': analysis_text, # Текст для отправки пользователю
        }
    
    async def prepare_combined_entry_for_analysis(self, user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
        """
        Подготавливает CombinedDiaryEntry для анализа дня.
        Если CombinedDiaryEntry не существует, но есть отдельные записи DiaryEntry,
        создаёт CombinedDiaryEntry на основе этих записей.

        Args:
            user (User): Пользователь.
            target_date (date): Дата для подготовки.

        Returns:
            Optional[CombinedDiaryEntry]: Подготовленный CombinedDiaryEntry или None, если нет записей.
        """
        logger.debug(f"[DiaryService] Подготовка CombinedDiaryEntry для анализа дня {target_date} пользователя {user.telegram_id}")
        combined_entry = await daily_state_service.get_daily_state(user, target_date)
        if combined_entry:
            logger.debug(f"[DiaryService] CombinedDiaryEntry ID {combined_entry.id} уже существует для {user.telegram_id}, {target_date}.")
            return combined_entry
        logger.info(f"[DiaryService] CombinedDiaryEntry не найден для {user.telegram_id} за {target_date}, проверяем отдельные записи.")
        entries = await self.get_user_entries_for_date(user, target_date)
        if not entries:
            logger.warning(f"[DiaryService] Нет записей для {user.telegram_id} за {target_date}, подготовка невозможна.")
            return None
        logger.debug(f"[DiaryService] Найдено {len(entries)} отдельных записей для {user.telegram_id}, {target_date}. Создаём CombinedDiaryEntry.")
        combined_text = await self.get_combined_entry_text(user, target_date, entries_list=entries)
        combined_entry = await self.get_or_create_daily_state(user=user, target_date=target_date, initial_text=combined_text)
        combined_entry.text = combined_text
        combined_entry.entry_count = len(entries)
        await combined_entry.asave(update_fields=['text', 'entry_count'])
        logger.debug(f"[DiaryService] Создан/обновлён CombinedDiaryEntry ID {combined_entry.id} для анализа {user.telegram_id}, {target_date}.")
        return combined_entry

    @async_error_handler('diary_service')
    async def process_first_onboarding_entry_logic(self,
                                      user: User,
                                      entry_text: str,
                                      language: str,
                                      entry_datetime: datetime = None) -> Dict[str, Any]:
        """
        Выполняет бизнес-логику обработки ПЕРВОЙ текстовой записи пользователя в онбординге.
        Использует специальный промпт 'incremental_day_analysis_first_entry'.
        НЕ создаёт задания и НЕ запускает уточнения.

        Args:
            user (User): Пользователь.
            entry_text (str): Текст записи.
            language (str): Язык.
            entry_datetime (datetime, optional): Время создания записи. Defaults to None.

        Returns:
            Dict[str, Any]: Результат обработки. Содержит:
                - 'success' (bool): Успешность операции (после валидации ИИ).
                - 'entry' (DiaryEntry): Созданная запись.
                - 'analysis' (PsychoAnalysis): Созданный анализ.
                - 'formatted_message_ai' (str): Форматированный текст для отправки пользователю
                  (может быть взят из 'analysis_text', 'comment', 'recommendation').
                - 'mood_score' (int): Оценка настроения.
                - 'comment' (str): Комментарий ИИ.
                - 'recommendation' (str): Рекомендация ИИ.
        """
        try:
            diary_entry = await self.create_text_entry(
                user=user,
                text=entry_text,
                language=language,
                entry_datetime=entry_datetime
            )
            logger.debug(f"[process_first_onboarding_entry_logic] Создана запись ID {diary_entry.id} для пользователя {user.telegram_id}")
            combined_entry, _ = await self.get_or_update_daily_state_with_entries(user, diary_entry)
            entry_date = await diary_entry.aentry_date()
            logger.debug(f"[process_first_onboarding_entry_logic] Обновлен CombinedDiaryEntry ID {combined_entry.id} для пользователя {user.telegram_id}")
            user_profile_data = await user.aget_profile_data()
            try:
                user_tz_str = user.timezone if user.timezone else 'UTC'
                user_tz = pytz.timezone(user_tz_str)
                created_at = diary_entry.created_at
                if created_at.tzinfo is None:
                    created_at = pytz.utc.localize(created_at)
                localized_time = created_at.astimezone(user_tz)
                new_entry_creation_time_local = _format_entry_datetime_for_prompt(localized_time, language)
                logger.debug(f"[process_first_onboarding_entry_logic] Локализованное время создания первой записи {diary_entry.id}: {new_entry_creation_time_local}")
            except Exception as e:
                logger.error(f"[process_first_onboarding_entry_logic] Ошибка при определении локального времени для первой записи {diary_entry.id}: {e}")
                new_entry_creation_time_local = _format_entry_datetime_for_prompt(diary_entry.created_at, language)
            prompt = get_prompt(
                key='incremental_day_analysis_first_entry',
                language=language,
                new_entry_text=diary_entry.text,
                new_entry_creation_time_local=new_entry_creation_time_local,
                first_name=user.first_name or user.username or f'Пользователь {user.telegram_id}',
                user_profile=user_profile_data,
            )
            logger.debug(f"[process_first_onboarding_entry_logic] Используется промпт: incremental_day_analysis_first_entry, для пользователя {user.telegram_id}")
            api_start_time = time.time()
            analysis_result = await self._call_deepseek_with_metrics(
                flow='diary.process_first_onboarding_entry_logic',
                prompt=prompt,
                language=language,
            )
            total_api_time = time.time() - api_start_time
            if not analysis_result.get('success'):
                comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, is_final=True)
                mood_score = 5
                is_valid_ai = False 
                result_data = {}
            else:
                result_data = analysis_result.get('result', {})
                mood_score = result_data.get('mood_score', 5)
                comment = result_data.get('comment', get_message('no_comment', language))
                recommendation = result_data.get('recommendation', get_message('no_recommendation', language))
                analysis_text = result_data.get('analysis', 'Текст проанализирован.')
                is_valid_ai = result_data.get('is_valid', True)
            if not is_valid_ai:
                validation_comment_ai = result_data.get('validation_comment', '')
                formatted_message_ai = result_data.get('formatted_message', '')
                logger.warning(f"[process_first_onboarding_entry_logic] Первая запись пользователя {user.telegram_id} не прошла валидацию ИИ: {validation_comment_ai}")
                return {
                    'success': False,
                    'entry': None,
                    'formatted_message_ai': formatted_message_ai,
                }
            analysis_obj = await psycho_analysis_service.create_or_update_analysis(
                entry=diary_entry,
                mood_score=mood_score,
                comment=comment,
                recommendation=recommendation,
                analysis_text=analysis_text,
                api_response=analysis_result.get('api_response', {}),
                processing_time=total_api_time,
                finalize_processing=True
            )
            logger.debug(f"[process_first_onboarding_entry_logic] Создан/обновлен PsychoAnalysis ID {analysis_obj.id} для записи {diary_entry.id}")
            new_ai_state_data = result_data.get('updated_ai_state_data', analysis_text)
            await daily_state_service.update_daily_state(
                combined_entry=combined_entry,
                new_ai_state_data=new_ai_state_data,
                latest_mood_score=mood_score
            )
            logger.debug(f"[process_first_onboarding_entry_logic] Обновлен CombinedDiaryEntry ID {combined_entry.id} с новым состоянием")
            return {
                'success': True,
                'entry': diary_entry,
                'analysis': analysis_obj,
                'formatted_message_ai': analysis_text,
                'mood_score': mood_score,
                'comment': comment,
                'recommendation': recommendation,
            }

        except Exception as e:
            logger.error(f"[process_first_onboarding_entry_logic] Критическая ошибка: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

diary_service = DiaryService()

#============================================УДОБНЫЕ ФУНКЦИИ=================================================
async def create_text_entry(user: User, text: str, language: str = 'ru', entry_datetime: datetime = None) -> DiaryEntry:
    """Удобная функция для создания текстовой записи"""
    return await diary_service.create_text_entry(user, text, language, entry_datetime)

async def create_voice_entry(
        user: User,
        voice_file_id: str,
        duration: int,
        recognized_text: str,
        language: str = 'ru',
        entry_datetime: datetime = None,
        speechkit_api_response: Optional[Dict[str, Any]] = None,
        deepseek_api_response: Optional[Dict[str, Any]] = None) -> DiaryEntry:
    """Удобная функция для создания голосовой записи"""
    return await diary_service.create_voice_entry(user, voice_file_id, duration, recognized_text, language, entry_datetime, speechkit_api_response, deepseek_api_response)

async def get_user_entries_for_date(user: User, target_date: date) -> List[DiaryEntry]:
    """Удобная функция для получения записей за дату"""
    return await diary_service.get_user_entries_for_date(user, target_date)

async def get_user_entry_by_id(user: User, entry_id: int) -> Optional[DiaryEntry]:
    """Удобная функция для получения записи пользователя по ID."""
    return await diary_service.get_user_entry_by_id(user, entry_id)

async def get_combined_entry_with_analysis_for_date(
    user: User,
    target_date: date,
) -> Optional[CombinedDiaryEntry]:
    """Удобная функция для получения CombinedDiaryEntry за дату с daily_analysis."""
    return await diary_service.get_combined_entry_with_analysis_for_date(user, target_date)

async def get_analysis_for_entry(entry: DiaryEntry) -> Optional[PsychoAnalysis]:
    """Удобная функция для получения PsychoAnalysis для записи."""
    return await diary_service.get_analysis_for_entry(entry)

async def get_combined_entry_text(
    user: User, 
    target_date: date, 
    entries_list: Optional[List[DiaryEntry]] = None
) -> str:
    """Удобная функция для получения объединенного текста (с учетом часового пояса)."""
    return await diary_service.get_combined_entry_text(user, target_date, entries_list)

async def delete_entry(entry_id: int, user: User) -> bool:
    """Удобная функция для удаления записи"""
    return await diary_service.delete_entry(entry_id, user)

async def get_days_with_entries(user: User, year: int, month: int) -> set:
    """Удобная функция для получения дней с записями"""
    return await diary_service.get_days_with_entries(user, year, month)

async def delete_all_entries_for_day(user: User, target_date: date) -> bool:
    """Удобная асинхронная функция для удаления всех записей за день."""
    return await diary_service.delete_all_entries_for_day(user, target_date)
  
async def get_entry_date(entry: DiaryEntry) -> date:
        try:
            user = await entry.user.aget()
            user_timezone_str = user.timezone or 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            created_at = entry.created_at
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            return created_at.astimezone(user_tz).date()
        except Exception as e:
            logger.error(f"Ошибка при получении даты записи {entry.id}: {e}")
            return entry.created_at.date()
        
def get_user_entries_for_date_sync(user: User, target_date: date) -> List[DiaryEntry]:
    """
    Синхронная удобная функция для получения записей за дату.
    """
    from asgiref.sync import async_to_sync
    return async_to_sync(diary_service.get_user_entries_for_date)(user, target_date)

async def process_new_entry_logic(
    user: User,
    entry_text: str,
    language: str,
    entry_datetime: datetime = None
) -> Dict[str, Any]:
    """Удобная функция для обработки новой записи."""
    return await diary_service.process_new_entry_logic(user, entry_text, language, entry_datetime)

async def process_new_entry_use_case(
    user: User,
    entry_text: str,
    language: str,
    entry_datetime: datetime = None
) -> ServiceResponse:
    """Удобная функция для универсального use-case обработки новой записи."""
    return await diary_service.process_new_entry_use_case(user, entry_text, language, entry_datetime)

async def process_clarification_answers_logic(
    user: User,
    diary_entry: DiaryEntry,
    clarification_answers_dict: Dict[str, str],
    language: str
) -> Dict[str, Any]:
    """Удобная функция для обработки уточнений."""
    return await diary_service.process_clarification_answers_logic(user, diary_entry, clarification_answers_dict, language)

async def process_clarification_answers_use_case(
    user: User,
    diary_entry: DiaryEntry,
    clarification_answers_dict: Dict[str, str],
    language: str
) -> ServiceResponse:
    """Удобная функция для универсального use-case уточнений."""
    return await diary_service.process_clarification_answers_use_case(user, diary_entry, clarification_answers_dict, language)

async def process_user_comment_logic(
    user: User,
    diary_entry: DiaryEntry,
    user_comment_text: str,
    language: str
) -> Dict[str, Any]:
    """Удобная функция для обработки комментария."""
    return await diary_service.process_user_comment_logic(user, diary_entry, user_comment_text, language)

async def process_user_comment_use_case(
    user: User,
    diary_entry: DiaryEntry,
    user_comment_text: str,
    language: str
) -> ServiceResponse:
    """Удобная функция для универсального use-case комментария пользователя."""
    return await diary_service.process_user_comment_use_case(user, diary_entry, user_comment_text, language)

async def process_entry_edit_use_case(
    user: User,
    entry_id: int,
    new_text: str,
    language: str,
    target_date_iso: Optional[str] = None,
) -> ServiceResponse:
    """Удобная функция для универсального use-case редактирования записи."""
    return await diary_service.process_entry_edit_use_case(
        user=user,
        entry_id=entry_id,
        new_text=new_text,
        language=language,
        target_date_iso=target_date_iso,
    )

async def process_delete_specific_entry_use_case(
    user: User,
    entry_id: int,
    language: str,
    target_date_iso: str,
) -> ServiceResponse:
    """Удобная функция для универсального use-case подтверждения удаления записи."""
    return await diary_service.process_delete_specific_entry_use_case(
        user=user,
        entry_id=entry_id,
        language=language,
        target_date_iso=target_date_iso,
    )

async def process_cancel_delete_specific_entry_use_case(
    user: User,
    language: str,
    target_date_iso: str,
) -> ServiceResponse:
    """Удобная функция для универсального use-case отмены удаления записи."""
    return await diary_service.process_cancel_delete_specific_entry_use_case(
        user=user,
        language=language,
        target_date_iso=target_date_iso,
    )

async def prepare_combined_entry_for_analysis(user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
    """Удобная функция для подготовки CombinedDiaryEntry для анализа."""
    return await diary_service.prepare_combined_entry_for_analysis(user, target_date)

async def process_first_onboarding_entry_logic(user: User,entry_text: str,language: str,entry_datetime: datetime = None) -> Dict[str, Any]:
    """Удобная функция для обработки первой записи в онбординге."""
    return await diary_service.process_first_onboarding_entry_logic(user, entry_text, language, entry_datetime)

async def process_first_onboarding_entry_use_case(
    user: User,
    entry_text: str,
    language: str,
    entry_datetime: datetime = None
) -> ServiceResponse:
    """Удобная функция для универсального use-case первой записи в онбординге."""
    return await diary_service.process_first_onboarding_entry_use_case(user, entry_text, language, entry_datetime)