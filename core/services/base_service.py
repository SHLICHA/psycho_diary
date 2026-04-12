# /core/services/base_service.py
"""
Базовый класс для всех сервисов.
Предоставляет общие утилиты для работы с БД, чтобы избежать дублирования.

Использование:
    class MyService(BaseService):
        async def do_something(self, telegram_id: int):
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user:
                return None
            ...
"""

import logging
from typing import Optional, List, Any, Callable, TypeVar
from collections.abc import Awaitable

from asgiref.sync import sync_to_async
from django.db import models

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseService:
    """Базовый класс для всех сервисов."""

    @staticmethod
    async def get_user_by_telegram_id(telegram_id: int) -> Optional[Any]:
        """
        Получает пользователя по Telegram ID.

        Args:
            telegram_id: Telegram ID.

        Returns:
            User или None.
        """
        from users.models import User
        try:
            return await User.objects.aget(telegram_id=telegram_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    async def async_db_operation(func: Callable[..., T], *args, **kwargs) -> T:
        """
        Выполняет синхронную DB-операцию в асинхронном контексте.

        Args:
            func: Синхронная функция (например, Model.objects.create).
            *args, **kwargs: Аргументы для функции.

        Returns:
            Результат выполнения.
        """
        return await sync_to_async(func)(*args, **kwargs)

    @staticmethod
    def sync_db(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
        """
        Декоратор для оборачивания синхронной DB-функции в async.

        Usage:
            @BaseService.sync_db
            def get_items():
                return list(MyModel.objects.all())

            items = await get_items()
        """
        return sync_to_async(func)

    @staticmethod
    async def get_queryset_sync(func: Callable[..., List[T]], *args, **kwargs) -> List[T]:
        """
        Выполняет синхронный запрос к БД и возвращает список результатов.

        Args:
            func: Функция запроса (например, Model.objects.filter(...)).
            *args, **kwargs: Аргументы для функции.

        Returns:
            List[T]: Список результатов.
        """
        return await sync_to_async(func)(*args, **kwargs)
