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
from django.db import close_old_connections

from bot.utils.message_utils import send_message_to_user
from users.models import User, UserProfileHistory
from diary.models import CombinedDiaryEntry, DailyAnalysis
from messages import get_message, get_button_text
from core.settings import TELEGRAM_BOT_TOKEN
from bot.services.deepseek_api import deepseek_api_service
from bot.utils.diary_utils import get_recoverable_gap_info
from prompts.get_prompt import get_prompt

logger = logging.getLogger(__name__)

async def aget_users_for_morning_motivation():
    """
    Асинхронное получение активных пользователей с включенными уведомлениями, не заблокированных.
    Предзагружает необходимые поля для эффективности и избегания lazy loading в асинхронной функции.
    """
    await sync_to_async(close_old_connections)()
    @sync_to_async
    def _get_users_sync():
        return list(User.objects.filter(
            notifications_enabled=True,
            is_blocked=False,
            deletion_status='active',
            deleted_at__isnull=True
        ).only(
            'telegram_id', 'timezone', 'language', 'date_of_birth', 'token_balance', 'auto_analysis_enabled',
            'first_name', 'username', 'awareness_level', 'is_blocked', 'deletion_status', 'deleted_at'
        ))
    return await _get_users_sync()

@shared_task
def send_morning_motivation_task():
    """
    Отправка ежедневных утренних мотивационных сообщений.
    Запускается раз в час Celery Beat.
    """
    return asyncio.run(_send_morning_motivation_async())

