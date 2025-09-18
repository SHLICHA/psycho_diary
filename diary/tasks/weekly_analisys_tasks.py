# /home/shlicha/psycho_diary/diary/tasks.py
"""
Celery задачи для diary приложения.
"""

import logging
from datetime import datetime, time
import pytz

from celery import shared_task
from django.conf import settings
from asgiref.sync import sync_to_async, async_to_sync

from users.models import User
from diary.services.weekly_analysis_service import weekly_analysis_service
# Импортируем новый сервис
from diary.services.user_profile_analysis_service import user_profile_analysis_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def perform_weekly_analysis_for_user_task(self, user_id: int) -> dict:
    """
    Celery задача для выполнения еженедельного анализа и последующего анализа профиля для одного пользователя.
    """
    logger.info(f"[Celery Task] Запуск еженедельного анализа и анализа профиля для пользователя ID {user_id}")
    try:
        # Получаем пользователя синхронно
        user = User.objects.get(id=user_id)
        
        if user.is_blocked:
            logger.info(f"[Celery Task] Пользователь {user_id} заблокирован. Пропуск анализа.")
            return {'status': 'skipped', 'reason': 'user_blocked', 'user_id': user_id}

        # --- 1. Выполняем еженедельный анализ ---
        logger.info(f"[Celery Task] -> Выполнение еженедельного анализа для пользователя {user_id}...")
        perform_weekly_sync = async_to_sync(weekly_analysis_service.perform_weekly_analysis)
        weekly_result = perform_weekly_sync(user)
        
        if weekly_result['success']:
            logger.info(f"[Celery Task] -> Еженедельный анализ для пользователя {user_id} успешен.")
            if weekly_result.get('weekly_analysis'):
                logger.debug(f"[Celery Task] -> Создан WeeklyAnalysis ID: {weekly_result['weekly_analysis'].id}")
        else:
            logger.warning(f"[Celery Task] -> Ошибка в еженедельном анализе для пользователя {user_id}: {weekly_result.get('message', 'Unknown error')}")
            # Можно решить, продолжать ли анализ профиля в случае ошибки еженедельного анализа
            # Например, продолжать, если ошибка "уже существует"
            # if weekly_result.get('error') != 'already_exists':
            #     return {'status': 'failed', 'step': 'weekly_analysis', 'reason': weekly_result.get('error'), 'message': weekly_result.get('message'), 'user_id': user_id}

        # --- 2. Выполняем анализ профиля пользователя ---
        # Это делается независимо от результата еженедельного анализа
        logger.info(f"[Celery Task] -> Выполнение анализа профиля пользователя {user_id}...")
        perform_profile_sync = async_to_sync(user_profile_analysis_service.perform_user_profile_analysis)
        profile_result = perform_profile_sync(user)
        
        if profile_result['success']:
            logger.info(f"[Celery Task] -> Анализ профиля пользователя {user_id} успешен.")
        else:
            logger.error(f"[Celery Task] -> Ошибка в анализе профиля для пользователя {user_id}: {profile_result.get('message', 'Unknown error')}")
            # Возвращаем частичный успех или ошибку, в зависимости от требований
            # Здесь мы возвращаем 'completed_with_profile_error', чтобы показать, что еженедельный прошёл
            return {
                'status': 'completed_with_profile_error', 
                'weekly_result': weekly_result, 
                'profile_error': profile_result.get('error'), 
                'profile_message': profile_result.get('message'),
                'user_id': user_id
            }

        logger.info(f"[Celery Task] Еженедельный анализ и анализ профиля для пользователя {user_id} успешно завершены.")
        return {
            'status': 'completed', 
            'weekly_result': weekly_result, 
            'profile_result': profile_result,
            'user_id': user_id
        }

    except User.DoesNotExist:
        logger.error(f"[Celery Task] Пользователь с ID {user_id} не найден.")
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}
    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка при выполнении анализа для пользователя {user_id}: {e}", exc_info=True)
        # Повторная попытка
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
    Проверяет, является ли текущее время 03:00 по часовому поясу пользователя.
    """
    logger.info("[Celery Task] Запуск планировщика еженедельных анализов")
    
    try:
        # Получаем всех активных (не заблокированных) пользователей
        users = User.objects.filter(is_blocked=False)
        logger.info(f"[Celery Task] Найдено {users.count()} активных пользователей для проверки.")
        
        tasks_scheduled = 0
        for user in users:
            try:
                # Определяем локальное время пользователя
                user_tz_str = user.timezone if user.timezone else 'UTC'
                user_tz = pytz.timezone(user_tz_str)
                # Получаем текущее время UTC и конвертируем в часовой пояс пользователя
                utc_now = datetime.utcnow()
                user_local_time = utc_now.replace(tzinfo=pytz.utc).astimezone(user_tz).time()
                
                # Проверяем, 03:00 ли у него сейчас (с небольшим допуском)
                if time(2, 50) <= user_local_time <= time(3, 10):
                    logger.info(f"[Celery Task] Пора запускать анализ для пользователя {user.telegram_id} (часовой пояс: {user_tz_str}, локальное время: {user_local_time})")
                    
                    # Планируем задачу для этого пользователя
                    perform_weekly_analysis_for_user_task.delay(user.id)
                    tasks_scheduled += 1
                    
            except Exception as user_error:
                logger.error(f"[Celery Task] Ошибка при обработке пользователя {user.telegram_id}: {user_error}")

        logger.info(f"[Celery Task] Планировщик завершен. Запланировано {tasks_scheduled} задач.")
        return {'status': 'completed', 'tasks_scheduled': tasks_scheduled}

    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка в планировщике: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}
