"""
Анализатор эмоций для записей дневника
"""

import logging
import random
from typing import Dict, Any
from messages import get_message

logger = logging.getLogger(__name__)

class EmotionAnalyzer:
    """Анализатор эмоций для записей дневника"""
    
    def __init__(self):
        """Инициализация анализатора эмоций"""
        logger.info("Анализатор эмоций инициализирован")
        
        # Словари ключевых слов для анализа эмоций
        self.positive_words = {
            'ru': [
                'хорошо', 'отлично', 'прекрасно', 'замечательно', 'великолепно',
                'счастливо', 'радостно', 'приятно', 'удовлетворенно', 'спокойно',
                'довольно', 'успешно', 'удачно', 'весело', 'интересно',
                'вдохновлено', 'мотивировано', 'энергично', 'активно', 'продуктивно'
            ],
            'en': [
                'good', 'great', 'excellent', 'wonderful', 'fantastic',
                'happy', 'joyful', 'pleasant', 'satisfied', 'calm',
                'content', 'successful', 'lucky', 'fun', 'interesting',
                'inspired', 'motivated', 'energetic', 'active', 'productive'
            ]
        }
        
        self.negative_words = {
            'ru': [
                'плохо', 'ужасно', 'страшно', 'отвратительно', 'мерзко',
                'грустно', 'тревожно', 'обеспокоенно', 'раздраженно', 'зло',
                'злобно', 'сердито', 'злостно', 'агрессивно', 'ненавидяще',
                'подавленно', 'депрессивно', 'апатично', 'устало', 'измученно'
            ],
            'en': [
                'bad', 'terrible', 'awful', 'disgusting', 'horrible',
                'sad', 'anxious', 'worried', 'irritated', 'angry',
                'furious', 'mad', 'hostile', 'aggressive', 'hateful',
                'depressed', 'depressive', 'apathetic', 'tired', 'exhausted'
            ]
        }
        
        self.neutral_words = {
            'ru': [
                'нормально', 'обычно', 'обыденно', 'нейтрально', 'спокойно',
                'равнодушно', 'безразлично', 'пассивно', 'нейтрально', 'стандартно'
            ],
            'en': [
                'normal', 'usual', 'ordinary', 'neutral', 'calm',
                'indifferent', 'passive', 'standard', 'routine', 'average'
            ]
        }
    
    async def analyze_emotions(self, text: str, language: str = 'ru') -> Dict[str, Any]:
        """
        Анализ эмоций в тексте
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            Dict[str, Any]: Результат анализа эмоций
        """
        logger.info(f"Начало анализа эмоций для текста длиной {len(text)} символов на языке {language}")
        
        try:
            # === 1. Подсчет ключевых слов ===
            logger.info("Шаг 1: Подсчет ключевых слов")
            positive_count, negative_count, neutral_count = await self._count_emotion_words(text, language)
            logger.info(f"Подсчитано: положительных={positive_count}, отрицательных={negative_count}, нейтральных={neutral_count}")
            
            # === 2. Определение настроения ===
            logger.info("Шаг 2: Определение настроения")
            mood_score, mood_category = await self._determine_mood(positive_count, negative_count, neutral_count)
            logger.info(f"Определено настроение: оценка={mood_score}/10, категория={mood_category}")
            
            # === 3. Формирование комментария ===
            logger.info("Шаг 3: Формирование комментария")
            comment = await self._generate_comment(mood_score, mood_category, language)
            logger.info(f"Сформирован комментарий: {comment[:50]}...")
            
            # === 4. Формирование рекомендации ===
            logger.info("Шаг 4: Формирование рекомендации")
            recommendation = await self._generate_recommendation(mood_score, mood_category, language)
            logger.info(f"Сформирована рекомендация: {recommendation[:50]}...")
            
            result = {
                'mood_score': mood_score,
                'mood_category': mood_category,
                'comment': comment,
                'recommendation': recommendation,
                'positive_words': positive_count,
                'negative_words': negative_count,
                'neutral_words': neutral_count,
                'processing_time': 1.2  # Заглушка
            }
            
            logger.info("Анализ эмоций завершен успешно")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при анализе эмоций: {e}")
            
            # Возвращаем заглушку в случае ошибки
            return await self._create_default_analysis(language)
    
    async def _count_emotion_words(self, text: str, language: str) -> tuple:
        """
        Подсчет ключевых слов эмоций
        
        Args:
            text: Обработанный текст
            language: Язык текста
            
        Returns:
            tuple: (положительные, отрицательные, нейтральные)
        """
        try:
            logger.info("Подсчет ключевых слов эмоций")
            
            # Приводим текст к нижнему регистру для поиска
            lower_text = text.lower()
            
            # Подсчитываем слова
            positive_count = sum(1 for word in self.positive_words[language] if word in lower_text)
            negative_count = sum(1 for word in self.negative_words[language] if word in lower_text)
            neutral_count = sum(1 for word in self.neutral_words[language] if word in lower_text)
            
            logger.info(f"Подсчет завершен: +{positive_count}, -{negative_count}, 0{neutral_count}")
            return positive_count, negative_count, neutral_count
            
        except Exception as e:
            logger.error(f"Ошибка при подсчете ключевых слов: {e}")
            return 0, 0, 0
    
    async def _determine_mood(self, positive_count: int, negative_count: int, neutral_count: int) -> tuple:
        """
        Определение настроения по подсчитанным словам
        
        Args:
            positive_count: Количество положительных слов
            negative_count: Количество отрицательных слов
            neutral_count: Количество нейтральных слов
            
        Returns:
            tuple: (оценка настроения 1-10, категория настроения)
        """
        try:
            logger.info("Определение настроения")
            
            # Общее количество эмоциональных слов
            total_emotional = positive_count + negative_count
            
            if total_emotional == 0:
                # Если нет эмоциональных слов, настроение нейтральное
                mood_score = 5
                mood_category = 'neutral'
            else:
                # Рассчитываем процент положительных слов
                positive_percentage = (positive_count / total_emotional) * 100
                
                # Определяем оценку настроения (1-10)
                if positive_percentage >= 80:
                    mood_score = 9
                    mood_category = 'very_positive'
                elif positive_percentage >= 60:
                    mood_score = 7
                    mood_category = 'positive'
                elif positive_percentage >= 40:
                    mood_score = 5
                    mood_category = 'neutral'
                elif positive_percentage >= 20:
                    mood_score = 3
                    mood_category = 'negative'
                else:
                    mood_score = 1
                    mood_category = 'very_negative'
            
            logger.info(f"Настроение определено: оценка={mood_score}, категория={mood_category}")
            return mood_score, mood_category
            
        except Exception as e:
            logger.error(f"Ошибка при определении настроения: {e}")
            return 5, 'neutral'
    
    async def _generate_comment(self, mood_score: int, mood_category: str, language: str) -> str:
        """
        Генерация комментария по оценке настроения
        
        Args:
            mood_score: Оценка настроения 1-10
            mood_category: Категория настроения
            language: Язык
            
        Returns:
            str: Комментарий
        """
        try:
            logger.info(f"Генерация комментария для оценки {mood_score}, категории {mood_category}")
            
            # Используем сообщения из messages.py
            mood_key = f'mood_{mood_score}'
            mood_text = get_message(mood_key, language)
            
            # Формируем комментарий
            comment_templates = {
                'ru': {
                    'very_positive': f'Отличный день! Ты чувствуешь себя {mood_text}. Продолжай в том же духе!',
                    'positive': f'Хороший день! Ты чувствуешь себя {mood_text}. Так держать!',
                    'neutral': f'Нормальный день. Ты чувствуешь себя {mood_text}. Всё в порядке.',
                    'negative': f'Сложный день. Ты чувствуешь себя {mood_text}. Не переживай, всё наладится.',
                    'very_negative': f'Тяжёлый день. Ты чувствуешь себя {mood_text}. Постарайся позаботиться о себе.'
                },
                'en': {
                    'very_positive': f'Great day! You feel {mood_text}. Keep it up!',
                    'positive': f'Good day! You feel {mood_text}. Keep going!',
                    'neutral': f'Normal day. You feel {mood_text}. Everything is fine.',
                    'negative': f'Difficult day. You feel {mood_text}. Don\'t worry, everything will be fine.',
                    'very_negative': f'Hard day. You feel {mood_text}. Try to take care of yourself.'
                }
            }
            
            templates = comment_templates[language]
            comment = templates.get(mood_category, f'Ты чувствуешь себя {mood_text}.')
            
            logger.info(f"Комментарий сгенерирован: {comment[:50]}...")
            return comment
            
        except Exception as e:
            logger.error(f"Ошибка при генерации комментария: {e}")
            return "Анализ записан"
    
    async def _generate_recommendation(self, mood_score: int, mood_category: str, language: str) -> str:
        """
        Генерация рекомендации по оценке настроения
        
        Args:
            mood_score: Оценка настроения 1-10
            mood_category: Категория настроения
            language: Язык
            
        Returns:
            str: Рекомендация
        """
        try:
            logger.info(f"Генерация рекомендации для оценки {mood_score}, категории {mood_category}")
            
            # Рекомендации по категориям
            recommendations = {
                'ru': {
                    'very_positive': [
                        'Продолжай в том же духе! Ты на правильном пути.',
                        'Отличная работа! Так держать!',
                        'Ты делаешь всё правильно. Продолжай!',
                        'Замечательно! Ты достиг хорошего результата.',
                        'Прекрасно! Ты в отличной форме.'
                    ],
                    'positive': [
                        'Хорошая работа! Продолжай в том же духе.',
                        'Ты на правильном пути. Так держать!',
                        'Отлично! Продолжай развиваться.',
                        'Хороший прогресс! Продолжай!',
                        'Ты делаешь успехи. Продолжай!'
                    ],
                    'neutral': [
                        'Всё в порядке. Попробуй найти что-то, что тебя вдохновляет.',
                        'Нормально. Может быть, стоит попробовать что-то новое?',
                        'Стабильно. Попробуй добавить больше позитива в свой день.',
                        'Средне. Найди что-то, что приносит радость.',
                        'Обычно. Попробуй разнообразить свой день.'
                    ],
                    'negative': [
                        'Не переживай. Завтра будет лучше.',
                        'Сложный день. Попробуй отдохнуть и позаботиться о себе.',
                        'Тяжело. Помни, что это временно.',
                        'Непросто. Найди поддержку и заботу.',
                        'Сложности. Постарайся найти что-то хорошее.'
                    ],
                    'very_negative': [
                        'Постарайся позаботиться о себе. Ты не один.',
                        'Тяжёлый день. Найди поддержку и помощь.',
                        'Сложно. Помни, что ты сильнее, чем думаешь.',
                        'Трудно. Обратись к близким или специалисту.',
                        'Серьёзно. Не стесняйся искать профессиональную помощь.'
                    ]
                },
                'en': {
                    'very_positive': [
                        'Keep it up! You are on the right path.',
                        'Great job! Keep going!',
                        'You are doing everything right. Continue!',
                        'Wonderful! You have achieved a good result.',
                        'Perfect! You are in great shape.'
                    ],
                    'positive': [
                        'Good job! Keep it up.',
                        'You are on the right path. Keep going!',
                        'Great! Keep developing.',
                        'Good progress! Continue!',
                        'You are making progress. Keep going!'
                    ],
                    'neutral': [
                        'Everything is fine. Try to find something that inspires you.',
                        'Normal. Maybe try something new?',
                        'Stable. Try to add more positivity to your day.',
                        'Average. Find something that brings joy.',
                        'Usually. Try to diversify your day.'
                    ],
                    'negative': [
                        'Don\'t worry. Tomorrow will be better.',
                        'Difficult day. Try to rest and take care of yourself.',
                        'Hard. Remember that this is temporary.',
                        'Tough. Find support and care.',
                        'Difficulties. Try to find something good.'
                    ],
                    'very_negative': [
                        'Try to take care of yourself. You are not alone.',
                        'Hard day. Find support and help.',
                        'Difficult. Remember that you are stronger than you think.',
                        'Tough. Reach out to loved ones or a specialist.',
                        'Serious. Don\'t hesitate to seek professional help.'
                    ]
                }
            }
            
            lang_recommendations = recommendations[language]
            category_recommendations = lang_recommendations.get(mood_category, ['Продолжай в том же духе!'])
            
            # Выбираем случайную рекомендацию
            recommendation = random.choice(category_recommendations)
            
            logger.info(f"Рекомендация сгенерирована: {recommendation[:50]}...")
            return recommendation
            
        except Exception as e:
            logger.error(f"Ошибка при генерации рекомендации: {e}")
            return "Продолжай в том же духе"
    
    async def _create_default_analysis(self, language: str) -> Dict[str, Any]:
        """
        Создание анализа по умолчанию в случае ошибки
        
        Args:
            language: Язык
            
        Returns:
            Dict[str, Any]: Анализ по умолчанию
        """
        try:
            logger.info("Создание анализа по умолчанию")
            
            default_analysis = {
                'mood_score': 5,
                'mood_category': 'neutral',
                'comment': get_message('analysis_default_comment', language),
                'recommendation': get_message('analysis_default_recommendation', language),
                'positive_words': 0,
                'negative_words': 0,
                'neutral_words': 0,
                'processing_time': 0.5
            }
            
            logger.info("Анализ по умолчанию создан")
            return default_analysis
            
        except Exception as e:
            logger.error(f"Ошибка при создании анализа по умолчанию: {e}")
            
            # Абсолютно минимальный анализ
            return {
                'mood_score': 5,
                'mood_category': 'neutral',
                'comment': 'Анализ записан',
                'recommendation': 'Продолжай в том же духе',
                'positive_words': 0,
                'negative_words': 0,
                'neutral_words': 0,
                'processing_time': 0.1
            }

# Глобальный экземпляр анализатора эмоций
emotion_analyzer = EmotionAnalyzer()

# Функция для удобного использования
async def analyze_emotions(text: str, language: str = 'ru') -> Dict[str, Any]:
    """
    Удобная функция для анализа эмоций
    
    Args:
        text: Обработанный текст
        language: Язык текста
        
    Returns:
        Dict[str, Any]: Результат анализа эмоций
    """
    return await emotion_analyzer.analyze_emotions(text, language)