async def _send_morning_motivation_async():
    # ... (начало как было)
    bot_instance = None
    try:
        users = await aget_users_for_morning_motivation()
        # Не логируем количество пользователей, если ничего не отправлено

        success_count = 0
        error_count = 0
        sent_motivation_count = 0
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
                if current_user_hour == 10:
                    # Только если наступил 10:00 — начинаем обработку
                    try:
                        user_language = user.language or 'ru'
                        await sync_to_async(close_old_connections)()

                        # --- НОВАЯ ЛОГИКА: Проверка дня недели и обновления профиля ---
                        profile_update_info = {}
                        is_monday = user_local_time.weekday() == 0  # 0 = Monday
                        profile_button_text = None
                        profile_button_callback = None

                        if is_monday:
                            logger.debug(f"[MOTIVATION] Пользователь {user.telegram_id} - Понедельник. Проверяем обновление профиля.")
                            # Получаем дату начала этой недели (понедельник)
                            current_monday_local = (user_local_time.date() - timedelta(days=user_local_time.date().weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                            logger.debug(f"[MOTIVATION] Понедельник недели для {user.telegram_id}: {current_monday_local}")

                            # Ищем последнюю историю профиля до начала этой недели
                            last_profile_history_before_this_week = await UserProfileHistory.objects.filter(
                                user=user,
                                created_at__lt=current_monday_local # Меньше, чем начало этой недели
                            ).order_by('-created_at').afirst()

                            current_profile_snapshot = {
                                'personality_traits': user.personality_traits,
                                'life_facts': user.life_facts,
                                'hobbies': user.hobbies,
                                'core_values': user.core_values,
                                'triggers': user.triggers,
                                'strengths': user.strengths,
                                'areas_for_growth': user.areas_for_growth,
                                'personality_insights': user.personality_insights,
                                'habits': user.habits,
                                'skills': user.skills,
                                'aspirations': user.aspirations,
                                'personality_description': user.personality_description,
                            }

                            profile_changed = False
                            if last_profile_history_before_this_week:
                                # Сравниваем с последней историей до этой недели
                                last_history_snapshot = {
                                    'personality_traits': last_profile_history_before_this_week.personality_traits,
                                    'life_facts': last_profile_history_before_this_week.life_facts,
                                    'hobbies': last_profile_history_before_this_week.hobbies,
                                    'core_values': last_profile_history_before_this_week.core_values,
                                    'triggers': last_profile_history_before_this_week.triggers,
                                    'strengths': last_profile_history_before_this_week.strengths,
                                    'areas_for_growth': last_profile_history_before_this_week.areas_for_growth,
                                    'personality_insights': last_profile_history_before_this_week.personality_insights,
                                    'habits': last_profile_history_before_this_week.habits,
                                    'skills': last_profile_history_before_this_week.skills,
                                    'aspirations': last_profile_history_before_this_week.aspirations,
                                    'personality_description': last_profile_history_before_this_week.personality_description,
                                }
                                profile_changed = current_profile_snapshot != last_history_snapshot
                                logger.debug(f"[MOTIVATION] Профиль для {user.telegram_id} до этой недели: {last_profile_history_before_this_week.created_at}")
                            else:
                                profile_changed = any(current_profile_snapshot.values())
                                logger.debug(f"[MOTIVATION] Для {user.telegram_id} нет истории профиля до этой недели.")

                            if profile_changed:
                                logger.info(f"[MOTIVATION] Обнаружено изменение профиля для {user.telegram_id} на этой неделе.")
                                profile_update_info = {
                                    'changed': True,
                                    'since': last_profile_history_before_this_week.created_at if last_profile_history_before_this_week else None
                                }
                                profile_button_text = get_button_text('btn_view_profile', user_language)
                                profile_button_callback = "view_psychology_profile"
                            else:
                                logger.debug(f"[MOTIVATION] Профиль для {user.telegram_id} не изменился с прошлой недели.")
                                profile_update_info = {'changed': False}
                        @sync_to_async
                        def get_entries_count():
                            return user.diary_entries.count()
                        entries_count = await get_entries_count()
                        user_profile_data = {
                            'first_name': user.first_name or user.username or f'Пользователь {user.telegram_id}',
                            'awareness_level': user.awareness_level,
                            'date_of_birth': user.date_of_birth,
                            'entries_count': entries_count,
                            'username': user.username,
                            'language': user.language,
                            'telegram_id': user.telegram_id
                        }
                        profile_change_summary_for_ai = ""
                        if profile_update_info.get('changed'):
                             profile_change_summary_for_ai = get_message('morning_motivation_profile_changed_ai_hint', user_language)
                        first_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"
                        target_analysis_date = user_local_time.date() - timedelta(days=1)
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
                                pass  # Не логируем, если нет анализа за вчерашний день
                        except CombinedDiaryEntry.DoesNotExist:
                             pass  # Не логируем, если нет записи за вчерашний день

                        prompt = get_prompt(
                            key='morning_motivation',
                            language=user_language,
                            user_profile=user_profile_data,
                            previous_day_analysis=previous_day_analysis_data,
                            # --- ПЕРЕДАЧА ИНФОРМАЦИИ ОБ ИЗМЕНЕНИИ ПРОФИЛЯ ---
                            profile_changed=profile_update_info.get('changed', False),
                            profile_change_summary=profile_change_summary_for_ai
                            # --- /ПЕРЕДАЧА ИНФОРМАЦИИ ОБ ИЗМЕНЕНИИ ПРОФИЛЯ ---
                        )
                        api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user_language)
                        if api_result.get('success'):
                            motivation_text_base = api_result.get('result', {}).get('motivation_message',
                                get_message('morning_motivation_default', user_language, first_name=first_name))
                        else:
                            motivation_text_base = get_message('morning_motivation_default', user_language, first_name=first_name)
                            logger.warning(f"ИИ не сгенерировал сообщение для {user.telegram_id}. Используется стандартное. Ошибка API: {api_result.get('error')}")

                        # --- ДОБАВЛЕНИЕ ТЕКСТА ОБ ИЗМЕНЕНИИ ПРОФИЛЯ ---
                        profile_update_text = ""
                        if profile_update_info.get('changed'):
                            profile_update_text = get_message('morning_motivation_profile_changed', user_language)
                            # Добавляем отступ
                            if motivation_text_base:
                                profile_update_text = f"\n\n{profile_update_text}"

                        motivation_text_base += profile_update_text
                        # --- /ДОБАВЛЕНИЕ ТЕКСТА ОБ ИЗМЕНЕНИИ ПРОФИЛЯ ---

                        dates_to_restore = await get_recoverable_gap_info(user)
                        restore_available = dates_to_restore is not None

                        restore_text = ""
                        if restore_available and dates_to_restore:
                            # Форматируем даты для сообщения
                            formatted_dates = [dt.strftime("%d.%m") for dt in dates_to_restore]
                            # Используем разные сообщения в зависимости от количества дней
                            if len(formatted_dates) == 1:
                                restore_text = get_message('morning_motivation_restore_single_day', user_language, date=formatted_dates[0])
                            else: # len == 2
                                # Объединяем даты, например, "07.10 и 08.10"
                                dates_str = " и ".join(formatted_dates)
                                restore_text = get_message('morning_motivation_restore_two_days', user_language, dates=dates_str)
                            restore_text = f"\n\n{restore_text}" # Добавляем отступ

                        # --- ПЕРЕНОС ВСЕХ ДОПОЛНЕНИЙ В ОДИН БЛОК ---
                        additional_text = ""
                        additional_button_callback = None
                        additional_button_text_key = None

                        if not user.is_premium and user.token_balance <= 0:
                            additional_text = (
                                get_message('morning_motivation_recharge_preamble', user_language) +
                                get_message('morning_motivation_recharge_text', user_language)
                            )
                            additional_button_callback = "premium_subscribe"
                            additional_button_text_key = 'btn_morning_motivation_recharge'
                        elif not user.auto_analysis_enabled and (user.is_premium or user.token_balance > 0):
                            additional_text = (
                                get_message('morning_motivation_enable_auto_analysis_preamble', user_language) +
                                get_message('morning_motivation_enable_auto_analysis_text', user_language)
                            )
                            additional_button_callback = "settings_toggle_auto_analysis"
                            additional_button_text_key = 'btn_morning_motivation_enable_auto_analysis'

                        # --- ПРОВЕРКА ПРОДЛЕНИЯ ПОДПИСКИ ---
                        is_user_premium_active = await sync_to_async(user.is_premium_active)()
                        renewal_button_callback = None
                        renewal_button_text_key = None
                        expiry_text = ""
                        if is_user_premium_active: # Используем результат асинхронного вызова
                            # Если подписка активна, проверяем, сколько дней осталось до окончания
                            # Переводим время окончания подписки в локальный часовой пояс пользователя
                            # Обратите внимание: premium_expires_at уже должен быть в UTC, мы переводим его в локальный
                            expires_local_dt = user.premium_expires_at.astimezone(user_tz)
                            expires_local_date = expires_local_dt.date()
                            user_local_date = user_local_time.date()

                            days_until_expiry = (expires_local_date - user_local_date).days

                            # Если осталось 3, 2 или 1 день, добавляем напоминание
                            if 1 <= days_until_expiry <= 3:
                                expiry_message_key = f'premium_expires_in_{days_until_expiry}_days'
                                # Используем преамбулу для стилистического выделения
                                expiry_text = (
                                    get_message('morning_motivation_premium_expiry_preamble', user_language) +
                                    get_message(expiry_message_key, user_language)
                                )
                                renewal_button_callback = "settings_premium" # или "purchase_subscription:month"
                                renewal_button_text_key = 'btn_manage_subscription'

                        # Собираем весь дополнительный текст
                        motivation_text = motivation_text_base + expiry_text + restore_text + additional_text
                        # --- /ПЕРЕНОС ВСЕХ ДОПОЛНЕНИЙ В ОДИН БЛОК ---


                        keyboard_buttons = [
                            [
                                InlineKeyboardButton(
                                    text=get_button_text('btn_new_entry', user_language),
                                    callback_data="new_entry"
                                )
                            ]
                        ]
                        # --- ДОБАВЛЕНИЕ КНОПКИ ПРОСМОТРА ПРОФИЛЯ ---
                        if profile_button_callback and profile_button_text:
                            keyboard_buttons.append([
                                InlineKeyboardButton(
                                    text=profile_button_text,
                                    callback_data=profile_button_callback
                                )
                            ])
                        # --- /ДОБАВЛЕНИЕ КНОПКИ ПРОСМОТРА ПРОФИЛЯ ---

                        if renewal_button_callback and renewal_button_text_key:
                            keyboard_buttons.append([
                                InlineKeyboardButton(
                                    text=get_button_text(renewal_button_text_key, user_language),
                                    callback_data=renewal_button_callback
                                )
                            ])
                        if additional_button_callback and additional_button_text_key:
                             keyboard_buttons.append([
                                InlineKeyboardButton(
                                    text=get_button_text(additional_button_text_key, user_language),
                                    callback_data=additional_button_callback
                                )
                             ])
                        keyboard_buttons.append([
                             InlineKeyboardButton(
                                text=get_button_text('btn_main_menu', user_language),
                                callback_data="main_menu"
                            )
                        ])

                        motivation_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                        success = await send_message_to_user(
                            bot=bot_instance,
                            user=user,
                            text=motivation_text,
                            reply_markup=motivation_keyboard
                        )
                        if success:
                            sent_motivation_count += 1
                            success_count += 1
                        else:
                            error_count += 1
                    except Exception as processing_error:
                        logger.error(f"Ошибка при генерации или подготовке утреннего сообщения для пользователя {user.telegram_id}: {processing_error}", exc_info=True)
                        error_count += 1
            except TelegramForbiddenError:
                logger.debug(f"Бот заблокирован пользователем {user.telegram_id} (обнаружено на уровне задачи).")
                user.is_blocked = True
                await sync_to_async(close_old_connections)()
                await sync_to_async(user.save)(update_fields=['is_blocked'])
                error_count += 1
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке пользователя {user.telegram_id} для утреннего сообщения: {e}", exc_info=True)
                error_count += 1
        # Логируем только если были отправки или ошибки
        if sent_motivation_count > 0 or error_count > 0:
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
        if bot_instance:
            try:
                await bot_instance.session.close()
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота утренних сообщений: {close_error}")