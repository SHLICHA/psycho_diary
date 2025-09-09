"""
Утилиты для удаления данных бота
"""

import logging

from asgiref.sync import sync_to_async
from typing import Callable, Any, Optional, Type, List
from django.db.models import QuerySet, Model

from diary.models import DiaryEntry, TaskCompletion
from users.models import User

logger = logging.getLogger(__name__)

async def _delete_related_objects(
    main_object,
    related_attributes: List[str],
    pre_delete_hook: Optional[Callable[[Any], None]] = None,
    post_delete_hook: Optional[Callable[[Any], None]] = None
):
    """
    Универсальная функция для удаления связанных объектов.
    
    Args:
        main_object: Основной объект, у которого удаляются связанные данные.
        related_attributes: Список строк - названий атрибутов (related_name) или свойств объекта,
                            которые представляют связанные объекты или QuerySet'ы.
        pre_delete_hook: (Опционально) Функция, вызываемая перед удалением каждого связанного объекта/QuerySet'а.
                         Принимает сам объект/QuerySet.
        post_delete_hook: (Опционально) Функция, вызываемая после удаления каждого связанного объекта/QuerySet'а.
                          Принимает сам объект/QuerySet.
    """
    for attr_name in related_attributes:
        try:
            related_data = getattr(main_object, attr_name, None)
            if related_data is None:
                logger.debug(f"    Атрибут {attr_name} отсутствует или равен None. Пропущено.")
                continue
            if pre_delete_hook:
                try:
                    pre_delete_hook(related_data)
                except Exception as hook_error:
                    logger.warning(f"    Ошибка в pre_delete_hook для {attr_name}: {hook_error}")
            if hasattr(related_data, 'delete') and callable(getattr(related_data, 'delete')):
                logger.debug(f"    Удаление связанного объекта {type(related_data).__name__}...")
                if hasattr(related_data, 'adelete'):
                     await related_data.adelete()
                else:
                     await sync_to_async(related_data.delete)()
            elif isinstance(related_data, QuerySet):
                logger.debug(f"    Удаление объектов из QuerySet {related_data.model.__name__}...")
                count = await related_data.acount()
                if count > 0:
                    logger.debug(f"    Найдено {count} объектов для удаления из {related_data.model.__name__}.")
                    deleted_count, _ = await related_data.adelete()
                    logger.debug(f"    Удалено {deleted_count} объектов из {related_data.model.__name__}.")
                else:
                    logger.debug(f"    Нет объектов для удаления из {related_data.model.__name__}.")
            elif hasattr(related_data, 'all'):
                 try:
                     related_queryset = related_data.all()
                     if isinstance(related_queryset, QuerySet):
                         logger.debug(f"    Удаление объектов через асинхронный менеджер {attr_name}...")
                         count = await related_queryset.acount()
                         if count > 0:
                             logger.debug(f"    Найдено {count} объектов для удаления через {attr_name}.")
                             deleted_count, _ = await related_queryset.adelete()
                             logger.debug(f"    Удалено {deleted_count} объектов через {attr_name}.")
                         else:
                             logger.debug(f"    Нет объектов для удаления через {attr_name}.")
                 except Exception as manager_error:
                     logger.error(f"    Ошибка при работе с асинхронным менеджером {attr_name}: {manager_error}")
            else:
                logger.warning(f"    Неизвестный тип связанных данных для атрибута {attr_name}: {type(related_data)}. Пропущено.")
            if post_delete_hook:
                try:
                    post_delete_hook(related_data)
                except Exception as hook_error:
                    logger.warning(f"    Ошибка в post_delete_hook для {attr_name}: {hook_error}")
        except Exception as e:
            logger.error(f"Ошибка при удалении связанных данных '{attr_name}' для объекта {type(main_object).__name__} ID {getattr(main_object, 'id', 'N/A')}: {e}")


# ==================== УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ ДАННЫХ ПОЛЬЗОВАТЕЛЯ ====================

async def _delete_user_data_by_model(
    user,
    model_class: Type[Model],
    filter_kwargs: Optional[dict] = None,
    pre_delete_hook: Optional[Callable[[QuerySet], None]] = None,
    post_delete_hook: Optional[Callable[[int], None]] = None
):
    """
    Универсальная функция для удаления данных пользователя по модели.
    
    Args:
        user: Объект пользователя.
        model_class: Класс модели Django, объекты которой нужно удалить.
        filter_kwargs: (Опционально) Словарь для дополнительной фильтрации QuerySet'а.
                       По умолчанию фильтрует по user.
        pre_delete_hook: (Опционально) Функция, вызываемая перед удалением QuerySet'а.
        post_delete_hook: (Опционально) Функция, вызываемая после удаления, принимает количество удаленных объектов.
    """
    try:
        logger.info(f"Удаление данных пользователя {user.telegram_id} для модели {model_class.__name__}")
        base_filter = {'user': user}
        if filter_kwargs:
            base_filter.update(filter_kwargs)
        queryset = model_class.objects.filter(**base_filter)
        count = await queryset.acount()
        logger.info(f"Найдено {count} объектов {model_class.__name__} для удаления у пользователя {user.telegram_id}")
        if count == 0:
            logger.info(f"Нет объектов {model_class.__name__} для удаления у пользователя {user.telegram_id}")
            if post_delete_hook:
                post_delete_hook(0)
            return
        if pre_delete_hook:
            try:
                pre_delete_hook(queryset)
            except Exception as hook_error:
                logger.warning(f"Ошибка в pre_delete_hook для {model_class.__name__}: {hook_error}")
        deleted_count, deleted_details = await queryset.adelete()
        logger.info(f"Удалено {deleted_count} объектов {model_class.__name__} у пользователя {user.telegram_id}")
        if post_delete_hook:
            try:
                post_delete_hook(deleted_count)
            except Exception as hook_error:
                logger.warning(f"Ошибка в post_delete_hook для {model_class.__name__}: {hook_error}")
    except Exception as e:
        logger.error(f"Ошибка при удалении данных {model_class.__name__} пользователя {user.telegram_id}: {e}")


