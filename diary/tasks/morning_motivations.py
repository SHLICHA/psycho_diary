"""
Периодические задачи для отправки утренних мотивационных сообщений пользователям.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
import pytz

from asgiref.sync import sync_to_async
from celery import shared_task
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

# Импортируем утилиту для отправки сообщений (предполагаем, что она есть и работает)
from bot.utils.message_utils import send_message_to_user # Убедитесь, что путь правильный
from users.models import User
from diary.models import CombinedDiaryEntry, DailyAnalysis
from messages import get_message, get_button_text
# Импортируем токен и сервис ИИ
from core.settings import TELEGRAM_BOT_TOKEN
from bot.services.deepseek_api import deepseek_api_service # Убедитесь, что путь правильный
from prompts.get_prompt import get_prompt # Убедитесь, что путь правильный

logger = logging.getLogger(__name__)

# === Вспомогательные асинхронные функции для работы с БД ===

@sync_to_async
def get_users_for_morning_motivation():
    """
    Получение активных пользователей с включенными уведомлениями, не заблокированных.
    """
    return list(User.objects.filter(
        notifications_enabled=True,
        is_blocked=False,
        deletion_status='active',
        deleted_at__isnull=True
    ))


# === Основная логика задачи ===

@shared_task
def send_morning_motivation_task():
    """
    Отправка ежедневных утренних мотивационных сообщений.
    Запускается раз в час Celery Beat.
    """
    logger.info("Запуск задачи отправки утренних мотивационных сообщений.")
    # Используем asyncio.run, как в reminder_tasks.py
    return asyncio.run(_send_morning_motivation_async())


async def _send_morning_motivation_async():
    """
    Асинхронная корутина для отправки утренних мотивационных сообщений.
    """
    bot_instance = None
    try:
        users = await get_users_for_morning_motivation()
        logger.info(f"Найдено {len(users)} активных пользователей с включенными уведомлениями для утреннего сообщения.")
        
        success_count = 0
        error_count = 0
        sent_motivation_count = 0
        
        # Создаем экземпляр бота, как в reminder_tasks.py
        bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        
        utc_now = datetime.now(pytz.utc)

        for user in users:
            try:
                user_timezone_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Неизвестный часовой пояс у пользователя {user.telegram_id}: {user_timezone_str}. Используется UTC.")
                    user_tz = pytz.UTC
                
                user_local_time = utc_now.astimezone(user_tz)
                current_user_hour = user_local_time.hour
                current_user_minute = user_local_time.minute
                # user_local_date = user_local_time.date() # Не используется напрямую
                
                # Проверяем, наступило ли 10:00 по местному времени пользователя
                #if current_user_hour == 10:
                if current_user_hour == 10:
                    logger.info(f"Время 10:00 наступило для пользователя {user.telegram_id} в часовом поясе {user_timezone_str}")
                    
                    # --- Логика генерации и отправки сообщения ---
                    try:
                        # 1. Получаем данные пользователя
                        user_language = user.language or 'ru'
                        user_profile_data = await user.aget_profile_data()
                        first_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"

                        # 2. Определяем дату для анализа (вчерашний день)
                        target_analysis_date = user_local_time.date() - timedelta(days=1)

                        # 3. Получаем данные предыдущего дня (асинхронно)
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
                                logger.debug(f"DailyAnalysis не найден для пользователя {user.telegram_id} за {target_analysis_date}")
                        except CombinedDiaryEntry.DoesNotExist:
                             logger.debug(f"CombinedDiaryEntry не найден для пользователя {user.telegram_id} за {target_analysis_date}")

                        # 4. Формируем промпт
                        prompt = get_prompt(
                            key='morning_motivation',
                            language=user_language,
                            user_profile=user_profile_data, # Или часть данных, если get_prompt требует конкретную структуру
                            previous_day_analysis=previous_day_analysis_data
                        )

                        # 5. Отправляем запрос к ИИ (асинхронно)
                        api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user_language)

                        # 6. Обрабатываем результат ИИ
                        if api_result.get('success'):
                            motivation_text = api_result.get('result', {}).get('motivation_message', 
                                get_message('morning_motivation_default', user_language, first_name=first_name))
                        else:
                            motivation_text = get_message('morning_motivation_default', user_language, first_name=first_name)
                            logger.warning(f"ИИ не сгенерировал сообщение для {user.telegram_id}. Используется стандартное. Ошибка API: {api_result.get('error')}")

                        # 7. Создаем клавиатуру
                        # Создаем клавиатуру, как в reminder_tasks.py, но с другими кнопками
                        motivation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=get_button_text('btn_new_entry', user_language),
                                    callback_data="new_entry"
                                )
                            ],
                            [
                                 InlineKeyboardButton(
                                    text=get_button_text('btn_main_menu', user_language),
                                    callback_data="main_menu"
                                )
                            ]
                        ])

                        # 8. Отправляем сообщение пользователю (используем проверенную утилиту)
                        # send_message_to_user обрабатывает ошибки и обновляет is_blocked
                        success = await send_message_to_user(
                            bot=bot_instance, # Передаем созданный экземпляр бота
                            user=user,
                            text=motivation_text,
                            reply_markup=motivation_keyboard
                        )
                        
                        if success:
                            sent_motivation_count += 1
                            success_count += 1
                            logger.info(f"Утреннее мотивационное сообщение успешно отправлено пользователю {user.telegram_id}")
                        else:
                            # send_message_to_user уже обработал ошибку (например, бот заблокирован)
                            error_count += 1
                            logger.info(f"Не удалось отправить утреннее сообщение пользователю {user.telegram_id} (возможно, бот заблокирован)")

                    except Exception as processing_error:
                        logger.error(f"Ошибка при генерации или подготовке утреннего сообщения для пользователя {user.telegram_id}: {processing_error}", exc_info=True)
                        error_count += 1
                    # --- Конец логики генерации и отправки ---
                        
            except TelegramForbiddenError:
                # send_message_to_user должна была поймать это, но на всякий случай
                logger.info(f"Бот заблокирован пользователем {user.telegram_id} (обнаружено на уровне задачи).")
                user.is_blocked = True
                await sync_to_async(user.save)(update_fields=['is_blocked'])
                error_count += 1
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке пользователя {user.telegram_id} для утреннего сообщения: {e}", exc_info=True)
                error_count += 1 
                
        logger.info(f"Задача утренних мотивационных сообщений завершена. "
                    f"Отправлено сообщений: {sent_motivation_count}, "
                    f"Успешно обработано: {success_count}, "
                    f"Ошибок: {error_count}")
        return (f"Утренних сообщений отправлено: {sent_motivation_count}, "
                f"Успешно: {success_count}, "
                f"Ошибок: {error_count}") 
                
    except Exception as e:
        logger.critical(f"Критическая ошибка в задаче отправки утренних мотивационных сообщений: {e}", exc_info=True)
        return f"Критическая ошибка: {e}"
    finally:
        # Закрываем сессию бота, как в reminder_tasks.py
        if bot_instance:
            try:
                await bot_instance.session.close()
                logger.info("Сессия бота для утренних сообщений закрыта.")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота утренних сообщений: {close_error}")