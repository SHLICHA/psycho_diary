import logging
from datetime import datetime
import pytz
from typing import Union

logger = logging.getLogger(__name__)

def convert_utc_to_user_timezone(utc_dt: datetime, user_timezone_str: str) -> datetime:
    """
    Конвертирует datetime в UTC в datetime, соответствующий часовому поясу пользователя.

    Args:
        utc_dt (datetime): Время в UTC (объект datetime, предположительно timezone-aware или naive UTC).
        user_timezone_str (str): Строка с названием часового пояса пользователя (например, 'Europe/Moscow').

    Returns:
        datetime: Время, локализованное в часовом поясе пользователя.
    """
    try:
        logger.debug(f"Конвертация времени UTC {utc_dt} в часовой пояс пользователя {user_timezone_str}")

        # Обеспечиваем, что utc_dt является timezone-aware (в UTC)
        if utc_dt.tzinfo is None:
            # Если naive, считаем его UTC
            utc_dt = pytz.utc.localize(utc_dt)
            logger.debug(f"Входное время было naive, локализовано как UTC: {utc_dt}")
        else:
            # Если уже aware, конвертируем в UTC
            utc_dt = utc_dt.astimezone(pytz.utc)
            logger.debug(f"Входное время было aware, сконвертировано в UTC: {utc_dt}")

        # Получаем объект часового пояса пользователя
        user_tz = pytz.timezone(user_timezone_str)
        logger.debug(f"Объект часового пояса пользователя: {user_tz}")

        # Конвертируем UTC время в пользовательский часовой пояс
        user_local_dt = utc_dt.astimezone(user_tz)
        logger.debug(f"Сконвертированное локальное время пользователя: {user_local_dt}")

        return user_local_dt

    except pytz.UnknownTimeZoneError:
        logger.error(f"Неизвестный часовой пояс пользователя: {user_timezone_str}. Используется UTC.")
        # Возвращаем исходное время, считая его UTC
        if utc_dt.tzinfo is None:
            return pytz.utc.localize(utc_dt)
        else:
            return utc_dt.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Ошибка при конвертации времени для пользователя с часовым поясом {user_timezone_str}: {e}")
        # Возвращаем исходное время, считая его UTC
        if utc_dt.tzinfo is None:
            return pytz.utc.localize(utc_dt)
        else:
            return utc_dt.astimezone(pytz.utc)