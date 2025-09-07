import logging
from typing import Dict, Any, List, Tuple
from asgiref.sync import sync_to_async
from django.db import transaction

from core.constants import INSIGHT_CATEGORIES, KEYPOINT_TYPES
from diary.models import DiaryEntry, KeyPoint, UserInsight
from users.models import User

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
                validated_text = insight_text_raw.strip()[:500] # Ограничиваем длину
                insight_category_raw = insight_data.get('category', 'other')
                valid_categories = [cat[0] for cat in INSIGHT_CATEGORIES]
                if insight_category_raw in valid_categories:
                    validated_category = insight_category_raw
                else:
                    logger.warning(f"Недопустимая категория '{insight_category_raw}' получена от API. Используется 'other'.")
                    validated_category = 'other'
                validated_category = validated_category[:50] # Ограничиваем длину категории

                # Извлечение и валидация веса
                insight_weight_raw = insight_data.get('weight', 1)
                try:
                    validated_weight = int(insight_weight_raw)
                    validated_weight = max(1, validated_weight) # Минимальный вес 1
                except (ValueError, TypeError):
                    logger.warning(f"Некорректное значение weight для инсайта: {insight_weight_raw}. Используется 1.")
                    validated_weight = 1

                validated_insights.append({
                    'text': validated_text,
                    'category': validated_category,
                    'weight': validated_weight
                })
                logger.debug(f"Инсайт провалидирован: {validated_text[:30]}...")

            except Exception as e:
                logger.error(f"Ошибка при валидации инсайта {insight_data}: {e}")

        logger.debug(f"Извлечено и провалидировано {len(validated_insights)} инсайтов.")
        return validated_insights

    @sync_to_async
    def extract_and_save_insights_and_keypoints(
        self,
        entry: DiaryEntry,
        analysis_result: Dict[str, Any]
    ) -> bool:
        """
        Извлекает и сохраняет инсайты и ключевые моменты из результата анализа.

        Args:
            entry: Запись дневника.
            analysis_result: Результат анализа от API (словарь result_data).

        Returns:
            bool: True, если операция прошла успешно, иначе False.
        """
        logger.info(f"Начало извлечения и сохранения инсайтов и ключевых моментов для записи {entry.id}")
        try:
            user = entry.user
            entry_date = entry.entry_date
            
            # === ИСПОЛЬЗУЕМ НОВЫЕ ФУНКЦИИ ДЛЯ ИЗВЛЕЧЕНИЯ И ВАЛИДАЦИИ ===
            
            # 1. Извлекаем и валидируем ключевые моменты
            raw_key_points = analysis_result.get('key_points', [])
            validated_keypoints_data = self._extract_and_validate_keypoints(raw_key_points)

            # 2. Извлекаем и валидируем инсайты
            raw_user_insights = analysis_result.get('user_insights', [])
            validated_insights_data = self._extract_and_validate_insights(raw_user_insights)

            # === СОХРАНЕНИЕ В БД ===

            # Сохраняем ключевые моменты (bulk_create)
            if validated_keypoints_data:
                keypoints_to_create = [
                    KeyPoint(
                        entry=entry,
                        text=kp_data['text'],
                        type=kp_data['type'],
                        confidence=kp_data['confidence']
                    )
                    for kp_data in validated_keypoints_data
                ]
                
                try:
                    with transaction.atomic():
                        created_keypoints = KeyPoint.objects.bulk_create(keypoints_to_create)
                        logger.info(f"Создано {len(created_keypoints)} ключевых моментов для записи {entry.id}.")
                except Exception as bulk_create_error:
                    logger.error(f"Ошибка при массовом создании KeyPoints для записи {entry.id}: {bulk_create_error}")
            else:
                logger.debug(f"Нет валидных ключевых моментов для сохранения для записи {entry.id}.")

            # Сохраняем инсайты (bulk_create и bulk_update)
            insights_to_create = []
            insights_to_update = []

            if validated_insights_data:
                try:
                    with transaction.atomic(): 
                        for insight_data in validated_insights_data:
                            try:
                                # Пытаемся найти существующий инсайт
                                existing_insight = UserInsight.objects.select_for_update().get(
                                    user=user, text=insight_data['text'], category=insight_data['category']
                                )
                                # Если найден - обновляем
                                existing_insight.weight = min(existing_insight.weight + insight_data['weight'], 100)
                                existing_insight.last_mentioned = entry.created_at
                                insights_to_update.append(existing_insight)
                                logger.debug(f"Найден существующий инсайт '{insight_data['text'][:30]}...' для обновления.")
                            except UserInsight.DoesNotExist:
                                # Если не найден - создаем новый
                                insights_to_create.append(UserInsight(
                                    user=user,
                                    text=insight_data['text'],
                                    category=insight_data['category'],
                                    weight=insight_data['weight'],
                                    last_mentioned=entry.created_at,
                                    first_mentioned=entry.created_at,
                                    source_entry=entry
                                ))
                                logger.debug(f"Подготовлен новый инсайт '{insight_data['text'][:30]}...' для создания.")

                        # Массовое создание новых инсайтов
                        if insights_to_create:
                            created_insights = UserInsight.objects.bulk_create(insights_to_create)
                            logger.info(f"Создано {len(created_insights)} новых инсайтов для пользователя {user.telegram_id}.")

                        # Массовое обновление существующих инсайтов
                        if insights_to_update:
                            updated_count = UserInsight.objects.bulk_update(
                                insights_to_update, ['weight', 'last_mentioned']
                            )
                            logger.info(f"Обновлено {updated_count} существующих инсайтов для пользователя {user.telegram_id}.")

                except Exception as bulk_ops_error:
                    logger.error(f"Ошибка при массовых операциях (создание/обновление) UserInsights для записи {entry.id}: {bulk_ops_error}")
                    return False
            else:
                logger.debug(f"Нет валидных инсайтов для сохранения для записи {entry.id}.")

            logger.info(f"Успешно завершено извлечение и сохранение инсайтов и ключевых моментов для записи {entry.id}.")
            return True
            
        except Exception as e:
            logger.error(f"Критическая ошибка в extract_and_save_insights_and_keypoints для записи {entry.id}: {e}", exc_info=True)
            return False

# Глобальный экземпляр сервиса
analysis_service = AnalysisService()

# Удобная функция (опционально)
async def extract_and_save_insights_and_keypoints(entry: DiaryEntry, analysis_result: Dict[str, Any]) -> bool:
    """
    Удобная асинхронная функция для извлечения и сохранения инсайтов и ключевых моментов.
    """
    return await analysis_service.extract_and_save_insights_and_keypoints(entry, analysis_result)
