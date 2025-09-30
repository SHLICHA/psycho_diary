import logging
import pytz
from datetime import datetime, date, timedelta
from celery import shared_task
from asgiref.sync import async_to_sync
from decouple import config
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from messages.messages_utils import get_button_text
from users.models import User
from diary.models import CombinedDiaryEntry, DailyAnalysis
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from messages.messages_utils import get_message

logger = logging.getLogger(__name__)

@shared_task
def send_morning_motivation_task():
    """
    Задача Celery для отправки утреннего мотивационного сообщения.
    Выполняется каждый час. Проверяет, наступило ли 10:00 у пользователей
    с учётом их часового пояса и статуса уведомлений.
    """
    logger.info("Запуск задачи send_morning_motivation_task")
    bot_token = config('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в настройках")
        return
    bot_instance = Bot(token=bot_token, parse_mode=ParseMode.HTML)
    if not bot_instance:
        logger.error("Не удалось инициализировать экземпляр бота")
        return
    users_to_check = User.objects.filter(
        is_blocked=False,
        deleted_at__isnull=True,
        deletion_status='active',
        notifications_enabled=True
    )
    utc_now = datetime.now(pytz.utc)
    logger.info(f"Найдено {users_to_check.count()} пользователей для проверки утреннего сообщения.")
    for user in users_to_check:
        try:
            user_timezone_str = user.timezone or 'UTC'
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Неверный часовой пояс для пользователя {user.telegram_id}: {user_timezone_str}. Используем UTC.")
                user_tz = pytz.utc
            user_local_datetime = utc_now.astimezone(user_tz)
            if user_local_datetime.hour == 10 and user_local_datetime.minute == 0:
                logger.info(f"Время 10:00 наступило для пользователя {user.telegram_id} в часовом поясе {user.timezone}")
                async_to_sync(_send_motivation_to_user)(user, bot_instance, user_local_datetime.date() - timedelta(days=1))
        except Exception as e:
            logger.error(f"Ошибка при проверке/отправке утреннего сообщения пользователю {user.telegram_id}: {e}", exc_info=True)
    try:
        async_to_sync(bot_instance.session.close)()
        logger.debug("Сессия бота закрыта после выполнения задачи.")
    except Exception as close_error:
        logger.error(f"Ошибка при закрытии сессии бота: {close_error}")
    logger.info("Завершена задача send_morning_motivation_task")

async def _send_motivation_to_user(user: User, bot_instance: Bot, target_date: date):
    """
    Внутренняя асинхронная функция для генерации и отправки сообщения одному пользователю.
    """
    logger.debug(f"Обработка пользователя {user.telegram_id} для утреннего сообщения на дату {target_date}.")
    user_profile = await user.aget_profile_data()
    extended_user_profile = {
        'username': user.username or f"user_{user.telegram_id}",
        'first_name': user.first_name or user.username or f"Пользователь {user.telegram_id}",
        'awareness_level': user.awareness_level,
        'is_premium': user.is_premium,
        'personality_traits': user.personality_traits,
        'life_facts': user.life_facts,
        'hobbies': user.hobbies,
        'core_values': user.core_values,
        'triggers': user.triggers,
        'strengths': user.strengths,
        'areas_for_growth': user.areas_for_growth,
        'habits': user.habits,
        'skills': user.skills,
        'aspirations': user.aspirations,
    }
    previous_day_analysis_data = {}
    try:
        combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_date)
        try:
            daily_analysis = await DailyAnalysis.objects.aget(combined_entry=combined_entry)
            previous_day_analysis_data = {
                "overall_analysis_text": daily_analysis.overall_analysis_text,
                "key_themes": daily_analysis.key_themes,
                "emotional_patterns": daily_analysis.emotional_patterns,
                "insights": daily_analysis.insights,
                "recommendations": daily_analysis.recommendations,
                "mood_trend": daily_analysis.mood_trend,
                "average_mood_score": combined_entry.average_mood_score if combined_entry.average_mood_score else None
            }
        except DailyAnalysis.DoesNotExist:
            previous_day_analysis_data = {}
            logger.debug(f"DailyAnalysis не найден для пользователя {user.telegram_id} за {target_date}, используем пустой контекст предыдущего дня.")
    except CombinedDiaryEntry.DoesNotExist:
        logger.debug(f"CombinedDiaryEntry не найден для пользователя {user.telegram_id} за {target_date}, используем пустой контекст предыдущего дня.")
    prompt = get_prompt(
        key='morning_motivation',
        language=user.language,
        user_profile=extended_user_profile,
        previous_day_analysis=previous_day_analysis_data
    )
    api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
    if api_result.get('success'):
        motivation_text = api_result.get('result', {}).get('motivation_message', 'Доброе утро! Пусть этот день будет наполнен радостью и вдохновением.')
    else:
        motivation_text = get_message('morning_motivation_default', user.language, first_name=extended_user_profile['first_name'])
        logger.warning(f"ИИ не сгенерировал сообщение для {user.telegram_id}, используется стандартное. Ошибка: {api_result.get('error')}")
    try:
        new_entry_button = InlineKeyboardButton(text=get_button_text('btn_new_entry', user.language), callback_data="new_entry")
        main_menu_button = InlineKeyboardButton(text=get_button_text('btn_main_menu', user.language), callback_data="main_menu")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[new_entry_button], [main_menu_button]])
        await bot_instance.send_message(chat_id=user.telegram_id, text=motivation_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        logger.info(f"Утреннее сообщение с кнопками отправлено пользователю {user.telegram_id} на дату {target_date}")
    except Exception as send_error:
        logger.error(f"Ошибка при отправке утреннего сообщения пользователю {user.telegram_id}: {send_error}")
        if isinstance(send_error, TelegramBadRequest):
            if "chat not found" in str(send_error).lower() or "bot was blocked" in str(send_error).lower():
                user.is_blocked = True
                await user.asave(update_fields=['is_blocked'])
                logger.info(f"Пользователь {user.telegram_id} заблокировал бота (обнаружено при отправке утреннего сообщения).")

