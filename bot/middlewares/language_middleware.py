"""
Middleware для определения языка
"""

import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from core.constants import LANGUAGES

logger = logging.getLogger(__name__)

class LanguageMiddleware(BaseMiddleware):
    """
    Middleware для определения языка пользователя
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get('user')
        
        if user:
            language = user.language
        else:
            language = self._detect_language_from_telegram(event)
        if language not in [lang[0] for lang in LANGUAGES]:
            language = 'ru'
        data['language'] = language
        result = await handler(event, data)
        return result
    
    def _detect_language_from_telegram(self, event: TelegramObject) -> str:
        """
        Определение языка из данных Telegram
        """
        try:
            if isinstance(event, Message):
                lang_code = event.from_user.language_code
            elif isinstance(event, CallbackQuery):
                lang_code = event.from_user.language_code
            else:
                logger.warning("Неизвестный тип события для определения языка")
                return 'ru'
            supported_languages = ['ru', 'en']
            if lang_code and lang_code[:2] in supported_languages:
                detected_lang = lang_code[:2]
                return detected_lang
            else:
                return 'ru'
        except Exception as e:
            logger.error(f"Ошибка при определении языка из Telegram: {e}")
            return 'ru'