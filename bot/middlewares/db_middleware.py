from asgiref.sync import sync_to_async
from django.db import close_old_connections
from typing import Any, Callable, Dict
from aiogram.types import TelegramObject

class DatabaseConnectionMiddleware:
    """
    Middleware для закрытия старых соединений с БД перед и после каждого обновления.
    Решает ошибки: 'connection already closed', 'SSL connection closed unexpectedly'.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Закрываем старые соединения ДО обработки
        await sync_to_async(close_old_connections)()
        try:
            return await handler(event, data)
        finally:
            # Закрываем соединения ПОСЛЕ обработки (на всякий случай)
            await sync_to_async(close_old_connections)()