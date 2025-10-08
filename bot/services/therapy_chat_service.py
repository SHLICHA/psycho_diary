# /home/shlicha/psycho_diary/bot/services/therapy_chat_service.py
"""
Сервис для обработки сообщений в чате с психологом ИИ.
"""

import logging
from typing import Dict, Any

from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt

logger = logging.getLogger(__name__)

class TherapyChatService:
    """
    Сервис для взаимодействия с API DeepSeek для чата с психологом.
    """

    @staticmethod
    async def process_therapy_message(
        user_profile: Dict[str, Any],
        history: str,
        user_message: str,
        language: str
    ) -> Dict[str, Any]:
        """
        Обрабатывает сообщение пользователя в чате с психологом.

        Args:
            user_profile (Dict[str, Any]): Профиль пользователя.
            history (str): История чата (предыдущие сообщения и ответы).
            user_message (str): Текст сообщения пользователя.
            language (str): Язык пользователя ('ru' или 'en').

        Returns:
            Dict[str, Any]: Результат обработки от API, включая 'is_valid', 'response_text'.
        """
        logger.debug(f"[TherapyChatService] Обработка сообщения. Язык: {language}, Длина сообщения: {len(user_message)}, Длина истории: {len(history) if history else 0}")

        try:
            # Генерация промпта с подстановкой данных
            prompt = get_prompt(
                key='therapy_chat',
                language=language,
                user_profile=user_profile,
                history=history or "", # Передаем пустую строку, если история None
                user_message=user_message
            )
            logger.debug(f"[TherapyChatService] Промт сгенерирован (длина: {len(prompt)} символов)")

            # Отправка промта в DeepSeek API
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt=prompt,
                language=language,
                max_retries=2, # Можно настроить количество попыток
                base_delay=1.0,
                timeout_per_attempt=60 # Таймаут для чата может быть меньше
            )

            if api_result.get('success'):
                # Возвращаем распарсенный JSON от ИИ
                return api_result['result']
            else:
                # Обработка ошибки от API
                error_msg = api_result.get('message', 'Неизвестная ошибка API')
                logger.error(f"[TherapyChatService] Ошибка API при обработке сообщения: {error_msg}")
                return {
                    "is_valid": False,
                    "response_text": "К сожалению, произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте снова позже.",
                    "error": "api_error"
                }

        except Exception as e:
            logger.error(f"[TherapyChatService] Неожиданная ошибка при обработке сообщения: {e}", exc_info=True)
            return {
                "is_valid": False,
                "response_text": "Произошла внутренняя ошибка. Пожалуйста, попробуйте снова позже.",
                "error": "internal_error"
            }

# Алиас для удобства, если нужно
async def process_therapy_message(
    user_profile: Dict[str, Any],
    history: str,
    user_message: str,
    language: str
) -> Dict[str, Any]:
    """
    Удобная функция для обработки сообщения в чате с психологом.
    """
    return await TherapyChatService.process_therapy_message(
        user_profile, history, user_message, language
    )
