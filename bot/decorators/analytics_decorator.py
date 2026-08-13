import logging
import time
from functools import wraps
from typing import Callable, Any, Awaitable, Optional

logger = logging.getLogger(__name__)


def log_user_activity(activity_type: str, metadata_extra: Optional[dict] = None):
    """
    Декоратор Telegram: после успешного handler вызывает activity_service.

    Типы вне allowlist не пишутся в UserActivity (см. ACTIVITY_TRACKING_PLAN.md).
    """
    def decorator(handler: Callable[..., Awaitable[Any]]):
        @wraps(handler)
        async def wrapper(*args, **kwargs):
            user = kwargs.get('user')
            start_time = time.time()
            result = await handler(*args, **kwargs)
            execution_time = time.time() - start_time

            if user:
                from diary.services.activity_service import record_user_activity

                metadata = {
                    'handler': handler.__name__,
                    'execution_time_sec': round(execution_time, 3),
                }
                if metadata_extra:
                    metadata.update(metadata_extra)
                await record_user_activity(
                    user,
                    activity_type,
                    platform='telegram',
                    metadata=metadata,
                )
            else:
                logger.debug(
                    "Пользователь не найден, активность '%s' не логируется "
                    "(время выполнения: %.3fс).",
                    activity_type,
                    execution_time,
                )

            return result
        return wrapper
    return decorator