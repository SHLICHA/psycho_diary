"""
Сервис TTL-очистки полей психологического профиля пользователя.
"""

import logging
from copy import deepcopy
from typing import Any, Dict, List

from asgiref.sync import sync_to_async
from django.db import transaction

from core.profile_field_utils import (
    PROFILE_FIELDS,
    cleanup_stale_items,
    convert_to_weighted_format,
    mark_stale_items,
)
from diary.services.compressed_profile_service import compressed_profile_service

logger = logging.getLogger(__name__)


class ProfileCleanupService:
    """Оркеструет TTL-очистку weighted-полей профиля пользователя."""

    def _format_changed_field_summary(self, field_stats: Dict[str, Dict[str, Any]]) -> str:
        """Возвращает краткую строку со статистикой по изменённым полям."""
        parts = []
        for field_name, stats in field_stats.items():
            if not stats.get("changed"):
                continue
            parts.append(
                f"{field_name}: {stats['before_count']}->{stats['after_count']}, "
                f"stale={stats['stale_count']}, removed={stats['removed_count']}"
            )
        return "; ".join(parts)

    def cleanup_profile_fields(self, user) -> Dict[str, Any]:
        """
        Выполняет TTL-очистку полей профиля в памяти без сохранения.

        Returns:
            dict со статистикой и изменёнными полями.
        """
        result: Dict[str, Any] = {
            "processed_fields": 0,
            "changed_fields": [],
            "field_stats": {},
            "removed_items": 0,
            "stale_items": 0,
            "inspected_items": 0,
            "remaining_items": 0,
            "updated_fields": {},
        }

        for field_name in PROFILE_FIELDS:
            current_value = getattr(user, field_name, None)
            if not isinstance(current_value, list):
                continue

            result["processed_fields"] += 1
            original_items = deepcopy(current_value)
            weighted_items = convert_to_weighted_format(original_items)
            stale_marked = mark_stale_items(weighted_items)
            stale_count = sum(1 for item in stale_marked if item.get("is_stale"))
            cleaned_items = cleanup_stale_items(stale_marked)
            removed_count = max(0, len(stale_marked) - len(cleaned_items))

            result["removed_items"] += removed_count
            result["stale_items"] += stale_count
            result["inspected_items"] += len(stale_marked)
            result["remaining_items"] += len(cleaned_items)
            result["field_stats"][field_name] = {
                "before_count": len(original_items),
                "after_count": len(cleaned_items),
                "removed_count": removed_count,
                "stale_count": stale_count,
                "changed": cleaned_items != original_items,
            }

            if cleaned_items != original_items:
                result["changed_fields"].append(field_name)
                result["updated_fields"][field_name] = cleaned_items
                logger.debug(
                    f"[ProfileCleanup] User {user.telegram_id}: field={field_name}, "
                    f"before={len(original_items)}, after={len(cleaned_items)}, "
                    f"stale={stale_count}, removed={removed_count}"
                )

        return result

    async def cleanup_user_profile(self, user, rebuild_compressed: bool = True) -> Dict[str, Any]:
        """
        Выполняет TTL-очистку профиля пользователя и при необходимости
        пересобирает compressed_psych_profile.
        """
        result = {
            "success": True,
            "user_id": user.id,
            "changed": False,
            "changed_fields": [],
            "changed_fields_count": 0,
            "processed_fields": 0,
            "removed_items": 0,
            "stale_items": 0,
            "inspected_items": 0,
            "remaining_items": 0,
            "field_stats": {},
            "compressed_profile_rebuilt": False,
            "compressed_profile_action": "skipped",
            "error": None,
        }

        try:
            cleanup_result = self.cleanup_profile_fields(user)
            result.update({
                "changed": bool(cleanup_result["changed_fields"]),
                "changed_fields": cleanup_result["changed_fields"],
                "changed_fields_count": len(cleanup_result["changed_fields"]),
                "processed_fields": cleanup_result["processed_fields"],
                "removed_items": cleanup_result["removed_items"],
                "stale_items": cleanup_result["stale_items"],
                "inspected_items": cleanup_result["inspected_items"],
                "remaining_items": cleanup_result["remaining_items"],
                "field_stats": cleanup_result["field_stats"],
            })

            if not cleanup_result["changed_fields"]:
                logger.debug(
                    f"[ProfileCleanup] User {user.telegram_id}: изменений не найдено, "
                    f"processed_fields={cleanup_result['processed_fields']}, "
                    f"inspected_items={cleanup_result['inspected_items']}, "
                    f"stale_items={cleanup_result['stale_items']}"
                )
                return result

            await self._save_updated_fields(user, cleanup_result["updated_fields"])

            if rebuild_compressed:
                action = await self._rebuild_compressed_profile(user)
                result["compressed_profile_action"] = action
                result["compressed_profile_rebuilt"] = action in {"rebuilt", "cleared"}

            logger.info(
                f"[ProfileCleanup] User {user.telegram_id}: "
                f"changed_fields={cleanup_result['changed_fields']}, "
                f"changed_fields_count={len(cleanup_result['changed_fields'])}, "
                f"processed_fields={cleanup_result['processed_fields']}, "
                f"inspected_items={cleanup_result['inspected_items']}, "
                f"remaining_items={cleanup_result['remaining_items']}, "
                f"removed_items={cleanup_result['removed_items']}, "
                f"stale_items={cleanup_result['stale_items']}, "
                f"compressed_action={result['compressed_profile_action']}, "
                f"field_summary={self._format_changed_field_summary(cleanup_result['field_stats'])}"
            )
            return result
        except Exception as exc:
            logger.error(
                f"[ProfileCleanup] User {user.telegram_id}: ошибка cleanup: {exc}",
                exc_info=True,
            )
            result["success"] = False
            result["error"] = str(exc)
            return result

    @sync_to_async
    def _save_updated_fields(self, user, updated_fields: Dict[str, List[Dict[str, Any]]]) -> None:
        """Сохраняет только изменённые поля профиля пользователя."""
        if not updated_fields:
            return

        with transaction.atomic():
            for field_name, field_value in updated_fields.items():
                setattr(user, field_name, field_value)
            user.save(update_fields=list(updated_fields.keys()))

    async def _rebuild_compressed_profile(self, user) -> str:
        """Пересобирает или очищает compressed_psych_profile после cleanup."""
        profile_data = compressed_profile_service.generate_for_user(user)
        if profile_data:
            saved = await compressed_profile_service.save_for_user_async(user, profile_data)
            return "rebuilt" if saved else "rebuild_failed"

        return await self._clear_compressed_profile(user)

    @sync_to_async
    def _clear_compressed_profile(self, user) -> str:
        """Очищает compressed_psych_profile, если после cleanup профиль не генерируется."""
        with transaction.atomic():
            user.compressed_psych_profile = {}
            user.save(update_fields=["compressed_psych_profile"])
        return "cleared"


profile_cleanup_service = ProfileCleanupService()


async def cleanup_user_profile(user, rebuild_compressed: bool = True) -> Dict[str, Any]:
    """Удобная async-функция для TTL-очистки профиля пользователя."""
    return await profile_cleanup_service.cleanup_user_profile(user, rebuild_compressed)