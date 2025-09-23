"""
Сервис для работы с DeepSeek API
"""

import logging
import asyncio
import json
import aiohttp
import re

from typing import Dict, Any
from prompts.get_prompt import get_prompt
from core.settings import DEEPSEEK_API_KEY
from bot.utils.api_utils import api_retry, handle_api_error, retry_api_call

logger = logging.getLogger(__name__)

class DeepSeekAPIService:
    def __init__(self):
        """Инициализация сервиса DeepSeek API"""
        if not DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY не настроен")

    async def send_prompt_and_parse(
        self, 
        prompt: str, 
        language: str, 
        max_retries: int = 3,
        base_delay: float = 1.5,
        timeout_per_attempt: int = 90 
    ) -> dict:
        """
        Отправляет готовый промт в DeepSeek и возвращает распарсенный результат.
        Реализует механизм повторных попыток при ошибках.
        """
        logger.debug(f"[DeepSeek API] Начало send_prompt_and_parse. Попыток: {max_retries}, Базовая задержка: {base_delay}s, Таймаут: {timeout_per_attempt}s")
        
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                if not DEEPSEEK_API_KEY:
                    logger.warning("[DeepSeek API] DEEPSEEK_API_KEY не настроен")
                    return {'success': False, 'error': 'api_key_missing', 'result': {}, 'raw_response': ''}

                # Исправленный URL (убраны пробелы)
                url = "https://api.deepseek.com/v1/chat/completions"
                
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 5000
                }
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }

                # Используем таймаут для каждой попытки
                timeout = aiohttp.ClientTimeout(total=timeout_per_attempt)
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1}/{max_retries} к {url}")

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        response_text = await response.text()
                        logger.debug(f"[DeepSeek API] Попытка {attempt + 1} получила статус: {response.status}")
                        
                        if response.status == 200:
                            data = await response.json()
                            response_content = data['choices'][0]['message']['content']
                            result = await self._parse_analysis_response(response_content, language)
                            logger.debug(f"[DeepSeek API] Попытка {attempt + 1} успешна.")
                            return {
                                'success': True,
                                'result': result,
                                'raw_response': response_content
                            }
                        else:
                            # Логируем не 200 ответ как ошибку, но не прекращаем retry
                            logger.warning(f"[DeepSeek API] Попытка {attempt + 1} получила статус {response.status}. Ответ: {response_text[:200]}...")
                            last_response_text = response_text # Сохраняем для последней ошибки
                            # Не выходим из цикла, продолжаем retry

            except asyncio.TimeoutError as te:
                last_exception = te
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1} превысила таймаут ({timeout_per_attempt}s): {te}")
                
            except aiohttp.ClientError as ce: # Охватывает большинство сетевых ошибок aiohttp
                last_exception = ce
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1} ошибка клиента aiohttp: {ce}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"[DeepSeek API] Попытка {attempt + 1} неожиданная ошибка: {e}", exc_info=True)
                # Для не сетевых ошибок, возможно, нет смысла retry, но для единообразия продолжаем
            
            # Если это не последняя попытка, делаем задержку
            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1) # Линейная задержка
                logger.debug(f"[DeepSeek API] Ожидание {delay:.2f} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
            else:
                logger.debug(f"[DeepSeek API] Все {max_retries} попыток исчерпаны.")

        # Если цикл завершился без return, значит все попытки провалились
        error_msg = "Превышено время ожидания" if isinstance(last_exception, asyncio.TimeoutError) else str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}..."
        error_code = 'timeout' if isinstance(last_exception, asyncio.TimeoutError) else 'request_failed'
        
        logger.error(f"[DeepSeek API] send_prompt_and_parse завершился ошибкой после {max_retries} попыток: {error_msg}")
        return {
            'success': False,
            'error': error_code,
            'message': error_msg,
            'result': {},
            'raw_response': last_response_text if last_response_text else (str(last_exception) if last_exception else '')
        }


    async def _parse_analysis_response(self, response_text: str, language: str) -> dict:
        """
        Парсит ответ от DeepSeek.
        """
        logger.debug(f"[DeepSeek API] Парсинг ответа API, язык: {language}, длина: {len(response_text)}")
        try:
            import json
            # Прямой парсинг
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            logger.warning("[DeepSeek API] Прямой парсинг JSON не удался. Ищем в Markdown-блоке...")
            try:
                import re
                json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                else:
                    logger.warning("[DeepSeek API] JSON-блок не найден.")
            except Exception as e:
                logger.error(f"[DeepSeek API] Ошибка при поиске JSON в Markdown: {e}")
            return {
                'mood_score': 5,
                'comment': 'Анализ записан' if language == 'ru' else 'Entry analyzed',
                'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Keep journaling',
                'analysis': 'Текст проанализирован' if language == 'ru' else 'Text analyzed'
            }
    
    async def punctuate_and_format_text(
        self, 
        text: str, 
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Расстановка знаков препинания и форматирование текста через DeepSeek API.
        Теперь использует get_prompt из prompts.py.
        Добавлена простая защита от таймаутов.
        """
        logger.debug(f"[DeepSeek API - Punctuation] Начало punctuate_and_format_text для текста длиной {len(text)} символов, язык: {language}")

        # Проверки
        if not text or len(text.strip()) < 1:
            return self._make_error_result('text_empty', 'Текст для расстановки знаков препинания пустой', text)

        if len(text) > 5000:
            return self._make_error_result('text_too_long', 'Текст слишком длинный', text)

        if not DEEPSEEK_API_KEY:
            return self._make_error_result('api_key_missing', 'API ключ DeepSeek не настроен', text)

        # === ГЕНЕРАЦИЯ ПРОМПТА ЧЕРЕЗ get_prompt ===
        try:
            prompt = get_prompt(
                key='punctuation',
                language=language,
                text=text
            )
            logger.debug(f"[DeepSeek API - Punctuation] Промт сгенерирован (длина: {len(prompt)} символов)")
        except Exception as e:
            logger.error(f"[DeepSeek API - Punctuation] Ошибка форматирования промпта 'punctuation': {e}")
            return self._make_error_result('prompt_generation_failed', f'Ошибка генерации промпта: {e}', text)

        # === ОТПРАВКА В API с простым retry ===
        max_retries = 2 # Меньше попыток для этой операции
        base_delay = 1.0
        timeout_per_attempt = 80
        
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                # Исправленный URL
                url = "https://api.deepseek.com/v1/chat/completions"
                
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 5000
                }
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }

                timeout = aiohttp.ClientTimeout(total=timeout_per_attempt)
                logger.debug(f"[DeepSeek API - Punctuation] Попытка {attempt + 1}/{max_retries}")

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        raw_response_text = await response.text()
                        logger.debug(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} получила статус: {response.status}")

                        if response.status == 200:
                            result = await response.json()
                            response_text = result['choices'][0]['message']['content']
                            formatted_text = await self._extract_formatted_text(response_text, language)
                            
                            success_result = self._make_success_result(formatted_text, raw_response_text, result)
                            logger.debug(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} успешна.")
                            return success_result
                        else:
                            logger.warning(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} получила статус {response.status}. Ответ: {raw_response_text[:200]}...")
                            last_response_text = raw_response_text

            except asyncio.TimeoutError as te:
                last_exception = te
                logger.debug(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} превысила таймаут ({timeout_per_attempt}s): {te}")
                
            except aiohttp.ClientError as ce:
                last_exception = ce
                logger.debug(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} ошибка клиента aiohttp: {ce}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"[DeepSeek API - Punctuation] Попытка {attempt + 1} неожиданная ошибка: {e}", exc_info=True)

            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1)
                logger.debug(f"[DeepSeek API - Punctuation] Ожидание {delay:.2f} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
            else:
                logger.debug(f"[DeepSeek API - Punctuation] Все {max_retries} попытки исчерпаны.")

        # Если все попытки провалились
        error_msg = "Превышено время ожидания" if isinstance(last_exception, asyncio.TimeoutError) else str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}..."
        error_code = 'timeout' if isinstance(last_exception, asyncio.TimeoutError) else 'request_failed'
        
        logger.error(f"[DeepSeek API - Punctuation] punctuate_and_format_text завершился ошибкой после {max_retries} попыток: {error_msg}")
        return self._make_error_result(error_code, error_msg, text)
    
    async def _extract_formatted_text(self, response_text: str, language: str) -> str:
        """
        Извлекает отформатированный текст из ответа DeepSeek.
        Удаляет префиксы и постфиксы.
        """
        logger.debug(f"[DeepSeek API] Извлечение отформатированного текста, язык: {language}")
        formatted_text = response_text.strip()

        prefixes = [
            "Конечно, вот отформатированный текст:",
            "Конечно, вот отформатированный текст",
            "Отформатированный текст:",
            "Отформатированный текст",
            "Форматированный текст:",
            "Форматированный текст",
            "RESPOND ONLY WITH FORMATTED TEXT",
            "Use the following response format:",
            "[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]",
            "[FORMATTED TEXT]",
            "```",
            "```text",
            "```plaintext"
        ]

        postfixes = ["```", "[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]", "[FORMATTED TEXT]"]

        for prefix in prefixes:
            if formatted_text.startswith(prefix):
                formatted_text = formatted_text[len(prefix):].strip()

        for postfix in postfixes:
            if formatted_text.endswith(postfix):
                formatted_text = formatted_text[:-len(postfix)].strip()

        return formatted_text if formatted_text else response_text.strip()

    def _make_success_result(self, formatted_text: str, raw_response: str, api_result: dict) -> dict:
        """Формирует успешный ответ с метаданными."""
        usage = api_result.get('usage', {})
        return {
            'success': True,
            'error': None,
            'message': 'Знаки препинания успешно расставлены',
            'result': formatted_text,
            'raw_response': raw_response,
            'processing_time': usage.get('total_tokens', 0) * 0.01,
            'tokens_used': usage.get('total_tokens', 0),
            'model_used': api_result.get('model', 'deepseek-chat'),
            'api_response': {
                'status': 200,
                'raw_response': raw_response,
                'json_response': api_result,
                'model_used': api_result.get('model'),
                'usage': usage,
                'processing_time': usage.get('total_tokens', 0) * 0.01,
                'tokens_used': usage.get('total_tokens', 0)
            }
        }

    def _make_error_result(self, error_code: str, error_text: str, original_text: str) -> dict:
        """Формирует ответ с ошибкой."""
        api_response_data = {
            'status': 'error',
            'error_text': error_text,
            'raw_response': error_text,
            'model_used': 'deepseek-chat',
            'usage': {},
            'processing_time': 0,
            'tokens_used': 0
        }
        return {
            'success': False,
            'error': error_code,
            'message': error_text,
            'result': original_text,
            'raw_response': error_text,
            'api_response': api_response_data
        }
    
    async def detect_timezone_by_city(
        self, 
        city_name: str, 
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Определяет часовой пояс по названию города через DeepSeek API.
        """
        logger.debug(f"[DeepSeek API - Timezone] Начало detect_timezone_by_city для города: {city_name}, язык: {language}")

        # Проверки
        if not city_name or len(city_name.strip()) < 1:
            return {
                'success': False,
                'error': 'city_name_empty',
                'message': 'Название города не указано'
            }

        if not DEEPSEEK_API_KEY:
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ DeepSeek не настроен'
            }

        # === ГЕНЕРАЦИЯ ПРОМПТА ЧЕРЕЗ get_prompt ===
        try:
            prompt = get_prompt(
                key='timezone_detection',
                language=language,
                city_name=city_name
            )
            logger.debug(f"[DeepSeek API - Timezone] Промт сгенерирован (длина: {len(prompt)} символов)")
        except Exception as e:
            logger.error(f"[DeepSeek API - Timezone] Ошибка форматирования промпта 'timezone_detection': {e}")
            return {
                'success': False,
                'error': 'prompt_generation_failed',
                'message': f'Ошибка генерации промпта: {e}'
            }

        # === ОТПРАВКА В API с retry (используем тот же механизм, что и в send_prompt_and_parse) ===
        max_retries = 3
        base_delay = 1.5
        timeout_per_attempt = 30 # Меньше таймаут для этой операции
        
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                # Исправленный URL
                url = "https://api.deepseek.com/v1/chat/completions"
                
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000
                }
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }

                timeout = aiohttp.ClientTimeout(total=timeout_per_attempt)
                logger.debug(f"[DeepSeek API - Timezone] Попытка {attempt + 1}/{max_retries}")

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        raw_response_text = await response.text()
                        logger.debug(f"[DeepSeek API - Timezone] Попытка {attempt + 1} получила статус: {response.status}")

                        if response.status == 200:
                            result = await response.json()
                            response_text = result['choices'][0]['message']['content']
                            
                            # Попытка парсинга JSON из ответа
                            try:
                                import json
                                import re
                                
                                # Ищем JSON в код блоке
                                json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
                                if json_match:
                                    json_text = json_match.group(1)
                                else:
                                    # Прямая попытка парсинга
                                    json_text = response_text
                                
                                parsed_result = json.loads(json_text)
                                
                                # Проверяем структуру ответа
                                if not isinstance(parsed_result, dict):
                                    raise ValueError("Ответ не является словарем")
                                    
                                logger.debug(f"[DeepSeek API - Timezone] Попытка {attempt + 1} успешна.")
                                return {
                                    'success': True,
                                    'result': parsed_result,
                                    'raw_response': response_text
                                }
                            except json.JSONDecodeError as e:
                                logger.error(f"[DeepSeek API - Timezone] Ошибка парсинга JSON из ответа API: {e}")
                                return {
                                    'success': False,
                                    'error': 'json_parse_error',
                                    'message': 'Ошибка парсинга ответа от API',
                                    'raw_response': response_text
                                }
                            except Exception as e:
                                logger.error(f"[DeepSeek API - Timezone] Ошибка обработки ответа API: {e}")
                                return {
                                    'success': False,
                                    'error': 'response_processing_error',
                                    'message': f'Ошибка обработки ответа: {e}',
                                    'raw_response': response_text
                                }
                        else:
                            logger.warning(f"[DeepSeek API - Timezone] Попытка {attempt + 1} получила статус {response.status}. Ответ: {raw_response_text[:200]}...")
                            last_response_text = raw_response_text

            except asyncio.TimeoutError as te:
                last_exception = te
                logger.debug(f"[DeepSeek API - Timezone] Попытка {attempt + 1} превысила таймаут ({timeout_per_attempt}s): {te}")
                
            except aiohttp.ClientError as ce:
                last_exception = ce
                logger.debug(f"[DeepSeek API - Timezone] Попытка {attempt + 1} ошибка клиента aiohttp: {ce}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"[DeepSeek API - Timezone] Попытка {attempt + 1} неожиданная ошибка: {e}", exc_info=True)

            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1)
                logger.debug(f"[DeepSeek API - Timezone] Ожидание {delay:.2f} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
            else:
                logger.debug(f"[DeepSeek API - Timezone] Все {max_retries} попытки исчерпаны.")

        # Если все попытки провалились
        error_msg = "Превышено время ожидания" if isinstance(last_exception, asyncio.TimeoutError) else str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}..."
        error_code = 'timeout' if isinstance(last_exception, asyncio.TimeoutError) else 'request_failed'
        
        logger.error(f"[DeepSeek API - Timezone] detect_timezone_by_city завершился ошибкой после {max_retries} попыток: {error_msg}")
        return {
            'success': False,
            'error': error_code,
            'message': error_msg,
            'raw_response': last_response_text if last_response_text else (str(last_exception) if last_exception else '')
        }

# Глобальный экземпляр сервиса DeepSeek API
deepseek_api_service = DeepSeekAPIService()

async def punctuate_and_format_text(
    text: str, 
    language: str = 'ru'
) -> Dict[str, Any]:
    """
    Удобная функция для расстановки знаков препинания и форматирования текста
    
    Args:
        text: Текст для расстановки знаков препинания
        language: Язык текста
        
    Returns:
        Dict[str, Any]: Результат форматирования
    """
    return await deepseek_api_service.punctuate_and_format_text(text, language)
