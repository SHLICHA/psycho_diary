"""
Сервис для обработки сообщений в чате с психологом ИИ.
Выносит бизнес-логику из хендлеров Telegram.
Теперь включает в себя логику вызова ИИ.
"""

import logging

from typing import Dict, Any, List

from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt
from users.models import User


logger = logging.getLogger(__name__)

class TherapyChatService:
    """
    Сервис для взаимодействия с API DeepSeek для чата с психологом.
    Содержит бизнес-логику, независимую от Telegram.
    """
    MAX_HISTORY_PAIRS = 10

    @classmethod
    async def start_chat(cls, user: User) -> Dict[str, Any]:
        """
        Инициализирует чат с психологом ИИ.
        Подготавливает начальное состояние (например, пустую историю).

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Результат инициализации.
                - success (bool): Успешность операции.
                - initial_history (List[Dict]): Начальная история чата.
                - welcome_message (str): Приветственное сообщение (может быть сформировано в хендлере).
                - error (Optional[str]): Сообщение об ошибке, если произошла ошибка.
        """
        try:
            logger.debug(f"[TherapyChatService] Инициализация чата для пользователя {user.telegram_id}")
            initial_history: List[Dict[str, str]] = []
            return {
                "success": True,
                "initial_history": initial_history,
                "error": None
            }
        except Exception as e:
            logger.error(f"[TherapyChatService] Ошибка при инициализации чата для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "initial_history": [],
                "error": str(e)
            }

    @classmethod
    async def process_user_message(
        cls,
        user: User,
        user_message_text: str,
        current_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Обрабатывает сообщение пользователя в чате с психологом.
        Вызывает ИИ, обновляет историю.

        Args:
            user: Объект пользователя Django.
            user_message_text (str): Текст сообщения пользователя.
            current_history (List[Dict[str, str]]): Текущая история чата в формате [{'role': '...', 'content': '...'}, ...].

        Returns:
            Dict[str, Any]: Результат обработки.
                - success (bool): Успешность операции.
                - response_text (str): Ответ ИИ.
                - updated_history (List[Dict[str, str]]): Обновлённая история чата.
                - error (Optional[str]): Сообщение об ошибке, если произошла ошибка.
        """
        logger.debug(f"[TherapyChatService] Обработка сообщения для пользователя {user.telegram_id}. Длина сообщения: {len(user_message_text)}, Длина истории: {len(current_history)}")
        try:
            history_str = "\n".join([f"{item['role']}: {item['content']}" for item in current_history])
            base_profile = await user.aget_profile_data()
            # Используем compressed_psych_profile для экономии токенов
            import json
            compressed_profile = user.compressed_psych_profile or {}
            compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, indent=2)
            extended_user_context = {
                "first_name": base_profile.get('first_name', 'Пользователь'),
                "awareness_level": base_profile.get('awareness_level', 1),
                "is_premium": base_profile.get('is_premium', False),
                "entries_count": base_profile.get('entries_count', 0),
            }
            prompt = get_prompt(
                key='therapy_chat',
                language=user.language,
                user_profile=extended_user_context,
                compressed_psych_profile_json=compressed_profile_json,
                history=history_str or "",
                user_message=user_message_text
            )
            logger.debug(f"[TherapyChatService] Промт для ИИ сгенерирован (длина: {len(prompt)} символов)")
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt=prompt,
                language=user.language,
                max_retries=2,
                base_delay=1.0,
                timeout_per_attempt=60
            )
            if api_result.get('success'):
                parsed_result = api_result['result']
                is_valid = parsed_result.get('is_valid', True)
                ai_response_text = parsed_result.get('response_text', "Не удалось сформировать ответ.")
                if not is_valid:
                     logger.warning(f"[TherapyChatService] Ответ ИИ признан невалидным для пользователя {user.telegram_id}.")
            else:
                # Обработка ошибки от API
                error_msg = api_result.get('message', 'Неизвестная ошибка API')
                logger.error(f"[TherapyChatService] Ошибка API при обработке сообщения: {error_msg}")
                ai_response_text = "К сожалению, произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте снова позже."
            new_pair = [
                {'role': 'Пользователь', 'content': user_message_text},
                {'role': 'ИИ', 'content': ai_response_text}
            ]
            updated_history = current_history + new_pair
            max_items = cls.MAX_HISTORY_PAIRS * 2
            if len(updated_history) > max_items:
                 updated_history = updated_history[-max_items:]
            logger.debug(f"[TherapyChatService] Сообщение обработано успешно для {user.telegram_id}")
            return {
                "success": True,
                "response_text": ai_response_text,
                "updated_history": updated_history,
                "error": None
            }
        except Exception as e:
            logger.error(f"[TherapyChatService] Неожиданная ошибка при обработке сообщения от {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "response_text": "Произошла внутренняя ошибка. Пожалуйста, попробуйте снова позже.",
                "updated_history": current_history,
                "error": str(e)
            }

    @classmethod
    async def end_chat(cls, user: User) -> Dict[str, Any]:
        """
        (Опционально) Логика завершения чата.
        Например, сброс временных данных в БД.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Результат завершения.
        """
        try:
            logger.debug(f"[TherapyChatService] Завершение чата для пользователя {user.telegram_id}")
            return {
                "success": True,
                "message": "Чат завершён."
            }
        except Exception as e:
            logger.error(f"[TherapyChatService] Ошибка при завершении чата для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

async def start_therapy_chat(user: User) -> Dict[str, Any]:
    """Удобная функция для инициализации чата."""
    return await TherapyChatService.start_chat(user)

async def process_user_message_in_chat(
    user: User,
    user_message_text: str,
    current_history: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Удобная функция для обработки сообщения пользователя."""
    return await TherapyChatService.process_user_message(user, user_message_text, current_history)

async def end_therapy_chat(user: User) -> Dict[str, Any]:
    """Удобная функция для завершения чата."""
    return await TherapyChatService.end_chat(user)
