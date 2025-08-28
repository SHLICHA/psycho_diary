"""
Сервис для работы с DeepSeek API
"""

import logging
import asyncio
import json
import aiohttp
import re

from typing import Dict, Any
from prompts import get_prompt
from core.settings import DEEPSEEK_API_KEY
from bot.utils.api_utils import api_retry, handle_api_error

logger = logging.getLogger(__name__)

class DeepSeekAPIService:
    def __init__(self):
        """Инициализация сервиса DeepSeek API"""
        if not DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY не настроен")

    # TODO Объединить валидацию длинны текста
    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def analyze_text(self, text: str, language: str = 'ru', analysis_type: str = 'default') -> Dict[str, Any]:
        """Анализ текста через DeepSeek API

        Args:
            text: Текст для анализа
            language: Язык анализа
            analysis_type: Тип анализа (emotion, default и т.д.)

        Returns:
            Dict[str, Any]: Результат анализа с финальным analysis_text
        """
        logger.info(f"Текст длиной: {len(text)} символов")
        if not text or len(text.strip()) < 1:
            logger.error("Текст для анализа пустой")
            api_response_data = {
                'status': 'text_empty',
                'error_text': 'Текст для анализа пустой',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'text_empty',
                'message': 'Текст для анализа пустой',
                'result': {},
                'raw_response': '',
                'api_response': api_response_data
            }
        if len(text) > 15000:
            logger.error("Текст для анализа слишком длинный")
            api_response_data = {
                'status': 'text_too_long',
                'error_text': 'Текст для анализа слишком длинный',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'text_too_long',
                'message': 'Текст для анализа слишком длинный',
                'result': {},
                'raw_response': '',
                'api_response': api_response_data
            }
        if not DEEPSEEK_API_KEY:
            logger.error("DeepSeek API key not configured")
            api_response_data = {
                'status': 'api_key_missing',
                'error_text': 'API ключ DeepSeek не настроен',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ DeepSeek не настроен',
                'result': {},
                'api_response': api_response_data
            }
        prompt = await self._generate_analysis_prompt(text, language, analysis_type)
        logger.info(f"Сформирован промт для анализа длиной: {len(prompt)} символов")
        url = "https://api.deepseek.com/v1/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,  # Низкая температура для точного анализа
            "max_tokens": 5000
        }
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    raw_response_text = await response.text()
                    logger.info(f"Получен ответ от DeepSeek API, статус: {response.status}")
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        logger.info(f"Текст успешно проанализирован, длина ответа: {len(response_text)} символов")
                        parsed_api_result = await self._parse_analysis_response(response_text, language, analysis_type)
                        comment_part = parsed_api_result.get('comment', 'Анализ записан')
                        recommendation_part = parsed_api_result.get('recommendation', 'Продолжайте в том же духе')
                        final_analysis_text = f"{comment_part}\n{recommendation_part}".strip()
                        if not final_analysis_text:
                             final_analysis_text = "Текст проанализирован."
                        final_result = parsed_api_result.copy()
                        final_result['analysis'] = final_analysis_text
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Текст успешно проанализирован',
                            'result': final_result,
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': response_text,
                            'needs_clarification': parsed_api_result.get('needs_clarification', False),
                            'clarification_questions': parsed_api_result.get('clarification_questions', []),
                            'api_response': api_response_data
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error: {response.status} - {error_text}")
                        api_response_data = {
                            'status': response.status,
                            'error_text': error_text,
                            'raw_response': error_text,
                            'model_used': 'deepseek-chat',
                            'usage': {},
                            'processing_time': 0,
                            'tokens_used': 0
                        }
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API: {response.status}',
                            'result': {},
                            'raw_response': error_text,
                            'api_response': api_response_data
                        }
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout")
            api_response_data = {
                'status': 'timeout',
                'error_text': 'Превышено время ожидания ответа от DeepSeek API',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API',
                'result': {},
                'raw_response': '',
                'api_response': api_response_data
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed: {e}")
            api_response_data = {
                'status': 'general_error',
                'error_text': str(e),
                'raw_response': str(e),
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при анализе текста',
                'result': {},
                'raw_response': str(e),
                'api_response': api_response_data
            }

    # TODO Объединить валидацию длинны текста
    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def analyze_text_with_profile(
        self,
        text: str,
        user_profile: dict,
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Анализ текста с профилем пользователя через DeepSeek API.

        Args:
            text: Текст для анализа.
            user_profile: Данные профиля пользователя.
            language: Язык анализа.

        Returns:
            Dict[str, Any]: Результат анализа с финальным analysis_text и метаданными API.
        """
        logger.info(f"Текст длиной: {len(text)} символов")
        try:
            if not text or len(text.strip()) < 1:
                logger.error("Текст для анализа пустой")
                api_response_data = {
                    'status': 'text_empty',
                    'error_text': 'Текст для анализа пустой',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'text_empty',
                    'message': 'Текст для анализа пустой',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }
            if len(text) > 1000:
                logger.error("Текст для анализа слишком длинный")
                api_response_data = {
                    'status': 'text_too_long',
                    'error_text': 'Текст для анализа слишком длинный',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'text_too_long',
                    'message': 'Текст для анализа слишком длинный',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }
            if not DEEPSEEK_API_KEY:
                logger.error("DeepSeek API key not configured")
                api_response_data = {
                    'status': 'api_key_missing',
                    'error_text': 'API ключ DeepSeek не настроен',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'api_key_missing',
                    'message': 'API ключ DeepSeek не настроен',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }
            prompt = await self._generate_analysis_prompt(text, language, 'profile')
            logger.info(f"Сформирован промт для анализа с профилем длиной: {len(prompt)} символов")
            url = "https://api.deepseek.com/v1/chat/completions"
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 5000
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    raw_response_text = await response.text()
                    logger.info(f"Получен ответ от DeepSeek API для анализа с профилем, статус: {response.status}")
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        logger.info(f"Текст успешно проанализирован с профилем, длина ответа LLM: {len(response_text)} символов")
                        parsed_result = await self._parse_analysis_response(response_text, language)
                        comment_part = parsed_result.get('comment', '')
                        recommendation_part = parsed_result.get('recommendation', '')
                        analysis_part = parsed_result.get('analysis', 'Текст проанализирован.')
                        final_analysis_text = f"{comment_part} {recommendation_part} {analysis_part}".strip()
                        if not final_analysis_text:
                            final_analysis_text = "Текст проанализирован."
                        final_result = parsed_result.copy()
                        final_result['analysis'] = final_analysis_text
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        final_result['api_response'] = api_response_data
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Текст успешно проанализирован с профилем',
                            'result': final_result,
                            'raw_response': raw_response_text,
                            'api_response': api_response_data
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при анализе с профилем: {response.status} - {error_text}")
                        api_response_data = {
                            'status': response.status,
                            'error_text': error_text,
                            'raw_response': error_text,
                            'model_used': 'deepseek-chat',
                            'usage': {},
                            'processing_time': 0,
                            'tokens_used': 0
                        }
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при анализе с профилем: {response.status}',
                            'result': {},
                            'raw_response': error_text,
                            'api_response': api_response_data
                        }
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при анализе с профилем")
            api_response_data = {
                'status': 'timeout',
                'error_text': 'Превышено время ожидания ответа от DeepSeek API',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при анализе с профилем',
                'result': {},
                'raw_response': '',
                'api_response': api_response_data
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при анализе с профилем: {e}")
            api_response_data = {
                'status': 'general_error',
                'error_text': str(e),
                'raw_response': str(e),
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при анализе текста с профилем',
                'result': {},
                'raw_response': str(e),
                'api_response': api_response_data
            }
    
    # TODO Объединить все три, если получится. Точно объединить валидацию
    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def analyze_text_with_clarifications(
        self,
        original_text: str,
        clarification_answers: str,
        user_profile: dict,
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Финальный анализ текста с учетом ответов на уточняющие вопросы через DeepSeek API.

        Args:
            original_text: Оригинальный текст записи.
            clarification_answers: Ответы пользователя на уточняющие вопросы.
            user_profile: Данные профиля пользователя.
            language: Язык анализа.

        Returns:
            Dict[str, Any]: Результат финального анализа.
        """
        try:
            if not original_text or len(original_text.strip()) < 1:
                logger.error("Оригинальный текст для финального анализа пустой")
            if not clarification_answers or len(clarification_answers.strip()) < 1:
                 logger.error("Ответы на уточнения для финального анализа пустые")
            if not DEEPSEEK_API_KEY:
                logger.error("DeepSeek API key not configured")
            prompt = await self._generate_clarification_analysis_prompt(
                original_text, clarification_answers, user_profile, language
            )
            url = "https://api.deepseek.com/v1/chat/completions"
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 5000
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    raw_response_text = await response.text()
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        parsed_result = await self._parse_analysis_response(
                            response_text, language, 'clarification'
                        )
                        final_analysis_text = parsed_result.get('analysis', 'Текст проанализирован.')
                        final_result = parsed_result.copy()
                        final_result['analysis'] = final_analysis_text
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        final_result['api_response'] = api_response_data
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Финальный анализ текста с уточнениями успешно выполнен',
                            'result': final_result,
                            'raw_response': raw_response_text,
                            'api_response': api_response_data
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при финальном анализе с уточнениями: {response.status} - {error_text}")  
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при финальном анализе с уточнениями")
        except Exception as e:
            logger.error(f"DeepSeek API request failed при финальном анализе с уточнениями: {e}")

    # TODO добавить вопросы
    async def _generate_clarification_analysis_prompt(
        self,
        original_text: str,
        clarification_answers: str,
        user_profile: dict,
        language: str
    ) -> str:
        """
        Генерация промта для финального анализа текста с учетом ответов на уточнения.

        Args:
            original_text: Оригинальный текст записи.
            clarification_answers: Ответы пользователя.
            user_profile: Профиль пользователя.
            language: Язык ('ru' или 'en').

        Returns:
            str: Сформированный промт.
        """
        keys = {
            'original_text': original_text,
            'clarification_answers': clarification_answers
        }
        print(get_prompt('final_with_clarifications', language, keys))
        prompts = {
            'ru': f'''Ты профессиональный психолог. Ниже приведена запись пользователя, на которую были заданы уточняющие вопросы, и ответы пользователя на них.

Оригинальная запись пользователя:
"{original_text}"

Ответы пользователя на уточнения:
"{clarification_answers}"

Пожалуйста, предоставь финальный психологический анализ этой записи, учитывая как оригинальный текст, так и ответы на уточнения. Ответ должен быть в стандартном формате JSON:
- "mood_score": оценка настроения от 1 до 10
- "comment": краткий комментарий (1 предложение)
- "recommendation": персональная рекомендация (1-2 предложения)
- "analysis": подробный финальный анализ (3-4 предложения)
- "suggested_task": объект (не обязательный пункт, только если необходимо, описание задания)
   - "title": название задания
   - "description": описание задания
   - "type": тип задания (из списка: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": приоритет (строка: low, medium, high, critical)
- "key_points": массив объектов (ключевые моменты)
   - "text": текст ключевого момента
   - "type": тип (emotion, event, thought, trigger, other)
   - "confidence": уверенность (float от 0.0 до 1.0)
- "user_insights": массив объектов (новые инсайты)
   - "text": текст инсайта
   - "category": категория из списка: emotion, behavior, thought, trigger, pattern, belief, other
   - "weight": вес (int, от 1 до 10)

Пример ответа:
{{
  "mood_score": 8,
  "comment": "Благодаря уточнениям, стало ясно, что вы мотивированы и поддерживаете себя.",
  "recommendation": "Продолжайте использовать внутренний диалог для самоподдержки.",
  "analysis": "Оригинальная запись содержала элементы самоодобрения. В ответах на уточнения вы подтвердили, что обращаетесь к себе. Это свидетельствует о развитом навыке самосострадания. Такой подход помогает эффективно справляться со стрессом и повышает устойчивость. Рекомендуется поощрять это позитивное поведение.",
  "suggested_task": {{
    "title": "Ежедневная благодарность себе",
    "description": "Каждый вечер записывайте одно достижение или качество, за которое вы благодарны себе.",
    "type": "mindfulness",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "самоодобрение",
      "type": "thought",
      "confidence": 0.95
    }},
    {{
      "text": "мотивация",
      "type": "emotion",
      "confidence": 0.9
    }}
  ],
  "user_insights": [
    {{
      "text": "Самосострадание - эффективный механизм эмоциональной регуляции",
      "category": "personal",
      "weight": 2
    }}
  ]
}}
''',
            'en': f'''You are a professional psychologist. Below is a user's entry, clarification questions that were asked, and the user's answers to those questions.

Original user entry:
"{original_text}"

User's answers to clarifications:
"{clarification_answers}"

Please provide a final psychological analysis of this entry, taking into account both the original text and the clarification answers. The response must be in standard JSON format:
- "mood_score": mood score from 1 to 10
- "comment": brief comment (1 sentence)
- "recommendation": personal recommendation (1-2 sentences)
- "analysis": detailed final analysis (3-4 sentences)
- "suggested_task": object (optional, only if necessary, task description)
   - "title": task title
   - "description": task description
   - "type": task type (from the list: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": priority (string: low, medium, high, critical)
- "key_points": array of objects (key points)
   - "text": text of the key point
   - "type": type (emotion, event, thought, trigger, other)
   - "confidence": confidence (float from 0.0 to 1.0)
- "user_insights": array of objects (new insights)
   - "text": text of the insight
   - "category": category from the list: emotion, behavior, thought, trigger, pattern, belief, other
   - "weight": weight (int, from 1 to 10)

Example response:
{{
  "mood_score": 8,
  "comment": "Thanks to the clarifications, it became clear that you are motivated and self-supporting.",
  "recommendation": "Continue to use inner dialogue for self-support.",
  "analysis": "The original entry contained elements of self-approval. Your answers to the clarifications confirmed that you were addressing yourself. This indicates a developed skill of self-compassion. This approach helps to cope with stress effectively and increases resilience. It is recommended to encourage this positive behavior.",
  "suggested_task": {{
    "title": "Daily Gratitude to Yourself",
    "description": "Every evening, write down one achievement or quality you are grateful for in yourself.",
    "type": "mindfulness",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "self-approval",
      "type": "thought",
      "confidence": 0.95
    }},
    {{
      "text": "motivation",
      "type": "emotion",
      "confidence": 0.9
    }}
  ],
  "user_insights": [
    {{
      "text": "Self-compassion is an effective mechanism of emotional regulation",
      "category": "personal",
      "weight": 2
    }}
  ]
}}
'''
        }

        prompt = prompts.get(language, prompts['en']) # По умолчанию английский
        logger.info(f"Промт для финального анализа с уточнениями сгенерирован длиной: {len(prompt)} символов")
        return prompt

    async def _generate_profile_based_analysis_prompt(
        self, 
        text: str, 
        user_profile: dict, 
        language: str
    ) -> str:
        """
        Генерация промта для анализа текста с профилем пользователя
        
        Args:
            text: Текст для анализа
            user_profile: Данные профиля пользователя
            language: Язык анализа
            
        Returns:
            str: Сформированный промт
        """
        logger.info(f"Генерация промта для анализа текста с профилем, язык: {language}")
        
        try:
            # Формируем промт в зависимости от языка
            if language == 'ru':
                prompt = f'''Проанализируй запись в дневнике и ответь в формате JSON:

    Запись для анализа:
    {text}

    Профиль пользователя:
    Имя пользователя: {user_profile.get('username', 'unknown')}
    Имя: {user_profile.get('first_name', '')}
    Фамилия: {user_profile.get('last_name', '')}
    Уровень осознанности: {user_profile.get('awareness_level', 1)}/10
    Премиум статус: {'Да' if user_profile.get('is_premium', False) else 'Нет'}
    Количество записей: {user_profile.get('entries_count', 0)}
    Дата регистрации: {user_profile.get('registration_date', 'unknown')}

    История последних записей:
    {json.dumps(user_profile.get('entry_history', []), ensure_ascii=False, indent=2)}

    Инсайты пользователя:
    {json.dumps(user_profile.get('user_insights', []), ensure_ascii=False, indent=2)}

    Ответь в формате JSON с полями:
    - "mood_score": оценка настроения от 1 до 10 (1 - ужасно, 10 - прекрасно)
    - "comment": краткий комментарий (1 предложение)
    - "recommendation": персональная рекомендация (1-2 предложения)
    - "analysis": подробный анализ (2-3 предложения)
    - "needs_clarification": boolean - нужны ли уточнения
    - "clarification_questions": массив строк - вопросы для уточнения (если needs_clarification=true)

    Пример ответа:
    {{"mood_score": 7, "comment": "Хорошее настроение", "recommendation": "Продолжайте в том же духе", "analysis": "Текст содержит позитивные эмоции", "needs_clarification": false, "clarification_questions": []}}'''
            else:
                prompt = f'''Analyze the diary entry and respond in JSON format:

    Entry to analyze:
    {text}

    User profile:
    Username: {user_profile.get('username', 'unknown')}
    First name: {user_profile.get('first_name', '')}
    Last name: {user_profile.get('last_name', '')}
    Awareness level: {user_profile.get('awareness_level', 1)}/10
    Premium status: {'Yes' if user_profile.get('is_premium', False) else 'No'}
    Entries count: {user_profile.get('entries_count', 0)}
    Registration date: {user_profile.get('registration_date', 'unknown')}

    History of recent entries:
    {json.dumps(user_profile.get('entry_history', []), ensure_ascii=False, indent=2)}

    User insights:
    {json.dumps(user_profile.get('user_insights', []), ensure_ascii=False, indent=2)}

    Respond in JSON format with fields:
    - "mood_score": mood rating from 1 to 10 (1 - terrible, 10 - wonderful)
    - "comment": brief comment (1 sentence)
    - "recommendation": personal recommendation (1-2 sentences)
    - "analysis": detailed analysis (2-3 sentences)
    - "needs_clarification": boolean - whether clarification is needed
    - "clarification_questions": array of strings - questions for clarification (if needs_clarification=true)

    Example response:
    {{"mood_score": 7, "comment": "Good mood", "recommendation": "Keep it up", "analysis": "The text contains positive emotions", "needs_clarification": false, "clarification_questions": []}}'''
            
            logger.info(f"Промт для анализа с профилем сгенерирован длиной: {len(prompt)} символов")
            return prompt
            
        except Exception as e:
            logger.error(f"Ошибка при генерации промта для анализа с профилем: {e}")
            return text  # Возвращаем оригинальный текст в случае ошибки

    async def _parse_profile_based_analysis_response(
        self, 
        response_text: str, 
        language: str
    ) -> Dict[str, Any]:
        """
        Парсинг ответа анализа текста с профилем
        
        Args:
            response_text: Текст ответа от API
            language: Язык ответа
            
        Returns:
            Dict[str, Any]: Распарсенный результат анализа
        """
        logger.info(f"Парсинг ответа анализа текста с профилем, язык: {language}")
        logger.info(f"Текст ответа длиной: {len(response_text)} символов")
        
        try:
            import json
            
            # Пытаемся распарсить JSON
            analysis_result = json.loads(response_text)
            
            logger.info("Ответ анализа с профилем успешно распарсен")
            return analysis_result
            
        except json.JSONDecodeError as json_error:
            logger.error(f"Ошибка при парсинге JSON ответа анализа с профилем: {json_error}")
            
            # Возвращаем заглушку в случае ошибки
            default_result = {
                'mood_score': 5,
                'comment': 'Анализ записан' if language == 'ru' else 'Analysis recorded',
                'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary',
                'analysis': 'Текст проанализирован' if language == 'ru' else 'Text analyzed',
                'needs_clarification': False,
                'clarification_questions': []
            }
            
            logger.info("Возвращен результат анализа по умолчанию")
            return default_result
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа анализа с профилем: {e}")
            
            # Возвращаем заглушку в случае ошибки
            default_result = {
                'mood_score': 5,
                'comment': 'Анализ записан' if language == 'ru' else 'Analysis recorded',
                'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary',
                'analysis': 'Текст проанализирован' if language == 'ru' else 'Text analyzed',
                'needs_clarification': False,
                'clarification_questions': []
            }
            
            logger.info("Возвращен результат анализа по умолчанию")
            return default_result

    async def _generate_final_analysis_prompt(
        self, 
        text: str, 
        user_profile: dict, 
        language: str,
        initial_analysis: dict = None,
        questions: list = None
    ) -> str:
        """
        Генерация промта для финального анализа текста с уточнениями
        
        Args:
            text: Текст уточнений
            user_profile: Данные профиля пользователя
            language: Язык анализа
            initial_analysis: Предыдущий анализ
            questions: Уточняющие вопросы
            
        Returns:
            str: Сформированный промт
        """
        logger.info(f"Генерация промта для финального анализа текста с уточнениями, язык: {language}")
        
        try:
            # Формируем промт в зависимости от языка
            if language == 'ru':
                prompt = f'''Выполни финальный анализ записи в дневнике с учетом уточнений и ответь в формате JSON:

    Исходная запись:
    {user_profile.get('original_text', 'unknown')}

    Уточняющие вопросы:
    {json.dumps(questions, ensure_ascii=False, indent=2) if questions else 'Нет вопросов'}

    Ответы на уточнения:
    {text}

    Профиль пользователя:
    Имя пользователя: {user_profile.get('username', 'unknown')}
    Имя: {user_profile.get('first_name', '')}
    Фамилия: {user_profile.get('last_name', '')}
    Уровень осознанности: {user_profile.get('awareness_level', 1)}/10
    Премиум статус: {'Да' if user_profile.get('is_premium', False) else 'Нет'}
    Количество записей: {user_profile.get('entries_count', 0)}
    Дата регистрации: {user_profile.get('registration_date', 'unknown')}

    История последних записей:
    {json.dumps(user_profile.get('entry_history', []), ensure_ascii=False, indent=2)}

    Инсайты пользователя:
    {json.dumps(user_profile.get('user_insights', []), ensure_ascii=False, indent=2)}

    Предыдущий анализ:
    {json.dumps(initial_analysis, ensure_ascii=False, indent=2) if initial_analysis else 'Нет предыдущего анализа'}

    Ответь в формате JSON с полями:
    - "mood_score": оценка настроения от 1 до 10 (1 - ужасно, 10 - прекрасно)
    - "comment": краткий комментарий (1 предложение)
    - "recommendation": персональная рекомендация (1-2 предложения)
    - "analysis": подробный анализ (2-3 предложения)

    Пример ответа:
    {{"mood_score": 7, "comment": "Хорошее настроение", "recommendation": "Продолжайте в том же духе", "analysis": "Текст содержит позитивные эмоции"}}'''
            else:
                prompt = f'''Perform final analysis of the diary entry with clarifications and respond in JSON format:

    Original entry:
    {user_profile.get('original_text', 'unknown')}

    Clarification questions:
    {json.dumps(questions, ensure_ascii=False, indent=2) if questions else 'No questions'}

    Answers to clarifications:
    {text}

    User profile:
    Username: {user_profile.get('username', 'unknown')}
    First name: {user_profile.get('first_name', '')}
    Last name: {user_profile.get('last_name', '')}
    Awareness level: {user_profile.get('awareness_level', 1)}/10
    Premium status: {'Yes' if user_profile.get('is_premium', False) else 'No'}
    Entries count: {user_profile.get('entries_count', 0)}
    Registration date: {user_profile.get('registration_date', 'unknown')}

    History of recent entries:
    {json.dumps(user_profile.get('entry_history', []), ensure_ascii=False, indent=2)}

    User insights:
    {json.dumps(user_profile.get('user_insights', []), ensure_ascii=False, indent=2)}

    Previous analysis:
    {json.dumps(initial_analysis, ensure_ascii=False, indent=2) if initial_analysis else 'No previous analysis'}

    Respond in JSON format with fields:
    - "mood_score": mood rating from 1 to 10 (1 - terrible, 10 - wonderful)
    - "comment": brief comment (1 sentence)
    - "recommendation": personal recommendation (1-2 sentences)
    - "analysis": detailed analysis (2-3 sentences)

    Example response:
    {{"mood_score": 7, "comment": "Good mood", "recommendation": "Keep it up", "analysis": "The text contains positive emotions"}}'''
            
            logger.info(f"Промт для финального анализа сгенерирован длиной: {len(prompt)} символов")
            return prompt
            
        except Exception as e:
            logger.error(f"Ошибка при генерации промта для финального анализа: {e}")
            return text  # Возвращаем оригинальный текст в случае ошибки

    async def _parse_final_analysis_response(
        self, 
        response_text: str, 
        language: str
    ) -> Dict[str, Any]:
        """
        Парсинг ответа финального анализа текста
        
        Args:
            response_text: Текст ответа от API
            language: Язык ответа
            
        Returns:
            Dict[str, Any]: Распарсенный результат финального анализа
        """
        logger.info(f"Парсинг ответа финального анализа текста, язык: {language}")
        logger.info(f"Текст ответа длиной: {len(response_text)} символов")
        
        try:
            import json
            
            # Пытаемся распарсить JSON
            final_analysis_result = json.loads(response_text)
            
            logger.info("Ответ финального анализа успешно распарсен")
            return final_analysis_result
            
        except json.JSONDecodeError as json_error:
            logger.error(f"Ошибка при парсинге JSON ответа финального анализа: {json_error}")
            
            # Возвращаем заглушку в случае ошибки
            default_result = {
                'mood_score': 5,
                'comment': 'Финальный анализ записан' if language == 'ru' else 'Final analysis recorded',
                'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary',
                'analysis': 'Текст проанализирован финально' if language == 'ru' else 'Text analyzed finally'
            }
            
            logger.info("Возвращен результат финального анализа по умолчанию")
            return default_result
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа финального анализа: {e}")
            
            # Возвращаем заглушку в случае ошибки
            default_result = {
                'mood_score': 5,
                'comment': 'Финальный анализ записан' if language == 'ru' else 'Final analysis recorded',
                'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary',
                'analysis': 'Текст проанализирован финально' if language == 'ru' else 'Text analyzed finally'
            }
            
            logger.info("Возвращен результат финального анализа по умолчанию")
            return default_result

    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def generate_response(
        self, 
        prompt: str, 
        language: str = 'ru',
        max_tokens: int = 5000
    ) -> Dict[str, Any]:
        """
        Генерация ответа через DeepSeek API
        
        Args:
            prompt: Промт для генерации
            language: Язык генерации
            max_tokens: Максимальное количество токенов
            
        Returns:
            Dict[str, Any]: Результат генерации с api_response
        """
        logger.info(f"Генерация ответа через DeepSeek API, язык: {language}, max_tokens: {max_tokens}")
        logger.info(f"Промт длиной: {len(prompt)} символов")
        
        # Проверяем минимальную длину промта
        if not prompt or len(prompt.strip()) < 1:
            logger.error("Промт для генерации пустой")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'prompt_empty',
                'error_text': 'Промт для генерации пустой',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'prompt_empty',
                'message': 'Промт для генерации пустой',
                'result': '',
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        # Проверяем максимальную длину промта
        if len(prompt) > 5000:
            logger.error("Промт для генерации слишком длинный")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'prompt_too_long',
                'error_text': 'Промт для генерации слишком длинный',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'prompt_too_long',
                'message': 'Промт для генерации слишком длинный',
                'result': '',
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        # Проверяем наличие API ключа
        if not DEEPSEEK_API_KEY:
            logger.error("DeepSeek API key not configured")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'api_key_missing',
                'error_text': 'API ключ DeepSeek не настроен',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ DeepSeek не настроен',
                'result': '',
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        url = "https://api.deepseek.com/v1/chat/completions"
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            # Создаем сессию aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    raw_response_text = await response.text()
                    logger.info(f"Получен ответ от DeepSeek API, статус: {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        
                        logger.info(f"Ответ успешно сгенерирован, длина: {len(response_text)} символов")
                        
                        # Извлекаем только отформатированный текст (ИСПРАВЛЕНО!)
                        formatted_text = await self._extract_formatted_text(response_text, language)
                        logger.info(f"Отформатированный текст извлечен, длина: {len(formatted_text)} символов")
                        
                        # Сохраняем сырой ответ API для отладки (ИСПРАВЛЕНО!)
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Ответ успешно сгенерирован',
                            'result': formatted_text,
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': raw_response_text,  # Сырой ответ для отладки
                            'api_response': api_response_data  # Ответ API для сохранения в БД!
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при генерации: {response.status} - {error_text}")
                        
                        # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
                        api_response_data = {
                            'status': response.status,
                            'error_text': error_text,
                            'raw_response': error_text,
                            'model_used': 'deepseek-chat',
                            'usage': {},
                            'processing_time': 0,
                            'tokens_used': 0
                        }
                        
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при генерации: {response.status}',
                            'result': '',
                            'raw_response': error_text,  # Сырой ответ для отладки
                            'api_response': api_response_data  # Ответ API для сохранения в БД!
                        }
                        
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при генерации")
            
            # Сохраняем ответ API даже при таймауте (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'timeout',
                'error_text': 'Превышено время ожидания ответа от DeepSeek API',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при генерации',
                'result': '',
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при генерации: {e}")
            
            # Сохраняем ответ API даже при общей ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'general_error',
                'error_text': str(e),
                'raw_response': str(e),
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при генерации ответа',
                'result': '',
                'raw_response': str(e),  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
    
    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def punctuate_and_format_text(
        self, 
        text: str, 
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Расстановка знаков препинания и форматирование текста через DeepSeek API
        
        Args:
            text: Текст для расстановки знаков препинания
            language: Язык текста
            
        Returns:
            Dict[str, Any]: Результат форматирования с api_response
        """
        logger.info(f"Расстановка знаков препинания через DeepSeek API, язык: {language}")
        logger.info(f"Текст длиной: {len(text)} символов")
        
        # Проверяем минимальную длину текста
        if not text or len(text.strip()) < 1:
            logger.error("Текст для расстановки знаков препинания пустой")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'text_empty',
                'error_text': 'Текст для расстановки знаков препинания пустой',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'text_empty',
                'message': 'Текст для расстановки знаков препинания пустой',
                'result': text,
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        # Проверяем максимальную длину текста
        if len(text) > 5000:
            logger.error("Текст для расстановки знаков препинания слишком длинный")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'text_too_long',
                'error_text': 'Текст для расстановки знаков препинания слишком длинный',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'text_too_long',
                'message': 'Текст для расстановки знаков препинания слишком длинный',
                'result': text,
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        # Проверяем наличие API ключа
        if not DEEPSEEK_API_KEY:
            logger.error("DeepSeek API key not configured")
            
            # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'api_key_missing',
                'error_text': 'API ключ DeepSeek не настроен',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ DeepSeek не настроен',
                'result': text,
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        
        # Формируем промт для расстановки знаков препинания
        prompt = await self._generate_punctuation_prompt(text, language)
        logger.info(f"Сформирован промт для расстановки знаков препинания длиной: {len(prompt)} символов")
        
        url = "https://api.deepseek.com/v1/chat/completions"
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,  # Низкая температура для точного форматирования
            "max_tokens": 5000  # Удваиваем токены для длинных текстов
        }
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            # Создаем сессию aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    raw_response_text = await response.text()
                    logger.info(f"Получен ответ от DeepSeek API, статус: {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        
                        logger.info(f"Знаки препинания успешно расставлены, длина ответа: {len(response_text)} символов")
                        
                        # Извлекаем только отформатированный текст (ИСПРАВЛЕНО!)
                        formatted_text = await self._extract_formatted_text(response_text, language)
                        logger.info(f"Отформатированный текст извлечен, длина: {len(formatted_text)} символов")
                        
                        # Сохраняем сырой ответ API для отладки (ИСПРАВЛЕНО!)
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Знаки препинания успешно расставлены',
                            'result': formatted_text,
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': raw_response_text,  # Сырой ответ для отладки
                            'api_response': api_response_data  # Ответ API для сохранения в БД!
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при расстановке знаков препинания: {response.status} - {error_text}")
                        
                        # Сохраняем ответ API даже при ошибке (ИСПРАВЛЕНО!)
                        api_response_data = {
                            'status': response.status,
                            'error_text': error_text,
                            'raw_response': error_text,
                            'model_used': 'deepseek-chat',
                            'usage': {},
                            'processing_time': 0,
                            'tokens_used': 0
                        }
                        
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при расстановке знаков препинания: {response.status}',
                            'result': text,
                            'raw_response': error_text,  # Сырой ответ для отладки
                            'api_response': api_response_data  # Ответ API для сохранения в БД!
                        }
                        
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при расстановке знаков препинания")
            
            # Сохраняем ответ API даже при таймауте (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'timeout',
                'error_text': 'Превышено время ожидания ответа от DeepSeek API',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при расстановке знаков препинания',
                'result': text,
                'raw_response': '',  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при расстановке знаков препинания: {e}")
            
            # Сохраняем ответ API даже при общей ошибке (ИСПРАВЛЕНО!)
            api_response_data = {
                'status': 'general_error',
                'error_text': str(e),
                'raw_response': str(e),
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при расстановке знаков препинания',
                'result': text,
                'raw_response': str(e),  # Сырой ответ для отладки
                'api_response': api_response_data  # Ответ API для сохранения в БД!
            }
    
    async def _generate_analysis_prompt(
        self, 
        text: str, 
        language: str, 
        analysis_type: str
    ) -> str:
        """
        Генерация промта для анализа текста.
        
        Args:
            text: Текст для анализа.
            language: Язык анализа ('ru' или 'en').
            analysis_type: Тип анализа ('default', 'emotion').
            
        Returns:
            str: Сформированный промт.
        """
        logger.info(f"Генерация промта для анализа текста, тип: {analysis_type}, язык: {language}")
        
        prompts = {
            'ru': {
                'emotion': f'''Проанализируй мое эмоциональное состояние и ответь в формате JSON:

Текст для анализа:
{text}

Ответь в формате JSON с полями:
- "mood_score": оценка настроения от 1 до 10 (1 - ужасно, 10 - прекрасно)
- "comment": краткий комментарий (1 предложение)
- "recommendation": персональная рекомендация (1-2 предложения)
- "analysis": подробный анализ (2-3 предложения)
- "key_points": массив объектов (ключевые моменты)
   - "text": текст ключевого момента
   - "type": тип (emotion, event, thought, trigger, other)
   - "confidence": уверенность (float от 0.0 до 1.0)
- "user_insights": массив объектов (новые инсайты)
   - "text": текст инсайта
   - "category": категория (personal, relational, professional, health, spiritual, other)
   - "weight": вес (int, от 1 до 10)

Пример ответа:
{{
  "mood_score": 7,
  "comment": "Хорошее настроение",
  "recommendation": "Продолжайте в том же духе",
  "analysis": "Текст содержит позитивные эмоции",
  "key_points": [
    {{
      "text": "счастье",
      "type": "emotion",
      "confidence": 0.9
    }},
    {{
      "text": "успех",
      "type": "event",
      "confidence": 0.8
    }}
  ],
  "user_insights": [
    {{
      "text": "Позитивные события повышают настроение",
      "category": "personal",
      "weight": 2
    }}
  ]
}}''',
                
                'default': f'''Проанализируй текст и ответь в формате JSON:

Текст для анализа:
{text}

Ответь в формате JSON с полями:
- "mood_score": оценка настроения от 1 до 10
- "comment": краткий комментарий
- "recommendation": персональная рекомендация
- "analysis": подробный анализ
- "key_points": массив объектов (ключевые моменты)
   - "text": текст ключевого момента
   - "type": тип (emotion, event, thought, trigger, other)
   - "confidence": уверенность (float от 0.0 до 1.0)
- "user_insights": массив объектов (новые инсайты)
   - "text": текст инсайта
   - "category": категория (personal, relational, professional, health, spiritual, other)
   - "weight": вес (int, от 1 до 10)

Пример ответа:
{{
  "mood_score": 5,
  "comment": "Нормальное настроение",
  "recommendation": "Продолжайте вести дневник",
  "analysis": "Текст нейтральный",
  "key_points": [],
  "user_insights": []
}}'''
            },
            'en': {
                'emotion': f'''Analyze my emotional state and respond in JSON format:

Text to analyze:
{text}

Respond in JSON format with fields:
- "mood_score": mood rating from 1 to 10 (1 - terrible, 10 - wonderful)
- "comment": brief comment (1 sentence)
- "recommendation": personal recommendation (1-2 sentences)
- "analysis": detailed analysis (2-3 sentences)
- "key_points": array of objects (key points)
   - "text": text of the key point
   - "type": type (emotion, event, thought, trigger, other)
   - "confidence": confidence (float from 0.0 to 1.0)
- "user_insights": array of objects (new insights)
   - "text": text of the insight
   - "category": category (personal, relational, professional, health, spiritual, other)
   - "weight": weight (int, from 1 to 10)

Example response:
{{
  "mood_score": 7,
  "comment": "Good mood",
  "recommendation": "Keep it up",
  "analysis": "The text contains positive emotions",
  "key_points": [
    {{
      "text": "happiness",
      "type": "emotion",
      "confidence": 0.9
    }},
    {{
      "text": "success",
      "type": "event",
      "confidence": 0.8
    }}
  ],
  "user_insights": [
    {{
      "text": "Positive events improve mood",
      "category": "personal",
      "weight": 2
    }}
  ]
}}''',
                
                'default': f'''Analyze the text and respond in JSON format:

Text to analyze:
{text}

Respond in JSON format with fields:
- "mood_score": mood rating from 1 to 10
- "comment": brief comment
- "recommendation": personal recommendation
- "analysis": detailed analysis
- "key_points": array of objects (key points)
   - "text": text of the key point
   - "type": type (emotion, event, thought, trigger, other)
   - "confidence": confidence (float from 0.0 to 1.0)
- "user_insights": array of objects (new insights)
   - "text": text of the insight
   - "category": category (personal, relational, professional, health, spiritual, other)
   - "weight": weight (int, from 1 to 10)

Example response:
{{
  "mood_score": 5,
  "comment": "Normal mood",
  "recommendation": "Continue keeping a diary",
  "analysis": "The text is neutral",
  "key_points": [],
  "user_insights": []
}}'''
            }
        }
        
        language_prompts = prompts.get(language, prompts['en']) # По умолчанию английский
        prompt = language_prompts.get(analysis_type, language_prompts['default'])
        
        logger.info(f"Промт для анализа сгенерирован длиной: {len(prompt)} символов")
        return prompt
    
    async def _generate_punctuation_prompt(
        self, 
        text: str, 
        language: str
    ) -> str:
        """
        Генерация промта для расстановки знаков препинания
        
        Args:
            text: Текст для расстановки знаков препинания
            language: Язык текста
            
        Returns:
            str: Сформированный промт
        """
        logger.info(f"Генерация промта для расстановки знаков препинания, язык: {language}")
        
        # Промты для разных языков
        prompts = {
            'ru': f'''Расставь знаки препинания в следующем тексте и раздели его на абзацы где это необходимо. 
Не изменяй содержание текста, только добавь знаки препинания и абзацы.

Текст без знаков препинания:
{text}

ОТВЕТЬ ТОЛЬКО ОТФОРМАТИРОВАННЫМ ТЕКСТОМ БЕЗ ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ И ПОЯСНЕНИЙ.
Используй следующий формат ответа:
[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]''',
            
            'en': f'''Add punctuation marks to the following text and divide it into paragraphs where necessary.
Do not change the content of the text, only add punctuation marks and paragraphs.

Text without punctuation marks:
{text}

RESPOND ONLY WITH FORMATTED TEXT WITHOUT ADDITIONAL COMMENTS AND EXPLANATIONS.
Use the following response format:
[FORMATTED TEXT]'''
        }
        
        prompt = prompts.get(language, prompts['ru'])
        
        logger.info(f"Промт для расстановки знаков препинания сгенерирован длиной: {len(prompt)} символов")
        return prompt
    
    async def _extract_formatted_text(
        self, 
        response_text: str, 
        language: str
    ) -> str:
        """
        Извлечение отформатированного текста из ответа DeepSeek
        
        Args:
            response_text: Текст ответа от DeepSeek
            language: Язык текста
            
        Returns:
            str: Отформатированный текст
        """
        logger.info(f"Извлечение отформатированного текста из ответа DeepSeek, язык: {language}")
        logger.info(f"Текст ответа длиной: {len(response_text)} символов")
        
        try:
            # Удаляем лишние префиксы и постфиксы
            formatted_text = response_text.strip()
            
            # Удаляем стандартные префиксы DeepSeek
            prefixes_to_remove = [
                "Конечно, вот отформатированный текст:",
                "Конечно, вот отформатированный текст",
                "Отформатированный текст:",
                "Отформатированный текст",
                "Форматированный текст:",
                "Форматированный текст",
                "RESPOND ONLY WITH FORMATTED TEXT WITHOUT ADDITIONAL COMMENTS AND EXPLANATIONS.",
                "Use the following response format:",
                "[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]",
                "[FORMATTED TEXT]",
                "```",
                "```text",
                "```plaintext"
            ]
            
            # Удаляем префиксы
            for prefix in prefixes_to_remove:
                if formatted_text.startswith(prefix):
                    formatted_text = formatted_text[len(prefix):].strip()
            
            # Удаляем постфиксы
            postfixes_to_remove = [
                "```",
                "[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]",
                "[FORMATED TEXT]"
            ]
            
            for postfix in postfixes_to_remove:
                if formatted_text.endswith(postfix):
                    formatted_text = formatted_text[:-len(postfix)].strip()
            
            # Если текст пустой после очистки, возвращаем оригинальный ответ
            if not formatted_text:
                logger.warning("Отформатированный текст пустой после очистки, возвращаем оригинальный ответ")
                return response_text.strip()
            
            logger.info(f"Отформатированный текст извлечен успешно, длина: {len(formatted_text)} символов")
            return formatted_text
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении отформатированного текста: {e}")
            # Возвращаем оригинальный текст в случае ошибки
            return response_text.strip()
    
    async def _parse_analysis_response(self, response_text: str, language: str = 'ru', analysis_type: str = 'default') -> Dict[str, Any]:
        """
        Парсинг ответа API анализа текста.
        Пытается извлечь JSON из ответа, в том числе из Markdown-блоков.
        Если не удается, возвращает результат по умолчанию.

        Args:
            response_text: Текст ответа от API.
            language: Язык для сообщений по умолчанию.
            analysis_type: Тип анализа ('default', 'incremental', 'clarification').

        Returns:
            Dict[str, Any]: Распарсенный результат анализа или результат по умолчанию.
        """
        # === ДОБАВЛЯЕМ ПОДРОБНОЕ ЛОГИРОВАНИЕ СЫРОГО ОТВЕТА ===
        logger.info(f"Парсинг ответа анализа текста, язык: {language}, тип: {analysis_type}")
        logger.info(f"Текст ответа API длиной: {len(response_text) if response_text else 0} символов")
        
        # ВАЖНО: Логируем ответ БЕЗОПАСНО, чтобы не засорять логи огромными строками
        # и избежать проблем с не-UTF символами. 
        # Логируем только начало и конец, или используем repr.
        try:
            if not response_text:
                log_preview = "[ПУСТОЙ ОТВЕТ]"
            elif len(response_text) > 1000:
                # Логируем первые 500 и последние 300 символов
                log_preview = f"{repr(response_text[:500])} ... {repr(response_text[-300:])} [Обрезано, общая длина: {len(response_text)}]"
            else:
                log_preview = repr(response_text) # repr безопасен для логов
            logger.debug(f"Предварительный просмотр ответа API: {log_preview}")
        except Exception as log_error:
            logger.error(f"Ошибка при логировании предварительного просмотра ответа: {log_error}")
            logger.debug(f"Тип ответа: {type(response_text)}")
        # ===================================================

        if not response_text or not response_text.strip():
            logger.warning("Получен пустой или только пробельный ответ от API.")
            return self._get_default_analysis_result(language, analysis_type)

        try:
            # 1. Попытка прямого парсинга
            logger.debug("Попытка прямого парсинга JSON...")
            analysis_result = json.loads(response_text)
            logger.info("Ответ анализа успешно распарсен напрямую.")
            return analysis_result

        except json.JSONDecodeError as direct_error:
            logger.warning(f"Прямой парсинг JSON не удался: {direct_error}")

            try:
                # 2. Поиск JSON внутри Markdown-блока (частая причина ошибки)
                logger.debug("Поиск JSON внутри Markdown-блока ```json...``` или ```...```")
                # Ищем блок кода, возможно, с указанием языка
                # re.DOTALL позволяет точке '.' совпадать с символом новой строки
                # Ищем наиболее общий паттерн
                code_matches = re.findall(r"```(?:json)?\s*({.*?})\s*```", response_text, re.DOTALL | re.IGNORECASE)
                if code_matches:
                    # Берем первый найденный блок, надеясь, что он правильный
                    # Можно добавить проверку на валидность каждого найденного блока
                    for i, json_str in enumerate(code_matches):
                        logger.debug(f"Найден потенциальный JSON-блок #{i+1} длиной: {len(json_str)} символов")
                        try:
                            # Пробуем распарсить каждый найденный блок
                            potential_result = json.loads(json_str)
                            # Базовая проверка: содержит ли объект ключи, которые мы ожидаем?
                            if isinstance(potential_result, dict) and 'mood_score' in potential_result:
                                logger.info(f"Валидный JSON найден и распарсен из блока #{i+1}.")
                                return potential_result
                            else:
                                logger.debug(f"Блок #{i+1} не содержит ожидаемых ключей или не является объектом.")
                        except json.JSONDecodeError:
                            logger.debug(f"Блок #{i+1} не является валидным JSON.")
                    
                    # Если ни один блок не подошел
                    logger.warning("Найдены блоки кода, но ни один не содержит валидный JSON с ожидаемой структурой.")
                else:
                    logger.debug("JSON-блоки в Markdown не найдены.")

                # 3. Попытка найти любой объект JSON в тексте (очень грубый способ)
                # Этот способ может привести к ложным срабатываниям, но иногда помогает.
                # Например, если API вернул что-то вроде: "... {\"mood_score\": 7, ...} ..."
                # Мы ищем первую { и последнюю } и пытаемся распарсить содержимое.
                # Это рискованно, но может дать результат.
                logger.debug("Попытка грубого поиска JSON-объекта в тексте...")
                first_brace = response_text.find('{')
                last_brace = response_text.rfind('}')
                if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
                    potential_json_str = response_text[first_brace:last_brace+1]
                    logger.debug(f"Найден потенциальный JSON-объект длиной: {len(potential_json_str)} символов")
                    try:
                        potential_result = json.loads(potential_json_str)
                        if isinstance(potential_result, dict):
                            logger.info("Валидный JSON найден и распарсен грубым поиском.")
                            return potential_result
                        else:
                            logger.debug("Грубый поиск нашел JSON, но это не объект.")
                    except json.JSONDecodeError as crude_error:
                         logger.debug(f"Грубый поиск нашел строку, но она не является валидным JSON: {crude_error}")
                else:
                     logger.debug("Не удалось найти потенциальный JSON-объект грубым поиском.")

            except Exception as markdown_general_error:
                logger.error(f"Общая ошибка при поиске JSON в коде/тексте: {markdown_general_error}")

        # 4. Если все попытки парсинга провалились, возвращаем результат по умолчанию
        logger.warning("Не удалось распарсить ответ API. Возвращен результат анализа по умолчанию.")
        # === ДОПОЛНИТЕЛЬНОЕ ЛОГИРОВАНИЕ ПРИ ОШИБКЕ ===
        # Логируем начало и конец ответа, если он не пустой, для отладки
        if response_text and len(response_text) <= 2000: # Ограничиваем длину для лога
            logger.info(f"Содержимое нераспаршенного ответа (первые 1000 символов): {repr(response_text[:1000])}")
            if len(response_text) > 1000:
                 logger.info(f"... (последние 500 символов): {repr(response_text[-500:])}")
        # =============================================
        return self._get_default_analysis_result(language, analysis_type)

    def _get_default_analysis_result(self, language: str, analysis_type: str) -> Dict[str, Any]:
        """
        Возвращает результат анализа по умолчанию.

        Args:
            language: Язык.
            analysis_type: Тип анализа.

        Returns:
            Dict[str, Any]: Результат по умолчанию.
        """
        default_comment = 'Анализ записан' if language == 'ru' else 'Analysis recorded'
        default_recommendation = 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary'
        default_analysis = 'Текст проанализирован.' if language == 'ru' else 'Text analyzed.'
        
        # Для уточнений по умолчанию не нужны уточнения
        if analysis_type == 'clarification':
             return {
                'mood_score': 5,
                'comment': default_comment,
                'recommendation': default_recommendation,
                'analysis': default_analysis,
                'needs_clarification': False,
                'clarification_questions': []
            }
        else:
            # Для обычного и инкрементального анализа
            return {
                'mood_score': 5,
                'comment': default_comment,
                'recommendation': default_recommendation,
                'analysis': default_analysis,
                'needs_clarification': False,
                'clarification_questions': [],
                # Для инкрементального анализа добавляем suggested_task по умолчанию
                # Хотя по логике, если API не вернул его, значит не предлагает
                # 'suggested_task': None # Можно явно указать, но по умолчанию его просто не будет в словаре
            }

    @api_retry(max_attempts=3, delay=1.0)
    @handle_api_error
    async def analyze_text_with_previous_state(
        self,
        previous_state_context: str,
        new_text: str,
        user_profile: dict,
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Инкрементальный анализ нового текста с учетом предыдущего состояния дня через DeepSeek API.

        Args:
            previous_state_context: Текстовое состояние дня от предыдущего анализа.
            new_text: Новая запись пользователя.
            user_profile: Данные профиля пользователя.
            language: Язык анализа.

        Returns:
            Dict[str, Any]: Результат анализа с финальным analysis_text и метаданными API.
        """
        logger.info(f"Инкрементальный анализ текста с предыдущим состоянием через DeepSeek API, язык: {language}")
        logger.info(f"Предыдущее состояние длиной: {len(previous_state_context)} символов")
        logger.info(f"Новая запись длиной: {len(new_text)} символов")
        logger.info(f"Профиль пользователя: {user_profile.get('username', 'unknown')}")

        try:
            # === 1. ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ ===
            if not new_text or len(new_text.strip()) < 1:
                logger.error("Новая запись для анализа пустая")
                api_response_data = {
                    'status': 'text_empty',
                    'error_text': 'Новая запись для анализа пустая',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'text_empty',
                    'message': 'Новая запись для анализа пустая',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }

            if len(new_text) > 10000: # Ограничение на длину новой записи
                logger.error("Новая запись для анализа слишком длинная")
                api_response_data = {
                    'status': 'text_too_long',
                    'error_text': 'Новая запись для анализа слишком длинная',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'text_too_long',
                    'message': 'Новая запись для анализа слишком длинная',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }

            if not DEEPSEEK_API_KEY:
                logger.error("DeepSeek API key not configured")
                api_response_data = {
                    'status': 'api_key_missing',
                    'error_text': 'API ключ DeepSeek не настроен',
                    'raw_response': '',
                    'model_used': 'deepseek-chat',
                    'usage': {},
                    'processing_time': 0,
                    'tokens_used': 0
                }
                return {
                    'success': False,
                    'error': 'api_key_missing',
                    'message': 'API ключ DeepSeek не настроен',
                    'result': {},
                    'raw_response': '',
                    'api_response': api_response_data
                }
            # ======================================

            # === 2. ФОРМИРОВАНИЕ ПРОМТА ===
            prompt = await self._generate_incremental_analysis_prompt(
                previous_state_context, new_text, user_profile, language
            )
            logger.info(f"Сформирован промт для инкрементального анализа длиной: {len(prompt)} символов")
            # =============================

            # === 3. ВЫЗОВ API ===
            url = "https://api.deepseek.com/v1/chat/completions"
            # Увеличиваем max_tokens для более сложного анализа
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3, # Низкая температура для точного анализа
                "max_tokens": 5000 # Удваиваем токены
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }

            # Создаем сессию aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60) # Увеличенный таймаут
                ) as response:
                    raw_response_text = await response.text()
                    logger.info(f"Получен ответ от DeepSeek API для инкрементального анализа, статус: {response.status}")

                    # ========= ДОБАВЛЕННОЕ ЛОГИРОВАНИЕ СЫРОГО ОТВЕТА =========
                    logger.debug(f"Сырой ответ от DeepSeek API (метод: analyze_text_with_previous_state) (первые 500 символов): {repr(raw_response_text[:500]) if raw_response_text else '[ПУСТО]'}")
                    if raw_response_text and len(raw_response_text) > 500:
                        logger.debug(f"... (последние 300 символов из {len(raw_response_text)}): {repr(raw_response_text[-300:])}")
                    logger.debug(f"Общая длина сырого ответа: {len(raw_response_text) if raw_response_text else 0} символов")
                    # ========================================================

                    if response.status == 200:
                        # ========= ДОПОЛНИТЕЛЬНОЕ ЛОГИРОВАНИЕ ПЕРЕД ПАРСИНГОМ =========
                        logger.debug(f"Попытка парсинга JSON из ответа метода analyze_text_with_previous_state...")
                        # ============================================================
                        
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        logger.info(f"Инкрементальный анализ успешно выполнен, длина ответа LLM: {len(response_text)} символов")

                        # === 4. ПАРСИНГ РЕЗУЛЬТАТА ===
                        # Используем существующий метод парсинга, так как формат ответа аналогичен
                        parsed_result = await self._parse_analysis_response(
                            response_text, language, 'incremental'
                        )
                        logger.info("Результат инкрементального анализа успешно распарсен")
                        # ============================

                        # === 5. ФОРМИРОВАНИЕ ФИНАЛЬНОГО РЕЗУЛЬТАТА ===
                        # Формируем финальный текст анализа на основе comment и recommendation
                        comment_part = parsed_result.get('comment', '')
                        recommendation_part = parsed_result.get('recommendation', '')
                        analysis_part = parsed_result.get('analysis', 'Текст проанализирован.')

                        # Формируем финальный текст анализа
                        final_analysis_text = f"{analysis_part}".strip()
                        if not final_analysis_text:
                            final_analysis_text = "Текст проанализирован."

                        # Создаем финальный результат для возврата
                        # Копируем распарсенный результат и заменяем/добавляем analysis
                        final_result = parsed_result.copy()
                        final_result['analysis'] = final_analysis_text

                        # Подготавливаем данные для api_response
                        api_response_data = {
                            'status': response.status,
                            'raw_response': raw_response_text,
                            'json_response': result,
                            'model_used': result.get('model', 'deepseek-chat'),
                            'usage': result.get('usage', {}),
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01, # Примерное время
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                        }
                        final_result['api_response'] = api_response_data
                        # =============================================

                        logger.info("Инкрементальный анализ успешно завершен")
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Текст успешно проанализирован с учетом предыдущего состояния',
                            'result': final_result, # Возвращаем распарсенный и обработанный результат
                            'raw_response': raw_response_text,
                            'api_response': api_response_data
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при инкрементальном анализе: {response.status} - {error_text}")
                        
                        # ========= ЛОГИРОВАНИЕ ОШИБКИ ОТ API =========
                        logger.debug(f"Сырой ответ об ошибке от DeepSeek API (метод: analyze_text_with_previous_state) (первые 500 символов): {repr(error_text[:500]) if error_text else '[ПУСТО]'}")
                        if error_text and len(error_text) > 500:
                            logger.debug(f"... (последние 300 символов из {len(error_text)}): {repr(error_text[-300:])}")
                        # ===========================================
                        
                        api_response_data = {
                            'status': response.status,
                            'error_text': error_text,
                            'raw_response': error_text,
                            'model_used': 'deepseek-chat',
                            'usage': {},
                            'processing_time': 0,
                            'tokens_used': 0
                        }
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при инкрементальном анализе: {response.status}',
                            'result': {},
                            'raw_response': error_text,
                            'api_response': api_response_data
                        }

        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при инкрементальном анализе")
            api_response_data = {
                'status': 'timeout',
                'error_text': 'Превышено время ожидания ответа от DeepSeek API',
                'raw_response': '',
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при инкрементальном анализе',
                'result': {},
                'raw_response': '',
                'api_response': api_response_data
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при инкрементальном анализе: {e}")
            api_response_data = {
                'status': 'general_error',
                'error_text': str(e),
                'raw_response': str(e),
                'model_used': 'deepseek-chat',
                'usage': {},
                'processing_time': 0,
                'tokens_used': 0
            }
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при инкрементальном анализе текста',
                'result': {},
                'raw_response': str(e),
                'api_response': api_response_data
            }

    # === НОВЫЙ МЕТОД: Генерация промта для инкрементального анализа ===
    async def _generate_incremental_analysis_prompt(
        self,
        previous_state_context: str,
        new_text: str,
        user_profile: dict,
        language: str
    ) -> str:
        """
        Генерация промта для инкрементального анализа нового текста с учетом предыдущего состояния.

        Args:
            previous_state_context: Предыдущее состояние дня (накопленный контекст).
            new_text: Новая запись.
            user_profile: Профиль пользователя.
            language: Язык.

        Returns:
            str: Сформированный промт.
        """
        logger.info("Генерация промта для инкрементального анализа")

        # Словарь промтов на разных языках
        prompts = {
            'ru': f'''Ты профессиональный психолог. Ниже приведен НАКОПЛЕННЫЙ КОНТЕКСТ эмоционального состояния пользователя за текущий день. Этот контекст включает обобщенную информацию из ВСЕХ предыдущих записей пользователя за этот день:
"{previous_state_context}"

Пользователь только что добавил НОВУЮ запись:
"{new_text}"

ТВОЯ ЗАДАЧА:
1.  ВНИМАТЕЛЬНО ИНТЕГРИРУЙ информацию из новой записи в существующий накопленный контекст. 
2.  УЧИТЫВАЙ, что новая запись - это лишь часть общего эмоционального фона дня. 
3.  НЕ позволяй одной записи (особенно последней) полностью ИЗМЕНИТЬ восприятие всего дня, если предыдущие записи указывали на другое.
4.  ОЦЕНИ, как новая запись влияет на ДИНАМИКУ эмоций в течение дня (например, улучшение, ухудшение, колебания).
5.  Предоставь анализ новой записи в стандартном формате JSON:
    - "mood_score": оценка настроения от 1 до 10 ТОЛЬКО ДЛЯ ЭТОЙ НОВОЙ ЗАПИСИ (не для всего дня!). Это помогает отследить динамику.
    - "comment": краткий комментарий (1 предложение) по новой записи.
    - "recommendation": персональная рекомендация (1-2 предложения) по новой записи.
    - "analysis": подробный анализ новой записи (2-3 предложения), рассматривающий её в свете предыдущего контекста.
    - "needs_clarification": boolean (нужны ли уточнения по новой записи).
    - "clarification_questions": массив строк (вопросы, если нужны уточнения).
    - "suggested_task": объект (опционально, описание задания).
       - "title": название задания.
       - "description": описание задания.
       - "type": тип задания (из списка: daily, reflection, cognitive, creative, behavioral, mindfulness).
       - "priority": приоритет (строка: low, medium, high, critical).
    - "key_points": массив объектов (ключевые моменты из новой записи).
       - "text": текст ключевого момента.
       - "type": тип (emotion, event, thought, trigger, other).
       - "confidence": уверенность (float от 0.0 до 1.0).
    - "user_insights": массив объектов (новые инсайты, выявленные из этой записи).
       - "text": текст инсайта.
       - "category": категория (personal, relational, professional, health, spiritual, other).
       - "weight": вес (int, от 1 до 10, где 10 - очень значимый инсайт).

ВАЖНО:
- ФИНАЛЬНАЯ оценка настроения за ДЕНЬ будет рассчитываться ОТДЕЛЬНО как СРЕДНЕЕ АРИФМЕТИЧЕСКОЕ всех индивидуальных оценок записей за день.
- Твоя задача - предоставить ТОЧНЫЙ и СБАЛАНСИРОВАННЫЙ анализ новой записи в контексте дня.

Пример ответа:
{{
  "mood_score": 7,
  "comment": "Вы испытали всплеск энтузиазма после утренней прогулки.",
  "recommendation": "Попробуйте чаще включать физическую активность в свой день.",
  "analysis": "Новая запись показывает положительный сдвиг в эмоциях по сравнению с предыдущим контекстом. Упоминание 'прогулка' и 'свежий воздух' коррелирует с повышением настроения. Однако, предыдущие записи указывали на усталость, что важно учитывать в общем контексте.",
  "needs_clarification": false,
  "clarification_questions": [],
  "suggested_task": {{
    "title": "Ежедневная прогулка",
    "description": "Планируйте хотя бы 20-минутную прогулку каждый день этой недели.",
    "type": "behavioral",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "прогулка",
      "type": "event",
      "confidence": 0.9
    }},
    {{
      "text": "энтузиазм",
      "type": "emotion",
      "confidence": 0.85
    }}
  ],
  "user_insights": [
    {{
      "text": "Физическая активность положительно влияет на настроение",
      "category": "health",
      "weight": 2
    }}
  ]
}}
''',
            'en': f'''You are a professional psychologist. Below is the ACCUMULATED CONTEXT of the user's emotional state for the current day. This context includes summarized information from ALL the user's previous entries for this day:
"{previous_state_context}"

The user has just added a NEW entry:
"{new_text}"

YOUR TASK:
1.  CAREFULLY INTEGRATE the information from the new entry into the existing accumulated context.
2.  CONSIDER that the new entry is just part of the overall emotional background of the day.
3.  DO NOT let one entry (especially the last one) completely CHANGE the perception of the entire day if previous entries indicated otherwise.
4.  ASSESS how the new entry affects the EMOTIONAL DYNAMICS throughout the day (e.g., improvement, deterioration, fluctuations).
5.  Provide an analysis of the new entry in standard JSON format:
    - "mood_score": mood score from 1 to 10 FOR THIS NEW ENTRY ONLY (not for the whole day!). This helps track dynamics.
    - "comment": brief comment (1 sentence) for the new entry.
    - "recommendation": personal recommendation (1-2 sentences) for the new entry.
    - "analysis": detailed analysis of the new entry (2-3 sentences), considering it in the light of the previous context.
    - "needs_clarification": boolean (whether clarifications are needed for the new entry).
    - "clarification_questions": array of strings (questions if clarifications are needed).
    - "suggested_task": object (optional, task description).
       - "title": task title.
       - "description": task description.
       - "type": task type (from the list: daily, reflection, cognitive, creative, behavioral, mindfulness).
       - "priority": priority (string: low, medium, high, critical).
    - "key_points": array of objects (key points from the new entry).
       - "text": text of the key point.
       - "type": type (emotion, event, thought, trigger, other).
       - "confidence": confidence (float from 0.0 to 1.0).
    - "user_insights": array of objects (new insights discovered from this entry).
       - "text": text of the insight.
       - "category": category (personal, relational, professional, health, spiritual, other).
       - "weight": weight (int, from 1 to 10, where 10 is a very significant insight).

IMPORTANT:
- The FINAL mood score for the DAY will be calculated SEPARATELY as the ARITHMETIC MEAN of all individual entry scores for the day.
- Your task is to provide an ACCURATE and BALANCED analysis of the new entry in the context of the day.

Example response:
{{
  "mood_score": 7,
  "comment": "You experienced a surge of enthusiasm after your morning walk.",
  "recommendation": "Try to include physical activity in your day more often.",
  "analysis": "The new entry shows a positive shift in emotions compared to the previous context. The mention of 'walk' and 'fresh air' correlates with an improved mood. However, previous entries indicated fatigue, which is important to consider in the overall context.",
  "needs_clarification": false,
  "clarification_questions": [],
  "suggested_task": {{
    "title": "Daily Walk",
    "description": "Plan at least a 20-minute walk every day this week.",
    "type": "behavioral",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "walk",
      "type": "event",
      "confidence": 0.9
    }},
    {{
      "text": "enthusiasm",
      "type": "emotion",
      "confidence": 0.85
    }}
  ],
  "user_insights": [
    {{
      "text": "Physical activity positively affects mood",
      "category": "health",
      "weight": 2
    }}
  ]
}}
'''
        }

        # Выбираем промт в зависимости от языка
        prompt = prompts.get(language, prompts['ru'])
        logger.info(f"Промт для инкрементального анализа сгенерирован длиной: {len(prompt)} символов")
        return prompt

