import logging
from datetime import datetime
import pytz

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
        if utc_dt.tzinfo is None:
            utc_dt = pytz.utc.localize(utc_dt)
        else:
            utc_dt = utc_dt.astimezone(pytz.utc)
        user_tz = pytz.timezone(user_timezone_str)
        user_local_dt = utc_dt.astimezone(user_tz)
        return user_local_dt
    except pytz.UnknownTimeZoneError:
        logger.error(f"Неизвестный часовой пояс пользователя: {user_timezone_str}. Используется UTC.")
        if utc_dt.tzinfo is None:
            return pytz.utc.localize(utc_dt)
        else:
            return utc_dt.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Ошибка при конвертации времени для пользователя с часовым поясом {user_timezone_str}: {e}")
        if utc_dt.tzinfo is None:
            return pytz.utc.localize(utc_dt)
        else:
            return utc_dt.astimezone(pytz.utc)