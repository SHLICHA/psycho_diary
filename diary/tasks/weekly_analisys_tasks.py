"""
Celery задачи для diary приложения.
"""

import logging
from datetime import datetime, time
import pytz

from celery import shared_task
from asgiref.sync import async_to_sync

from users.models import User
from diary.services.profile_cleanup_service import profile_cleanup_service
from diary.services.weekly_analysis_service import weekly_analysis_service
from diary.services.user_profile_analysis_service import user_profile_analysis_service
from diary.services.user_profile_change_analysis_service import perform_profile_change_analysis
from diary.tasks.ai_activity_filter import is_user_active_for_ai_tasks

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def perform_weekly_analysis_for_user_task(self, user_id: int) -> dict:
    """
    Celery задача для выполнения еженедельного анализа и последующего анализа профиля для одного пользователя.
    """
    
    logger.debug(
        f"[Celery Task] Запуск еженедельного анализа, анализа профиля, cleanup и анализа изменений профиля для пользователя ID {user_id}"
    )
    try:
        user = User.objects.get(id=user_id)
        if user.is_blocked:
            logger.debug(f"[Celery Task] Пользователь {user_id} заблокирован. Пропуск анализа.")
            return {'status': 'skipped', 'reason': 'user_blocked', 'user_id': user_id}

        if not is_user_active_for_ai_tasks(user):
            logger.info(f"[Celery Task] Пропуск еженедельного ИИ-анализа для пользователя {user_id}: нет активности за последние 30 дней")
            return {'status': 'skipped', 'reason': 'inactive_for_30_days', 'user_id': user_id}

        logger.debug(f"[Celery Task] -> Выполнение еженедельного анализа для пользователя {user_id}...")
        perform_weekly_sync = async_to_sync(weekly_analysis_service.perform_weekly_analysis)
        weekly_result = perform_weekly_sync(user)
        
        weekly_analysis_obj = weekly_result.get('weekly_analysis')
        weekly_analysis_success = weekly_result.get('success', False) # Явно получаем успех недельного

        if not weekly_analysis_success:
            # Если недельный анализ не удался, останавливаем выполнение последующих шагов
            logger.warning(f"[Celery Task] -> Ошибка в еженедельном анализе для пользователя {user_id}: {weekly_result.get('message', 'Unknown error')}. Пропуск анализа профиля и изменений.")
            return {
                'status': 'failed_weekly_analysis', # Новый статус
                'weekly_result': weekly_result,
                'profile_result': None,
                'profile_change_result': None,
                'cleanup_result': None,
                'user_id': user_id
            }
        
        # Если weekly_analysis_success == True, weekly_analysis_obj должен существовать
        if not weekly_analysis_obj:
             # Это всё ещё может произойти в редких случаях, добавим проверку
             logger.error(f"[Celery Task] weekly_result.success=True, но WeeklyAnalysis не возвращён для пользователя {user_id}.")
             return {
                'status': 'failed', 
                'reason': 'weekly_analysis_object_missing_after_success', 
                'weekly_result': weekly_result,
                'user_id': user_id
            }

        logger.debug(f"[Celery Task] -> Еженедельный анализ для пользователя {user_id} успешен. Объект: {weekly_analysis_obj.id if weekly_analysis_obj else 'None'}")

        # Теперь, если недельный анализ успешен, запускаем анализ профиля
        logger.debug(f"[Celery Task] -> Выполнение анализа профиля пользователя {user_id}...")
        perform_profile_sync = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)
        profile_result = perform_profile_sync(user)
        
        if profile_result['success']:
            logger.debug(f"[Celery Task] -> Анализ профиля пользователя {user_id} успешен.")
        else:
            logger.error(f"[Celery Task] -> Ошибка в анализе профиля для пользователя {user_id}: {profile_result.get('message', 'Unknown error')}")
            # Важно: даже если анализ профиля не удался, мы всё равно можем попробовать анализ изменений,
            # так как он использует текущий (потенциально частично обновлённый) профиль и историю.
            # Поэтому не возвращаем ошибку здесь, а идём дальше.

        logger.debug(f"[Celery Task] -> Выполнение cleanup профиля пользователя {user_id}...")
        perform_cleanup_sync = async_to_sync(profile_cleanup_service.cleanup_user_profile)
        cleanup_result = perform_cleanup_sync(user)

        if cleanup_result['success']:
            logger.info(
                f"[Celery Task] -> Cleanup профиля пользователя {user_id} завершён: "
                f"changed={cleanup_result.get('changed')}, "
                f"changed_fields={cleanup_result.get('changed_fields', [])}, "
                f"removed_items={cleanup_result.get('removed_items', 0)}, "
                f"stale_items={cleanup_result.get('stale_items', 0)}, "
                f"compressed_action={cleanup_result.get('compressed_profile_action', 'skipped')}"
            )
        else:
            logger.error(
                f"[Celery Task] -> Ошибка cleanup профиля для пользователя {user_id}: "
                f"{cleanup_result.get('error', 'Unknown error')}"
            )

        # Теперь запускаем анализ изменений, используя успешно созданный weekly_analysis_obj
        logger.debug(f"[Celery Task] -> Выполнение анализа изменений профиля пользователя {user_id}...")
        # Вызываем новый сервис
        perform_profile_change_sync = async_to_sync(perform_profile_change_analysis)
        profile_change_result = perform_profile_change_sync(user, weekly_analysis_obj, num_snapshots_to_compare=3)

        if profile_change_result['success']:
            logger.debug(f"[Celery Task] -> Анализ изменений профиля для пользователя {user_id} успешен.")
        else:
            logger.error(f"[Celery Task] -> Ошибка в анализе изменений профиля для пользователя {user_id}: {profile_change_result.get('message', 'Unknown error')}")
            # Возвращаем статус с ошибкой в анализе изменений, но успехом в основных анализах
            return {
                'status': 'completed_with_change_error', 
                'weekly_result': weekly_result, 
                'profile_result': profile_result,
                'cleanup_result': cleanup_result,
                'profile_change_error': profile_change_result.get('error'), 
                'profile_change_message': profile_change_result.get('message'),
                'user_id': user_id
            }

        logger.debug(f"[Celery Task] Полный цикл анализа (недельный, профиль, изменения) для пользователя {user_id} успешно завершён.")
        return {
            'status': 'completed', 
            'weekly_result': weekly_result, 
            'profile_result': profile_result,
            'cleanup_result': cleanup_result,
            'profile_change_result': profile_change_result,
            'user_id': user_id
        }
    except User.DoesNotExist:
        logger.error(f"[Celery Task] Пользователь с ID {user_id} не найден.")
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}
    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка при выполнении анализа для пользователя {user_id}: {e}", exc_info=True)
        try:
            self.retry(countdown=60 * 5) # Повтор через 5 минут
        except self.MaxRetriesExceededError:
            logger.error(f"[Celery Task] Максимум повторов превышен для пользователя {user_id}")
            return {
                'status': 'failed', 
                'reason': 'max_retries_exceeded', 
                'error': str(e), 
                'user_id': user_id
            }

