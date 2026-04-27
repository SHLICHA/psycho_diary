# /home/shlicha/psycho_diary/diary/services/user_profile_change_analysis_service.py
"""
Сервис для выполнения анализа изменений психологического профиля пользователя
на основе сравнения текущего профиля и исторических слепков (UserProfileHistory).
"""

import logging
from typing import Dict, Any, Optional, List
import json

from asgiref.sync import sync_to_async
from django.core.serializers.json import DjangoJSONEncoder

from users.models import User, UserProfileHistory
from core.profile_field_utils import build_personal_fields_payload_for_ai, normalize_compressed_profile_for_prompt
from diary.models import WeeklyAnalysis
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from diary.services.compressed_profile_service import compressed_profile_service

logger = logging.getLogger(__name__)

class UserProfileChangeAnalysisService:
    """Сервис для анализа изменений профиля пользователя."""

    async def perform_profile_change_analysis(
        self, 
        user: User, 
        current_weekly_analysis: WeeklyAnalysis,
        num_snapshots_to_compare: int = 3
    ) -> Dict[str, Any]:
        """
        Выполняет анализ изменений профиля пользователя.

        Args:
            user: Пользователь.
            current_weekly_analysis: Объект текущего WeeklyAnalysis, в который будет сохранён результат.
            num_snapshots_to_compare: Количество исторических слепков для сравнения (по умолчанию 3).

        Returns:
            Dict[str, Any]: Результат операции.
                - success (bool): Успешность операции.
                - message (str): Сообщение о результате.
                - error (Optional[str]): Сообщение об ошибке, если есть.
        """
        logger.debug(f"[UserProfileChangeAnalysisService] Начало анализа изменений профиля для пользователя {user.telegram_id}")

        try:
            # 1. Собрать контекст: текущий профиль и исторические слепки
            context = await self._gather_change_context(user, num_snapshots_to_compare)
            if not context.get('historical_snapshots'):
                 logger.warning(f"[UserProfileChangeAnalysisService] Недостаточно исторических данных для анализа изменений пользователя {user.telegram_id}")
                 # Даже если нет исторических данных, можно сохранить пустой отчёт
                 await self._save_changes_summary(current_weekly_analysis, {})
                 return {
                    "success": True, # Считаем это успешным завершением, если нет данных для сравнения
                    "message": "Недостаточно исторических данных для анализа изменений.",
                    "error": None
                }

            logger.debug(f"[UserProfileChangeAnalysisService] Контекст для анализа изменений собран для {user.telegram_id}")

            # 2. Сформировать промпт
            prompt = get_prompt(
                key='profile_change_analysis',
                language=user.language,
                current_compressed_psych_profile_json=context['current_compressed_psych_profile_json'],
                current_personal_fields_json=context['current_personal_fields_json'],
                current_personality_description=context['current_personality_description'],
                historical_snapshots_json=context['historical_snapshots_str'],
                num_snapshots=num_snapshots_to_compare
            )
            logger.debug(f"[UserProfileChangeAnalysisService] Промпт анализа изменений сформирован для {user.telegram_id} (длина: {len(prompt)} символов)")

            # 3. Вызвать ИИ
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt,
                language=user.language,
                max_retries = 5,
                timeout_per_attempt=150 # Возможно, анализ сложнее, увеличим таймаут
            )
            logger.debug(f"[UserProfileChangeAnalysisService] Ответ API для анализа изменений: success={api_result.get('success')}")

            # 4. Обработать результат ИИ
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[UserProfileChangeAnalysisService] Ошибка API при анализе изменений: {error_msg}")
                # Даже при ошибке ИИ, можно сохранить информацию об ошибке или пустой результат
                await self._save_changes_summary(current_weekly_analysis, {})
                return {
                    "success": False,
                    "message": f"Ошибка при анализе изменений: {error_msg}",
                    "error": error_msg
                }

            parsed_result = api_result.get('result', {})
            logger.debug(f"[UserProfileChangeAnalysisService] Распарсенный результат изменений: {parsed_result}")

            # 5. Сохранить результат в WeeklyAnalysis
            await self._save_changes_summary(current_weekly_analysis, parsed_result)

            logger.debug(f"[UserProfileChangeAnalysisService] Результат анализа изменений сохранён в WeeklyAnalysis ID {current_weekly_analysis.id}")
            return {
                "success": True,
                "message": "Анализ изменений профиля успешно завершён.",
                "error": None
            }

        except Exception as e:
            logger.error(f"[UserProfileChangeAnalysisService] Критическая ошибка при анализе изменений для пользователя {user.telegram_id}: {e}", exc_info=True)
            try:
                 # Попробуем сохранить пустой результат в случае критической ошибки
                 await self._save_changes_summary(current_weekly_analysis, {})
            except Exception as save_error:
                 logger.error(f"[UserProfileChangeAnalysisService] Не удалось сохранить пустой результат после критической ошибки: {save_error}")
            return {
                "success": False,
                "message": "Критическая ошибка при анализе изменений.",
                "error": str(e)
            }

    async def _gather_change_context(self, user: User, num_snapshots: int) -> Dict[str, Any]:
        """
        Собирает контекст для анализа изменений: текущий профиль и последние N слепков.

        Args:
            user: Пользователь.
            num_snapshots: Количество слепков для извлечения.

        Returns:
            Dict[str, Any]: Словарь с контекстом.
        """
        logger.debug(f"[UserProfileChangeAnalysisService] Сбор контекста для анализа изменений, snapshots: {num_snapshots}")

        context = {
            'current_compressed_psych_profile_json': '{}',
            'current_personal_fields_json': '{}',
            'current_personality_description': '',
            'historical_snapshots': [],
            'historical_snapshots_str': "" # Для передачи в промпт
        }

        # --- 1. Текущий профиль ---
        current_personal_fields = build_personal_fields_payload_for_ai(user)
        context['current_personal_fields_json'] = json.dumps(current_personal_fields, cls=DjangoJSONEncoder, ensure_ascii=False)
        context['current_personality_description'] = user.personality_description or ''

        current_compressed_profile = user.compressed_psych_profile or {}
        if not current_compressed_profile:
            generated_profile = compressed_profile_service.generate_for_user(user)
            current_compressed_profile = generated_profile or {}
        normalized_compressed_profile = normalize_compressed_profile_for_prompt(current_compressed_profile)
        context['current_compressed_psych_profile_json'] = json.dumps(normalized_compressed_profile, cls=DjangoJSONEncoder, ensure_ascii=False)

        # --- 2. Исторические слепки ---
        @sync_to_async
        def _get_snapshots_sync():
            return list(
                UserProfileHistory.objects.filter(user=user)
                .order_by('-created_at')[:num_snapshots]
            )

        historical_snapshots_raw = await _get_snapshots_sync()
        # Разворачиваем список, чтобы самые старые слепки были первыми в списке для ИИ
        historical_snapshots_raw.reverse()

        historical_snapshots_formatted = []
        for snapshot in historical_snapshots_raw:
            snapshot_personal_fields = build_personal_fields_payload_for_ai(snapshot)
            snapshot_compressed_profile = getattr(snapshot, 'compressed_psych_profile', None) or {}
            snapshot_data = {
                'created_at': snapshot.created_at.date().isoformat(),
                'compressed_psych_profile': snapshot_compressed_profile,
                'personal_fields': snapshot_personal_fields,
                'personality_description': snapshot.personality_description or '',
            }
            historical_snapshots_formatted.append(snapshot_data)

        context['historical_snapshots'] = historical_snapshots_formatted
        # Сериализуем список слепков в строку для передачи в промпт
        context['historical_snapshots_str'] = json.dumps(historical_snapshots_formatted, cls=DjangoJSONEncoder, ensure_ascii=False)

        logger.debug(f"[UserProfileChangeAnalysisService] Контекст для анализа изменений собран. Найдено {len(historical_snapshots_formatted)} слепков.")
        return context

    async def _save_changes_summary(self, weekly_analysis: WeeklyAnalysis, changes_summary: Dict[str, Any]):
        """
        Сохраняет резюме изменений в объект WeeklyAnalysis.

        Args:
            weekly_analysis: Объект WeeklyAnalysis.
            changes_summary: Словарь с результатами анализа изменений.
        """
        logger.debug(f"[UserProfileChangeAnalysisService] Сохранение profile_changes_summary в WeeklyAnalysis ID {weekly_analysis.id}")
        try:
            weekly_analysis.profile_changes_summary = changes_summary
            # Обновляем только это поле, чтобы не перезаписать другие
            await sync_to_async(weekly_analysis.save)(update_fields=['profile_changes_summary'])
            logger.debug(f"[UserProfileChangeAnalysisService] profile_changes_summary сохранено в WeeklyAnalysis ID {weekly_analysis.id}")
        except Exception as e:
            logger.error(f"[UserProfileChangeAnalysisService] Ошибка при сохранении profile_changes_summary в WeeklyAnalysis ID {weekly_analysis.id}: {e}", exc_info=True)
            # Не вызываем raise, чтобы основной процесс не прерывался из-за ошибки сохранения результата


# Глобальный экземпляр сервиса
user_profile_change_analysis_service = UserProfileChangeAnalysisService()

# Удобная функция
async def perform_profile_change_analysis(user: User, current_weekly_analysis: WeeklyAnalysis, num_snapshots_to_compare: int = 3) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения анализа изменений профиля.
    """
    return await user_profile_change_analysis_service.perform_profile_change_analysis(user, current_weekly_analysis, num_snapshots_to_compare)
