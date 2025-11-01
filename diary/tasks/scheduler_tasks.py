"""
Celery задачи для периодического анализа дней.
"""
import asyncio
import logging

from datetime import datetime, date, time, timedelta
import pytz
from celery import shared_task
from django.utils import timezone
from aiogram import Bot
from asgiref.sync import async_to_sync, sync_to_async
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from django.db import close_old_connections

from users.models import User, TokenTransaction
from diary.models import DailyAnalysis
from diary.services.smart_prompt_manager import smart_prompt_manager
from bot.services.diary_service import diary_service
from diary.services.full_day_analysis_service import full_day_analysis_service
from core.settings import TELEGRAM_BOT_TOKEN
from bot.utils.message_utils import send_message_to_user
from messages import get_message, get_button_text

logger = logging.getLogger(__name__)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _get_user_local_time(user: User) -> datetime:
    """Получить локальное время пользователя."""
    user_tz_str = user.timezone if user.timezone else 'UTC'
    try:
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Неизвестный часовой пояс '{user_tz_str}' для пользователя {user.id}. Используется UTC.")
        user_tz = pytz.utc
    return timezone.now().astimezone(user_tz)

# ==================== ОСНОВНЫЕ ЗАДАЧИ CELERY ====================

@shared_task(bind=True)
def schedule_daily_analyses(self):
    """
    Центральная задача планировщика.
    Проверяет пользователей и ставит в очередь задачи анализа.
    """
    logger.debug("--- НАЧАЛО: Задача планировщика schedule_daily_analyses ---")
    try:
        utc_now = timezone.now()
        logger.debug(f"Текущее UTC время: {utc_now}")
        users_qs = User.objects.filter(
            auto_analysis_enabled=True,
            is_blocked=False
        )
        logger.debug(f"Найдено пользователей с auto_analysis_enabled=True: {users_qs.count()}")
        for user in users_qs:
            try:
                logger.debug(f"Обработка пользователя {user.telegram_id} ({user.username})")
                user_local_time = _get_user_local_time(user)
                yesterday_date_user_tz = (user_local_time - timedelta(days=1)).date()
                logger.debug(f"  Локальное время пользователя: {user_local_time}")
                logger.debug(f"  Вчерашняя дата по часовому поясу пользователя: {yesterday_date_user_tz}")
                today_user_tz = user_local_time.date()
                analysis_time_for_today_user_tz_naive = datetime.combine(today_user_tz, time(0, 1))
                user_tz_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = pytz.timezone(user_tz_str)
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Неизвестный часовой пояс '{user_tz_str}' для пользователя {user.id}. Используется UTC.")
                    user_tz = pytz.utc
                analysis_time_for_today_user_tz = user_tz.localize(analysis_time_for_today_user_tz_naive)
                analysis_time_for_today_utc = analysis_time_for_today_user_tz.astimezone(pytz.utc)
                is_time_to_analyze = utc_now >= analysis_time_for_today_utc
                if not is_time_to_analyze:
                    logger.debug(f"  Момент анализа (00:30 пользовательского времени) для дня {yesterday_date_user_tz} еще не наступил для пользователя {user.telegram_id}. Пропуск.")
                    continue
                logger.debug(f"  Момент анализа (00:30 пользовательского времени) для дня {yesterday_date_user_tz} наступил для пользователя {user.telegram_id}. Проверка записей...")
                entries_yesterday = async_to_sync(diary_service.get_user_entries_for_date)(user, yesterday_date_user_tz)
                if not entries_yesterday:
                    try:
                        logger.debug(f"  -> Генерация подсказки для пользователя {user.telegram_id} (записей нет)")
                        prompt_target_date = yesterday_date_user_tz + timedelta(days=1)
                        async def _call_generate_prompt():
                            await _generate_prompt_for_user_no_entries(user, prompt_target_date, user.language)
                        async_to_sync(_call_generate_prompt)()
                        logger.debug(f"  -> Подсказка для пользователя {user.telegram_id} на {prompt_target_date} сгенерирована (записей нет)")
                    except Exception as prompt_error:
                        logger.error(f"  -> Ошибка генерации подсказки для пользователя {user.telegram_id} (записей нет): {prompt_error}", exc_info=True)
                    logger.debug(f"  Записей за {yesterday_date_user_tz} не найдено для пользователя {user.telegram_id}. Пропуск.")
                    continue
                logger.debug(f"  Найдено {len(entries_yesterday)} записей за {yesterday_date_user_tz} для пользователя {user.telegram_id}.")
                combined_entry = async_to_sync(diary_service.get_daily_state)(user, yesterday_date_user_tz)
                if not combined_entry:
                    logger.debug(f"  CombinedDiaryEntry за {yesterday_date_user_tz} не найден для пользователя {user.telegram_id}. Он будет создан при анализе.")
                needs_analysis = False
                if combined_entry:
                    if not combined_entry.is_analyzed:
                        logger.debug(f"  CombinedDiaryEntry {combined_entry.id} не анализирован. Требуется анализ.")
                        needs_analysis = True
                    else:
                        try:
                            daily_analysis = DailyAnalysis.objects.get(combined_entry=combined_entry)
                            analysis_created_at = daily_analysis.created_at
                        except DailyAnalysis.DoesNotExist:
                            logger.debug(f"  DailyAnalysis для CDE {combined_entry.id} не найден, но CDE.is_analyzed=True. Считаем, что анализ нужен.")
                            needs_analysis = True
                        if 'analysis_created_at' in locals() and analysis_created_at:
                            latest_entry_updated_at = max(entry.updated_at for entry in entries_yesterday)

                            if latest_entry_updated_at and latest_entry_updated_at > analysis_created_at:
                                logger.debug(f"  Найдены обновления записей после последнего анализа "
                                             f"(latest_entry_updated_at={latest_entry_updated_at} > analysis_created_at={analysis_created_at}). "
                                             f"Требуется повторный анализ.")
                                needs_analysis = True
                            else:
                                logger.debug(f"  Записи не обновлялись после последнего анализа. Повторный анализ не требуется.")
                else:
                    if entries_yesterday:
                         logger.debug(f"  CombinedDiaryEntry отсутствует, но есть записи. Требуется анализ.")
                         needs_analysis = True
                if needs_analysis:
                    logger.debug(f"  -> Постановка задачи анализа для пользователя {user.telegram_id} за {yesterday_date_user_tz}")
                    perform_scheduled_daily_analysis.delay(user.id, yesterday_date_user_tz.isoformat())
                else:
                    logger.debug(f"  Анализ для пользователя {user.telegram_id} за {yesterday_date_user_tz} не требуется.")
            except Exception as user_error:
                logger.error(f"Ошибка при обработке пользователя {user.id}: {user_error}", exc_info=True)
    except Exception as e:
        logger.error(f"Критическая ошибка в schedule_daily_analyses: {e}", exc_info=True)
    finally:
        logger.debug("--- ЗАВЕРШЕНИЕ: Задача планировщика schedule_daily_analyses ---")

