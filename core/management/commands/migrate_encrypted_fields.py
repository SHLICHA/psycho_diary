# psycho_diary/core/management/commands/migrate_encrypted_fields.py

import json
import logging
from typing import Dict, List, Type
from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import connection, transaction
from django.db.models import Model

from core.encrypted_fields import is_raw_value_encrypted

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Мигрирует незашифрованные данные в зашифрованные поля.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--config',
            type=str,
            help='Конфигурация полей для миграции в формате JSON: {"app.Model": ["field1", "field2"], ...}',
            default='{}'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Размер пакета для обработки записей.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет изменено без фактического обновления.'
        )

    def handle(self, *args, **options):
        """Основной обработчик команды."""
        try:
            config_str = options['config']
            config = json.loads(config_str)
        except json.JSONDecodeError as e:
            raise CommandError(f"Неверный формат JSON в --config: {e}")

        if not config:
            config = self.get_default_config()
            self.stdout.write(
                self.style.WARNING("Используется конфигурация по умолчанию.")
            )

        if not config:
            self.stdout.write(
                self.style.ERROR("Конфигурация пустая! Добавьте модели в get_default_config() или используйте --config")
            )
            return

        batch_size = options['batch_size']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("РЕЖИМ ПРОБНОГО ЗАПУСКА - изменения не будут сохранены"))

        self.stdout.write(f"Конфигурация: {json.dumps(config, indent=2)}")
        self.stdout.write(f"Размер пакета: {batch_size}")

        # Подтверждение
        if not dry_run:
            self.stdout.write(self.style.WARNING("\nВНИМАНИЕ: Эта операция изменит данные в базе данных."))
            confirm = input("Продолжить? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Отменено.")
                return

        self.run_migrations(config, batch_size, dry_run)

    def get_default_config(self) -> Dict[str, List[str]]:
        """ЗАМЕНИТЕ НА ВАШИ РЕАЛЬНЫЕ МОДЕЛИ"""
        return {
            'diary.DiaryEntry': ['text'],  # ПРИМЕР
            # 'users.User': ['first_name', 'last_name'],
        }

    def run_migrations(self, config: Dict[str, List[str]], batch_size: int, dry_run: bool):
        """Запускает миграции."""
        total_updated = 0
        
        for model_path, field_names in config.items():
            try:
                updated_count = self.migrate_model_fields(model_path, field_names, batch_size, dry_run)
                total_updated += updated_count
                if updated_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"Модель {model_path}: обновлено {updated_count} записей"))
                else:
                    self.stdout.write(self.style.WARNING(f"Модель {model_path}: нет изменений"))
            except Exception as e:
                logger.error(f"Ошибка при миграции {model_path}: {e}")
                self.stdout.write(self.style.ERROR(f"Ошибка: {model_path} - {e}"))

        if total_updated > 0:
            self.stdout.write(self.style.SUCCESS(f"\nВсего обновлено записей: {total_updated}"))
        else:
            self.stdout.write(self.style.WARNING("Нет данных для обновления"))

    def migrate_model_fields(self, model_path: str, field_names: List[str], batch_size: int, dry_run: bool) -> int:
        """Мигрирует поля для конкретной модели."""
        app_name, model_name = model_path.rsplit('.', 1)
        model_class = apps.get_model(app_label=app_name, model_name=model_name)
        
        self.stdout.write(f"\nОбработка: {model_path} -> {field_names}")

        rows = self.fetch_model_data(model_class, field_names)
        if not rows:
            self.stdout.write("  Нет данных для обработки")
            return 0

        objects_to_update = self.process_rows(model_class, rows, field_names)
        if not objects_to_update:
            self.stdout.write("  Все данные уже зашифрованы")
            return 0

        if dry_run:
            self.stdout.write(self.style.WARNING(f"  Будет обновлено: {len(objects_to_update)} записей"))
            return len(objects_to_update)
        else:
            return self.apply_changes(model_class, objects_to_update, field_names, batch_size)

    def fetch_model_data(self, model_class: Type[Model], field_names: List[str]) -> List[tuple]:
        """Получает данные из базы."""
        table_name = model_class._meta.db_table
        pk_name = model_class._meta.pk.name
        
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {pk_name}, {', '.join(field_names)} FROM {table_name}")
            return cursor.fetchall()

    def process_rows(self, model_class: Type[Model], rows: List[tuple], field_names: List[str]) -> List[Model]:
        """Обрабатывает строки для обновления."""
        objects_to_update = []
        
        for row in rows:
            pk_value, *field_values = row
            updated_fields = {}
            
            for i, field_name in enumerate(field_names):
                raw_value = field_values[i]
                if raw_value in (None, ""):
                    continue
                    
                is_encrypted, reason = is_raw_value_encrypted(raw_value)
                if not is_encrypted:
                    try:
                        field = model_class._meta.get_field(field_name)
                        encrypted_value = field.get_prep_value(raw_value)
                        updated_fields[field_name] = encrypted_value
                        self.stdout.write(f"    Шифруем поле {field_name} записи {pk_value}")
                    except Exception as e:
                        logger.error(f"Ошибка шифрования {field_name} записи {pk_value}: {e}")
                        self.stdout.write(f"    ОШИБКА шифрования {field_name} записи {pk_value}: {e}")
                else:
                    self.stdout.write(f"    Поле {field_name} записи {pk_value} уже зашифровано")
            
            if updated_fields:
                obj = model_class(pk=pk_value)
                for field_name, value in updated_fields.items():
                    setattr(obj, field_name, value)
                objects_to_update.append(obj)

        return objects_to_update

    def apply_changes(self, model_class: Type[Model], objects_to_update: List[Model], 
                     field_names: List[str], batch_size: int) -> int:
        """Применяет изменения к БД."""
        self.stdout.write(f"  Обновление {len(objects_to_update)} записей...")
        
        try:
            with transaction.atomic():
                for i in range(0, len(objects_to_update), batch_size):
                    batch = objects_to_update[i:i + batch_size]
                    model_class.objects.bulk_update(batch, field_names, batch_size=batch_size)
                    self.stdout.write(f"    Обновлено {min(i + batch_size, len(objects_to_update))}/{len(objects_to_update)}")
            return len(objects_to_update)
        except Exception as e:
            logger.error(f"Ошибка обновления БД: {e}")
            self.stdout.write(self.style.ERROR(f"Ошибка обновления БД: {e}"))
            raise