"""
Периодические задачи для отправки напоминаний пользователям.
"""

import asyncio
import logging
import pytz

from django.db.models import Q
from datetime import datetime, timedelta, time as dtime
from asgiref.sync import sync_to_async
from celery import shared_task
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from django.db import close_old_connections

from bot.utils.message_utils import send_message_to_user
from bot.services import deepseek_api_service
from bot.utils.bot_factory import create_bot_for_task
from diary.models import TherapyTask, DiaryEntry, CombinedDiaryEntry, DailyAnalysis
from diary.services.task_management_service import get_uncompleted_tasks_count_for_user
from users.models import User
from messages import get_message, get_button_text
from prompts.get_prompt import get_prompt
from bot.utils.diary_utils import get_user_streaks

logger = logging.getLogger(__name__)

# === Вспомогательные асинхронные функции для работы с БД ===

@sync_to_async
def get_active_users_with_notifications():
    """Получение активных пользователей с включенными уведомлениями и не заблокированных."""
    close_old_connections()
    return list(User.objects.filter(
        notifications_enabled=True,
        is_blocked=False,
        deletion_status='active'
    ))

@sync_to_async
def get_user_language(user):
    """Получение языка пользователя."""
    close_old_connections()
    return user.language or 'ru'

@sync_to_async
def has_entries_for_user_on_date(user, target_date):
    """
    Проверяет, есть ли у пользователя записи на заданную дату (в его часовом поясе).
    """

    close_old_connections()
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

@shared_task
def send_entry_reminders():
    """
    Отправка ежедневных напоминаний о записи в дневник.
    Запускается раз в час Celery Beat.
    """
    logger.debug("Запуск задачи отправки напоминаний о записи в дневник.")
    return asyncio.run(_send_entry_reminders_async())


@sync_to_async
def get_uncompleted_tasks_count_for_user_today(user):
    """
    Подсчитывает количество незавершенных задач для пользователя (статус в ['pending', 'in_progress']).
    """
    close_old_connections()
    try:
        count = TherapyTask.objects.filter(
            user=user,
            status__in=['pending',]
        ).count()
        return count
    except Exception as e:
        logger.error(f"Ошибка при подсчете незавершенных задач пользователя {user.telegram_id}: {e}", exc_info=True)
        return 0

async def _send_entry_reminders_async():
    """
    Асинхронная корутина для отправки напоминаний о записи в дневник.
    """
    bot = None
    try:
        users = await get_active_users_with_notifications()
        logger.debug(f"Найдено {len(users)} активных пользователей с включенными уведомлениями")
        success_count = 0
        error_count = 0
        sent_entry_reminder_count = 0
        bot = await create_bot_for_task()
        
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
                language = await get_user_language(user)
                if current_user_hour == 22:
                    has_entries_today = await has_entries_for_user_on_date(user, user_local_date)
                    if has_entries_today:
                        logger.debug(f"Пользователь {user.telegram_id} уже сделал запись сегодня ({user_local_date}). Напоминание о записи не отправляется.")
                        continue

                    uncompleted_tasks_count = await get_uncompleted_tasks_count_for_user(user)
                    current_streak, longest_streak, has_entry_today = await get_user_streaks(user)
                    yesterday = user_local_date - timedelta(days=1)
                    previous_day_text = ""
                    previous_day_analysis = {}
                    try:
                        combined_entry_yesterday = await CombinedDiaryEntry.objects.aget(user=user, date=yesterday)
                        previous_day_text = combined_entry_yesterday.text
                        try:
                            daily_analysis_yesterday = await DailyAnalysis.objects.aget(combined_entry=combined_entry_yesterday)
                            previous_day_analysis = {
                                "overall_analysis_text": daily_analysis_yesterday.overall_analysis_text,
                                "key_themes": daily_analysis_yesterday.key_themes,
                                "emotional_patterns": daily_analysis_yesterday.emotional_patterns,
                                "insights": daily_analysis_yesterday.insights,
                                "recommendations": daily_analysis_yesterday.recommendations,
                                "mood_trend": daily_analysis_yesterday.mood_trend,
                                "average_mood_score": combined_entry_yesterday.average_mood_score
                            }
                        except DailyAnalysis.DoesNotExist:
                            previous_day_analysis = {}
                    except CombinedDiaryEntry.DoesNotExist:
                        previous_day_text = ""
                        previous_day_analysis = {}
                    user_profile_data = await user.aget_profile_data()
                    prompt = get_prompt(
                        key='reminder_message',
                        language=language,
                        user_profile=user_profile_data,
                        uncompleted_tasks_count=uncompleted_tasks_count,
                        current_streak=current_streak,
                        longest_streak=longest_streak,
                        previous_day_analysis=previous_day_analysis
                    )
                    api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=language)
                    if api_result.get('success'):
                        entry_reminder_text = api_result.get('result', {}).get('motivation_message', 
                            get_message('reminder_entry', language))
                    else:
                        logger.warning(f"ИИ не сгенерировал персонализированное напоминание для {user.telegram_id}. Используется стандартное. Ошибка API: {api_result.get('error')}")
                        try:
                            entry_reminder_text = get_message('reminder_entry', language)
                        except Exception as msg_error:
                            logger.warning(f"Не удалось получить сообщение 'reminder_entry' для пользователя {user.telegram_id}: {msg_error}")
                            base_text = (
                                "📝 <b>Не забудь сделать запись в дневник сегодня!</b>\n\n"
                                "Поделись своими мыслями и чувствами, чтобы лучше понимать себя."
                            ) if language == 'ru' else (
                                "📝 <b>Don't forget to make a diary entry today!</b>\n\n"
                                "Share your thoughts and feelings to better understand yourself."
                            )
                            entry_reminder_text = base_text

                    entry_keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
                        text=entry_reminder_text,
                        reply_markup=entry_keyboard
                    )
                    if success:
                        sent_entry_reminder_count += 1
                        success_count += 1
                        logger.debug(f"Напоминание о записи успешно отправлено пользователю {user.telegram_id}")
                    else:
                        error_count += 1
                        logger.debug(f"Не удалось отправить напоминание о записи пользователю {user.telegram_id}")
                else:
                    continue
                    
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке пользователя {user.telegram_id}: {e}", exc_info=True)
                error_count += 1 
        
        logger.info(f"Задача напоминаний завершена. "
                    f"Напоминаний о записи: {sent_entry_reminder_count}, "
                    f"Успешно обработано: {success_count}, "
                    f"Ошибок: {error_count}")
        return (f"Напоминаний о записи: {sent_entry_reminder_count}, "
                f"Успешно: {success_count}, "
                f"Ошибок: {error_count}") 
    except Exception as e:
        logger.error(f"Критическая ошибка в задаче отправки напоминаний: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"
    finally:
        if bot:
            try:
                await bot.session.close()
                logger.debug("Сессия бота для напоминаний закрыта")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота: {close_error}")