# Глобальный экземпляр сервиса DeepSeek API
deepseek_api_service = DeepSeekAPIService()

# Удобные функции для использования
async def analyze_text(
    text: str, 
    language: str = 'ru',
    analysis_type: str = 'emotion'
) -> Dict[str, Any]:
    """
    Удобная функция для анализа текста
    
    Args:
        text: Текст для анализа
        language: Язык анализа
        analysis_type: Тип анализа
        
    Returns:
        Dict[str, Any]: Результат анализа
    """
    return await deepseek_api_service.analyze_text(text, language, analysis_type)

async def generate_response(
    prompt: str, 
    language: str = 'ru',
    max_tokens: int = 5000
) -> Dict[str, Any]:
    """
    Удобная функция для генерации ответа
    
    Args:
        prompt: Промт для генерации
        language: Язык генерации
        max_tokens: Максимальное количество токенов
        
    Returns:
        Dict[str, Any]: Результат генерации
    """
    return await deepseek_api_service.generate_response(prompt, language, max_tokens)

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

# ==================== УДОБНЫЕ ФУНКЦИИ ====================

async def analyze_text_with_profile(
    text: str, 
    user_profile: dict, 
    language: str = 'ru'
) -> Dict[str, Any]:
    """
    Удобная функция для анализа текста с профилем пользователя
    
    Args:
        text: Текст для анализа
        user_profile: Данные профиля пользователя
        language: Язык анализа
        
    Returns:
        Dict[str, Any]: Результат анализа
    """
    return await deepseek_api_service.analyze_text_with_profile(text, user_profile, language)

