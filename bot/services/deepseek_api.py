"""
Сервис для работы с DeepSeek API
"""

import logging
import asyncio
import aiohttp
import json
import re
import time

from typing import Dict, Any, Optional
from prompts import get_prompt
from core.settings import DEEPSEEK_API_KEY
from bot.utils.html_sanitizer import sanitize_html_in_dict_or_string

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
        max_retries: int = 5,
        base_delay: float = 1.5,
        timeout_per_attempt: int = 100,
        temperature: float = 0.3,
        max_tokens: int = 8100,
    ) -> dict:
        """
        Отправляет готовый промт в DeepSeek и возвращает распарсенный результат.
        Реализует механизм повторных попыток при ошибках.
        """
        logger.debug(
            "[DeepSeek API] Начало send_prompt_and_parse. "
            f"Попыток: {max_retries}, Базовая задержка: {base_delay}s, "
            f"Таймаут: {timeout_per_attempt}s, temperature={temperature}, max_tokens={max_tokens}"
        )
        
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                request_start_time = time.time()
                if not DEEPSEEK_API_KEY:
                    logger.warning("[DeepSeek API] DEEPSEEK_API_KEY не настроен")
                    return {'success': False, 'error': 'api_key_missing', 'result': {}, 'raw_response': ''}
                url = "https://api.deepseek.com/v1/chat/completions"
                # DeepSeek требует слово "json" в промпте при response_format=json_object.
                api_prompt = prompt
                if 'json' not in (prompt or '').lower():
                    api_prompt = (
                        f"{prompt}\n\n"
                        "Ответь строго одним JSON-объектом (json object) без пояснений вне JSON."
                    )
                payload = {
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": api_prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "thinking": {"type": "disabled"},
                    "response_format": {"type": "json_object"},
                }
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }
                timeout = aiohttp.ClientTimeout(total=timeout_per_attempt)
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1}/{max_retries} к {url}")
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        response_text = await response.text()
                        logger.debug(f"[DeepSeek API] Попытка {attempt + 1} получила статус: {response.status}")
                        if response.status == 200:
                            data = await response.json()
                            response_content = data['choices'][0]['message']['content']
                            api_processing_time = data.get('usage', {}).get('total_tokens', 0) * 0.01
                            request_processing_time = time.time() - request_start_time
                            try:
                                result = await self._parse_analysis_response(response_content, language)
                            except ValueError as ve: # Ловим ValueError от _parse_analysis_response
                                logger.error(f"[DeepSeek API] Ошибка парсинга ответа API на попытке {attempt + 1}: {ve}")
                                # Не устанавливаем success = False здесь, просто переходим к следующей итерации цикла (следующей попытке)
                                last_exception = ve
                                last_response_text = response_content # Сохраняем текст, вызвавший ошибку
                                continue # Переходим к следующей попытке, если они есть
                            logger.debug(f"[DeepSeek API] Попытка {attempt + 1} успешна. Время: {request_processing_time:.3f}s")
                            return {
                                'success': True,
                                'result': result,
                                'raw_response': response_content,
                                'processing_time': request_processing_time,  # Добавляем время в ответ
                                'api_usage': data.get('usage', {})
                            }
                        else:
                            logger.warning(f"[DeepSeek API] Попытка {attempt + 1} получила статус {response.status}. Ответ: {response_text[:200]}...")
                            last_response_text = response_text
                            if response.status == 400:
                                response_lower = response_text.lower()
                                if "maximum context length" in response_lower or "context length" in response_lower:
                                    logger.error(
                                        "[DeepSeek API] Контекст запроса превышает лимит модели. "
                                        "Повторные попытки не выполняются."
                                    )
                                    return {
                                        'success': False,
                                        'error': 'context_length_exceeded',
                                        'message': response_text[:500],
                                        'result': {},
                                        'raw_response': response_text,
                                    }
            except asyncio.TimeoutError as te:
                last_exception = te
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1} превысила таймаут ({timeout_per_attempt}s): {te}")
            except aiohttp.ClientError as ce:
                last_exception = ce
                logger.debug(f"[DeepSeek API] Попытка {attempt + 1} ошибка клиента aiohttp: {ce}")
            except Exception as e:
                last_exception = e
                logger.error(f"[DeepSeek API] Попытка {attempt + 1} неожиданная ошибка: {e}", exc_info=True)
            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1)
                logger.debug(f"[DeepSeek API] Ожидание {delay:.2f} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
            else:
                logger.debug(f"[DeepSeek API] Все {max_retries} попыток исчерпаны.")
        failure_payload = self._build_failure_payload(
            last_exception=last_exception,
            last_response_text=last_response_text,
        )
        logger.error(
            f"[DeepSeek API] send_prompt_and_parse завершился ошибкой после {max_retries} попыток: {failure_payload['message']}"
        )
        return failure_payload

    def _build_failure_payload(
        self,
        last_exception: Optional[Exception],
        last_response_text: str,
    ) -> Dict[str, Any]:
        """Build a deterministic failure payload for callers and UI fallbacks."""
        raw_response = last_response_text if last_response_text else (str(last_exception) if last_exception else '')

        if isinstance(last_exception, asyncio.TimeoutError):
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания',
                'result': {},
                'raw_response': raw_response,
            }

        if isinstance(last_exception, ValueError):
            return {
                'success': False,
                'error': 'response_parse_failed',
                'message': 'Не удалось обработать ответ AI. Попробуйте позже.',
                'result': {},
                'raw_response': raw_response,
            }

        if isinstance(last_exception, aiohttp.ClientError):
            return {
                'success': False,
                'error': 'upstream_unavailable',
                'message': 'Внешний AI сервис временно недоступен',
                'result': {},
                'raw_response': raw_response,
            }

        return {
            'success': False,
            'error': 'request_failed',
            'message': str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}...",
            'result': {},
            'raw_response': raw_response,
        }

    # Часто встречающиеся одиночные строковые поля в ответах ИИ.
    _KNOWN_STRING_JSON_KEYS = (
        'prompt_text',
        'motivation_message',
        'cleaned_text',
        'response_text',
        'text',
        'message',
        'analysis',
        'overall_analysis_text',
    )

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Убирает обёртку ``` / ```json вокруг ответа, если она есть."""
        stripped = (text or '').strip()
        if not stripped.startswith('```'):
            return stripped
        match = re.match(r'^```(?:\w+)?\s*(.*?)\s*```$', stripped, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Незакрытый fence: срезаем первую строку ```json
        lines = stripped.split('\n')
        if lines and lines[0].startswith('```'):
            body = '\n'.join(lines[1:])
            if body.rstrip().endswith('```'):
                body = body.rstrip()[:-3]
            return body.strip()
        return stripped

    @staticmethod
    def _repair_json_control_chars(text: str) -> str:
        """Экранирует «сырые» control-символы внутри JSON-строк."""
        out: list[str] = []
        in_string = False
        escape = False
        for ch in text:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == '\\' and in_string:
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                out.append(ch)
                continue
            if in_string:
                if ch == '\n':
                    out.append('\\n')
                    continue
                if ch == '\r':
                    out.append('\\r')
                    continue
                if ch == '\t':
                    out.append('\\t')
                    continue
                if ord(ch) < 0x20:
                    out.append(f'\\u{ord(ch):04x}')
                    continue
            out.append(ch)
        return ''.join(out)

    @staticmethod
    def _unescape_json_string(value: str) -> str:
        """Декодирует стандартные JSON escape-последовательности в строке."""
        try:
            return json.loads(f'"{value}"')
        except json.JSONDecodeError:
            return (
                value.replace('\\n', '\n')
                .replace('\\r', '\r')
                .replace('\\t', '\t')
                .replace('\\"', '"')
                .replace('\\\\', '\\')
            )

    def _extract_string_field_lenient(self, text: str, key: str) -> Optional[str]:
        """
        Достаёт строковое поле даже если внутри значения есть неэкранированные ".
        Конец значения — кавычка, за которой следует "," или "}".
        """
        marker = f'"{key}"'
        key_pos = text.find(marker)
        if key_pos < 0:
            return None
        colon = text.find(':', key_pos + len(marker))
        if colon < 0:
            return None
        i = colon + 1
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text) or text[i] != '"':
            return None
        i += 1
        chars: list[str] = []
        escape = False
        while i < len(text):
            ch = text[i]
            if escape:
                chars.append(ch)
                escape = False
                i += 1
                continue
            if ch == '\\':
                chars.append(ch)
                escape = True
                i += 1
                continue
            if ch == '"':
                rest = text[i + 1:].lstrip()
                if not rest or rest[0] in ',}':
                    return self._unescape_json_string(''.join(chars))
                # Неэкранированная кавычка внутри текста — оставляем как символ.
                chars.append(ch)
                i += 1
                continue
            chars.append(ch)
            i += 1
        return None

    def _extract_known_string_fields(self, text: str) -> Optional[dict]:
        """Fallback: собирает dict из известных строковых ключей."""
        result: dict[str, str] = {}
        for key in self._KNOWN_STRING_JSON_KEYS:
            value = self._extract_string_field_lenient(text, key)
            if value is not None:
                result[key] = value
        return result or None

    def _loads_json_candidate(self, text: str) -> Optional[Any]:
        """Пробует json.loads, ремонт control-chars, extract и lenient string fields."""
        if not text or not text.strip():
            return None
        candidates = (text.strip(), self._repair_json_control_chars(text.strip()))
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        for candidate in candidates:
            extracted = self._extract_json_from_raw_text(candidate)
            if extracted is not None:
                return extracted
        return self._extract_known_string_fields(text)

    def _extract_json_from_raw_text(self, text: str) -> Optional[dict]:
        """
        Пытается найти первый валидный JSON-объект или массив в произвольном тексте
        методом поиска первого { или [ с совпадающим закрывающим символом.
        Возвращает распарсенный объект или None при неудаче.
        """
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            if start == -1:
                continue
            # Находим позицию последнего совпадающего закрывающего символа
            depth = 0
            end = -1
            in_string = False
            escape_next = False
            for i, ch in enumerate(text[start:], start=start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                continue
            candidate = text[start:end + 1]
            for variant in (candidate, self._repair_json_control_chars(candidate)):
                try:
                    return json.loads(variant)
                except json.JSONDecodeError:
                    continue
        return None

    async def _parse_analysis_response(self, response_text: str, language: str) -> dict:
        """
        Парсит ответ от DeepSeek.
        Порядок: прямой JSON → без markdown-fence → блоки ``` → raw extract →
        ремонт control-chars → lenient string fields.
        """
        logger.debug(
            f"[DeepSeek API] Парсинг ответа API, язык: {language}, длина: {len(response_text)}"
        )
        result: Any = None
        try:
            # 1. Прямой JSON
            result = self._loads_json_candidate(response_text)
            if result is None:
                # 2. Срез fence целиком
                stripped = self._strip_markdown_fences(response_text)
                if stripped != response_text.strip():
                    result = self._loads_json_candidate(stripped)

            if result is None:
                # 3. Все markdown-блоки по отдельности
                code_blocks = re.findall(
                    r'```(?:\w+)?\s*(.*?)\s*```', response_text, re.DOTALL
                )
                for i, block in enumerate(code_blocks):
                    result = self._loads_json_candidate(block)
                    if result is not None:
                        logger.debug(
                            f"[DeepSeek API] Успешный парсинг JSON-блока {i + 1} из Markdown."
                        )
                        break

            if result is None:
                logger.warning("[DeepSeek API] Ни один JSON-блок не удалось распарсить корректно.")
                logger.error(
                    "[DeepSeek API] Ни прямой JSON, ни блок Markdown не удалось распарсить "
                    f"корректно. Ответ API: {response_text[:500]}..."
                )
                raise ValueError("Не удалось распарсить корректный JSON из ответа API.")

            logger.debug("[DeepSeek API] Успешный парсинг ответа API.")
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"[DeepSeek API] Неожиданная ошибка при парсинге: {e}")
            logger.error(
                "[DeepSeek API] Ни прямой JSON, ни блок Markdown не удалось распарсить "
                f"корректно. Ответ API: {response_text[:500]}..."
            )
            raise ValueError("Не удалось распарсить корректный JSON из ответа API.") from e

        allowed_tags_for_responses = {'b', 'i', 'u', 'em', 'strong'}
        try:
            sanitized_result = sanitize_html_in_dict_or_string(
                result, allowed_tags=allowed_tags_for_responses
            )
            logger.debug("[DeepSeek API] HTML в строковых значениях результата санитизировано.")
        except Exception as e:
            logger.error(
                f"[DeepSeek API] Ошибка при санитизации HTML в результате: {e}. "
                "Возвращаем оригинальный результат."
            )
            sanitized_result = result

        return sanitized_result
    
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
        if not text or len(text.strip()) < 1:
            return self._make_error_result('text_empty', 'Текст для расстановки знаков препинания пустой', text)
        if len(text) > 5000:
            return self._make_error_result('text_too_long', 'Текст слишком длинный', text)

        if not DEEPSEEK_API_KEY:
            return self._make_error_result('api_key_missing', 'API ключ DeepSeek не настроен', text)
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
        max_retries = 2
        base_delay = 1.0
        timeout_per_attempt = 80
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                url = "https://api.deepseek.com/v1/chat/completions"
                payload = {
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 5000,
                    "thinking": {"type": "disabled"},
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
        error_msg = "Превышено время ожидания" if isinstance(last_exception, asyncio.TimeoutError) else str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}..."
        error_code = 'timeout' if isinstance(last_exception, asyncio.TimeoutError) else 'request_failed'
        logger.error(f"[DeepSeek API - Punctuation] punctuate_and_format_text завершился ошибкой после {max_retries} попыток: {error_msg}")
        return self._make_error_result(error_code, error_msg, text)
    
    async def _extract_formatted_text(self, response_text: str, language: str) -> str:
        """
        Извлекает отформатированный текст из ответа DeepSeek.
        Удаляет префиксы и постфиксы.
        Санитизирует HTML в возвращаемом тексте.
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
        
        # --- НОВОЕ: Санитизация HTML в извлеченном тексте ---
        # Используем ту же утилиту, передав ей строку
        allowed_tags_for_punctuation = {'b', 'i', 'u', 'em', 'strong'} # Уточните, какие теги ИИ может использовать
        try:
            sanitized_formatted_text = sanitize_html_in_dict_or_string(formatted_text, allowed_tags=allowed_tags_for_punctuation)
            logger.debug("[DeepSeek API] HTML в извлеченном тексте санитизировано.")
        except Exception as e:
            logger.error(f"[DeepSeek API] Ошибка при санитизации HTML в извлеченном тексте: {e}. Возвращаем оригинальный текст.")
            sanitized_formatted_text = formatted_text
        # --- КОНЕЦ САНИТИЗАЦИИ ---

        return sanitized_formatted_text if sanitized_formatted_text else response_text.strip()

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
            'model_used': api_result.get('model', 'deepseek-v4-flash'),
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
            'model_used': 'deepseek-v4-flash',
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
        try:
            prompt = get_prompt(
                key='timezone_detection',
                language=language,
                city_name=city_name
            )
        except Exception as e:
            logger.error(f"[DeepSeek API - Timezone] Ошибка форматирования промпта 'timezone_detection': {e}")
            return {
                'success': False,
                'error': 'prompt_generation_failed',
                'message': f'Ошибка генерации промпта: {e}'
            }
        max_retries = 3
        base_delay = 1.5
        timeout_per_attempt = 30
        last_exception = None
        last_response_text = ""

        for attempt in range(max_retries):
            try:
                url = "https://api.deepseek.com/v1/chat/completions"
                payload = {
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                    "thinking": {"type": "disabled"},
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
                        if response.status == 200:
                            result = await response.json()
                            response_text = result['choices'][0]['message']['content']
                            try:
                                json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
                                if json_match:
                                    json_text = json_match.group(1)
                                else:
                                    json_text = response_text
                                parsed_result = json.loads(json_text)
                                if not isinstance(parsed_result, dict):
                                    raise ValueError("Ответ не является словарем")
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
                logger.warning(f"[DeepSeek API - Timezone] Попытка {attempt + 1} превысила таймаут ({timeout_per_attempt}s): {te}")
            except aiohttp.ClientError as ce:
                last_exception = ce
                logger.warning(f"[DeepSeek API - Timezone] Попытка {attempt + 1} ошибка клиента aiohttp: {ce}")
            except Exception as e:
                last_exception = e
                logger.warning(f"[DeepSeek API - Timezone] Попытка {attempt + 1} неожиданная ошибка: {e}", exc_info=True)
            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1)
                await asyncio.sleep(delay)
            else:
                logger.debug(f"[DeepSeek API - Timezone] Все {max_retries} попытки исчерпаны.")
        error_msg = "Превышено время ожидания" if isinstance(last_exception, asyncio.TimeoutError) else str(last_exception) if last_exception else f"Ошибка API: {last_response_text[:200]}..."
        error_code = 'timeout' if isinstance(last_exception, asyncio.TimeoutError) else 'request_failed'
        logger.error(f"[DeepSeek API - Timezone] detect_timezone_by_city завершился ошибкой после {max_retries} попыток: {error_msg}")
        return {
            'success': False,
            'error': error_code,
            'message': error_msg,
            'raw_response': last_response_text if last_response_text else (str(last_exception) if last_exception else '')
        }

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
