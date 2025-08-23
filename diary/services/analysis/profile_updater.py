"""
Обновление профиля пользователя на основе анализа
"""

import logging
from typing import List, Dict, Any
from users.models import User
from diary.models import PsychoAnalysis, UserInsight

logger = logging.getLogger(__name__)

class ProfileUpdater:
    """Обновление профиля пользователя на основе анализа"""
    
    def __init__(self):
        """Инициализация обновителя профиля"""
        logger.info("Обновитель профиля инициализирован")
    
    async def update_user_profile(self, user: User, analysis: PsychoAnalysis, key_points: List[Dict[str, Any]]) -> bool:
        """
        Обновление профиля пользователя на основе анализа
        
        Args:
            user: Пользователь
            analysis: Результат анализа
            key_points: Ключевые моменты
            
        Returns:
            bool: Успешность обновления
        """
        logger.info(f"Начало обновления профиля пользователя {user.telegram_id}")
        
        try:
            # === 1. Обновление уровня осознанности ===
            logger.info("Шаг 1: Обновление уровня осознанности")
            await self._update_awareness_level(user, analysis, key_points)
            logger.info("Уровень осознанности обновлен")
            
            # === 2. Обновление статистики ===
            logger.info("Шаг 2: Обновление статистики")
            await self._update_statistics(user, analysis, key_points)
            logger.info("Статистика обновлена")
            
            # === 3. Обновление предпочтений ===
            logger.info("Шаг 3: Обновление предпочтений")
            await self._update_preferences(user, analysis, key_points)
            logger.info("Предпочтения обновлены")
            
            # === 4. Сохранение изменений ===
            logger.info("Шаг 4: Сохранение изменений")
            await user.asave()
            logger.info("Изменения сохранены")
            
            logger.info(f"Профиль пользователя {user.telegram_id} обновлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}")
            return False
    
    async def _update_awareness_level(self, user: User, analysis: PsychoAnalysis, key_points: List[Dict[str, Any]]) -> None:
        """
        Обновление уровня осознанности пользователя
        
        Args:
            user: Пользователь
            analysis: Результат анализа
            key_points: Ключевые моменты
        """
        try:
            logger.info("Обновление уровня осознанности")
            
            # Базовый уровень осознанности
            awareness_level = user.awareness_level or 1
            
            # Увеличиваем уровень за каждый анализ
            awareness_level += 0.1
            
            # Увеличиваем уровень за каждый ключевой момент
            awareness_level += len(key_points) * 0.05
            
            # Увеличиваем уровень за высокую оценку настроения
            if analysis.mood_score >= 8:
                awareness_level += 0.2
            elif analysis.mood_score >= 6:
                awareness_level += 0.1
            
            # Ограничиваем уровень максимальным значением
            from core.constants import AWARENESS_LEVEL_MAX
            awareness_level = min(awareness_level, AWARENESS_LEVEL_MAX)
            
            # Округляем до целого числа
            user.awareness_level = int(awareness_level)
            
            logger.info(f"Уровень осознанности обновлен до {user.awareness_level}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении уровня осознанности: {e}")
    
    async def _update_statistics(self, user: User, analysis: PsychoAnalysis, key_points: List[Dict[str, Any]]) -> None:
        """
        Обновление статистики пользователя
        
        Args:
            user: Пользователь
            analysis: Результат анализа
            key_points: Ключевые моменты
        """
        try:
            logger.info("Обновление статистики")
            
            # Обновляем дату последней записи
            from datetime import datetime
            user.last_entry = datetime.now()
            
            # Обновляем количество записей (это делается в модели DiaryEntry)
            # Пока просто логируем
            logger.info("Статистика обновлена")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
    
    async def _update_preferences(self, user: User, analysis: PsychoAnalysis, key_points: List[Dict[str, Any]]) -> None:
        """
        Обновление предпочтений пользователя
        
        Args:
            user: Пользователь
            analysis: Результат анализа
            key_points: Ключевые моменты
        """
        try:
            logger.info("Обновление предпочтений")
            
            # Анализируем ключевые моменты и обновляем предпочтения
            emotion_count = sum(1 for point in key_points if point['type'] == 'emotion')
            event_count = sum(1 for point in key_points if point['type'] == 'event')
            thought_count = sum(1 for point in key_points if point['type'] == 'thought')
            trigger_count = sum(1 for point in key_points if point['type'] == 'trigger')
            
            # Пока просто логируем
            logger.info(f"Предпочтения: эмоции={emotion_count}, события={event_count}, мысли={thought_count}, триггеры={trigger_count}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении предпочтений: {e}")

# Глобальный экземпляр обновителя профиля
profile_updater = ProfileUpdater()

# Функция для удобного использования
async def update_user_profile(user: User, analysis: PsychoAnalysis, key_points: List[Dict[str, Any]]) -> bool:
    """
    Удобная функция для обновления профиля пользователя
    
    Args:
        user: Пользователь
        analysis: Результат анализа
        key_points: Ключевые моменты
        
    Returns:
        bool: Успешность обновления
    """
    return await profile_updater.update_user_profile(user, analysis, key_points)