"""
Универсальная миграция полей профиля в обогащённый формат с весами.

Конвертирует:
- Старый формат: ["значение1", "значение2"]
- Новый формат: [{"value": "значение1", "weight": 0.5, "frequency": 1, "added_at": "...", "last_seen": "...", "is_stale": False}]

Безопасна для повторного запуска — пропускает уже мигрированные записи.

Запуск:
    python manage.py migrate_profile_field --field=life_facts --dry-run
    python manage.py migrate_profile_field --field=life_facts
    python manage.py migrate_profile_field --field=hobbies --check
    python manage.py migrate_profile_field --field=core_values
    python manage.py migrate_profile_field --field=strengths
    python manage.py migrate_profile_field --field=areas_for_growth
    python manage.py migrate_profile_field --field=practical_patterns
    python manage.py migrate_profile_field --field=aspirations
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import User

logger = logging.getLogger(__name__)

# Список поддерживаемых полей
SUPPORTED_FIELDS = [
    'triggers',
    'life_fields',
    'hobbies',
    'core_values',
    'strengths',
    'areas_for_growth',
    'practical_patterns',
    'aspirations',
]


def is_already_migrated(field_data):
    """Проверяет, мигрировано ли поле в новый формат."""
    if not field_data:
        return True
    return isinstance(field_data[0], dict)


def convert_to_weighted(field_data):
    """Конвертирует поле в обогащённый формат."""
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
        elif isinstance(item, dict) and "value" in item:
            result.append(item)
        else:
            logger.warning(f"[migrate_profile_field] Пропущен элемент: {type(item)}")
    
    return result


def migrate_user_field(user, field_name, dry_run=False):
    """Мигрирует указанное поле для одного пользователя."""
    field_value = getattr(user, field_name, None)
    
    if not field_value:
        return False, None, None
    
    if isinstance(field_value[0], dict):
        logger.debug(f"[migrate_{field_name}] Пользователь {user.telegram_id} уже в новом формате")
        return False, field_value, field_value
    
    new_value = convert_to_weighted(field_value)
    
    if dry_run:
        return len(new_value) > 0, field_value, new_value
    
    setattr(user, field_name, new_value)
    user.save(update_fields=[field_name])
    return True, field_value, new_value


class Command(BaseCommand):
    help = 'Мигрирует указанное поле профиля в обогащённый формат с весами'

    def add_arguments(self, parser):
        parser.add_argument(
            '--field',
            type=str,
            required=True,
            help='Имя поля для миграции (triggers, life_facts, hobbies, core_values, strengths, areas_for_growth, practical_patterns, aspirations)'
        )
        parser.add_argument('--dry-run', action='store_true', help='Тестовый прогон без сохранения')
        parser.add_argument('--check', action='store_true', help='Только проверить статус миграции')
        parser.add_argument('--batch-size', type=int, default=100, help='Размер батча')
        parser.add_argument('--limit', type=int, help='Ограничить количество пользователей')

    def handle(self, *args, **options):
        field_name = options['field']
        dry_run = options['dry_run']
        check_only = options['check']
        batch_size = options['batch_size']
        limit = options['limit']

        # Валидация поля
        valid_fields = ['triggers', 'life_facts', 'hobbies', 'core_values', 'strengths', 'areas_for_growth', 'practical_patterns', 'aspirations']
        if field_name not in valid_fields:
            self.stdout.write(self.style.ERROR(f'❌ Неподдерживаемое поле: {field_name}'))
            self.stdout.write(self.style.INFO(f'Доступные поля: {", ".join(valid_fields)}'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 Режим DRY-RUN — изменения не будут сохранены'))
        
        if check_only:
            self.stdout.write(self.style.WARNING(f'🔍 Проверка статуса миграции поля {field_name}'))
        
        queryset = User.objects.filter(**{f'{field_name}__isnull': False}).exclude(**{field_name: []})
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f'📊 Найдено пользователей с {field_name}: {total}')
        
        migrated = 0
        skipped = 0
        errors = 0

        for user in queryset.iterator(chunk_size=batch_size):
            try:
                current_value = getattr(user, field_name)
                
                if check_only:
                    if current_value and isinstance(current_value[0], dict):
                        migrated += 1
                    else:
                        skipped += 1
                    continue
                
                was_changed, old_val, new_val = migrate_user_field(user, field_name, dry_run)
                
                if was_changed:
                    migrated += 1
                    logger.info(f'Мигрировано {field_name} для пользователя {user.telegram_id}')
                else:
                    skipped += 1
                    
            except Exception as e:
                errors += 1
                logger.error(f'Ошибка миграции {field_name} для {user.telegram_id}: {e}')
                self.stdout.write(self.style.ERROR(f'❌ Ошибка: {e}'))

        if check_only:
            self.stdout.write(self.style.SUCCESS(f'✅ Уже мигрировано: {migrated}'))
            self.stdout.write(self.style.WARNING(f'⏳ Требуют миграции: {skipped}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Мигрировано: {migrated}'))
            self.stdout.write(self.style.WARNING(f'⏳ Пропущено: {skipped}'))
            self.stdout.write(self.style.ERROR(f'❌ Ошибок: {errors}'))