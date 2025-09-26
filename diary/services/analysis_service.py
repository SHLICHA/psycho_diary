import logging
from typing import Dict, Any, List
from asgiref.sync import sync_to_async
from django.db import transaction

from core.constants import INSIGHT_CATEGORIES, KEYPOINT_TYPES
from diary.models import DiaryEntry

logger = logging.getLogger(__name__)

class AnalysisService:
    """Сервис для работы с инсайтами и ключевыми моментами анализа."""
    def _extract_and_validate_keypoints(self, raw_key_points: Any) -> List[Dict[str, Any]]:
        """
        Извлекает и валидирует список ключевых моментов из результата анализа.

        Args:
            raw_key_points: Сырой список key_points из API.

        Returns:
            List[Dict[str, Any]]: Список провалидированных и очищенных данных для KeyPoint.
        """
        logger.debug("Начало извлечения и валидации ключевых моментов.")
        validated_keypoints = []
        if not isinstance(raw_key_points, list):
            logger.warning("key_points в результате анализа не является списком.")
            return validated_keypoints
        for kp_data in raw_key_points:
            if not isinstance(kp_data, dict):
                logger.warning(f"Некорректный формат ключевого момента: {kp_data}")
                continue
            try:
                kp_text = kp_data.get('text')
                if not isinstance(kp_text, str) or not kp_text.strip():
                    logger.warning(f"Ключевой момент не содержит текста или текст не строка: {kp_data}")
                    continue
                validated_text = kp_text.strip()[:500]
                kp_type_raw = kp_data.get('type', 'other')
                valid_kp_types = [t[0] for t in KEYPOINT_TYPES]
                validated_type = kp_type_raw if kp_type_raw in valid_kp_types else 'other'
                validated_type = validated_type[:20]
                kp_confidence_raw = kp_data.get('confidence', 0.5)
                try:
                    validated_confidence = float(kp_confidence_raw)
                    validated_confidence = max(0.0, min(1.0, validated_confidence))
                except (ValueError, TypeError):
                    logger.warning(f"Некорректное значение confidence для ключевого момента: {kp_confidence_raw}. Используется 0.5.")
                    validated_confidence = 0.5
                validated_keypoints.append({
                    'text': validated_text,
                    'type': validated_type,
                    'confidence': validated_confidence
                })
            except Exception as e:
                logger.error(f"Ошибка при валидации ключевого момента {kp_data}: {e}")
        return validated_keypoints

    def _extract_and_validate_insights(self, raw_user_insights: Any) -> List[Dict[str, Any]]:
        """
        Извлекает и валидирует список инсайтов из результата анализа.

        Args:
            raw_user_insights: Сырой список user_insights из API.

        Returns:
            List[Dict[str, Any]]: Список провалидированных и очищенных данных для UserInsight.
        """
        logger.debug("Начало извлечения и валидации инсайтов.")
        validated_insights = []
        if not isinstance(raw_user_insights, list):
            logger.warning("user_insights в результате анализа не является списком.")
            return validated_insights
        for insight_data in raw_user_insights:
            if not isinstance(insight_data, dict):
                logger.warning(f"Некорректный формат инсайта: {insight_data}")
                continue
            try:
                insight_text_raw = insight_data.get('text')
                if not isinstance(insight_text_raw, str) or not insight_text_raw.strip():
                    logger.warning(f"Инсайт не содержит текста или текст не строка: {insight_data}")
                    continue
                validated_text = insight_text_raw.strip()[:500]
                insight_category_raw = insight_data.get('category', 'other')
                valid_categories = [cat[0] for cat in INSIGHT_CATEGORIES]
                if insight_category_raw in valid_categories:
                    validated_category = insight_category_raw
                else:
                    logger.warning(f"Недопустимая категория '{insight_category_raw}' получена от API. Используется 'other'.")
                    validated_category = 'other'
                validated_category = validated_category[:50]
                insight_weight_raw = insight_data.get('weight', 1)
                try:
                    validated_weight = int(insight_weight_raw)
                    validated_weight = max(1, validated_weight)
                except (ValueError, TypeError):
                    logger.warning(f"Некорректное значение weight для инсайта: {insight_weight_raw}. Используется 1.")
                    validated_weight = 1
                validated_insights.append({
                    'text': validated_text,
                    'category': validated_category,
                    'weight': validated_weight
                })
            except Exception as e:
                logger.error(f"Ошибка при валидации инсайта {insight_data}: {e}")
        return validated_insights

analysis_service = AnalysisService()

async def extract_and_save_insights_and_keypoints(entry: DiaryEntry, analysis_result: Dict[str, Any]) -> bool:
    """
    Удобная асинхронная функция для извлечения и сохранения инсайтов и ключевых моментов.
    """
    return await analysis_service.extract_and_save_insights_and_keypoints(entry, analysis_result)
