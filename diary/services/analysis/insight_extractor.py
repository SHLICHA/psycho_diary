"""
Извлекатель инсайтов из записей дневника
"""

import logging
from typing import List, Dict, Any
from users.models import User

logger = logging.getLogger(__name__)

class InsightExtractor:
    """Извлекатель инсайтов из записей дневника"""
    
    def __init__(self):
        """Инициализация извлекателя инсайтов"""
        logger.info("Извлекатель инсайтов инициализирован")
        
        # Ключевые слова для извлечения инсайтов
        self.insight_keywords = {
            'ru': {
                'emotion': [
                    'чувство', 'эмоция', 'радость', 'грусть', 'злость', 'страх', 'любовь',
                    'ненависть', 'удовольствие', 'боль', 'счастье', 'тревога', 'спокойствие'
                ],
                'event': [
                    'событие', 'происшествие', 'встреча', 'разговор', 'работа', 'семья',
                    'друзья', 'путешествие', 'покупка', 'решение', 'выбор', 'перемены'
                ],
                'thought': [
                    'мысль', 'идея', 'размышление', 'понимание', 'осознание', 'реализация',
                    'вдохновение', 'озарение', 'прозрение', 'инсайт', 'понимаю', 'думаю'
                ],
                'trigger': [
                    'триггер', 'спусковой крючок', 'провокатор', 'причина', 'повод',
                    'вызывает', 'вызывает', 'провоцирует', 'активирует', 'запускает'
                ]
            },
            'en': {
                'emotion': [
                    'feeling', 'emotion', 'joy', 'sadness', 'anger', 'fear', 'love',
                    'hatred', 'pleasure', 'pain', 'happiness', 'anxiety', 'calm'
                ],
                'event': [
                    'event', 'incident', 'meeting', 'conversation', 'work', 'family',
                    'friends', 'travel', 'purchase', 'decision', 'choice', 'changes'
                ],
                'thought': [
                    'thought', 'idea', 'reflection', 'understanding', 'realization',
                    'inspiration', 'revelation', 'insight', 'insight', 'understand', 'think'
                ],
                'trigger': [
                    'trigger', 'trigger', 'provocateur', 'reason', 'occasion',
                    'causes', 'triggers', 'provokes', 'activates', 'launches'
                ]
            }
        }
    
    async def extract_key_points(self, text: str, user: User, language: str = 'ru') -> List[Dict[str, Any]]:
        """
        Извлечение ключевых моментов из текста
        
        Args:
            text: Обработанный текст
            user: Пользователь
            language: Язык текста
            
        Returns:
            List[Dict[str, Any]]: Список ключевых моментов
        """
        logger.info(f"Начало извлечения ключевых моментов для пользователя {user.telegram_id}")
        
        try:
            # === 1. Извлечение эмоций ===
            logger.info("Шаг 1: Извлечение эмоций")
            emotions = await self._extract_emotions(text, language)
            logger.info(f"Извлечено {len(emotions)} эмоций")
            
            # === 2. Извлечение событий ===
            logger.info("Шаг 2: Извлечение событий")
            events = await self._extract_events(text, language)
            logger.info(f"Извлечено {len(events)} событий")
            
            # === 3. Извлечение мыслей ===
            logger.info("Шаг 3: Извлечение мыслей")
            thoughts = await self._extract_thoughts(text, language)
            logger.info(f"Извлечено {len(thoughts)} мыслей")
            
            # === 4. Извлечение триггеров ===
            logger.info("Шаг 4: Извлечение триггеров")
            triggers = await self._extract_triggers(text, language)
            logger.info(f"Извлечено {len(triggers)} триггеров")
            
            # === 5. Объединение всех ключевых моментов ===
            logger.info("Шаг 5: Объединение ключевых моментов")
            key_points = []
            
            # Добавляем эмоции
            for emotion in emotions:
                key_points.append({
                    'text': emotion,
                    'type': 'emotion',
                    'confidence': 0.9,  # Высокая уверенность
                    'user': user
                })
            
            # Добавляем события
            for event in events:
                key_points.append({
                    'text': event,
                    'type': 'event',
                    'confidence': 0.8,  # Средняя уверенность
                    'user': user
                })
            
            # Добавляем мысли
            for thought in thoughts:
                key_points.append({
                    'text': thought,
                    'type': 'thought',
                    'confidence': 0.7,  # Средняя уверенность
                    'user': user
                })
            
            # Добавляем триггеры
            for trigger in triggers:
                key_points.append({
                    'text': trigger,
                    'type': 'trigger',
                    'confidence': 0.85,  # Высокая уверенность
                    'user': user
                })
            
            logger.info(f"Всего извлечено {len(key_points)} ключевых моментов")
            return key_points
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении ключевых моментов: {e}")
            return []  # Возвращаем пустой список в случае ошибки
    
    async def _extract_emotions(self, text: str, language: str) -> List[str]:
        """
        Извлечение эмоций из текста
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            List[str]: Список найденных эмоций
        """
        try:
            logger.info("Извлечение эмоций из текста")
            
            # Приводим текст к нижнему регистру для поиска
            lower_text = text.lower()
            
            # Получаем ключевые слова для эмоций
            emotion_keywords = self.insight_keywords[language]['emotion']
            
            # Ищем эмоции в тексте
            found_emotions = []
            for keyword in emotion_keywords:
                if keyword in lower_text:
                    # Извлекаем контекст вокруг ключевого слова
                    context = self._extract_context(lower_text, keyword, 20)
                    if context and context not in found_emotions:
                        found_emotions.append(context)
            
            logger.info(f"Найдено {len(found_emotions)} эмоций")
            return found_emotions
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении эмоций: {e}")
            return []
    
    async def _extract_events(self, text: str, language: str) -> List[str]:
        """
        Извлечение событий из текста
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            List[str]: Список найденных событий
        """
        try:
            logger.info("Извлечение событий из текста")
            
            # Приводим текст к нижнему регистру для поиска
            lower_text = text.lower()
            
            # Получаем ключевые слова для событий
            event_keywords = self.insight_keywords[language]['event']
            
            # Ищем события в тексте
            found_events = []
            for keyword in event_keywords:
                if keyword in lower_text:
                    # Извлекаем контекст вокруг ключевого слова
                    context = self._extract_context(lower_text, keyword, 30)
                    if context and context not in found_events:
                        found_events.append(context)
            
            logger.info(f"Найдено {len(found_events)} событий")
            return found_events
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении событий: {e}")
            return []
    
    async def _extract_thoughts(self, text: str, language: str) -> List[str]:
        """
        Извлечение мыслей из текста
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            List[str]: Список найденных мыслей
        """
        try:
            logger.info("Извлечение мыслей из текста")
            
            # Приводим текст к нижнему регистру для поиска
            lower_text = text.lower()
            
            # Получаем ключевые слова для мыслей
            thought_keywords = self.insight_keywords[language]['thought']
            
            # Ищем мысли в тексте
            found_thoughts = []
            for keyword in thought_keywords:
                if keyword in lower_text:
                    # Извлекаем контекст вокруг ключевого слова
                    context = self._extract_context(lower_text, keyword, 25)
                    if context and context not in found_thoughts:
                        found_thoughts.append(context)
            
            logger.info(f"Найдено {len(found_thoughts)} мыслей")
            return found_thoughts
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении мыслей: {e}")
            return []
    
    async def _extract_triggers(self, text: str, language: str) -> List[str]:
        """
        Извлечение триггеров из текста
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            List[str]: Список найденных триггеров
        """
        try:
            logger.info("Извлечение триггеров из текста")
            
            # Приводим текст к нижнему регистру для поиска
            lower_text = text.lower()
            
            # Получаем ключевые слова для триггеров
            trigger_keywords = self.insight_keywords[language]['trigger']
            
            # Ищем триггеры в тексте
            found_triggers = []
            for keyword in trigger_keywords:
                if keyword in lower_text:
                    # Извлекаем контекст вокруг ключевого слова
                    context = self._extract_context(lower_text, keyword, 25)
                    if context and context not in found_triggers:
                        found_triggers.append(context)
            
            logger.info(f"Найдено {len(found_triggers)} триггеров")
            return found_triggers
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении триггеров: {e}")
            return []
    
    def _extract_context(self, text: str, keyword: str, context_length: int) -> str:
        """
        Извлечение контекста вокруг ключевого слова
        
        Args:
            text: Обработанный текст
            keyword: Ключевое слово
            context_length: Длина контекста в словах
            
        Returns:
            str: Контекст вокруг ключевого слова
        """
        try:
            logger.debug(f"Извлечение контекста для ключевого слова: {keyword}")
            
            # Находим позицию ключевого слова
            keyword_pos = text.find(keyword)
            if keyword_pos == -1:
                return ""
            
            # Разбиваем текст на слова
            words = text.split()
            
            # Находим слово с ключевым словом
            for i, word in enumerate(words):
                if keyword in word.lower():
                    # Извлекаем контекст
                    start_index = max(0, i - context_length // 2)
                    end_index = min(len(words), i + context_length // 2 + 1)
                    context_words = words[start_index:end_index]
                    context = " ".join(context_words)
                    logger.debug(f"Контекст извлечен: {context[:50]}...")
                    return context
            
            return keyword  # Если не удалось извлечь контекст
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении контекста: {e}")
            return keyword

# Глобальный экземпляр извлекателя инсайтов
insight_extractor = InsightExtractor()

# Функция для удобного использования
async def extract_key_points(text: str, user: User, language: str = 'ru') -> List[Dict[str, Any]]:
    """
    Удобная функция для извлечения ключевых моментов
    
    Args:
        text: Обработанный текст
        user: Пользователь
        language: Язык текста
        
    Returns:
        List[Dict[str, Any]]: Список ключевых моментов
    """
    return await insight_extractor.extract_key_points(text, user, language)