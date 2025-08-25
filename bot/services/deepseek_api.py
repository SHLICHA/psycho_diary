"""
Сервис для работы с DeepSeek API
"""

import logging
import asyncio
import json
import aiohttp
import re

from typing import Optional, Dict, Any, List
from core.settings import DEEPSEEK_API_KEY
from bot.utils.api_utils import api_retry, handle_api_error

logger = logging.getLogger(__name__)

class DeepSeekAPIService:
    """Сервис для работы с DeepSeek API"""
    
    def __init__(self):
        """Инициализация сервиса DeepSeek API"""
        logger.info("Инициализация сервиса DeepSeek API")
        
        # Проверяем наличие API ключа
        if not DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY не настроен")
        else:
            logger.info("DEEPSEEK_API_KEY найден")
    
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
        logger.info(f"Анализ текста через DeepSeek API, тип: {analysis_type}, язык: {language}")
        logger.info(f"Текст длиной: {len(text)} символов")

        # Проверяем минимальную длину текста
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

        # Проверяем максимальную длину текста
        if len(text) > 5000:
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

        # Проверяем наличие API ключа
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

        # Формируем промт для анализа
        prompt = await self._generate_analysis_prompt(text, language, analysis_type)
        logger.info(f"Сформирован промт для анализа длиной: {len(prompt)} символов")

        url = "https://api.deepseek.com/v1/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,  # Низкая температура для точного анализа
            "max_tokens": 2000
            #"max_tokens": min(5000, len(text) * 2)  # Удваиваем токены для длинных текстов
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
                        logger.info(f"Текст успешно проанализирован, длина ответа: {len(response_text)} символов")

                        # === ИСПРАВЛЕНИЕ ===
                        # 1. Парсим ответ API
                        parsed_api_result = await self._parse_analysis_response(response_text, language, analysis_type)
                        logger.info("Ответ анализа спарсен успешно")

                        # 2. Формируем ФИНАЛЬНЫЙ analysis_text
                        # Берем comment и recommendation из распарсенного результата
                        comment_part = parsed_api_result.get('comment', 'Анализ записан')
                        recommendation_part = parsed_api_result.get('recommendation', 'Продолжайте в том же духе')
                        
                        # Комбинируем их в финальный текст анализа
                        # Это гарантирует, что даже если отдельные поля обрезаны,
                        # пользователь получит осмысленную информацию.
                        final_analysis_text = f"{comment_part} {recommendation_part}".strip()
                        if not final_analysis_text:
                             final_analysis_text = "Текст проанализирован."

                        # 3. Создаем финальный результат для возврата
                        # Копируем распарсенный результат и заменяем/добавляем analysis_text
                        final_result = parsed_api_result.copy()
                        final_result['analysis'] = final_analysis_text # Используем сформированный текст

                        # 4. Подготавливаем данные для api_response
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
                            'message': 'Текст успешно проанализирован',
                            'result': final_result, # Возвращаем результат с финальным analysis_text
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': response_text,
                            'needs_clarification': parsed_api_result.get('needs_clarification', False),
                            'clarification_questions': parsed_api_result.get('clarification_questions', []),
                            'api_response': api_response_data # Ответ API для сохранения в БД!
                        }
                        # ===============

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

    async def analyze_text_with_profile(
        self, 
        text: str, 
        user_profile: dict, 
        language: str = 'ru'
    ) -> Dict[str, Any]:
        """
        Анализ текста с профилем пользователя через DeepSeek API
        
        Args:
            text: Текст для анализа
            user_profile: Данные профиля пользователя
            language: Язык анализа
            
        Returns:
            Dict[str, Any]: Результат анализа
        """
        logger.info(f"Анализ текста с профилем пользователя через DeepSeek API, язык: {language}")
        logger.info(f"Текст длиной: {len(text)} символов")
        logger.info(f"Профиль пользователя: {user_profile.get('username', 'unknown')}")
        
        try:
            # Проверяем минимальную длину текста
            if not text or len(text.strip()) < 1:
                logger.error("Текст для анализа пустой")
                return {
                    'success': False,
                    'error': 'text_empty',
                    'message': 'Текст для анализа пустой',
                    'result': {}
                }
            
            # Проверяем максимальную длину текста
            if len(text) > 10000:
                logger.error("Текст для анализа слишком длинный")
                return {
                    'success': False,
                    'error': 'text_too_long',
                    'message': 'Текст для анализа слишком длинный',
                    'result': {}
                }
            
            # Проверяем наличие API ключа
            if not DEEPSEEK_API_KEY:
                logger.error("DeepSeek API key not configured")
                return {
                    'success': False,
                    'error': 'api_key_missing',
                    'message': 'API ключ DeepSeek не настроен',
                    'result': {}
                }
            
            # Формируем промт для анализа с профилем
            prompt = await self._generate_profile_based_analysis_prompt(text, user_profile, language)
            logger.info(f"Сформирован промт для анализа с профилем длиной: {len(prompt)} символов")
            
            url = "https://api.deepseek.com/v1/chat/completions"
            
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,  # Низкая температура для точного анализа
                "max_tokens": min(5000, len(text) * 2)  # Удваиваем токены для длинных текстов
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
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        
                        logger.info(f"Текст успешно проанализирован с профилем, длина ответа: {len(response_text)} символов")
                        
                        # Парсим ответ анализа
                        analysis_result = await self._parse_profile_based_analysis_response(response_text, language)
                        logger.debug(f"Результат парсинга ответа: {analysis_result}")
                        logger.info(f"Ответ анализа спарсен успешно")
                        
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Текст успешно проанализирован с профилем',
                            'result': analysis_result,
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': response_text,  # Для отладки
                            'needs_clarification': analysis_result.get('needs_clarification', False),
                            'clarification_questions': analysis_result.get('clarification_questions', [])
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при анализе с профилем: {response.status} - {error_text}")
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при анализе с профилем: {response.status}',
                            'result': {},
                            'raw_response': error_text  # Для отладки
                        }
                        
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при анализе с профилем")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при анализе с профилем',
                'result': {}
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при анализе с профилем: {e}")
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при анализе текста с профилем',
                'result': {}
            }
        
    async def analyze_text_with_clarifications(
        self, 
        text: str, 
        user_profile: dict, 
        language: str = 'ru',
        initial_analysis: dict = None,
        questions: list = None
    ) -> Dict[str, Any]:
        """
        Финальный анализ текста с уточнениями через DeepSeek API
        
        Args:
            text: Текст уточнений
            user_profile: Данные профиля пользователя
            language: Язык анализа
            initial_analysis: Предыдущий анализ
            questions: Уточняющие вопросы
            
        Returns:
            Dict[str, Any]: Результат финального анализа
        """
        logger.info(f"Финальный анализ текста с уточнениями через DeepSeek API, язык: {language}")
        logger.info(f"Текст уточнений длиной: {len(text)} символов")
        logger.info(f"Профиль пользователя: {user_profile.get('username', 'unknown')}")
        
        try:
            # Проверяем минимальную длину текста уточнений
            if not text or len(text.strip()) < 1:
                logger.error("Текст уточнений пустой")
                return {
                    'success': False,
                    'error': 'clarification_text_empty',
                    'message': 'Текст уточнений пустой',
                    'result': {}
                }
            
            # Проверяем максимальную длину текста уточнений
            if len(text) > 5000:
                logger.error("Текст уточнений слишком длинный")
                return {
                    'success': False,
                    'error': 'clarification_text_too_long',
                    'message': 'Текст уточнений слишком длинный',
                    'result': {}
                }
            
            # Проверяем наличие API ключа
            if not DEEPSEEK_API_KEY:
                logger.error("DeepSeek API key not configured")
                return {
                    'success': False,
                    'error': 'api_key_missing',
                    'message': 'API ключ DeepSeek не настроен',
                    'result': {}
                }
            
            # Формируем промт для финального анализа с уточнениями
            prompt = await self._generate_final_analysis_prompt(
                text=text,
                user_profile=user_profile,
                language=language,
                initial_analysis=initial_analysis,
                questions=questions
            )
            logger.info(f"Сформирован промт для финального анализа длиной: {len(prompt)} символов")
            
            url = "https://api.deepseek.com/v1/chat/completions"
            
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,  # Очень низкая температура для точного финального анализа
                "max_tokens": min(5000, len(text) * 3)  # Утраиваем токены для финального анализа
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
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        
                        logger.info(f"Финальный анализ текста выполнен, длина ответа: {len(response_text)} символов")
                        
                        # Парсим ответ финального анализа
                        final_analysis_result = await self._parse_final_analysis_response(response_text, language)
                        logger.info(f"Ответ финального анализа спарсен успешно")
                        
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Финальный анализ текста выполнен',
                            'result': final_analysis_result,
                            'processing_time': result.get('usage', {}).get('total_tokens', 0) * 0.01,  # Заглушка
                            'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                            'model_used': result.get('model', 'deepseek-chat'),
                            'raw_response': response_text,  # Для отладки
                            'needs_clarification': False,  # Финальный анализ не требует уточнений
                            'clarification_questions': []
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error при финальном анализе: {response.status} - {error_text}")
                        return {
                            'success': False,
                            'error': f'deepseek_api_error_{response.status}',
                            'message': f'Ошибка DeepSeek API при финальном анализе: {response.status}',
                            'result': {},
                            'raw_response': error_text  # Для отладки
                        }
                        
        except asyncio.TimeoutError:
            logger.warning("DeepSeek API timeout при финальном анализе")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от DeepSeek API при финальном анализе',
                'result': {}
            }
        except Exception as e:
            logger.error(f"DeepSeek API request failed при финальном анализе: {e}")
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при финальном анализе текста',
                'result': {}
            }

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
        max_tokens: int = 500
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
            "max_tokens": min(5000, len(text) * 2)  # Удваиваем токены для длинных текстов
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
        Генерация промта для анализа текста
        
        Args:
            text: Текст для анализа
            language: Язык анализа
            analysis_type: Тип анализа
            
        Returns:
            str: Сформированный промт
        """
        logger.info(f"Генерация промта для анализа текста, тип: {analysis_type}, язык: {language}")
        
        # Промты для разных языков
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

Пример ответа:
{{"mood_score": 7, "comment": "Хорошее настроение", "recommendation": "Продолжайте в том же духе", "analysis": "Текст содержит позитивные эмоции"}}''',
                
                'default': f'''Проанализируй текст и ответь в формате JSON:

Текст для анализа:
{text}

Ответь в формате JSON с полями:
- "mood_score": оценка настроения от 1 до 10
- "comment": краткий комментарий
- "recommendation": персональная рекомендация
- "analysis": подробный анализ

Пример ответа:
{{"mood_score": 5, "comment": "Нормальное настроение", "recommendation": "Продолжайте вести дневник", "analysis": "Текст нейтральный"}}'''
            },
            'en': {
                'emotion': f'''Analyze му the emotional state and respond in JSON format:

Text to analyze:
{text}

Respond in JSON format with fields:
- "mood_score": mood rating from 1 to 10 (1 - terrible, 10 - wonderful)
- "comment": brief comment (1 sentence)
- "recommendation": personal recommendation (1-2 sentences)
- "analysis": detailed analysis (2-3 sentences)

Example response:
{{"mood_score": 7, "comment": "Good mood", "recommendation": "Keep it up", "analysis": "The text contains positive emotions"}}''',
                
                'default': f'''Analyze the text and respond in JSON format:

Text to analyze:
{text}

Respond in JSON format with fields:
- "mood_score": mood rating from 1 to 10
- "comment": brief comment
- "recommendation": personal recommendation
- "analysis": detailed analysis

Example response:
{{"mood_score": 5, "comment": "Normal mood", "recommendation": "Continue keeping a diary", "analysis": "The text is neutral"}}'''
            }
        }
        
        language_prompts = prompts.get(language, prompts['ru'])
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
    
    async def _parse_analysis_response(self, response_text: str, language: str, analysis_type: str) -> Dict[str, Any]:
        """
        Парсинг ответа анализа от DeepSeek API.
        Извлекает JSON из markdown-обёртки и возвращает его как есть.
        Формирование окончательного analysis_text происходит на более высоком уровне.

        Args:
            response_text: Текст ответа от API.
            language: Язык ответа.
            analysis_type: Тип анализа.

        Returns:
            Dict[str, Any]: Распарсенный результат анализа или заглушка.
        """
        logger.info(f"Парсинг ответа анализа от DeepSeek API, тип: {analysis_type}, язык: {language}")
        # logger.debug(f"Сырой текст ответа для парсинга: {repr(response_text)}") # Может быть много

        try:
            # 1. Попробуем извлечь JSON, обернутый в ```json ... ```
            json_match = re.search(r"```(?:json)?\s*({.*?})\s*```", response_text, re.DOTALL | re.IGNORECASE)
            extracted_json_text = None
            if json_match:
                extracted_json_text = json_match.group(1)
                logger.debug("JSON найден и извлечен из блока кода.")
            else:
                # 2. Если не найден, попробуем найти любой блок кода ``` ... ```
                code_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
                if code_match:
                    potential_json = code_match.group(1)
                    if potential_json.strip().startswith('{') and potential_json.strip().endswith('}'):
                        extracted_json_text = potential_json
                        logger.debug("Потенциальный JSON найден в блоке кода.")

            # 3. Если JSON извлечен, попробуем его распарсить
            if extracted_json_text:
                logger.debug("Попытка парсинга извлеченного JSON.")
                try:
                    analysis_result = json.loads(extracted_json_text)
                    logger.info("JSON успешно распарсен.")

                    # Проверяем наличие обязательных ключей
                    required_keys = ['mood_score', 'comment', 'recommendation']
                    if all(key in analysis_result for key in required_keys):
                        logger.info("Ответ анализа содержит все обязательные ключи.")
                        # Возвращаем результат как есть, без модификации поля 'analysis'.
                        # Формирование финального 'analysis_text' будет позже.
                        return analysis_result
                    else:
                        logger.warning("Распарсенный JSON не содержит все обязательные ключи.")

                except json.JSONDecodeError as json_error:
                    logger.error(f"Ошибка при парсинге извлеченного JSON: {json_error}")

            # 4. Попытка парсинга всего response_text (если не обернут в ````)
            logger.debug("Попытка парсинга всего response_text как JSON...")
            try:
                full_json_result = json.loads(response_text.strip())
                if isinstance(full_json_result, dict) and all(key in full_json_result for key in ['mood_score', 'comment', 'recommendation']):
                    logger.info("Весь response_text успешно распарсен как JSON.")
                    # Возвращаем результат как есть.
                    return full_json_result
                else:
                    logger.warning("Весь response_text распарсен, но не является словарем с нужными ключами")
            except json.JSONDecodeError:
                logger.debug("Не удалось распарсить весь response_text как JSON")

            # 5. Если ничего не помогло, возвращаем заглушку
            logger.warning("Не удалось извлечь валидный JSON из ответа. Возвращается заглушка.")
            raise ValueError("Не удалось извлечь валидный JSON")

        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Неожиданная ошибка при парсинге ответа анализа: {e}")

        # Возвращаем заглушку
        default_result = {
            'mood_score': 5,
            'comment': 'Анализ записан' if language == 'ru' else 'Analysis recorded',
            'recommendation': 'Продолжайте вести дневник' if language == 'ru' else 'Continue keeping a diary',
            'analysis': 'Текст проанализирован' if language == 'ru' else 'Text analyzed',
            'needs_clarification': False,
            'clarification_questions': []
        }
        if language == 'en':
            default_result.update({
                'comment': 'Analysis recorded',
                'recommendation': 'Continue keeping a diary',
                'analysis': 'Text analyzed'
            })
        logger.info("Возвращен результат анализа по умолчанию")
        return default_result

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
                "max_tokens": min(5000, (len(previous_state_context) + len(new_text)) * 2) # Удваиваем токены
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

                    if response.status == 200:
                        result = await response.json()
                        response_text = result['choices'][0]['message']['content']
                        logger.info(f"Инкрементальный анализ успешно выполнен, длина ответа: {len(response_text)} символов")

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
            previous_state_context: Предыдущее состояние дня.
            new_text: Новая запись.
            user_profile: Профиль пользователя.
            language: Язык.

        Returns:
            str: Сформированный промт.
        """
        logger.info("Генерация промта для инкрементального анализа")

        # Словарь промтов на разных языках
        prompts = {
            'ru': f'''Ты профессиональный психолог. Ниже приведен контекст эмоционального состояния пользователя за текущий день:
{previous_state_context}

Пользователь только что добавил новую запись:
"{new_text}"

Пожалуйста, обнови контекст эмоционального состояния пользователя, интегрируя новую информацию. Также предоставь анализ новой записи в стандартном формате JSON:
- "mood_score": оценка настроения от 1 до 10
- "comment": краткий комментарий (1 предложение)
- "recommendation": персональная рекомендация (1-2 предложения)
- "analysis": подробный анализ новой записи (2-3 предложения)
- "needs_clarification": boolean (нужны ли уточнения по новой записи)
- "clarification_questions": массив строк (вопросы, если нужны уточнения)
- "suggested_task": объект (опционально, описание задания)
   - "title": название задания
   - "description": описание задания
   - "type": тип задания (из списка: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": приоритет (строка: low, medium, high, critical)

Пример ответа:
{{
  "mood_score": 7,
  "comment": "Вы испытали всплеск энтузиазма после утренней прогулки.",
  "recommendation": "Попробуйте чаще включать физическую активность в свой день.",
  "analysis": "Новая запись показывает положительный сдвиг в эмоциях. Упоминание 'прогулка' и 'свежий воздух' коррелирует с повышением настроения.",
  "needs_clarification": false,
  "clarification_questions": [],
  "suggested_task": {{
    "title": "Ежедневная прогулка",
    "description": "Планируйте хотя бы 20-минутную прогулку каждый день этой недели.",
    "type": "behavioral",
    "priority": "medium"
  }}
}}
''',
            'en': f'''You are a professional psychologist. Below is the context of the user's emotional state for the current day:
{previous_state_context}

The user has just added a new entry:
"{new_text}"

Please update the user's emotional state context by integrating the new information. Also, provide an analysis of the new entry in standard JSON format:
- "mood_score": mood score from 1 to 10
- "comment": brief comment (1 sentence)
- "recommendation": personal recommendation (1-2 sentences)
- "analysis": detailed analysis of the new entry (2-3 sentences)
- "needs_clarification": boolean (whether clarifications are needed for the new entry)
- "clarification_questions": array of strings (questions if clarifications are needed)
- "suggested_task": object (optional, task description)
   - "title": task title
   - "description": task description
   - "type": task type (from the list: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": priority (string: low, medium, high, critical)

Example response:
{{
  "mood_score": 7,
  "comment": "You experienced a surge of enthusiasm after your morning walk.",
  "recommendation": "Try to include physical activity in your day more often.",
  "analysis": "The new entry shows a positive shift in emotions. The mention of 'walk' and 'fresh air' correlates with an improved mood.",
  "needs_clarification": false,
  "clarification_questions": [],
  "suggested_task": {{
    "title": "Daily Walk",
    "description": "Plan at least a 20-minute walk every day this week.",
    "type": "behavioral",
    "priority": "medium"
  }}
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
    max_tokens: int = 500
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