@shared_task(bind=True)
def schedule_weekly_analyses_task(self) -> dict:
    """
    Celery задача, запускаемая ежечасно, для планирования еженедельных анализов.
    Проверяет, является ли текущее время понедельником 03:00 по часовому поясу пользователя.
    """
    logger.debug("[Celery Task] Запуск планировщика еженедельных анализов")
    try:
        users = User.objects.filter(is_blocked=False)
        logger.debug(f"[Celery Task] Найдено {users.count()} активных пользователей для проверки.")
        tasks_scheduled = 0
        for user in users:
            try:
                user_tz_str = user.timezone if user.timezone else 'UTC'
                user_tz = pytz.timezone(user_tz_str)
                utc_now = datetime.utcnow()
                user_local_datetime = utc_now.replace(tzinfo=pytz.utc).astimezone(user_tz)
                user_local_time = user_local_datetime.time()
                user_local_weekday = user_local_datetime.weekday()
                is_monday = user_local_weekday == 0
                is_correct_time = time(2, 50) <= user_local_time <= time(3, 10)
                if is_monday and is_correct_time:
                    logger.debug(f"[Celery Task] Пора запускать еженедельный анализ для пользователя {user.telegram_id} (понедельник {user_local_time}, часовой пояс: {user_tz_str})")
                    perform_weekly_analysis_for_user_task.delay(user.id)
                    tasks_scheduled += 1  
            except Exception as user_error:
                logger.error(f"[Celery Task] Ошибка при обработке пользователя {user.telegram_id}: {user_error}")
        logger.debug(f"[Celery Task] Планировщик завершен. Запланировано {tasks_scheduled} задач.")
        return {'status': 'completed', 'tasks_scheduled': tasks_scheduled}
    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка в планировщике: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}