# ==================== ОБНОВЛЕННЫЕ СУЩЕСТВУЮЩИЕ ФУНКЦИИ ====================


async def _delete_related_data_unified(entry: 'DiaryEntry'):
    """
    Удаление связанных данных записи дневника, используя универсальную функцию.
    """
    logger.info(f"Удаление связанных данных записи {entry.id}")
    related_attrs = ['analysis', 'key_points', 'voice_to_text', 'task_completion']

    def pre_hook(related_data):
        if hasattr(related_data, 'model'):
            logger.debug(f"  Начало удаления QuerySet {related_data.model.__name__}")
        elif hasattr(related_data, '__class__'):
            logger.debug(f"  Начало удаления объекта {related_data.__class__.__name__}")
    def post_hook(related_data):
        if hasattr(related_data, 'model'):
            logger.debug(f"  Завершено удаление QuerySet {related_data.model.__name__}")
        elif hasattr(related_data, '__class__'):
             logger.debug(f"  Завершено удаление объекта {related_data.__class__.__name__}")
    await _delete_related_objects(entry, related_attrs, pre_hook, post_hook)
    logger.info(f"Все связанные данные записи {entry.id} удалены")

async def _delete_task_completion_related_data_unified(task_completion: 'TaskCompletion'):
    """
    Удаление связанных данных выполнения задания, используя универсальную функцию.
    """
    logger.info(f"Удаление связанных данных выполнения задания {task_completion.id}")
    related_attrs = ['analysis']
    
    await _delete_related_objects(task_completion, related_attrs)
    logger.info(f"Все связанные данные выполнения задания {task_completion.id} удалены")

async def _delete_user_entries_unified(user: 'User'):
    """
    Удаление записей пользователя, используя универсальную функцию.
    """
    from diary.models import DiaryEntry # Импортируем здесь, чтобы избежать циклических импортов
    logger.info(f"Удаление записей пользователя {user.telegram_id}")
    
    # Функция для удаления связанных данных для каждой записи
    async def delete_entry_related(entry):
        await _delete_related_data_unified(entry)
        
    # Хук перед удалением записей
    def pre_delete_entries_hook(queryset):
        logger.debug(f"Начало удаления записей пользователя {user.telegram_id}")
    
    # Хук после удаления записей
    def post_delete_entries_hook(deleted_count):
        logger.debug(f"Завершено удаление записей пользователя {user.telegram_id}. Удалено: {deleted_count}")

    # Используем универсальную функцию
    await _delete_user_data_by_model(
        user=user,
        model_class=DiaryEntry,
        pre_delete_hook=pre_delete_entries_hook,
        post_delete_hook=post_delete_entries_hook
    )
    
    logger.info(f"Записи пользователя {user.telegram_id} удалены")

async def _delete_user_tasks_unified(user: 'User'):
    """
    Удаление заданий пользователя, используя универсальную функцию.
    """
    from diary.models import TherapyTask # Импортируем здесь
    logger.info(f"Удаление заданий пользователя {user.telegram_id}")
    
    # Функция для удаления связанных данных для каждого задания
    # Предполагаем, что у TherapyTask есть related_name='completion'
    async def delete_task_related(task):
        if hasattr(task, 'completion'):
            try:
                task_completion = await task.completion
                await _delete_task_completion_related_data_unified(task_completion)
                # task_completion сам удалится каскадно, если настроено в модели
            except Exception as e:
                logger.error(f"Ошибка при удалении связанных данных задания {task.id}: {e}")
    
    # Хук перед удалением заданий
    def pre_delete_tasks_hook(queryset):
        logger.debug(f"Начало удаления заданий пользователя {user.telegram_id}")
    
    # Хук после удаления заданий
    def post_delete_tasks_hook(deleted_count):
        logger.debug(f"Завершено удаление заданий пользователя {user.telegram_id}. Удалено: {deleted_count}")

    # Используем универсальную функцию
    await _delete_user_data_by_model(
        user=user,
        model_class=TherapyTask,
        pre_delete_hook=pre_delete_tasks_hook,
        post_delete_hook=post_delete_tasks_hook
    )
    logger.info(f"Задания пользователя {user.telegram_id} удалены")

async def _delete_user_analytics_unified(user: 'User'):
    """
    Удаление аналитики пользователя, используя универсальную функцию.
    """
    from diary.models import UserActivity, TherapyProgress, UserInsight # Импортируем здесь
    logger.info(f"Удаление аналитики пользователя {user.telegram_id}")
    
    models_to_delete = [UserActivity, TherapyProgress, UserInsight]
    
    for model_class in models_to_delete:
        # Хуки для каждой модели
        def make_pre_hook(model_name):
            return lambda queryset: logger.debug(f"Начало удаления {model_name} пользователя {user.telegram_id}")
        def make_post_hook(model_name): 
            return lambda deleted_count: logger.debug(f"Завершено удаление {model_name} пользователя {user.telegram_id}. Удалено: {deleted_count}")

        await _delete_user_data_by_model(
            user=user,
            model_class=model_class,
            pre_delete_hook=make_pre_hook(model_class.__name__),
            post_delete_hook=make_post_hook(model_class.__name__)
        )
        
    logger.info(f"Аналитика пользователя {user.telegram_id} удалена")