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
                continue
            if pre_delete_hook:
                try:
                    pre_delete_hook(related_data)
                except Exception as hook_error:
                    logger.warning(f"    Ошибка в pre_delete_hook для {attr_name}: {hook_error}")
            if hasattr(related_data, 'delete') and callable(getattr(related_data, 'delete')):
                if hasattr(related_data, 'adelete'):
                     await related_data.adelete()
                else:
                     await sync_to_async(related_data.delete)()
            elif isinstance(related_data, QuerySet):
                count = await related_data.acount()
                if count > 0:
                    deleted_count, _ = await related_data.adelete()
            elif hasattr(related_data, 'all'):
                 try:
                     related_queryset = related_data.all()
                     if isinstance(related_queryset, QuerySet):
                         count = await related_queryset.acount()
                         if count > 0:
                             deleted_count, _ = await related_queryset.adelete()
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