async def analyze_text_with_clarifications(
    text: str, 
    user_profile: dict, 
    language: str = 'ru',
    initial_analysis: dict = None,
    questions: list = None
) -> Dict[str, Any]:
    """
    Удобная функция для финального анализа текста с уточнениями
    
    Args:
        text: Текст уточнений
        user_profile: Данные профиля пользователя
        language: Язык анализа
        initial_analysis: Предыдущий анализ
        questions: Уточняющие вопросы
        
    Returns:
        Dict[str, Any]: Результат финального анализа
    """
    return await deepseek_api_service.analyze_text_with_clarifications(text, user_profile, language, initial_analysis, questions)

async def analyze_text_with_previous_state(
    previous_state_context: str,
    new_text: str,
    user_profile: dict,
    language: str = 'ru'
) -> Dict[str, Any]:
    """
    Удобная функция для инкрементального анализа нового текста с учетом предыдущего состояния.

    Args:
        previous_state_context: Текстовое состояние дня от предыдущего анализа.
        new_text: Новая запись пользователя.
        user_profile: Данные профиля пользователя.
        language: Язык анализа.

    Returns:
        Dict[str, Any]: Результат анализа.
    """
    return await deepseek_api_service.analyze_text_with_previous_state(
        previous_state_context, new_text, user_profile, language
    )


