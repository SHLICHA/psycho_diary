"""
Middleware для сбора аналитики
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from django.utils import timezone

from diary.models import UserActivity

logger = logging.getLogger(__name__)

class AnalyticsMiddleware(BaseMiddleware):
    """
    Middleware для сбора аналитики использования бота
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        start_time = time.time()
        result = await handler(event, data)
        await self._collect_analytics(event, data, start_time)
        return result
    
    async def _collect_analytics(
        self, 
        event: TelegramObject, 
        data: Dict[str, Any], 
        start_time: float
        ):
        """
        Сбор аналитики по событию
        """
        try:
            user = data.get('user')
            if not user:
                return
            activity_type = self._determine_activity_type(event)
            if not activity_type:
                return
            processing_time = time.time() - start_time
            await UserActivity.objects.acreate(
                user=user,
                activity_type=activity_type,
                metadata={
                    'processing_time': round(processing_time, 3),
                    'timestamp': timezone.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Ошибка при сборе аналитики: {e}")
    
    # TODO Доделать, расширить, уточнить типы
    def _determine_activity_type(self, event: TelegramObject) -> str:
        """
        Определение типа активности по событию
        """
        if isinstance(event, Message):
            if event.text:
                return 'message_text'
            elif event.voice:
                return 'message_voice'
            elif event.photo:
                return 'message_photo'
            else:
                return 'message_other'
        elif isinstance(event, CallbackQuery):
            callback_data = event.data or ''
            if callback_data.startswith('task_'):
                return 'task_interaction'
            elif callback_data.startswith('entry_'):
                return 'entry_interaction'
            elif callback_data in ['new_entry', 'archive', 'tasks', 'progress', 'settings', 'help']:
                return 'menu_navigation'
            else:
                return 'callback_query'
        else:
            return 'other_activity'