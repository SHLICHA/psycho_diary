"""
Основной сервис анализа записей
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from diary.models import DiaryEntry, PsychoAnalysis, KeyPoint, UserInsight
from users.models import User
from diary.services.analysis.text_processor import TextProcessor
from diary.services.analysis.emotion_analyzer import EmotionAnalyzer
from diary.services.analysis.insight_extractor import InsightExtractor
from diary.services.analysis.profile_updater import ProfileUpdater

logger = logging.getLogger(__name__)

class AnalysisService:
    """Сервис для анализа записей дневника"""
    
    def __init__(self):
        """Инициализация сервиса анализа"""
        self.text_processor = TextProcessor()
        self.emotion_analyzer = EmotionAnalyzer()
        self.insight_extractor = InsightExtractor()
        self.profile_updater = ProfileUpdater()
        logger.info("Сервис анализа инициализирован")
    
    async def analyze_entry(self, entry: DiaryEntry) -> PsychoAnalysis:
        """
        Полный анализ записи дневника
        
        Args:
            entry: Запись дневника для анализа
            
        Returns:
            PsychoAnalysis: Результат анализа
        """
        logger.info(f"Начало анализа записи {entry.id} пользователя {entry.user.telegram_id}")
        
        try:
            # === 1. Предварительная обработка текста ===
            logger.info("Шаг 1: Предварительная обработка текста")
            processed_text = await self.text_processor.process_text(entry.text)
            logger.info(f"Текст обработан, длина: {len(processed_text)} символов")
            
            # === 2. Анализ эмоций ===
            logger.info("Шаг 2: Анализ эмоций")
            emotion_analysis = await self.emotion_analyzer.analyze_emotions(processed_text, entry.language)
            logger.info(f"Эмоции проанализированы: оценка {emotion_analysis['mood_score']}/10")
            
            # === 3. Извлечение ключевых моментов ===
            logger.info("Шаг 3: Извлечение ключевых моментов")
            key_points = await self.insight_extractor.extract_key_points(processed_text, entry.user, entry.language)
            logger.info(f"Извлечено {len(key_points)} ключевых моментов")
            
            # === 4. Создание анализа ===
            logger.info("Шаг 4: Создание анализа")
            analysis = await self._create_analysis(entry, emotion_analysis, key_points)
            logger.info(f"Анализ создан, ID: {analysis.id}")
            
            # === 5. Обновление профиля пользователя ===
            logger.info("Шаг 5: Обновление профиля пользователя")
            await self.profile_updater.update_user_profile(entry.user, analysis, key_points)
            logger.info("Профиль пользователя обновлен")
            
            # === 6. Сохранение ключевых моментов ===
            logger.info("Шаг 6: Сохранение ключевых моментов")
            await self._save_key_points(entry, key_points)
            logger.info("Ключевые моменты сохранены")
            
            # === 7. Обновление инсайтов пользователя ===
            logger.info("Шаг 7: Обновление инсайтов пользователя")
            await self._update_user_insights(entry.user, key_points)
            logger.info("Инсайты пользователя обновлены")
            
            logger.info(f"Полный анализ записи {entry.id} завершен успешно")
            return analysis
            
        except Exception as e:
            logger.error(f"Ошибка при анализе записи {entry.id}: {e}", exc_info=True)
            
            # Создаем анализ с ошибкой
            error_analysis = await self._create_error_analysis(entry, str(e))
            return error_analysis
    
    async def _create_analysis(self, entry: DiaryEntry, emotion_analysis: Dict[str, Any], key_points: list) -> PsychoAnalysis:
        """
        Создание анализа записи
        
        Args:
            entry: Запись дневника
            emotion_analysis: Результат анализа эмоций
            key_points: Ключевые моменты
            
        Returns:
            PsychoAnalysis: Созданный анализ
        """
        try:
            logger.info(f"Создание анализа для записи {entry.id}")
            
            # Формируем комментарий на основе анализа эмоций
            comment = emotion_analysis.get('comment', 'Анализ записан')
            
            # Формируем рекомендацию на основе ключевых моментов
            recommendation = emotion_analysis.get('recommendation', 'Продолжайте в том же духе')
            
            # Создаем анализ
            analysis = await PsychoAnalysis.objects.acreate(
                entry=entry,
                mood_score=emotion_analysis['mood_score'],
                comment=comment,
                recommendation=recommendation,
                processing_time=2.5,  # Заглушка
                insights_extracted=len(key_points),
                language=entry.language
            )
            
            logger.info(f"Анализ создан, ID: {analysis.id}")
            return analysis
            
        except Exception as e:
            logger.error(f"Ошибка при создании анализа для записи {entry.id}: {e}")
            raise
    
    async def _save_key_points(self, entry: DiaryEntry, key_points: list):
        """
        Сохранение ключевых моментов
        
        Args:
            entry: Запись дневника
            key_points: Ключевые моменты для сохранения
        """
        try:
            logger.info(f"Сохранение {len(key_points)} ключевых моментов для записи {entry.id}")
            
            for point in key_points:
                try:
                    await KeyPoint.objects.acreate(
                        entry=entry,
                        text=point['text'],
                        type=point['type'],
                        confidence=point['confidence']
                    )
                    logger.info(f"Ключевой момент '{point['text']}' сохранен")
                except Exception as point_error:
                    logger.error(f"Ошибка при сохранении ключевого момента '{point['text']}': {point_error}")
            
            logger.info(f"Все ключевые моменты для записи {entry.id} сохранены")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении ключевых моментов для записи {entry.id}: {e}")
    
    async def _update_user_insights(self, user: User, key_points: list):
        """
        Обновление инсайтов пользователя
        
        Args:
            user: Пользователь
            key_points: Ключевые моменты
        """
        try:
            logger.info(f"Обновление инсайтов пользователя {user.telegram_id}")
            
            for point in key_points:
                try:
                    # Проверяем, существует ли такой инсайт
                    insight_exists = await UserInsight.objects.filter(
                        user=user,
                        text=point['text'],
                        category=point['type']
                    ).aexists()
                    
                    if insight_exists:
                        # Увеличиваем вес существующего инсайта
                        insight = await UserInsight.objects.aget(
                            user=user,
                            text=point['text'],
                            category=point['type']
                        )
                        insight.weight += 1
                        insight.last_mentioned = datetime.now()
                        await insight.asave(update_fields=['weight', 'last_mentioned'])
                        logger.info(f"Инсайт '{point['text']}' обновлен, новый вес: {insight.weight}")
                    else:
                        # Создаем новый инсайт
                        await UserInsight.objects.acreate(
                            user=user,
                            text=point['text'],
                            category=point['type'],
                            weight=1,
                            last_mentioned=datetime.now()
                        )
                        logger.info(f"Новый инсайт '{point['text']}' создан")
                        
                except Exception as insight_error:
                    logger.error(f"Ошибка при обновлении инсайта '{point['text']}': {insight_error}")
            
            logger.info(f"Инсайты пользователя {user.telegram_id} обновлены")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении инсайтов пользователя {user.telegram_id}: {e}")
    
    async def _create_error_analysis(self, entry: DiaryEntry, error_message: str) -> PsychoAnalysis:
        """
        Создание анализа с ошибкой
        
        Args:
            entry: Запись дневника
            error_message: Сообщение об ошибке
            
        Returns:
            PsychoAnalysis: Анализ с ошибкой
        """
        try:
            logger.info(f"Создание анализа с ошибкой для записи {entry.id}")
            
            error_analysis = await PsychoAnalysis.objects.acreate(
                entry=entry,
                mood_score=5,  # Средняя оценка
                comment="Произошла ошибка при анализе",
                recommendation="Попробуйте позже",
                processing_time=0.1,  # Минимальное время
                insights_extracted=0,
                language=entry.language,
                error_message=error_message[:500]  # Ограничиваем длину
            )
            
            logger.info(f"Анализ с ошибкой создан, ID: {error_analysis.id}")
            return error_analysis
            
        except Exception as e:
            logger.error(f"Ошибка при создании анализа с ошибкой для записи {entry.id}: {e}")
            
            # Если не удалось создать даже анализ с ошибкой, возвращаем заглушку
            from unittest.mock import Mock
            mock_analysis = Mock()
            mock_analysis.id = 0
            mock_analysis.mood_score = 5
            mock_analysis.comment = "Произошла ошибка при анализе"
            mock_analysis.recommendation = "Попробуйте позже"
            return mock_analysis

# Глобальный экземпляр сервиса анализа
analysis_service = AnalysisService()

# Функция для удобного использования
async def analyze_entry(entry: DiaryEntry) -> PsychoAnalysis:
    """
    Удобная функция для анализа записи
    
    Args:
        entry: Запись дневника для анализа
        
    Returns:
        PsychoAnalysis: Результат анализа
    """
    return await analysis_service.analyze_entry(entry)