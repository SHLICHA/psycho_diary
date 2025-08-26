# diary/services/analysis_service.py
"""
Сервис для извлечения и сохранения инсайтов и ключевых моментов.
"""

import logging
from typing import Dict, Any, List
from asgiref.sync import sync_to_async
from django.db import transaction

from core.constants import INSIGHT_CATEGORIES
from diary.models import DiaryEntry, KeyPoint, UserInsight
from users.models import User


logger = logging.getLogger(__name__)

class AnalysisService:
    """Сервис для работы с инсайтами и ключевыми моментами анализа."""

    @sync_to_async
    def extract_and_save_insights_and_keypoints(
        self,
        entry: DiaryEntry,
        analysis_result: Dict[str, Any] # Это result_data из API
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
            entry_date = entry.entry_date # Предполагается, что это свойство есть

            # --- 1. ИЗВЛЕЧЕНИЕ ДАННЫХ ---
            # Извлекаем ключевые моменты из результата
            # Ожидаем, что API возвращает их в поле 'key_points'
            # Формат: [{'text': '...', 'type': 'emotion', 'confidence': 0.9}, ...]
            raw_key_points = analysis_result.get('key_points', [])
            if not isinstance(raw_key_points, list):
                logger.warning("key_points в результате анализа не является списком.")
                raw_key_points = []

            # Извлекаем инсайты из результата
            # Ожидаем, что API возвращает их в поле 'user_insights'
            # Формат: [{'text': '...', 'category': 'personal', 'weight': 1}, ...]
            raw_user_insights = analysis_result.get('user_insights', [])
            if not isinstance(raw_user_insights, list):
                 logger.warning("user_insights в результате анализа не является списком.")
                 raw_user_insights = []

            logger.info(f"Извлечено {len(raw_key_points)} ключевых моментов и {len(raw_user_insights)} инсайтов из результата API.")
            # -----------------------------

            # --- 2. СОХРАНЕНИЕ КЛЮЧЕВЫХ МОМЕНТОВ ---
            logger.info("Сохранение ключевых моментов...")
            keypoints_to_create = []
            for kp_data in raw_key_points:
                if not isinstance(kp_data, dict):
                     logger.warning(f"Некорректный формат ключевого момента: {kp_data}")
                     continue
                try:
                    keypoints_to_create.append(KeyPoint(
                        entry=entry,
                        text=kp_data['text'][:500], # Ограничиваем длину
                        type=kp_data.get('type', 'other')[:20], # Ограничиваем длину и даем дефолт
                        confidence=min(max(kp_data.get('confidence', 0.5), 0.0), 1.0) # Clamp 0.0 - 1.0
                    ))
                except Exception as e:
                    logger.error(f"Ошибка при подготовке KeyPoint к созданию: {e}, данные: {kp_data}")

            if keypoints_to_create:
                 try:
                     with transaction.atomic():
                         # Удаляем старые KeyPoints для этой записи (опционально, зависит от логики)
                         # KeyPoint.objects.filter(entry=entry).delete() 
                         # Если не удаляем, то будут добавляться. Пока оставим добавление.
                         
                         created_keypoints = KeyPoint.objects.bulk_create(keypoints_to_create)
                         logger.info(f"Создано {len(created_keypoints)} ключевых моментов для записи {entry.id}.")
                 except Exception as e:
                      logger.error(f"Ошибка при массовом создании KeyPoints: {e}")
            else:
                 logger.info("Нет новых ключевых моментов для сохранения.")
            # -------------------------------------

            # --- 3. СОХРАНЕНИЕ/ОБНОВЛЕНИЕ ИНСАЙТОВ ---
            # Оборачиваем в transaction.atomic(), так как используем select_for_update
            logger.info("Сохранение/обновление инсайтов пользователя...")
            insights_to_create = []
            insights_to_update = []

            try:
                # ВСЯ ЛОГИКА ПОДГОТОВКИ И СОХРАНЕНИЯ ДОЛЖНА БЫТЬ ВНУТРИ ТРАНЗАКЦИИ
                with transaction.atomic(): 
                    for insight_data in raw_user_insights:
                        if not isinstance(insight_data, dict):
                            logger.warning(f"Некорректный формат инсайта: {insight_data}")
                            continue
                        try:
                            insight_text = insight_data['text'][:500]
                            insight_category_raw = insight_data.get('category', 'other')[:20]
                            # Убедимся, что вес - целое число, минимум 1
                            insight_weight = max(int(insight_data.get('weight', 1)), 1)
                            valid_categories = [cat[0] for cat in INSIGHT_CATEGORIES]
                            if insight_category_raw in valid_categories:
                                insight_category = insight_category_raw
                            else:
                                logger.warning(f"Недопустимая категория '{insight_category_raw}' получена от API. Используется 'other'.")
                                insight_category = 'other' # Значение по умолчанию
                            insight_category = insight_category[:50]
                            # Проверяем, существует ли такой инсайт у пользователя
                            # Используем select_for_update внутри транзакции
                            try:
                                # select_for_update БЛОКИРУЕТ СТРОКУ ДО КОНЦА ТРАНЗАКЦИИ
                                existing_insight = UserInsight.objects.select_for_update().get(
                                    user=user, text=insight_text, category=insight_category
                                )
                                # Обновляем существующий
                                existing_insight.weight = min(existing_insight.weight + insight_weight, 100)
                                existing_insight.last_mentioned = entry.created_at
                                insights_to_update.append(existing_insight)
                                logger.debug(f"Найден существующий инсайт '{insight_text}' для обновления.")
                            except UserInsight.DoesNotExist:
                                # Создаем новый
                                insights_to_create.append(UserInsight(
                                    user=user,
                                    text=insight_text,
                                    category=insight_category,
                                    weight=insight_weight,
                                    last_mentioned=entry.created_at,
                                    first_mentioned=entry.created_at
                                ))
                                logger.debug(f"Подготовлен новый инсайт '{insight_text}' к созданию.")

                        except (ValueError, KeyError) as ve: # Более конкретные ошибки
                             logger.error(f"Ошибка при подготовке UserInsight (ValueError/KeyError): {ve}, данные: {insight_data}")
                        except Exception as e:
                             logger.error(f"Ошибка при подготовке UserInsight: {e}, данные: {insight_data}")

                    # --- Выполняем массовое создание и обновление ВНУТРИ ТОЙ ЖЕ ТРАНЗАКЦИИ ---
                    if insights_to_create:
                        created_insights = UserInsight.objects.bulk_create(insights_to_create)
                        logger.info(f"Создано {len(created_insights)} новых инсайтов для пользователя {user.telegram_id}.")

                    if insights_to_update:
                        # bulk_update требует указания полей для обновления
                        updated_count = UserInsight.objects.bulk_update(
                            insights_to_update, ['weight', 'last_mentioned']
                        )
                        logger.info(f"Обновлено {updated_count} существующих инсайтов для пользователя {user.telegram_id}.")

                    # Если код доходит до этой точки, транзакция коммитится автоматически
                    logger.info("Транзакция по сохранению инсайтов успешно завершена.")

            except Exception as e: # Перехватываем ошибки транзакции
                 logger.error(f"Ошибка при массовом создании/обновлении UserInsights внутри транзакции: {e}")
                 # Транзакция откатывается автоматически при выходе из блока with при исключении
                 # Можно добавить логику повтора или уведомления об ошибке
                 return False # Возвращаем False, если не удалось сохранить инсайты

            # --- Конец блока с транзакцией ---
            
            logger.info("Извлечение и сохранение инсайтов и ключевых моментов завершено.")
            return True # Возвращаем True, если всё прошло успешно

        except Exception as e:
            logger.error(f"Критическая ошибка в extract_and_save_insights_and_keypoints: {e}", exc_info=True)
            return False # Возвращаем False в случае критической ошибки

# Глобальный экземпляр сервиса
analysis_service = AnalysisService()

# Удобная асинхронная функция
async def extract_and_save_insights_and_keypoints(entry: DiaryEntry, analysis_result: Dict[str, Any]) -> bool:
    """
    Удобная асинхронная функция для извлечения и сохранения инсайтов и ключевых моментов.

    Args:
        entry: Запись дневника.
        analysis_result: Результат анализа от API.

    Returns:
        bool: True, если успешно, иначе False.
    """
    return await analysis_service.extract_and_save_insights_and_keypoints(entry, analysis_result)
