"""
Периодические задачи для отправки напоминаний пользователям.
"""

import asyncio
import logging
from datetime import datetime
import pytz

from asgiref.sync import sync_to_async
from celery import shared_task
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.message_utils import send_message_to_user
from users.models import User
from messages import get_message, get_button_text
from core.settings import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

# === Вспомогательные асинхронные функции для работы с БД ===

@sync_to_async
def get_active_users_with_notifications():
    """Получение активных пользователей с включенными уведомлениями и не заблокированных."""
    return list(User.objects.filter(
        notifications_enabled=True,
        is_blocked=False,
        deletion_status='active'
    ))

@sync_to_async
def get_user_language(user):
    """Получение языка пользователя."""
    return user.language or 'ru'

@sync_to_async
def has_entries_for_user_on_date(user, target_date):
    """
    Проверяет, есть ли у пользователя записи на заданную дату (в его часовом поясе).
    """
    from diary.models import DiaryEntry
    from django.db.models import Q
    from datetime import time as dtime

    try:
        import pytz
        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)
        start_of_day_user_tz = datetime.combine(target_date, dtime.min)
        start_of_day_user_tz = user_tz.localize(start_of_day_user_tz)
        end_of_day_user_tz = datetime.combine(target_date, dtime.max)
        end_of_day_user_tz = user_tz.localize(end_of_day_user_tz)
        start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
        end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)
        return DiaryEntry.objects.filter(
            Q(user=user) &
            Q(created_at__gte=start_of_day_utc) &
            Q(created_at__lte=end_of_day_utc)
        ).exists()
    except Exception as e:
        logger.error(f"Ошибка при проверке записей пользователя {user.telegram_id} за {target_date}: {e}")
        return True 

# === Основная логика задачи ===

@shared_task
def send_entry_reminders():
    """
    Отправка ежедневных напоминаний о записи в дневник.
    Запускается раз в час Celery Beat.
    """
    logger.info("Запуск задачи отправки напоминаний о записи в дневник.")
    return asyncio.run(_send_entry_reminders_async())


async def _send_entry_reminders_async():
    """
    Асинхронная корутина для отправки напоминаний о записи в дневник.
    """
    bot = None
    try:
        users = await get_active_users_with_notifications()
        logger.info(f"Найдено {len(users)} активных пользователей с включенными уведомлениями (предварительная фильтрация по is_blocked=False)")
        success_count = 0
        error_count = 0
        sent_count = 0
        bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        for user in users:
            try:
                user_timezone_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Неизвестный часовой пояс у пользователя {user.telegram_id}: {user_timezone_str}. Используется UTC.")
                    user_tz = pytz.UTC
                user_local_time = datetime.now(user_tz)
                current_user_hour = user_local_time.hour
                user_local_date = user_local_time.date()
                if current_user_hour == 21: 
                    has_entries_today = await has_entries_for_user_on_date(user, user_local_date)
                    if has_entries_today:
                        logger.info(f"Пользователь {user.telegram_id} уже сделал запись сегодня ({user_local_date}). Напоминание не отправляется.")
                        continue
                    language = await get_user_language(user)
                    try:
                        message_text = get_message('reminder_entry', language)
                    except Exception as msg_error:
                        logger.warning(f"Не удалось получить сообщение 'reminder_entry' для пользователя {user.telegram_id}, язык {language}: {msg_error}")
                        message_text = (
                            "📝 <b>Не забудь сделать запись в дневник сегодня!</b>\n\n"
                            "Поделись своими мыслями и чувствами, чтобы лучше понимать себя."
                        ) if language == 'ru' else (
                            "📝 <b>Don't forget to make a diary entry today!</b>\n\n"
                            "Share your thoughts and feelings to better understand yourself."
                        )
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=get_button_text('btn_new_entry', language),
                                callback_data="new_entry"
                            )
                        ]
                    ])
                    success = await send_message_to_user(
                        bot=bot,
                        user=user,
                        text=message_text,
                        reply_markup=keyboard
                    )
                    if success:
                        sent_count += 1
                        success_count += 1
                        logger.info(f"Напоминание о записи успешно отправлено пользователю {user.telegram_id} (часовой пояс: {user_timezone_str})")
                    else:
                        error_count += 1
                        logger.info(f"Не удалось отправить напоминание пользователю {user.telegram_id} (возможно, заблокировал бота)")           
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке пользователя {user.telegram_id}: {e}", exc_info=True)
                error_count += 1
        logger.info(f"Задача напоминаний о записи завершена. "
                    f"Отправлено: {sent_count}, "
                    f"Успешно обработано: {success_count}, "
                    f"Ошибок: {error_count}")
        return (f"Отправлено: {sent_count}, "
                f"Успешно: {success_count}, "
                f"Ошибок: {error_count}")
    except Exception as e:
        logger.error(f"Критическая ошибка в задаче отправки напоминаний о записи в дневник: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"
    finally:
        if bot:
            try:
                await bot.session.close()
                logger.info("Сессия бота для напоминаний закрыта")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота для напоминаний: {close_error}")