@shared_task(bind=True)
def perform_scheduled_daily_analysis(self, user_id: int, target_date_iso: str):
    """
    Индивидуальная задача анализа дня.
    """
    logger.debug(f"--- НАЧАЛО: Индивидуальная задача анализа для пользователя {user_id}, дата {target_date_iso} ---")
    from asgiref.sync import async_to_sync
    try:
        target_date = date.fromisoformat(target_date_iso)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"Пользователь с ID {user_id} не найден для анализа {target_date_iso}")
            return
        cost = 1
        if not user.is_premium:
            current_balance = user.token_balance
            if current_balance < cost:
                logger.info(f"Недостаточно токенов для автоматического анализа дня у пользователя {user_id}. Баланс: {current_balance}, Стоимость: {cost}")
                if user.notifications_enabled:
                    from bot.main import bot as global_bot
                    if global_bot:
                        from messages import get_message
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        from aiogram.enums import ParseMode
                        language = user.language or 'ru'
                        message_text = get_message('insufficient_tokens_for_auto_analysis_and_disabled', language)
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=get_message('btn_main_menu', language),
                                    callback_data="main_menu"
                                ),
                                InlineKeyboardButton(
                                    text=get_message('btn_recharge_tokens', language),
                                    callback_data="recharge_tokens"
                                )
                            ]
                        ])
                        try:
                            asyncio.run(
                                global_bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=message_text,
                                    reply_markup=keyboard,
                                    parse_mode=ParseMode.HTML
                                )
                            )
                        except Exception as msg_error:
                            logger.error(f"Не удалось отправить сообщение о недостатке токенов пользователю {user_id}: {msg_error}")
                if user.auto_analysis_enabled:
                    user.auto_analysis_enabled = False
                    sync_to_async(user.save)(update_fields=['auto_analysis_enabled'])
                    logger.info(f"Автоматический анализ для пользователя {user_id} отключен из-за недостатка токенов.")
                return
            TokenTransaction.create_and_update_balance(
                user=user,
                amount=-cost,
                transaction_type='analysis',
                description=f"Автоматический полный анализ дня за {target_date_iso}"
            )
            logger.debug(f"Списание {cost} токенов через create_and_update_balance для пользователя {user_id} за автоматический анализ дня {target_date_iso}.")
        logger.debug(f"  Вызов full_day_analysis_service.perform_full_day_analysis для пользователя {user_id}...")
        try:
            analysis_result_dict = async_to_sync(full_day_analysis_service.perform_full_day_analysis)(user, target_date)
            success = analysis_result_dict.get("success", False)
            message = analysis_result_dict.get("message", "Неизвестный результат")
            error = analysis_result_dict.get("error")
            if success:
                logger.debug(f"  ✅ Анализ дня {target_date} для пользователя {user_id} успешно завершен. {message}")
            else:
                logger.error(f"  ❌ Ошибка анализа дня {target_date} для пользователя {user_id}: {message}. Ошибка: {error}")
        except Exception as service_call_error:
            logger.error(f"  ❌ Критическая ошибка вызова сервиса анализа для пользователя {user_id}: {service_call_error}", exc_info=True)
    except Exception as e:
        logger.error(f"Критическая ошибка в perform_scheduled_daily_analysis для пользователя {user_id}, дата {target_date_iso}: {e}", exc_info=True)
    finally:
        logger.debug(f"--- ЗАВЕРШЕНИЕ: Индивидуальная задача анализа для пользователя {user_id}, дата {target_date_iso} ---")


