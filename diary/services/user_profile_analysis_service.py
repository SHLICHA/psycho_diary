# /home/shlicha/psycho_diary/diary/services/user_profile_analysis_service.py
"""
Сервис для выполнения глубокого анализа и обновления психологического профиля пользователя.
"""

import logging
import asyncio
from datetime import datetime, date, timedelta, timezone as dt_timezone
from typing import Dict, Any, Optional, List
import json
import re

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from users.models import User, UserProfileHistory
from diary.models import WeeklyAnalysis
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from core.profile_field_utils import (
    PERSONAL_LIST_FIELDS,
    build_personal_fields_payload_for_ai,
    compact_weighted_items,
    compact_personality_traits,
    convert_to_weighted_format,
    normalize_compressed_profile_for_prompt,
)
from diary.services.compressed_profile_service import compressed_profile_service
from diary.services.profile_cluster_service import local_profile_cluster_service

logger = logging.getLogger(__name__)

class UserProfileAnalysisService:
    """Сервис для анализа и обновления психологического профиля пользователя."""

    FIELD_PRECLEANUP_CONCURRENCY = 3

    async def perform_user_profile_analysis(self, user: User) -> Dict[str, Any]:
        """
        Выполняет полный цикл анализа профиля пользователя.
        Собирает данные, вызывает ИИ, сохраняет результат и историю.

        Args:
            user: Пользователь.

        Returns:
            Dict[str, Any]: Результат операции.
                - success (bool): Успешность операции.
                - message (str): Сообщение о результате.
                - error (Optional[str]): Сообщение об ошибке, если есть.
        """
        logger.debug(f"[UserProfileAnalysisService] Начало анализа профиля для пользователя {user.telegram_id}")

        try:
            await self._run_profile_field_precleanup(user)
            await self._create_profile_snapshot(user)
            logger.debug(f"[UserProfileAnalysisService] Слепок профиля создан для пользователя {user.telegram_id}")
            context = await self._gather_user_context(user)
            if not context.get('has_data'):
                 logger.warning(f"[UserProfileAnalysisService] Недостаточно данных для анализа профиля пользователя {user.telegram_id}")
                 return {
                    "success": False,
                    "message": "Недостаточно данных для анализа профиля.",
                    "error": "no_data"
                }
            logger.debug(f"[UserProfileAnalysisService] Контекст собран для пользователя {user.telegram_id}")
            prompt = get_prompt(
                key='user_profile_analysis',
                language=user.language,
                personality_description=context['personality_description'],
                compressed_psych_profile_json=context['compressed_psych_profile_json'],
                personal_fields_json=context['personal_fields_json'],
                recent_weekly_analyses=context['recent_weekly_analyses'],
            )
            logger.debug(f"[UserProfileAnalysisService] Промпт сформирован для {user.telegram_id} (длина: {len(prompt)} символов)")
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt, 
                language=user.language,
                max_retries = 5,
                timeout_per_attempt=150
            )
            logger.debug(f"[UserProfileAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[UserProfileAnalysisService] Ошибка API при анализе профиля: {error_msg}")
                return {
                    "success": False,
                    "message": f"Ошибка при анализе профиля: {error_msg}",
                    "error": error_msg
                }
            parsed_result = api_result.get('result', {})
            logger.debug(f"[UserProfileAnalysisService] Распарсенный результат от API: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else type(parsed_result)}")
            update_success = await self._update_user_profile_from_analysis(user, parsed_result)
            if not update_success:
                 logger.error(f"[UserProfileAnalysisService] Не удалось обновить профиль пользователя {user.telegram_id} после анализа.")
                 return {
                    "success": False,
                    "message": "Ошибка при обновлении профиля пользователя.",
                    "error": "update_failed"
                }
            logger.debug(f"[UserProfileAnalysisService] Профиль пользователя {user.telegram_id} успешно обновлен.")
            return {
                "success": True,
                "message": "Профиль пользователя успешно обновлен.",
                "error": None
            }
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Критическая ошибка при анализе профиля для пользователя {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Критическая ошибка при анализе профиля.",
                "error": str(e)
            }

    async def _run_profile_field_precleanup(self, user: User) -> Dict[str, Any]:
        """Pre-cleanup list-полей через AI по блокам с fail-safe fallback."""
        stats: Dict[str, Any] = {
            "processed_fields": 0,
            "updated_fields": [],
            "fallback_fields": [],
            "errors": {},
        }
        updates: Dict[str, List[Dict[str, Any]]] = {}
        tasks: List[asyncio.Task] = []
        semaphore = asyncio.Semaphore(self.FIELD_PRECLEANUP_CONCURRENCY)

        for field_name in PERSONAL_LIST_FIELDS:
            raw_items = getattr(user, field_name, None)
            if not isinstance(raw_items, list) or not raw_items:
                continue

            stats["processed_fields"] += 1
            tasks.append(
                asyncio.create_task(
                    self._precleanup_single_field(
                        field_name=field_name,
                        raw_items=raw_items,
                        language=user.language,
                        semaphore=semaphore,
                    )
                )
            )

        if tasks:
            results = await asyncio.gather(*tasks)
        else:
            results = []

        for result in results:
            field_name = result['field_name']
            if result['used_fallback']:
                stats["fallback_fields"].append(field_name)
                if result.get('error'):
                    stats["errors"][field_name] = result['error']

            if result['updated']:
                updates[field_name] = result['cleaned_items']
                stats["updated_fields"].append(field_name)

        if updates:
            await self._save_profile_list_fields(user, updates)
            logger.info(
                f"[UserProfileAnalysisService] Pre-cleanup обновил поля пользователя {user.telegram_id}: "
                f"{stats['updated_fields']}"
            )

        if stats["fallback_fields"]:
            logger.warning(
                f"[UserProfileAnalysisService] Pre-cleanup fallback для пользователя {user.telegram_id}: "
                f"{stats['fallback_fields']}"
            )

        return stats

    async def _precleanup_single_field(
        self,
        *,
        field_name: str,
        raw_items: List[Any],
        language: str,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        prepared_items = compact_weighted_items(raw_items)
        if not prepared_items:
            return {
                'field_name': field_name,
                'updated': False,
                'used_fallback': False,
                'error': None,
                'cleaned_items': prepared_items,
            }

        try:
            local_result = await sync_to_async(local_profile_cluster_service.cluster_items)(
                prepared_items,
                field_name=field_name,
            )
            cleaned_items = local_result.get('cleaned_items') or []
            if not isinstance(cleaned_items, list):
                raise ValueError('local_cluster_payload_invalid')

            # Локальный путь не должен раздувать список относительно входа.
            if len(cleaned_items) > len(prepared_items):
                raise ValueError(
                    f'local_cluster_growth_rejected: local={len(cleaned_items)} > before={len(prepared_items)}'
                )

            cleaned_items = self._normalize_cleaned_items(cleaned_items, prepared_items)
            return {
                'field_name': field_name,
                'updated': cleaned_items != prepared_items,
                'used_fallback': False,
                'error': None,
                'cleaned_items': cleaned_items,
            }

        except Exception as cleanup_error:
            logger.warning(
                f"[UserProfileAnalysisService] Local pre-cleanup failed for '{field_name}', falling back to DeepSeek: {cleanup_error}"
            )
            return await self._precleanup_single_field_with_deepseek(
                field_name=field_name,
                prepared_items=prepared_items,
                language=language,
                semaphore=semaphore,
                error_text=str(cleanup_error),
            )

    async def _precleanup_single_field_with_deepseek(
        self,
        *,
        field_name: str,
        prepared_items: List[Dict[str, Any]],
        language: str,
        semaphore: asyncio.Semaphore,
        error_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback pre-cleanup через DeepSeek, если локальная кластеризация недоступна."""
        try:
            field_items_json = json.dumps(
                prepared_items,
                cls=DjangoJSONEncoder,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            prompt = get_prompt(
                key='profile_field_cleanup',
                language=language,
                field_name=field_name,
                field_items_json=field_items_json,
            )

            async with semaphore:
                api_result = await deepseek_api_service.send_prompt_and_parse(
                    prompt,
                    language=language,
                    max_retries=2,
                    timeout_per_attempt=180,
                )

            if not api_result.get('success'):
                raise ValueError(api_result.get('error', 'cleanup_request_failed'))

            parsed = api_result.get('result', {})
            ai_items = self._extract_cleaned_items(parsed, field_name)
            if not ai_items:
                raise ValueError('cleanup_payload_empty')

            if len(ai_items) > len(prepared_items):
                raise ValueError(
                    f'cleanup_growth_rejected: ai={len(ai_items)} > before={len(prepared_items)}'
                )

            cleaned_items = self._normalize_cleaned_items(ai_items, prepared_items)
            return {
                'field_name': field_name,
                'updated': cleaned_items != prepared_items,
                'used_fallback': True,
                'error': error_text,
                'cleaned_items': cleaned_items,
            }

        except Exception as cleanup_error:
            logger.warning(
                f"[UserProfileAnalysisService] Pre-cleanup no-op for '{field_name}': {cleanup_error}"
            )
            return {
                'field_name': field_name,
                'updated': False,
                'used_fallback': True,
                'error': str(cleanup_error),
                'cleaned_items': prepared_items,
            }

    def _normalize_cleaned_items(
        self,
        ai_items: List[Dict[str, Any]],
        original_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Нормализует AI-результат очистки поля перед replace:
        - Конвертирует в weighted-формат через convert_to_weighted_format.
        - Сохраняет историю дат: added_at=min, last_seen=max между
          исходными и очищенными элементами для совпадающих canonical-ключей.
        """
        original_by_canonical: Dict[str, Dict[str, Any]] = {}
        for item in original_items:
            key = self._canonical_key(str(item.get('value', '')))
            if key:
                original_by_canonical[key] = item

        today = timezone.now().date().isoformat()
        result = []
        for item in convert_to_weighted_format(ai_items):
            key = self._canonical_key(str(item.get('value', '')))
            orig = original_by_canonical.get(key)

            orig_added_at = orig.get('added_at') if orig else None
            orig_last_seen = orig.get('last_seen') if orig else None
            item_added_at = item.get('added_at')
            item_last_seen = item.get('last_seen')

            merged_added_at = self._pick_datetime_value(
                values=[orig_added_at, item_added_at],
                strategy='min',
            )
            merged_last_seen = self._pick_datetime_value(
                values=[orig_last_seen, item_last_seen],
                strategy='max',
            )

            if orig:
                item['added_at'] = merged_added_at or orig_added_at or item_added_at or today
            else:
                item['added_at'] = merged_added_at or item_added_at or today

            item['last_seen'] = merged_last_seen or orig_last_seen or item_last_seen or today
            result.append(item)
        return result

    def _pick_datetime_value(self, values: List[Any], strategy: str) -> Optional[str]:
        """
        Возвращает ISO-дату по стратегии min/max среди валидных datetime значений.

        strategy:
        - min: самое раннее значение
        - max: самое позднее значение
        """
        normalized: List[datetime] = []
        for raw in values:
            parsed = self._parse_datetime(raw)
            if parsed is not None:
                normalized.append(parsed)

        if not normalized:
            return None

        if strategy == 'min':
            return min(normalized).isoformat()
        if strategy == 'max':
            return max(normalized).isoformat()
        raise ValueError(f"Unknown datetime pick strategy: {strategy}")

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Преобразует дату/датавремя в timezone-aware datetime (UTC)."""
        if value is None:
            return None

        parsed: Optional[datetime] = None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except ValueError:
                try:
                    parsed_date = date.fromisoformat(raw)
                    parsed = datetime.combine(parsed_date, datetime.min.time())
                except ValueError:
                    return None
        else:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_timezone.utc)
        else:
            parsed = parsed.astimezone(dt_timezone.utc)
        return parsed

    def _canonical_key(self, value: str) -> str:
        """Canonical-ключ для нечёткого сопоставления значений."""
        normalized = re.sub(r'\s+', ' ', value.strip().lower())
        return re.sub(r'[^\w\s]', '', normalized)

    def _extract_cleaned_items(self, parsed: Any, field_name: str) -> List[Dict[str, Any]]:
        """Извлекает cleaned list из ответа AI в устойчивом формате."""
        if isinstance(parsed, list):
            return convert_to_weighted_format(parsed)
        if not isinstance(parsed, dict):
            return []

        candidates = parsed.get('cleaned_items')
        if candidates is None:
            candidates = parsed.get('items')
        if candidates is None:
            candidates = parsed.get(field_name)

        if not isinstance(candidates, list):
            return []
        return convert_to_weighted_format(candidates)

    def _fallback_cleanup_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Локальный fallback: каноническая дедупликация без лимитов количества."""
        return self._merge_cleanup_items([], items)

    def _merge_cleanup_items(
        self,
        baseline_items: List[Dict[str, Any]],
        incoming_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Детерминированный merge без count-cap: max(weight/frequency), min(added_at), max(last_seen)."""
        merged: Dict[str, Dict[str, Any]] = {}

        def _canonical(value: str) -> str:
            normalized = re.sub(r"\s+", " ", str(value).strip().lower())
            return re.sub(r"[^\w\s]", "", normalized)

        def _to_dt(value: Any):
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    return None
            return None

        def _store(item: Dict[str, Any], *, prefer_value: bool = False):
            value = str(item.get('value', '')).strip()
            if not value:
                return
            key = _canonical(value)
            if not key:
                return

            weight = max(0.0, min(1.0, float(item.get('weight', 0.5) or 0.5)))
            frequency = max(1, int(item.get('frequency', 1) or 1))
            is_stale = bool(item.get('is_stale', False))
            added_at = _to_dt(item.get('added_at'))
            last_seen = _to_dt(item.get('last_seen'))

            current = merged.get(key)
            if not current:
                merged[key] = {
                    'value': value,
                    'weight': weight,
                    'frequency': frequency,
                    'is_stale': is_stale,
                    'added_at': added_at,
                    'last_seen': last_seen,
                }
                return

            # Для AI-cleanup этапа предпочитаем формулировку из incoming.
            if prefer_value:
                current['value'] = value
            elif len(value) > len(current['value']):
                current['value'] = value

            current['weight'] = max(float(current['weight']), weight)
            current['frequency'] = max(int(current['frequency']), frequency)
            current['is_stale'] = bool(current['is_stale']) and is_stale

            if added_at and (current['added_at'] is None or added_at < current['added_at']):
                current['added_at'] = added_at
            if last_seen and (current['last_seen'] is None or last_seen > current['last_seen']):
                current['last_seen'] = last_seen

        for item in convert_to_weighted_format(baseline_items):
            _store(item)
        for item in convert_to_weighted_format(incoming_items):
            _store(item, prefer_value=True)

        now_iso = timezone.now().date().isoformat()
        result: List[Dict[str, Any]] = []
        for item in merged.values():
            result.append({
                'value': item['value'],
                'weight': float(item['weight']),
                'frequency': int(item['frequency']),
                'is_stale': bool(item['is_stale']),
                'added_at': item['added_at'].date().isoformat() if hasattr(item['added_at'], 'date') else (item['added_at'] if item['added_at'] else now_iso),
                'last_seen': item['last_seen'].date().isoformat() if hasattr(item['last_seen'], 'date') else (item['last_seen'] if item['last_seen'] else now_iso),
            })

        result.sort(
            key=lambda x: (
                bool(x.get('is_stale', False)),
                -float(x.get('weight', 0.0)),
                -int(x.get('frequency', 0)),
                x.get('value', ''),
            )
        )
        return result

    @sync_to_async
    def _save_profile_list_fields(self, user: User, updates: Dict[str, List[Dict[str, Any]]]) -> None:
        """Сохраняет обновлённые list-поля профиля после pre-cleanup."""
        with transaction.atomic():
            update_fields: List[str] = []
            for field_name, value in updates.items():
                setattr(user, field_name, value)
                update_fields.append(field_name)
            if update_fields:
                user.save(update_fields=update_fields)

    async def _create_profile_snapshot(self, user: User) -> Optional[UserProfileHistory]:
        """
        Создает снимок текущего состояния профиля пользователя и сохраняет его в истории.
        Выполняется ДО обновления профиля.
        """
        logger.debug(f"[UserProfileAnalysisService] Создание слепка профиля для пользователя {user.telegram_id}")
        try:
            @sync_to_async
            def _create_snapshot_sync():
                snapshot_payload = self._build_snapshot_payload(user)
                with transaction.atomic():
                    snapshot = UserProfileHistory(
                        user=user,
                        awareness_level=snapshot_payload['awareness_level'],
                        personality_traits=snapshot_payload['personality_traits'],
                        life_facts=snapshot_payload['life_facts'],
                        hobbies=snapshot_payload['hobbies'],
                        core_values=snapshot_payload['core_values'],
                        triggers=snapshot_payload['triggers'],
                        strengths=snapshot_payload['strengths'],
                        areas_for_growth=snapshot_payload['areas_for_growth'],
                        personality_insights=snapshot_payload['personality_insights'],
                        practical_patterns=snapshot_payload['practical_patterns'],
                        aspirations=snapshot_payload['aspirations'],
                        personality_description=snapshot_payload['personality_description'],
                    )
                    snapshot.save()
                    logger.debug(f"[SYNC] Слепок профиля ID {snapshot.id} создан для пользователя {user.telegram_id}")
                    return snapshot
            return await _create_snapshot_sync()
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при создании слепка профиля для пользователя {user.telegram_id}: {e}")
            return None

    def _build_snapshot_payload(self, user: User) -> Dict[str, Any]:
        """Готовит snapshot payload без служебного техмусора и неиспользуемых ключей."""
        return {
            'awareness_level': int(getattr(user, 'awareness_level', 0) or 0),
            'personality_traits': self._sanitize_traits_for_snapshot(getattr(user, 'personality_traits', {})),
            'life_facts': compact_weighted_items(getattr(user, 'life_facts', [])),
            'hobbies': compact_weighted_items(getattr(user, 'hobbies', [])),
            'core_values': compact_weighted_items(getattr(user, 'core_values', [])),
            'triggers': compact_weighted_items(getattr(user, 'triggers', [])),
            'strengths': compact_weighted_items(getattr(user, 'strengths', [])),
            'areas_for_growth': compact_weighted_items(getattr(user, 'areas_for_growth', [])),
            'personality_insights': self._sanitize_insights_for_snapshot(getattr(user, 'personality_insights', {})),
            'practical_patterns': compact_weighted_items(getattr(user, 'practical_patterns', [])),
            'aspirations': compact_weighted_items(getattr(user, 'aspirations', [])),
            'personality_description': self._sanitize_personality_description(getattr(user, 'personality_description', '')),
        }

    def _sanitize_traits_for_snapshot(self, traits: Any) -> Dict[str, float]:
        """Очищает personality_traits от служебных ключей и нечисловых значений."""
        result: Dict[str, float] = {}
        for item in compact_personality_traits(traits):
            key = str(item.get('value', '')).strip()
            if not key:
                continue
            lowered = key.lower()
            if key.startswith('_') or lowered in {'meta', 'metadata', 'debug', 'technical_notes', 'documentation'}:
                continue
            weight = float(item.get('weight', 0.5) or 0.5)
            result[key] = max(0.0, min(1.0, weight))
        return result

    def _sanitize_insights_for_snapshot(self, insights: Any) -> Dict[str, str]:
        """Очищает personality_insights от служебных ключей и пустых значений."""
        if not isinstance(insights, dict):
            return {}

        result: Dict[str, str] = {}
        for raw_key, raw_value in insights.items():
            key = str(raw_key or '').strip()
            if not key:
                continue
            lowered = key.lower()
            if key.startswith('_') or lowered in {'meta', 'metadata', 'debug', 'technical_notes', 'documentation'}:
                continue

            value = str(raw_value or '').strip()
            if not value:
                continue
            result[key] = value
        return result

    def _sanitize_personality_description(self, description: Any) -> str:
        """Нормализует текст описания личности для snapshot."""
        if isinstance(description, dict):
            description = description.get('text', '')
        return str(description or '').strip()

    async def _gather_user_context(self, user: User) -> Dict[str, Any]:
        """
        Собирает контекст для анализа профиля пользователя.

        Args:
            user: Пользователь.

        Returns:
            Dict[str, Any]: Словарь с контекстом.
        """
        logger.debug(f"[UserProfileAnalysisService] Сбор контекста для пользователя {user.telegram_id}")

        context = {
            'has_data': False,
            'personality_description': '',
            'compressed_psych_profile_json': '{}',
            'personal_fields_json': '{}',
            'recent_weekly_analyses': [],
        }
        context['personality_description'] = user.personality_description or ''
        personal_fields_payload = build_personal_fields_payload_for_ai(user)
        context['personal_fields_json'] = json.dumps(personal_fields_payload, cls=DjangoJSONEncoder, ensure_ascii=False)

        compressed_profile = user.compressed_psych_profile or {}
        if not compressed_profile:
            generated_profile = compressed_profile_service.generate_for_user(user)
            compressed_profile = generated_profile or {}
        normalized_profile = normalize_compressed_profile_for_prompt(compressed_profile)
        context['compressed_psych_profile_json'] = json.dumps(
            normalized_profile,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        recent_weekly_analyses_data = []
        try:
            four_weeks_ago = datetime.now().date() - timedelta(weeks=4)
            @sync_to_async
            def _get_recent_weekly_analyses_sync():
                return list(WeeklyAnalysis.objects.filter(
                    user=user, week_start_date__gte=four_weeks_ago
                ).order_by('-week_start_date'))
            recent_weekly_analyses = await _get_recent_weekly_analyses_sync()
            for wa in recent_weekly_analyses:
                wa_data = {
                    "week_start_date": wa.week_start_date.isoformat(),
                    "summary_text": wa.summary_text,
                    "progress_insights": wa.progress_insights,
                    "statistics": wa.statistics,
                    "comparison_with_previous": wa.comparison_with_previous,
                }
                recent_weekly_analyses_data.append(wa_data)
                
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при сборе WeeklyAnalysis для пользователя {user.telegram_id}: {e}")

        context['recent_weekly_analyses'] = recent_weekly_analyses_data
        if recent_weekly_analyses_data:
            context['has_data'] = True
        logger.debug(
            f"[UserProfileAnalysisService] Контекст собран для пользователя {user.telegram_id}. "
            f"WeeklyAnalyses: {len(recent_weekly_analyses_data)}"
        )
        return context

    async def _update_user_profile_from_analysis(self, user: User, parsed_result: Dict[str, Any]) -> bool:
        """
        Обновляет поля профиля пользователя на основе результата анализа ИИ.
        Обрабатывает пометки {"remove": ...} в списках и словарях.

        Args:
            user: Объект пользователя.
            parsed_result: Словарь обновлений из ответа ИИ.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.debug(f"[UserProfileAnalysisService] Обновление профиля пользователя {user.telegram_id} на основе данных ИИ.")
        logger.debug(f"[UserProfileAnalysisService] Полученные обновления: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else type(parsed_result)}")

        if not parsed_result or not isinstance(parsed_result, dict):
            logger.debug("[UserProfileAnalysisService] Нет данных для обновления профиля пользователя.")
            return True

        fields_updated = []
        updates_to_apply = {}

        try:
            from core.profile_field_utils import (
                convert_to_weighted_format,
                mark_stale_items,
                create_weighted_item,
            )
            profile_updates = parsed_result
            # Поля, которые являются списками
            list_field_names = [
                'life_facts', 'hobbies', 'core_values', 
                'triggers', 'strengths', 'areas_for_growth', 
                'practical_patterns', 'aspirations'
            ]
            # Поля, которые являются словарями
            dict_field_names = [
                'personality_traits', 'personality_insights'
            ]

            # --- Обработка списковых полей (weighted changed-format) ---
            for field_name in list_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue
                if not isinstance(updates_for_field, list):
                    logger.warning(f"[UserProfileAnalysisService] Некорректный формат для поля '{field_name}': {type(updates_for_field)}. Ожидается list.")
                    continue

                current_list = getattr(user, field_name, [])
                if not isinstance(current_list, list):
                    current_list = []

                existing_weighted = convert_to_weighted_format(current_list)

                # Строим индекс оригинальных элементов по canonical-ключу
                # чтобы сохранять added_at при replace
                original_by_canonical: Dict[str, Dict[str, Any]] = {
                    self._canonical_key(str(e.get('value', ''))): e
                    for e in existing_weighted
                    if e.get('value')
                }

                items_to_remove: List[str] = []
                new_weighted_items: List[Dict[str, Any]] = []

                for item in updates_for_field:
                    if isinstance(item, dict) and 'remove' in item:
                        remove_val = item.get('remove')
                        if isinstance(remove_val, str) and remove_val.strip():
                            items_to_remove.append(remove_val.strip())
                    elif isinstance(item, str) and item.strip():
                        new_weighted_items.append(create_weighted_item(item.strip(), weight=0.5))
                    elif isinstance(item, dict) and item.get('value'):
                        value = str(item.get('value')).strip()
                        if value:
                            new_weighted_items.append({
                                'value': value,
                                'weight': float(item.get('weight', 0.5)),
                                'frequency': int(item.get('frequency', 1)),
                                'added_at': item.get('added_at'),
                                'last_seen': item.get('last_seen'),
                                'is_stale': bool(item.get('is_stale', False)),
                            })
                    else:
                        logger.warning(f"[UserProfileAnalysisService] Неподдерживаемый элемент в '{field_name}': {item}. Пропущен.")

                # Только элементы из ответа AI + перенос added_at из оригинала
                # (replace-политика: AI возвращает полный актуальный список)
                today = timezone.now().date().isoformat()
                replaced_weighted: List[Dict[str, Any]] = []
                for item in new_weighted_items:
                    canon = self._canonical_key(str(item.get('value', '')))
                    orig = original_by_canonical.get(canon)
                    if orig:
                        item['added_at'] = orig.get('added_at') or item.get('added_at') or today
                    else:
                        item.setdefault('added_at', today)
                    item['last_seen'] = item.get('last_seen') or today
                    replaced_weighted.append(item)

                # Применяем remove-маркеры
                if items_to_remove:
                    remove_set = {val.lower() for val in items_to_remove}
                    replaced_weighted = [
                        e for e in replaced_weighted
                        if isinstance(e.get('value'), str)
                        and e.get('value', '').strip().lower() not in remove_set
                    ]

                # Если AI вернул пустой список — это подозрительно; не применяем
                if not replaced_weighted:
                    logger.warning(
                        f"[UserProfileAnalysisService] AI вернул пустой список для '{field_name}', "
                        f"поле не изменено."
                    )
                    continue

                # Anti-growth guard: не применяем рост, но пустое поле можно заполнить впервые
                if existing_weighted and len(replaced_weighted) > len(existing_weighted):
                    logger.warning(
                        f"[UserProfileAnalysisService] Growth guard: поле '{field_name}' "
                        f"выросло бы {len(existing_weighted)} -> {len(replaced_weighted)}, "
                        f"обновление отклонено."
                    )
                    continue

                replaced_weighted = mark_stale_items(replaced_weighted)

                if str(replaced_weighted) != str(current_list):
                    updates_to_apply[field_name] = replaced_weighted
                    fields_updated.append(field_name)
                    logger.debug(
                        f"[UserProfileAnalysisService] Обновлено поле '{field_name}': "
                        f"{len(current_list)} -> {len(replaced_weighted)}"
                    )

            # --- Обработка словарных полей ---
            for field_name in dict_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue
                if field_name == 'personality_traits' and isinstance(updates_for_field, list):
                    # Поддержка changed-format: [{"value": "эмпатия", "weight": 0.8}, ...]
                    updates_for_field = {
                        str(item.get('value')).strip(): float(item.get('weight', 0.5))
                        for item in updates_for_field
                        if isinstance(item, dict) and item.get('value')
                    }

                if not isinstance(updates_for_field, dict):
                    logger.warning(f"[UserProfileAnalysisService] Некорректный формат для поля '{field_name}': {type(updates_for_field)}. Ожидается dict.")
                    continue

                current_dict = getattr(user, field_name, {})
                if not isinstance(current_dict, dict):
                    current_dict = {}

                new_dict = current_dict.copy()
                for key, value in updates_for_field.items():
                    if isinstance(value, dict) and 'remove' in value:
                        # Удалить ключ из текущего словаря
                        if key in new_dict:
                            del new_dict[key]
                            logger.debug(f"[UserProfileAnalysisService] Удалён ключ '{key}' из '{field_name}'")
                    else:
                        # Обновить/добавить ключ
                        new_dict[key] = value

                updates_to_apply[field_name] = new_dict
                fields_updated.append(field_name)
                logger.debug(f"[UserProfileAnalysisService] Обновлено поле '{field_name}': {new_dict}")

            # --- Обработка строковых полей ---
            new_personality_description = profile_updates.get('personality_description')
            if isinstance(new_personality_description, str):
                updates_to_apply['personality_description'] = new_personality_description
                fields_updated.append('personality_description')
                logger.debug("[UserProfileAnalysisService] Подготовлено обновление для поля 'personality_description'")
            elif new_personality_description is not None:
                 logger.warning(f"[UserProfileAnalysisService] Некорректный формат для поля 'personality_description': {type(new_personality_description)}. Ожидается str.")

            # --- Сохранение обновлений ---
            if fields_updated:
                # Total anti-growth guard: рост только непустых полей (первичное заполнение разрешено)
                blocked: List[str] = []
                for field_name in list_field_names:
                    if field_name not in updates_to_apply:
                        continue
                    before_len = len(getattr(user, field_name, []) or [])
                    after_len = len(updates_to_apply[field_name])
                    if before_len > 0 and after_len > before_len:
                        blocked.append(field_name)

                if blocked:
                    for field_name in blocked:
                        del updates_to_apply[field_name]
                        fields_updated.remove(field_name)
                    logger.warning(
                        f"[UserProfileAnalysisService] Total anti-growth guard: "
                        f"list-обновления отклонены для непустых полей с ростом: {blocked}. "
                        f"Остались: {fields_updated}"
                    )

                if not fields_updated:
                    logger.debug(f"[UserProfileAnalysisService] Все обновления отклонены guard'ами для {user.telegram_id}.")
                    return True

                logger.debug(f"[UserProfileAnalysisService] Обновлены поля профиля пользователя {user.telegram_id}: {fields_updated}")

                @sync_to_async
                def _save_updates_sync():
                    with transaction.atomic():
                        for field, value in updates_to_apply.items():
                            setattr(user, field, value)
                        user.save(update_fields=fields_updated)
                    logger.debug(f"[SYNC] Изменения профиля пользователя {user.telegram_id} сохранены.")

                await _save_updates_sync()

                # После обновления — запускаем безопасную очистку дубликатов
                try:
                    from core.profile_field_utils import get_profile_field_utils
                    pfu = get_profile_field_utils()
                    cleanup_result = pfu.cleanup_user_profile(user)
                    if cleanup_result:
                        # Сохраняем результаты очистки
                        @sync_to_async
                        def _save_cleanup_sync():
                            with transaction.atomic():
                                for field_name in cleanup_result:
                                    new_val = getattr(user, field_name, [])
                                    if isinstance(new_val, list):
                                        setattr(user, field_name, new_val)
                                    elif isinstance(new_val, dict):
                                        setattr(user, field_name, {k: v for k, v in new_val.items() if v is not None})
                                user.save(update_fields=list(cleanup_result.keys()))
                        await _save_cleanup_sync()
                        logger.info(
                            f"[UserProfileAnalysisService] Очистка дубликатов для пользователя {user.telegram_id}: "
                            f"{cleanup_result}"
                        )
                except Exception as cleanup_error:
                    logger.warning(
                        f"[UserProfileAnalysisService] Ошибка при очистке дубликатов: {cleanup_error}"
                    )

                # После обновления профиля — сохраняем compressed_psych_profile из ответа AI
                # По RECOMENDATIONS_ANALISYS.md: AI генерирует compressed_psych_profile
                compressed_from_ai = parsed_result.get('compressed_psych_profile')
                
                if compressed_from_ai and isinstance(compressed_from_ai, dict):
                    # Используем AI-сгенерированный профиль
                    user.compressed_psych_profile = compressed_from_ai
                    await sync_to_async(user.save)(update_fields=['compressed_psych_profile'])
                    logger.debug(
                        f"[UserProfileAnalysisService] compressed_psych_profile сохранён из AI "
                        f"для пользователя {user.telegram_id}"
                    )
                else:
                    # Fallback: используем heuristic (старый способ)
                    logger.debug(
                        f"[UserProfileAnalysisService] AI не вернул compressed_psych_profile, "
                        f"используем heuristic для пользователя {user.telegram_id}"
                    )
                    try:
                        from diary.services.compressed_profile_service import compressed_profile_service
                        compressed = compressed_profile_service.generate_for_user(user)
                        if compressed:
                            user.compressed_psych_profile = compressed
                            await sync_to_async(user.save)(update_fields=['compressed_psych_profile'])
                            logger.debug(
                                f"[UserProfileAnalysisService] compressed_psych_profile сгенерирован "
                                f"(heuristic) для пользователя {user.telegram_id}"
                            )
                    except Exception as compressed_error:
                        logger.warning(
                            f"[UserProfileAnalysisService] Ошибка генерации compressed_psych_profile: {compressed_error}"
                        )

                return True
            else:
                logger.debug(f"[UserProfileAnalysisService] Нет изменений для сохранения в профиле пользователя {user.telegram_id}.")
                return True

        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}", exc_info=True)
            return False

user_profile_analysis_service = UserProfileAnalysisService()

async def perform_user_profile_analysis(user: User) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения анализа профиля пользователя.
    """
    return await user_profile_analysis_service.perform_user_profile_analysis(user)
