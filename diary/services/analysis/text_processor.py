"""
Обработчик текста для анализа
"""

import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

class TextProcessor:
    """Обработчик текста для анализа записей"""
    
    def __init__(self):
        """Инициализация обработчика текста"""
        logger.info("Обработчик текста инициализирован")
    
    async def process_text(self, text: str) -> str:
        """
        Предварительная обработка текста
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Обработанный текст
        """
        logger.info(f"Начало обработки текста длиной {len(text)} символов")
        
        try:
            # === 1. Очистка текста ===
            logger.info("Шаг 1: Очистка текста")
            cleaned_text = self._clean_text(text)
            logger.info(f"Текст очищен, новая длина: {len(cleaned_text)} символов")
            
            # === 2. Нормализация текста ===
            logger.info("Шаг 2: Нормализация текста")
            normalized_text = self._normalize_text(cleaned_text)
            logger.info(f"Текст нормализован, новая длина: {len(normalized_text)} символов")
            
            # === 3. Удаление лишних пробелов ===
            logger.info("Шаг 3: Удаление лишних пробелов")
            final_text = self._remove_extra_spaces(normalized_text)
            logger.info(f"Лишние пробелы удалены, финальная длина: {len(final_text)} символов")
            
            logger.info("Обработка текста завершена успешно")
            return final_text
            
        except Exception as e:
            logger.error(f"Ошибка при обработке текста: {e}")
            # Возвращаем оригинальный текст в случае ошибки
            return text
    
    def _clean_text(self, text: str) -> str:
        """
        Очистка текста от лишних символов
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Очищенный текст
        """
        try:
            logger.info("Очистка текста от лишних символов")
            
            # Удаляем множественные пробелы
            text = re.sub(r'\s+', ' ', text)
            
            # Удаляем лишние символы (оставляем только буквы, цифры, пробелы и основную пунктуацию)
            text = re.sub(r'[^\w\s.,!?;:()\-\—\"\'«»]', '', text)
            
            # Удаляем множественные знаки препинания
            text = re.sub(r'[.]{2,}', '.', text)  # Множественные точки
            text = re.sub(r'[!]{2,}', '!', text)  # Множественные восклицательные знаки
            text = re.sub(r'[?]{2,}', '?', text)  # Множественные вопросительные знаки
            
            logger.info("Текст очищен успешно")
            return text.strip()
            
        except Exception as e:
            logger.error(f"Ошибка при очистке текста: {e}")
            return text
    
    def _normalize_text(self, text: str) -> str:
        """
        Нормализация текста
        
        Args:
            text: Очищенный текст
            
        Returns:
            str: Нормализованный текст
        """
        try:
            logger.info("Нормализация текста")
            
            # Приводим к нижнему регистру (для анализа)
            normalized_text = text.lower()
            
            # Заменяем тире на дефисы
            normalized_text = re.sub(r'[\u2014\u2013]', '-', normalized_text)
            
            # Заменяем кавычки на стандартные
            normalized_text = re.sub(r'[\u201c\u201d\u00ab\u00bb]', '"', normalized_text)
            normalized_text = re.sub(r'[\u2018\u2019]', "'", normalized_text)
            
            logger.info("Текст нормализован успешно")
            return normalized_text
            
        except Exception as e:
            logger.error(f"Ошибка при нормализации текста: {e}")
            return text
    
    def _remove_extra_spaces(self, text: str) -> str:
        """
        Удаление лишних пробелов
        
        Args:
            text: Нормализованный текст
            
        Returns:
            str: Текст без лишних пробелов
        """
        try:
            logger.info("Удаление лишних пробелов")
            
            # Удаляем множественные пробелы
            text = re.sub(r'\s+', ' ', text)
            
            # Удаляем пробелы в начале и конце
            text = text.strip()
            
            logger.info("Лишние пробелы удалены успешно")
            return text
            
        except Exception as e:
            logger.error(f"Ошибка при удалении лишних пробелов: {e}")
            return text
    
    async def extract_words(self, text: str) -> List[str]:
        """
        Извлечение слов из текста
        
        Args:
            text: Обработанный текст
            
        Returns:
            List[str]: Список слов
        """
        try:
            logger.info("Извлечение слов из текста")
            
            # Разбиваем текст на слова
            words = text.split()
            
            # Удаляем пустые слова и слова меньше 2 символов
            filtered_words = [word for word in words if len(word.strip()) >= 2]
            
            logger.info(f"Извлечено {len(filtered_words)} слов")
            return filtered_words
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении слов: {e}")
            return text.split()
    
    async def extract_sentences(self, text: str) -> List[str]:
        """
        Извлечение предложений из текста
        
        Args:
            text: Обработанный текст
            
        Returns:
            List[str]: Список предложений
        """
        try:
            logger.info("Извлечение предложений из текста")
            
            # Разбиваем текст на предложения по знакам препинания
            sentences = re.split(r'[.!?]+', text)
            
            # Удаляем пустые предложения и предложения меньше 5 слов
            filtered_sentences = [
                sentence.strip() 
                for sentence in sentences 
                if len(sentence.strip()) > 0 and len(sentence.split()) >= 5
            ]
            
            logger.info(f"Извлечено {len(filtered_sentences)} предложений")
            return filtered_sentences
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении предложений: {e}")
            return [text]

# Глобальный экземпляр обработчика текста
text_processor = TextProcessor()

# Функция для удобного использования
async def process_text(text: str) -> str:
    """
    Удобная функция для обработки текста
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Обработанный текст
    """
    return await text_processor.process_text(text)