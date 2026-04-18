"""
Celery задачи для миграции полей профиля в обогащённый формат.

Использование:
    from diary.tasks.profile_migration import migrate_user_triggers_task
    
    # Миграция одного пользователя
    migrate_user_triggers_task.delay(user_id=123)
    
    # Миграция всех пользователей
    migrate_all_triggers.delay()
"""

import logging
from celery import shared_task
from django.utils import timezone
from users.models import User

logger = logging.getLogger(__name__)


def convert_field_to_weighted(field_data, field_name='unknown'):
    """
    Универсальная конвертация поля в обогащённый формат.
    
    Args:
        field_data: Данные поля (список)
        field_name: Имя поля для логирования
        
    Returns:
        Список в новом формате
    """
    if not field_data:
        return []
    
    result = []
    now = timezone.now()
    
    for item in field_data:
        if isinstance(item, str):
            result.append({
                "value": item.strip(),
                "weight": 0.5,
                "frequency": 1,
                "added_at": now.isoformat(),
                "last_seen": now.isoformat(),
                "is_stale": False
            })
        elif isinstance(item, dict):
            if "value" in item:
                result.append(item)
        else:
            logger.warning(f"[convert_field_to_weighted] {field_name}: неизвестный тип {type(item)}")
    
    return result


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def migrate_user_triggers_task(self, user_id: int):
    """
    Мигрирует triggers для одного пользователя.
    
    Args:
        user_id: ID пользователя
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Проверяем формат
        current_triggers = user.triggers or []
        if not current_triggers:
            return {'status': 'skipped', 'reason': 'empty'}
        
        # Если уже в новом формате — пропускаем
        if isinstance(current_triggers[0], dict):
            return {'status': 'skipped', 'reason': 'already_new_format'}
        
        # Конвертируем
        new_triggers = convert_field_to_weighted(current_triggers, 'triggers')
        
        # Сохраняем
        user.triggers = new_triggers
        user.save(update_fields=['triggers'])
        
        logger.info(f"[migrate_user_triggers_task] Пользователь {user.telegram_id}: {len(current_triggers)} → {len(new_triggers)}")
        
        return {
            'status': 'success',
            'user_id': user_id,
            'telegram_id': user.telegram_id,
            'count_before': len(current_triggers),
            'count_after': len(new_triggers)
        }
        
    except User.DoesNotExist:
        logger.error(f"[migrate_user_triggers_task] Пользователь {user_id} не найден")
        return {'status': 'error', 'reason': 'user_not_found'}
        
    except Exception as e:
        logger.error(f"[migrate_user_triggers_task] Ошибка для пользователя {user_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3)
def migrate_all_triggers(self, batch_size: int = 50):
    """
    Мигрирует triggers для всех пользователей батчами.
    
    Args:
        batch_size: Размер батча
    """
    # Находим пользователей в старом формате
    users = User.objects.filter(
        triggers__isnull=False
    ).exclude(
        triggers=[]
    )
    
    # Фильтр: первый элемент не dict (старый формат)
    # Это можно сделать через raw query или итеративно
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for user in users:
        try:
            current_triggers = user.triggers or []
            if not current_triggers:
                skipped_count += 1
                continue
            
            # Проверяем формат
            if isinstance(current_triggers[0], dict):
                skipped_count += 1
                continue
            
            # Мигрируем
            new_triggers = convert_field_to_weighted(current_triggers, 'triggers')
            user.triggers = new_triggers
            user.save(update_fields=['triggers'])
            
            migrated_count += 1
            
            if migrated_count % batch_size == 0:
                logger.info(f"[migrate_all_triggers] Мигрировано: {migrated_count}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"[migrate_all_triggers] Ошибка для {user.telegram_id}: {e}")
    
    result = {
        'status': 'completed',
        'migrated': migrated_count,
        'skipped': skipped_count,
        'errors': error_count
    }
    
    logger.info(f"[migrate_all_triggers] Завершено: {result}")
    
    return result


@shared_task
def migrate_user_field_task(user_id: int, field_name: str):
    """
    Универсальная задача для миграции любого поля.
    
    Args:
        user_id: ID пользователя
        field_name: Имя поля (triggers, life_facts, hobbies, etc.)
    """
    try:
        user = User.objects.get(id=user_id)
        field_data = getattr(user, field_name, None) or []
        
        if not field_data:
            return {'status': 'skipped', 'reason': 'empty'}
        
        # Проверяем формат
        if isinstance(field_data[0], dict):
            return {'status': 'skipped', 'reason': 'already_new_format'}
        
        # Конвертируем
        new_data = convert_field_to_weighted(field_data, field_name)
        
        # Сохраняем
        setattr(user, field_name, new_data)
        user.save(update_fields=[field_name])
        
        return {
            'status': 'success',
            'field': field_name,
            'count_before': len(field_data),
            'count_after': len(new_data)
        }
        
    except User.DoesNotExist:
        return {'status': 'error', 'reason': 'user_not_found'}
    except Exception as e:
        logger.error(f"[migrate_user_field_task] Ошибка: {e}")
        return {'status': 'error', 'reason': str(e)}