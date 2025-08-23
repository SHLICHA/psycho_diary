"""
Middleware для сбора аналитики
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from django.utils import timezone

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
        
        # Выполняем обработчик
        result = await handler(event, data)
        
        # Собираем аналитику после обработки
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
                logger.info("Пользователь не найден, аналитика не собирается")
                return
            
            # Определяем тип активности
            activity_type = self._determine_activity_type(event)
            if not activity_type:
                logger.info("Тип активности не определен")
                return
            
            # Вычисляем время обработки
            processing_time = time.time() - start_time
            
            # Импортируем модель активности внутри функции чтобы избежать циклических импортов
            from diary.models import UserActivity
            
            # Создаем запись активности
            await UserActivity.objects.acreate(
                user=user,
                activity_type=activity_type,
                metadata={
                    'processing_time': round(processing_time, 3),
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            logger.info(
                f"Аналитика: Пользователь {user.telegram_id} - {activity_type} "
                f"(время обработки: {processing_time:.3f}с)"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при сборе аналитики: {e}")
    
    def _determine_activity_type(self, event: TelegramObject) -> str:
        """
        Определение типа активности по событию
        """
        logger.info("Определение типа активности")
        
        if isinstance(event, Message):
            if event.text:
                logger.info("Тип активности: текстовое сообщение")
                return 'message_text'
            elif event.voice:
                logger.info("Тип активности: голосовое сообщение")
                return 'message_voice'
            elif event.photo:
                logger.info("Тип активности: фото сообщение")
                return 'message_photo'
            else:
                logger.info("Тип активности: другое сообщение")
                return 'message_other'
        elif isinstance(event, CallbackQuery):
            callback_data = event.data or ''
            if callback_data.startswith('task_'):
                logger.info("Тип активности: взаимодействие с заданием")
                return 'task_interaction'
            elif callback_data.startswith('entry_'):
                logger.info("Тип активности: взаимодействие с записью")
                return 'entry_interaction'
            elif callback_data in ['new_entry', 'archive', 'tasks', 'progress', 'settings', 'help']:
                logger.info("Тип активности: навигация по меню")
                return 'menu_navigation'
            else:
                logger.info("Тип активности: callback запрос")
                return 'callback_query'
        else:
            logger.info("Тип активности: другая активность")
            return 'other_activity'