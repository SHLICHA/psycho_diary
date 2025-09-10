"""
Celery задачи для периодического анализа дней.
"""
import logging
from datetime import datetime, date, time, timedelta
import pytz
from celery import shared_task
from django.utils import timezone
from django.db.models import Max
from asgiref.sync import async_to_sync
from users.models import User
from diary.models import CombinedDiaryEntry, DailyAnalysis, DiaryEntry

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

def _is_analysis_time_reached(user: User, target_date: date) -> bool:
    """
    Проверить, наступил ли момент `preferred_analysis_time` для указанной даты у пользователя.
    Логика: анализ дня `target_date` должен быть выполнен ПОСЛЕ наступления
    `preferred_analysis_time` в дату `target_date + 1` по пользовательскому времени.
    """
    user_tz_str = user.timezone if user.timezone else 'UTC'
    try:
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Неизвестный часовой пояс '{user_tz_str}' для пользователя {user.id}. Используется UTC.")
        user_tz = pytz.utc

    preferred_analysis_time = user.preferred_analysis_time or time(2, 0) # Дефолт 02:00

    try:
        # --- ИСПРАВЛЕНИЕ ЛОГИКИ ---
        # Момент анализа для дня `target_date` наступает в
        # `preferred_analysis_time` в дате `target_date + 1` по пользовательскому времени.
        # Это момент, когда "день target_date закончился достаточно, чтобы запустить анализ".
        analysis_trigger_date_user_tz = target_date + timedelta(days=1)
        analysis_trigger_moment_user_tz_naive = datetime.combine(
            analysis_trigger_date_user_tz, 
            preferred_analysis_time
        )
        analysis_trigger_moment_user_tz = user_tz.localize(analysis_trigger_moment_user_tz_naive)
        analysis_trigger_moment_utc = analysis_trigger_moment_user_tz.astimezone(pytz.utc)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        
        now_utc = timezone.now()
        # Если СЕЙЧАС (UTC) >= МОМЕНТ_АНАЛИЗА (UTC), то время анализа наступило
        return now_utc >= analysis_trigger_moment_utc
    except Exception as e:
        logger.error(f"Ошибка при вычислении момента анализа для пользователя {user.id}, дата {target_date}: {e}")
        return False # В случае ошибки считаем, что время не наступило

# ==================== ОСНОВНЫЕ ЗАДАЧИ CELERY ====================

