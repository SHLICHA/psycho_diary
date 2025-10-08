"""
Celery задачи для diary приложения.
"""

import logging
from datetime import datetime, time
import pytz

from celery import shared_task
from asgiref.sync import async_to_sync

from users.models import User
from diary.services.weekly_analysis_service import weekly_analysis_service
from diary.services.user_profile_analysis_service import user_profile_analysis_service
from diary.services.user_profile_change_analysis_service import perform_profile_change_analysis

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def perform_weekly_analysis_for_user_task(self, user_id: int) -> dict:
    """
    Celery задача для выполнения еженедельного анализа и последующего анализа профиля для одного пользователя.
    """
    
    logger.debug(f"[Celery Task] Запуск еженедельного анализа, анализа профиля и анализа изменений профиля для пользователя ID {user_id}")
    try:
        user = User.objects.get(id=user_id)
        if user.is_blocked:
            logger.debug(f"[Celery Task] Пользователь {user_id} заблокирован. Пропуск анализа.")
            return {'status': 'skipped', 'reason': 'user_blocked', 'user_id': user_id}
        logger.debug(f"[Celery Task] -> Выполнение еженедельного анализа для пользователя {user_id}...")
        perform_weekly_sync = async_to_sync(weekly_analysis_service.perform_weekly_analysis)
        weekly_result = perform_weekly_sync(user)
        
        weekly_analysis_obj = weekly_result.get('weekly_analysis')
        if not weekly_analysis_obj:
            # Если WeeklyAnalysis не был создан (например, уже существовал и был возвращён),
            # нужно его получить отдельно для передачи в следующие шаги.
            # Логика получения week_start_date должна быть аналогична weekly_analysis_service
            from datetime import datetime, timedelta
            import pytz
            user_tz_str = user.timezone or 'UTC'
            try:
                user_tz = pytz.timezone(user_tz_str)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.UTC
                logger.warning(f"Неверный часовой пояс для пользователя {user.id}: {user_tz_str}. Используем UTC.")
            today_user_tz = datetime.now(user_tz).date()
            last_sunday = today_user_tz - timedelta(days=today_user_tz.weekday() + 1)
            week_start_date = last_sunday - timedelta(days=6)
            from diary.models import WeeklyAnalysis
            weekly_analysis_obj = WeeklyAnalysis.objects.filter(user=user, week_start_date=week_start_date).first()
            # Если и сейчас не нашли (хотя weekly_result.success == True), значит что-то не так
            if not weekly_analysis_obj:
                 logger.error(f"[Celery Task] Не удалось получить объект WeeklyAnalysis после выполнения weekly_analysis_service для пользователя {user_id}.")
                 return {
                    'status': 'failed', 
                    'reason': 'weekly_analysis_object_not_found', 
                    'weekly_result': weekly_result,
                    'user_id': user_id
                }


        if weekly_result['success']:
            logger.debug(f"[Celery Task] -> Еженедельный анализ для пользователя {user_id} успешен.")
            if weekly_analysis_obj:
                logger.debug(f"[Celery Task] -> Используется WeeklyAnalysis ID: {weekly_analysis_obj.id}")
        else:
            logger.warning(f"[Celery Task] -> Ошибка в еженедельном анализе для пользователя {user_id}: {weekly_result.get('message', 'Unknown error')}")
            # Возвращаем результат, даже если weekly не удался, т.к. profile_change_analysis может быть полезен
            # Но обычно, если weekly не удался, дальше не идём.
            # ВОЗМОЖНО, стоит остановить выполнение, если weekly_result['success'] == False
            # Пока оставим как есть, но можно пересмотреть.
            # Пока что предположим, что weekly_result['success'] == True, иначе weekly_analysis_obj не был бы получен.
            # Но на всякий случай проверим.
            if not weekly_analysis_obj:
                 logger.error(f"[Celery Task] WeeklyAnalysis не создан или не найден, не могу продолжить. Пользователь {user_id}")
                 return {
                    'status': 'failed', 
                    'reason': 'weekly_analysis_object_missing', 
                    'weekly_result': weekly_result,
                    'user_id': user_id
                }

        logger.debug(f"[Celery Task] -> Выполнение анализа профиля пользователя {user_id}...")
        perform_profile_sync = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)
        profile_result = perform_profile_sync(user)
        
        if profile_result['success']:
            logger.debug(f"[Celery Task] -> Анализ профиля пользователя {user_id} успешен.")
        else:
            logger.error(f"[Celery Task] -> Ошибка в анализе профиля для пользователя {user_id}: {profile_result.get('message', 'Unknown error')}")
            # Важно: даже если анализ профиля не удался, мы всё равно можем попробовать анализ изменений,
            # так как он использует текущий (потенциально частично обновлённый) профиль и историю.
            # Поэтому не возвращаем ошибку здесь.

        logger.debug(f"[Celery Task] -> Выполнение анализа изменений профиля пользователя {user_id}...")
        # Вызываем новый сервис
        perform_profile_change_sync = async_to_sync(perform_profile_change_analysis)
        profile_change_result = perform_profile_change_sync(user, weekly_analysis_obj, num_snapshots_to_compare=3) # Указываем количество слепков

        if profile_change_result['success']:
            logger.debug(f"[Celery Task] -> Анализ изменений профиля для пользователя {user_id} успешен.")
        else:
            logger.error(f"[Celery Task] -> Ошибка в анализе изменений профиля для пользователя {user_id}: {profile_change_result.get('message', 'Unknown error')}")
            # Возвращаем статус с ошибкой в анализе изменений, но успехом в основных анализах
            return {
                'status': 'completed_with_change_error', 
                'weekly_result': weekly_result, 
                'profile_result': profile_result,
                'profile_change_error': profile_change_result.get('error'), 
                'profile_change_message': profile_change_result.get('message'),
                'user_id': user_id
            }

        logger.debug(f"[Celery Task] Полный цикл анализа (недельный, профиль, изменения) для пользователя {user_id} успешно завершён.")
        return {
            'status': 'completed', 
            'weekly_result': weekly_result, 
            'profile_result': profile_result,
            'profile_change_result': profile_change_result, # Добавим результат и этого шага
            'user_id': user_id
        }
    except User.DoesNotExist:
        logger.error(f"[Celery Task] Пользователь с ID {user_id} не найден.")
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}
    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка при выполнении анализа для пользователя {user_id}: {e}", exc_info=True)
        try:
            self.retry(countdown=60 * 5)
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
