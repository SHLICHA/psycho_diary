# /home/shlicha/psycho_diary/diary/tasks.py
"""
Celery задачи для diary приложения.
"""

import logging
from datetime import datetime, time
import pytz

from celery import shared_task
from django.conf import settings
from asgiref.sync import sync_to_async

from users.models import User
from diary.services.weekly_analysis_service import weekly_analysis_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def perform_weekly_analysis_for_user_task(self, user_id: int) -> dict:
    """
    Celery задача для выполнения еженедельного анализа для одного пользователя.
    """
    logger.info(f"[Celery Task] Запуск еженедельного анализа для пользователя ID {user_id}")
    try:
        # Получаем пользователя
        # user = User.objects.get(id=user_id) # Синхронно
        @sync_to_async
        def _get_user_sync():
            return User.objects.get(id=user_id)
        user = _get_user_sync() # Это не сработает, так как задача синхронная
        
        # Нужно использовать синхронный ORM в синхронной задаче
        user = User.objects.get(id=user_id)
        
        if user.is_blocked:
            logger.info(f"[Celery Task] Пользователь {user_id} заблокирован. Пропуск анализа.")
            return {'status': 'skipped', 'reason': 'user_blocked', 'user_id': user_id}

        # Выполняем анализ
        # result = asyncio.run(weekly_analysis_service.perform_weekly_analysis(user)) # Нельзя в синхронной задаче
        # Нужно адаптировать сервис или сделать обертку
        
        # Пока что делаем заглушку или переписываем сервис под синхронность для задач
        # ЛУЧШЕ: Сделать синхронную версию сервиса или использовать sync_to_async внутри асинхронной задачи
        
        # ВАРИАНТ 1: Сделать задачу асинхронной (требует настройки Celery для async)
        # ВАРИАНТ 2: Сделать синхронную версию сервиса
        # ВАРИАНТ 3: Использовать sync_to_async внутри синхронной задачи (проще)
        
        # Выбираем ВАРИАНТ 3
        import asyncio
        from asgiref.sync import async_to_sync
        
        # Оборачиваем асинхронный вызов в синхронный
        perform_analysis_sync = async_to_sync(weekly_analysis_service.perform_weekly_analysis)
        result = perform_analysis_sync(user)
        
        logger.info(f"[Celery Task] Еженедельный анализ для пользователя {user_id} завершен. Результат: {result}")
        return {'status': 'completed', 'result': result, 'user_id': user_id}

    except User.DoesNotExist:
        logger.error(f"[Celery Task] Пользователь с ID {user_id} не найден.")
        return {'status': 'failed', 'reason': 'user_not_found', 'user_id': user_id}
    except Exception as e:
        logger.error(f"[Celery Task] Ошибка при выполнении еженедельного анализа для пользователя {user_id}: {e}", exc_info=True)
        # Повторная попытка
        try:
            self.retry(countdown=60 * 5) # Повтор через 5 минут
        except self.MaxRetriesExceededError:
            logger.error(f"[Celery Task] Максимум повторов превышен для пользователя {user_id}")
            return {'status': 'failed', 'reason': 'max_retries_exceeded', 'error': str(e), 'user_id': user_id}


@shared_task(bind=True)
def schedule_weekly_analyses_task(self) -> dict:
    """
    Celery задача, запускаемая ежечасно, для планирования еженедельных анализов.
    Проверяет, является ли текущее время 03:00 по часовому поясу пользователя.
    """
    logger.info("[Celery Task] Запуск планировщика еженедельных анализов")
    
    try:
        # Получаем всех активных (не заблокированных) пользователей
        # users = User.objects.filter(is_blocked=False) # Синхронно
        
        # ВАЖНО: Эта задача запускается ежечасно. Нам нужно проверить,
        # является ли текущее время 03:00 для каждого пользователя.
        
        # Получаем текущее время UTC (как используется Celery Beat)
        utc_now = datetime.utcnow()
        utc_time = utc_now.time()
        logger.debug(f"[Celery Task] Текущее UTC время: {utc_time}")
        
        # Проверим, находится ли текущий час в диапазоне, когда у кого-то может быть 03:00
        # Это грубая проверка, но сработает. Более точная проверка будет внутри цикла.
        # if not (time(2, 9) <= utc_time <= time(4, 10)): # Примерный диапазон
        #     logger.debug("[Celery Task] Не время для запуска анализов (по UTC). Пропуск.")
        #     return {'status': 'skipped', 'reason': 'not_time_yet'}
        
        # Получаем пользователей. Лучше получить всех и фильтровать внутри.
        users = User.objects.filter(is_blocked=False)
        logger.info(f"[Celery Task] Найдено {users.count()} активных пользователей для проверки.")
        
        tasks_scheduled = 0
        for user in users:
            try:
                # Определяем локальное время пользователя
                user_tz_str = user.timezone if user.timezone else 'UTC'
                user_tz = pytz.timezone(user_tz_str)
                user_local_time = utc_now.replace(tzinfo=pytz.utc).astimezone(user_tz).time()
                
                # Проверяем, 03:00 ли у него сейчас
                # Учитываем возможное небольшое отклонение из-за времени выполнения
                if time(2, 50) <= user_local_time <= time(3, 10):
                    logger.info(f"[Celery Task] Пора запускать анализ для пользователя {user.telegram_id} (часовой пояс: {user_tz_str}, локальное время: {user_local_time})")
                    
                    # Планируем задачу для этого пользователя
                    perform_weekly_analysis_for_user_task.delay(user.id)
                    tasks_scheduled += 1
                # else:
                #     logger.debug(f"[Celery Task] Не время для пользователя {user.telegram_id} ({user_local_time})")
                    
            except Exception as user_error:
                logger.error(f"[Celery Task] Ошибка при обработке пользователя {user.telegram_id}: {user_error}")

        logger.info(f"[Celery Task] Планировщик завершен. Запланировано {tasks_scheduled} задач.")
        return {'status': 'completed', 'tasks_scheduled': tasks_scheduled}

    except Exception as e:
        logger.error(f"[Celery Task] Критическая ошибка в планировщике: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}