@shared_task(bind=True)
def schedule_daily_analyses(self):
    """
    Центральная задача планировщика.
    Проверяет пользователей и ставит в очередь задачи анализа.
    """
    # Ленивый импорт для избежания циклических импортов
    from bot.services.diary_service import diary_service 
    
    logger.info("--- НАЧАЛО: Задача планировщика schedule_daily_analyses ---")
    try:
        utc_now = timezone.now()
        logger.debug(f"Текущее UTC время: {utc_now}")

        users_qs = User.objects.filter(auto_analysis_enabled=True)
        logger.info(f"Найдено пользователей с auto_analysis_enabled=True: {users_qs.count()}")

        for user in users_qs:
            try:
                logger.debug(f"Обработка пользователя {user.telegram_id} ({user.username})")

                user_local_time = _get_user_local_time(user)
                yesterday_date_user_tz = (user_local_time - timedelta(days=1)).date()
                logger.debug(f"  Локальное время пользователя: {user_local_time}")
                logger.debug(f"  Вчерашняя дата по часовому поясу пользователя: {yesterday_date_user_tz}")

                if not _is_analysis_time_reached(user, yesterday_date_user_tz):
                    logger.debug(f"  Момент анализа для {yesterday_date_user_tz} еще не наступил для пользователя {user.telegram_id}. Пропуск.")
                    continue

                logger.debug(f"  Момент анализа для {yesterday_date_user_tz} наступил для пользователя {user.telegram_id}. Проверка записей...")

                # 4. Проверить, были ли записи вчера
                # diary_service.get_user_entries_for_date уже учитывает часовой пояс
                entries_yesterday = async_to_sync(diary_service.get_user_entries_for_date)(user, yesterday_date_user_tz)
                if not entries_yesterday:
                    logger.debug(f"  Записей за {yesterday_date_user_tz} не найдено для пользователя {user.telegram_id}. Пропуск.")
                    continue

                logger.debug(f"  Найдено {len(entries_yesterday)} записей за {yesterday_date_user_tz} для пользователя {user.telegram_id}.")

                # 5. Проверить/получить CombinedDiaryEntry
                # diary_service.get_daily_state уже учитывает часовой пояс
                combined_entry = async_to_sync(diary_service.get_daily_state)(user, yesterday_date_user_tz)
                if not combined_entry:
                    logger.debug(f"  CombinedDiaryEntry за {yesterday_date_user_tz} не найден для пользователя {user.telegram_id}. Он будет создан при анализе.")
                    # combined_entry будет создан сервисом анализа

                # 6. Проверить необходимость анализа (новые записи или не анализирован)
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
                            # Проверка актуальности: были ли записи обновлены после анализа?
                            # diary_service.get_user_entries_for_date уже дал нам нужные записи
                            latest_entry_updated_at = max(entry.updated_at for entry in entries_yesterday)

                            if latest_entry_updated_at and latest_entry_updated_at > analysis_created_at:
                                logger.debug(f"  Найдены обновления записей после последнего анализа "
                                             f"(latest_entry_updated_at={latest_entry_updated_at} > analysis_created_at={analysis_created_at}). "
                                             f"Требуется повторный анализ.")
                                needs_analysis = True
                            else:
                                logger.debug(f"  Записи не обновлялись после последнего анализа. Повторный анализ не требуется.")
                else:
                    # Если CDE не существует, но есть записи, значит, анализ нужен
                    if entries_yesterday:
                         logger.debug(f"  CombinedDiaryEntry отсутствует, но есть записи. Требуется анализ.")
                         needs_analysis = True

                if needs_analysis:
                    logger.info(f"  -> Постановка задачи анализа для пользователя {user.telegram_id} за {yesterday_date_user_tz}")
                    perform_scheduled_daily_analysis.delay(user.id, yesterday_date_user_tz.isoformat())
                else:
                    logger.debug(f"  Анализ для пользователя {user.telegram_id} за {yesterday_date_user_tz} не требуется.")

            except Exception as user_error:
                logger.error(f"Ошибка при обработке пользователя {user.id}: {user_error}", exc_info=True)

    except Exception as e:
        logger.error(f"Критическая ошибка в schedule_daily_analyses: {e}", exc_info=True)
    finally:
        logger.info("--- ЗАВЕРШЕНИЕ: Задача планировщика schedule_daily_analyses ---")


@shared_task(bind=True)
def perform_scheduled_daily_analysis(self, user_id: int, target_date_iso: str):
    """
    Индивидуальная задача анализа дня.
    """
    # Ленивый импорт для избежания циклических импортов
    from diary.services.full_day_analysis_service import full_day_analysis_service
    
    logger.info(f"--- НАЧАЛО: Индивидуальная задача анализа для пользователя {user_id}, дата {target_date_iso} ---")
    try:
        target_date = date.fromisoformat(target_date_iso)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"Пользователь с ID {user_id} не найден для анализа {target_date_iso}")
            return

        logger.debug(f"  Вызов full_day_analysis_service.perform_full_day_analysis для пользователя {user_id}...")
        
        # --- РЕАЛИЗАЦИЯ: Корректный вызов асинхронного сервиса ---
        # Используем async_to_sync для вызова асинхронного метода из синхронной задачи Celery.
        try:
            analysis_result_dict = async_to_sync(full_day_analysis_service.perform_full_day_analysis)(user, target_date)
            
            success = analysis_result_dict.get("success", False)
            message = analysis_result_dict.get("message", "Неизвестный результат")
            error = analysis_result_dict.get("error")

            if success:
                logger.info(f"  ✅ Анализ дня {target_date} для пользователя {user_id} успешно завершен. {message}")
            else:
                logger.error(f"  ❌ Ошибка анализа дня {target_date} для пользователя {user_id}: {message}. Ошибка: {error}")

        except Exception as service_call_error:
            logger.error(f"  ❌ Критическая ошибка вызова сервиса анализа для пользователя {user_id}: {service_call_error}", exc_info=True)

    except Exception as e:
        logger.error(f"Критическая ошибка в perform_scheduled_daily_analysis для пользователя {user_id}, дата {target_date_iso}: {e}", exc_info=True)
    finally:
        logger.info(f"--- ЗАВЕРШЕНИЕ: Индивидуальная задача анализа для пользователя {user_id}, дата {target_date_iso} ---")