@sync_to_async
def get_users_with_utc_timezone():
    """Получение пользователей с UTC часовым поясом"""
    close_old_connections()
    return list(User.objects.filter(
        timezone='UTC',
        notifications_enabled=True,
        is_active=True,
        is_blocked=False
    ))

@sync_to_async
def get_user_language(user):
    """Получение языка пользователя"""
    close_old_connections()
    return user.language or 'ru'

@shared_task
def send_timezone_reminder():
    """
    Отправка напоминания о смене часового пояса пользователям с UTC.
    """
    return asyncio.run(_send_timezone_reminder_async())

async def _send_timezone_reminder_async():
    """
    Асинхронная корутина для отправки напоминаний.
    """
    bot = None
    try:
        users = await get_users_with_utc_timezone()
        logger.debug(f"Найдено {len(users)} пользователей с UTC часовым поясом (не заблокировали бота)")
        success_count = 0
        error_count = 0
        bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        for user in users:
            try:
                language = await get_user_language(user)
                try:
                    message_text = get_message('timezone_reminder', language)
                except Exception as msg_error:
                    logger.warning(f"Не удалось получить сообщение 'timezone_reminder' для пользователя {user.telegram_id}, язык {language}: {msg_error}")
                    message_text = (
                        "🌍 <b>Не забудьте установить свой часовой пояс!</b>\n\n"
                        "Вы все еще используете часовой пояс по умолчанию (UTC). "
                        "Для более точной работы бота рекомендуем установить ваш местный часовой пояс "
                        "в настройках."
                    ) if language == 'ru' else (
                        "🌍 <b>Don't forget to set your timezone!</b>\n\n"
                        "You are still using the default timezone (UTC). "
                        "For more accurate bot operation, we recommend setting your local timezone "
                        "in the settings."
                    )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=get_button_text('btn_settings', language),
                            callback_data="settings"
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
                    success_count += 1
                    logger.debug(f"Напоминание успешно отправлено пользователю {user.telegram_id}")
                else:
                    error_count += 1
                    logger.warning(f"Не удалось отправить напоминание пользователю {user.telegram_id}") 
            except Exception as e:
                logger.error(f"Ошибка при обработке пользователя {user.telegram_id}: {e}", exc_info=True)
                error_count += 1
        logger.info(f"Напоминания отправлены: успешно {success_count}, ошибок {error_count}")
        return f"Успешно: {success_count}, Ошибок: {error_count}"
    except Exception as e:
        logger.error(f"Ошибка в задаче отправки напоминаний о часовом поясе: {e}", exc_info=True)
        return f"Ошибка: {e}"
    finally:
        if bot:
            try:
                await bot.session.close()
                logger.debug("Сессия бота закрыта")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота: {close_error}")

