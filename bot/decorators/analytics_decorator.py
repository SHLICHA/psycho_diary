import logging
import time
from functools import wraps
from typing import Callable, Any, Awaitable, Optional
from django.utils import timezone
from diary.models import UserActivity
from users.models import User

logger = logging.getLogger(__name__)

def log_user_activity(activity_type: str, metadata_extra: Optional[dict] = None):
    """
    Декоратор для логирования активности пользователя в UserActivity.

    Args:
        activity_type (str): Тип активности (например, 'entry_created', 'timezone_changed').
                             Должен соответствовать choices в модели UserActivity.
    ('message_text', 'Текстовое сообщение'),
    ('message_voice', 'Голосовое сообщение'),
    ('task_assigned', 'Назначение задания'),
    ('task_completed', 'Выполнение задания'),
    ('task_skipped', 'Пропуск задания'),
    ('entry_created', 'Создание записи'),
    ('entry_viewed', 'Просмотр записи'),
    ('entry_deleted', 'Удаление записи'),
    ('profile_updated', 'Обновление профиля'),
    ('settings_changed', 'Изменение настроек'),
    ('command', 'Использование команды')
        metadata_extra (Optional[dict]): Дополнительные данные для поля metadata.
                                         Будут объединены с базовыми метаданными.
    """
    def decorator(handler: Callable[..., Awaitable[Any]]):
        @wraps(handler)
        async def wrapper(*args, **kwargs):
            # Пытаемся получить 'user' из kwargs, который добавляется middleware
            user = kwargs.get('user')

            # Засекаем время начала выполнения хендлера
            start_time = time.time()

            # Выполняем оригинальный хендлер
            result = await handler(*args, **kwargs)

            # Вычисляем время выполнения после завершения хендлера
            execution_time = time.time() - start_time

            if user:
                try:
                    # Подготовим метаданные
                    metadata = {
                        'handler': handler.__name__, # Имя хендлера как часть контекста
                        'execution_time_sec': round(execution_time, 3), # Время выполнения в секундах, округлённое до 3 знаков
                    }
                    if metadata_extra:
                        metadata.update(metadata_extra)

                    # Создаём запись активности
                    await UserActivity.objects.acreate(
                        user=user,
                        activity_type=activity_type,
                        timestamp=timezone.now(), # Используем Django timezone
                        metadata=metadata
                    )
                    logger.debug(f"Активность пользователя {user.telegram_id} залогирована: {activity_type}, время выполнения: {execution_time:.3f}с")
                except Exception as e:
                    # Логируем ошибку, но не прерываем выполнение хендлера
                    logger.error(f"Ошибка при логировании активности '{activity_type}' для пользователя {user.telegram_id}: {e}")
            else:
                logger.debug(f"Пользователь не найден, активность '{activity_type}' не логируется (время выполнения: {execution_time:.3f}с).")

            return result
        return wrapper
    return decorator