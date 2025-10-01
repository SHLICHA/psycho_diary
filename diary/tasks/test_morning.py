# diary/tasks/test_morning_motivation.py
"""
Тестовая задача для отправки утреннего мотивационного сообщения в заданное время.
"""

import asyncio
import logging
from datetime import datetime, timedelta
import pytz

from asgiref.sync import sync_to_async
from celery import shared_task
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

from bot.utils.message_utils import send_message_to_user
from users.models import User
from diary.models import CombinedDiaryEntry, DailyAnalysis
from messages import get_message, get_button_text
from core.settings import TELEGRAM_BOT_TOKEN
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt

logger = logging.getLogger(__name__)

@sync_to_async
def get_test_user(): # Функция для получения тестового пользователя
    """Получение тестового пользователя по telegram_id."""
    try:
        # ЗАМЕНИТЕ НА СВОЙ ID
        return User.objects.get(telegram_id=399096554) # <-- Ваш telegram_id
    except User.DoesNotExist:
        logger.error("Тестовый пользователь не найден!")
        return None

@shared_task
def send_test_morning_motivation_task():
    """
    Тестовая задача для отправки утреннего мотивационного сообщения.
    Отправляет сообщение тестовому пользователю, если московское время 13:17.
    """
    logger.info("Запуск ТЕСТОВОЙ задачи отправки утреннего мотивационного сообщения.")
    return asyncio.run(_send_test_morning_motivation_async())

async def _send_test_morning_motivation_async():
    """
    Асинхронная корутина для тестовой отправки утреннего мотивационного сообщения.
    """
    bot_instance = None
    try:
        user = await get_test_user()
        if not user:
            return "Тестовый пользователь не найден."

        # Проверяем московское время
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_time = datetime.now(moscow_tz)
        logger.info(f"[ТЕСТ] Московское время: {moscow_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if moscow_time.hour == 13 and moscow_time.minute == 42:
            logger.info(f"Время 13:17 в Москве. Отправляем тестовое сообщение пользователю {user.telegram_id}.")
            
            bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
            
            # --- Логика генерации и отправки (скопируйте из оригинальной задачи) ---
            try:
                user_language = user.language or 'ru'
                user_profile_data = await user.aget_profile_data()
                first_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"
                # Для теста используем "вчерашний" день по Москве
                target_analysis_date = moscow_time.date() - timedelta(days=1)

                previous_day_analysis_data = {}
                try:
                    combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_analysis_date)
                    try:
                        daily_analysis = await DailyAnalysis.objects.aget(combined_entry=combined_entry)
                        previous_day_analysis_data = {
                            "overall_analysis_text": daily_analysis.overall_analysis_text,
                            "key_themes": daily_analysis.key_themes,
                            "emotional_patterns": daily_analysis.emotional_patterns,
                            "insights": daily_analysis.insights,
                            "recommendations": daily_analysis.recommendations,
                            "mood_trend": daily_analysis.mood_trend,
                            "average_mood_score": getattr(combined_entry, 'average_mood_score', None)
                        }
                    except DailyAnalysis.DoesNotExist:
                        logger.debug(f"[ТЕСТ] DailyAnalysis не найден для пользователя {user.telegram_id} за {target_analysis_date}")
                except CombinedDiaryEntry.DoesNotExist:
                     logger.debug(f"[ТЕСТ] CombinedDiaryEntry не найден для пользователя {user.telegram_id} за {target_analysis_date}")

                prompt = get_prompt(
                    key='morning_motivation',
                    language=user_language,
                    user_profile=user_profile_data,
                    previous_day_analysis=previous_day_analysis_data
                )

                api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user_language)

                if api_result.get('success'):
                    motivation_text = api_result.get('result', {}).get('motivation_message', 
                        get_message('morning_motivation_default', user_language, first_name=first_name))
                else:
                    motivation_text = get_message('morning_motivation_default', user_language, first_name=first_name)
                    logger.warning(f"[ТЕСТ] ИИ не сгенерировал сообщение для {user.telegram_id}. Используется стандартное. Ошибка API: {api_result.get('error')}")

                motivation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_button_text('btn_new_entry', user_language), callback_data="new_entry")],
                    [InlineKeyboardButton(text=get_button_text('btn_main_menu', user_language), callback_data="main_menu")]
                ])

                success = await send_message_to_user(
                    bot=bot_instance,
                    user=user,
                    text=motivation_text,
                    reply_markup=motivation_keyboard
                )
                
                if success:
                    logger.info(f"[ТЕСТ] Тестовое утреннее сообщение успешно отправлено пользователю {user.telegram_id}")
                    return f"Тестовое сообщение отправлено пользователю {user.telegram_id}"
                else:
                    logger.error(f"[ТЕСТ] Не удалось отправить тестовое сообщение пользователю {user.telegram_id}")
                    return f"Ошибка отправки тестового сообщения пользователю {user.telegram_id}"
                    
            except Exception as processing_error:
                logger.error(f"[ТЕСТ] Ошибка при генерации или подготовке тестового сообщения для пользователя {user.telegram_id}: {processing_error}", exc_info=True)
                return f"Ошибка обработки для пользователя {user.telegram_id}: {processing_error}"
            # --- Конец логики генерации и отправки ---
        else:
            logger.info(f"[ТЕСТ] Время не 13:17 по Москве. Текущее время: {moscow_time.hour}:{moscow_time.minute}")
            return f"Время не 13:17 по Москве. Текущее время: {moscow_time.hour}:{moscow_time.minute}"

    except Exception as e:
        logger.critical(f"[ТЕСТ] Критическая ошибка в тестовой задаче: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"
    finally:
        if bot_instance:
            try:
                await bot_instance.session.close()
                logger.info("[ТЕСТ] Сессия бота для тестового утреннего сообщения закрыта.")
            except Exception as close_error:
                logger.error(f"[ТЕСТ] Ошибка при закрытии сессии бота: {close_error}")