async def _generate_prompt_for_user_no_entries(user: User, target_date: date, language: str):
    """
    Генерирует подсказку для пользователя на заданную дату в сценарии "нет записей".
    Использует smart_prompt_manager для вызова API и сохранения результата.
    """
    logger.debug(f"[_generate_prompt_for_user_no_entries] Начало генерации подсказки для {user.telegram_id} на {target_date} (нет записей)")
    try:
        days_since_last_entry = await smart_prompt_manager._get_days_since_last_entry(user)
        logger.debug(f"[_generate_prompt_for_user_no_entries] Days since last entry: {days_since_last_entry}")
        analysis_context = "Записей за предыдущий день не найдено. Это может быть хорошей возможностью для рефлексии или начала нового дня."
        user_profile = await user.aget_profile_data()
        first_name = user_profile.get('first_name', 'Пользователь')
        awareness_level = user_profile.get('awareness_level', 1)
        logger.debug(f"[_generate_prompt_for_user_no_entries] User profile: first_name={first_name}, awareness_level={awareness_level}")
        prompt_text = await smart_prompt_manager._call_ai_prompt_generation(
            user=user,
            analysis_context=analysis_context,
            days_since_last=days_since_last_entry,
            language=language
        )
        logger.debug(f"[_generate_prompt_for_user_no_entries] AI prompt generated: {prompt_text is not None}")
        prompt_target_date = target_date + timedelta(days=1)
        if prompt_text:
            logger.debug(f"[_generate_prompt_for_user_no_entries] AI сгенерировал подсказку для {user.telegram_id}")
            await smart_prompt_manager._save_prompt(user, prompt_target_date, prompt_text, force_overwrite=True)
        else:
            logger.warning(f"[_generate_prompt_for_user_no_entries] AI не вернул подсказку для {user.telegram_id}, используем fallback")
            await smart_prompt_manager._prepare_first_prompt_tomorrow(user, language)
        logger.debug(f"[_generate_prompt_for_user_no_entries] Подсказка для {user.telegram_id} на {prompt_target_date} успешно обработана")
    except Exception as e:
        logger.error(f"[_generate_prompt_for_user_no_entries] Ошибка генерации подсказки для {user.telegram_id}: {e}", exc_info=True)
        try:
            await smart_prompt_manager._prepare_first_prompt_tomorrow(user, language)
            logger.debug(f"[_generate_prompt_for_user_no_entries] Fallback подсказка создана для {user.telegram_id}")
        except Exception as fallback_error:
            logger.error(f"[_generate_prompt_for_user_no_entries] Ошибка создания fallback подсказки для {user.telegram_id}: {fallback_error}")
