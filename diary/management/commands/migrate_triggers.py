"""
Миграция поля triggers в обогащённый формат с весами.

Конвертирует:
- Старый формат: ["шум", "толпа"]
- Новый формат: [{"value": "шум", "weight": 0.5, "frequency": 1, "added_at": "...", "last_seen": "...", "is_stale": False}]

Безопасна для повторного запуска — пропускает уже мигрированные записи.

Запуск:
    python manage.py migrate_triggers --dry-run  # тестовый прогон
    python manage.py migrate_triggers            # реальная миграция
    python manage.py migrate_triggers --check    # только проверить статус
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from users.models import User

logger = logging.getLogger(__name__)


def is_already_migrated(field_data):
    """
    Проверяет, мигрировано ли поле в новый формат.
    
    Returns:
        True если уже в новом формате (dict)
    """
    if not field_data:
        return True  # пустое — считаем мигрированным
    return isinstance(field_data[0], dict)


def convert_triggers_to_weighted(triggers):
    """
    Конвертирует triggers в обогащённый формат.
    
    Args:
        triggers: Список в старом или новом формате
        
    Returns:
        Список в новом формате
    """
    if not triggers:
        return []
    
    result = []
    now = timezone.now()
    
    for item in triggers:
        if isinstance(item, str):
            # Старый формат — строка
            result.append({
                "value": item.strip(),
                "weight": 0.5,  # дефолтный вес
                "frequency": 1,
                "added_at": now.isoformat(),
                "last_seen": now.isoformat(),
                "is_stale": False
            })
        elif isinstance(item, dict):
            # Уже новый формат — пропускаем
            if "value" in item:
                result.append(item)
        else:
            logger.warning(f"[migrate_triggers] Пропущен элемент неизвестного типа: {type(item)}")
    
    return result


def migrate_user_triggers(user, dry_run=False):
    """
    Мигрирует triggers для одного пользователя.
    
    Args:
        user: Объект User
        dry_run: Если True — только возвращает данные, не сохраняет
        
    Returns:
        (было_изменено, старые_данные, новые_данные)
    """
    current_triggers = user.triggers
    
    # Проверяем, уже ли в новом формате
    if current_triggers and isinstance(current_triggers[0], dict):
        logger.info(f"[migrate_triggers] Пользователь {user.telegram_id} уже в новом формате")
        return False, current_triggers, current_triggers
    
    # Конвертируем
    new_triggers = convert_triggers_to_weighted(current_triggers)
    
    if dry_run:
        return len(new_triggers) > 0, current_triggers, new_triggers
    
    # Сохраняем
    user.triggers = new_triggers
    user.save(update_fields=['triggers'])
    
    logger.info(f"[migrate_triggers] Пользователь {user.telegram_id}: {len(current_triggers)} → {len(new_triggers)}")
    
    return True, current_triggers, new_triggers


class Command(BaseCommand):
    help = 'Мигрирует поле triggers в обогащённый формат с весами'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Тестовый прогон без сохранения изменений',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Только проверить статус миграции, не мигрировать',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Размер батча для обработки',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество пользователей',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        check_only = options['check']
        batch_size = options['batch_size']
        limit = options['limit']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 Режим DRY RUN — изменения не будут сохранены'))
        
        # Находим пользователей с triggers
        users = User.objects.filter(
            triggers__isnull=False
        ).exclude(
            triggers=[]
        ).exclude(
            triggers=[{}]
        )
        
        if limit:
            users = users[:limit]
        
        total_users = users.count()
        self.stdout.write(f'📊 Найдено пользователей с triggers: {total_users}')
        
        # Режим проверки — только считаем статусы
        if check_only:
            old_format = 0
            new_format = 0
            empty = 0
            
            for user in users:
                triggers = user.triggers or []
                if not triggers:
                    empty += 1
                elif isinstance(triggers[0], dict):
                    new_format += 1
                else:
                    old_format += 1
            
            self.stdout.write(self.style.SUCCESS('✅ Статус миграции:'))
            self.stdout.write(f'   Всего с triggers: {total_users}')
            self.stdout.write(f'   Новый формат (dict): {new_format}')
            self.stdout.write(f'   Старый формат (str): {old_format}')
            self.stdout.write(f'   Пустые: {empty}')
            
            if old_format > 0:
                self.stdout.write(self.style.WARNING(f'   ⚠️ Требуют миграции: {old_format}'))
            else:
                self.stdout.write(self.style.SUCCESS('   ✅ Все мигрированы!'))
            return
        
        migrated = 0
        skipped = 0
        errors = 0
        
        for i, user in enumerate(users):
            try:
                changed, old_data, new_data = migrate_user_triggers(user, dry_run=dry_run)
                
                if changed:
                    migrated += 1
                    if i < 3:  # Показываем первые 3 примера
                        self.stdout.write(f'  Пример {i+1}: {old_data} → {new_data}')
                else:
                    skipped += 1
                    
            except Exception as e:
                errors += 1
                logger.error(f'[migrate_triggers] Ошибка для пользователя {user.telegram_id}: {e}')
                self.stdout.write(self.style.ERROR(f'  ❌ Ошибка: {user.telegram_id} — {e}'))
            
            # Прогресс
            if (i + 1) % batch_size == 0:
                self.stdout.write(f'  Прогресс: {i + 1}/{total_users}')
        
        # Итог
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Миграция завершена:'))
        self.stdout.write(f'   Обработано: {total_users}')
        self.stdout.write(f'   Мигрировано: {migrated}')
        self.stdout.write(f'   Пропущено (уже новый формат): {skipped}')
        self.stdout.write(f'   Ошибок: {errors}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 Это был dry run. Запустите без --dry-run для применения изменений.'))