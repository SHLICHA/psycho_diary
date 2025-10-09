import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from django.utils import timezone
from users.models import User

logger = logging.getLogger(__name__)

class PremiumCheckMiddleware(BaseMiddleware):
    """
    Middleware для проверки актуальности премиум подписки пользователя.
    Если `user.premium_expires_at` < `now`, то:
    - `user.is_premium` = False
    - `user.premium_expires_at` = None (опционально, если не нужно хранить дату окончания)
    Обновления сохраняются в БД.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get('user')

        if not user:
            logger.warning("UserMiddleware не установила объект user, невозможно проверить подписку.")
            # Пропускаем middleware, если нет пользователя
            return await handler(event, data)

        # Проверяем, есть ли у пользователя дата окончания подписки и активен ли флаг
        if user.premium_expires_at and user.is_premium:
            now = timezone.now()
            if user.premium_expires_at < now:
                # Подписка истекла
                logger.info(f"Подписка пользователя {user.telegram_id} истекла ({user.premium_expires_at} < {now}). Деактивация.")
                user.is_premium = False
                # Опционально: можно сбросить дату, если она больше не нужна
                # user.premium_expires_at = None
                await user.asave(update_fields=['is_premium']) # , 'premium_expires_at'
                # Обновляем флаг в data, если handler его использует
                data['is_premium_active'] = False
            else:
                # Подписка активна
                data['is_premium_active'] = True
        elif not user.is_premium:
            # is_premium уже False, точно не активна
            data['is_premium_active'] = False
        else:
            # is_premium True, но нет даты окончания (старая логика, например)
            # Считаем, что не активна
            logger.debug(f"У пользователя {user.telegram_id} is_premium=True, но нет даты окончания подписки.")
            data['is_premium_active'] = False

        # Продолжаем выполнение
        result = await handler(event, data)
        return result