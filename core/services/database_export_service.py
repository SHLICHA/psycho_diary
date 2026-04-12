"""
Сервис для экспорта/импорта базы данных в Excel.
Универсальный сервис: работает и для бота, и для API.

Отвечается за:
- Проверку прав разработчика
- Сбор данных из всех моделей для экспорта
- Запись данных в Excel
- Импорт данных из Excel файла
"""

import ast
import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, List, Tuple

import pandas as pd
import pytz
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.models import User, UserProfileHistory, CityTimezone, Feedback
from diary.models import (
    DiaryEntry, PsychoAnalysis, TherapyProgress, TherapyTask,
    TaskCompletion, TaskCompletionAnalysis, UserActivity,
    CombinedDiaryEntry, DailyAnalysis, WeeklyAnalysis,
    NextEntryPrompt, AnalysisRating
)
from core.services.admin_service import admin_service

logger = logging.getLogger(__name__)

MODELS_ORDER = [
    User,
    CityTimezone,
    DiaryEntry,
    PsychoAnalysis,
    TherapyProgress,
    TherapyTask,
    TaskCompletion,
    TaskCompletionAnalysis,
    UserActivity,
    CombinedDiaryEntry,
    DailyAnalysis,
    WeeklyAnalysis,
    NextEntryPrompt,
    AnalysisRating,
    UserProfileHistory,
    Feedback
]


class DatabaseExportService:
    """Сервис для экспорта/импорта базы данных."""

    def is_developer(self, user_id: int) -> bool:
        """
        Проверяет, является ли пользователь разработчиком.
        Делегирует в единый метод admin_service.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            bool: True если разработчик.
        """
        return admin_service.is_developer(user_id)

    def collect_all_models_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Собирает данные из всех моделей для экспорта.

        Returns:
            Dict[str, List[Dict]]: Словарь {model_name: [rows]}.
        """
        excel_data = {}
        for model in MODELS_ORDER:
            model_name = model._meta.model_name
            queryset = model.objects.all()
            if queryset.exists():
                data = []
                for obj in queryset:
                    row = {}
                    for field in obj._meta.fields:
                        field_name = field.name
                        field_value = getattr(obj, field_name)
                        if field.is_relation and field_value is not None:
                            row[field_name] = field_value.id
                        elif isinstance(field_value, (list, dict)):
                            row[field_name] = str(field_value)
                        elif hasattr(field_value, 'tzinfo') and field_value.tzinfo is not None:
                            try:
                                utc_value = field_value.astimezone(pytz.utc)
                                row[field_name] = utc_value.replace(tzinfo=None)
                            except Exception as e:
                                logger.warning(f"Ошибка преобразования datetime для поля {field_name}: {e}")
                                row[field_name] = field_value
                        else:
                            row[field_name] = field_value
                    data.append(row)
                excel_data[model_name] = data
            else:
                columns = [field.name for field in model._meta.fields]
                excel_data[model_name] = []
        return excel_data

    def write_data_to_excel(self, output: BytesIO, excel_data: Dict[str, List[Dict[str, Any]]]) -> BytesIO:
        """
        Записывает данные в Excel файл.

        Args:
            output: BytesIO буфер для записи.
            excel_data: Данные моделей.

        Returns:
            BytesIO: Буфер с данными Excel.
        """
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                self._write_sheets(writer, excel_data)
        except ImportError:
            try:
                output.seek(0)
                output.truncate(0)
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    self._write_sheets(writer, excel_data)
            except ImportError:
                output.seek(0)
                output.truncate(0)
                with pd.ExcelWriter(output) as writer:
                    self._write_sheets(writer, excel_data)

        output.seek(0)
        return output

    def _write_sheets(self, writer, excel_data: Dict[str, List[Dict[str, Any]]]):
        """Записывает листы в Excel writer."""
        for model in MODELS_ORDER:
            model_name = model._meta.model_name
            if model_name in excel_data and excel_data[model_name]:
                df = pd.DataFrame(excel_data[model_name])
                for column in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[column]):
                        df[column] = pd.to_datetime(df[column], utc=False)
                df.to_excel(writer, sheet_name=model_name, index=False)
            else:
                columns = [field.name for field in model._meta.fields]
                df = pd.DataFrame(columns=columns)
                df.to_excel(writer, sheet_name=model_name, index=False)

    def generate_excel_filename(self) -> str:
        """
        Генерирует имя файла для экспорта.

        Returns:
            str: Имя файла вида database_backup_YYYYMMDD_HHMMSS.xlsx
        """
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        return f"database_backup_{timestamp}.xlsx"

    def perform_import(self, excel_data: pd.ExcelFile) -> List[str]:
        """
        Выполняет импорт данных из Excel файла.

        Args:
            excel_data: pd.ExcelFile объект.

        Returns:
            List[str]: Список сообщений о результатах импорта.
        """
        results = []
        skipped_users = []

        try:
            with transaction.atomic():
                for model in MODELS_ORDER:
                    model_name = model._meta.model_name

                    if model_name not in excel_data.sheet_names:
                        continue

                    df = pd.read_excel(excel_data, sheet_name=model_name)

                    if df.empty:
                        continue

                    df = df.where(pd.notnull(df), None)

                    imported_count = 0
                    updated_count = 0
                    skipped_count = 0

                    for index, row in df.iterrows():
                        try:
                            if model == User:
                                username = row.get('username')
                                password = row.get('password')

                                if username == 'admin':
                                    skipped_count += 1
                                    skipped_users.append("admin")
                                    continue

                                import math
                                if not password or password == '' or (isinstance(password, float) and math.isnan(password)):
                                    skipped_count += 1
                                    if username:
                                        skipped_users.append(username)
                                    else:
                                        skipped_users.append(f"user_with_id_{row.get('id', 'unknown')}")
                                    continue

                            data = {}
                            for field in model._meta.fields:
                                field_name = field.name

                                if field_name not in row:
                                    continue

                                value = row[field_name]

                                if field_name in ['id', 'created_at', 'updated_at']:
                                    continue

                                if field.is_relation and value is not None:
                                    try:
                                        related_model = field.related_model
                                        if hasattr(related_model.objects, 'get'):
                                            data[field_name] = related_model.objects.get(id=int(value))
                                        else:
                                            continue
                                    except (ValueError, related_model.DoesNotExist):
                                        continue
                                else:
                                    if field.get_internal_type() in ['DateTimeField', 'DateField'] and value is not None:
                                        value = self._parse_datetime(value)
                                    elif field.get_internal_type() == 'JSONField' and isinstance(value, str):
                                        try:
                                            value = ast.literal_eval(value)
                                        except Exception:
                                            pass

                                    data[field_name] = value

                            if model == User:
                                if 'last_name' not in data or data['last_name'] is None:
                                    data['last_name'] = ""

                            if 'id' in row and pd.notnull(row['id']):
                                try:
                                    obj = model.objects.get(id=int(row['id']))
                                    for key, val in data.items():
                                        setattr(obj, key, val)
                                    obj.save()
                                    updated_count += 1
                                except model.DoesNotExist:
                                    data['id'] = int(row['id'])
                                    model.objects.create(**data)
                                    imported_count += 1
                            else:
                                model.objects.create(**data)
                                imported_count += 1

                        except Exception as e:
                            logger.error(f"Ошибка при импорте строки {index} в модель {model_name}: {e}")
                            error_msg = f"❌ Ошибка при импорте {model_name} (строка {index + 2}): {str(e)}"
                            results.append(error_msg)
                            raise Exception(error_msg)

                    if imported_count > 0 or updated_count > 0 or skipped_count > 0:
                        result_msg = f"✅ {model._meta.verbose_name_plural}: "
                        parts = []
                        if imported_count > 0:
                            parts.append(f"импортировано {imported_count}")
                        if updated_count > 0:
                            parts.append(f"обновлено {updated_count}")
                        if skipped_count > 0:
                            parts.append(f"пропущено {skipped_count}")
                        result_msg += ", ".join(parts)
                        results.append(result_msg)

        except Exception as e:
            if str(e) not in results:
                results.append(f"❌ Ошибка транзакции: {str(e)}")
            raise

        if skipped_users:
            unique_skipped = list(set(skipped_users))
            if len(unique_skipped) <= 5:
                results.append(f"⏭️ Пропущенные пользователи: {', '.join(unique_skipped)}")
            else:
                results.append(f"⏭️ Пропущено {len(unique_skipped)} пользователей (включая admin)")

        return results

    def _parse_datetime(self, value) -> Any:
        """
        Парсит значение в datetime с учётом часового пояса.

        Args:
            value: Значение для парсинга.

        Returns:
            datetime или исходное значение.
        """
        try:
            if pd.isna(value):
                return None
            elif isinstance(value, (datetime, pd.Timestamp)):
                if value.tzinfo is None:
                    return timezone.make_aware(value, timezone=timezone.utc)
                else:
                    return value
            elif isinstance(value, str):
                if 'T' in value:
                    parsed_dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                else:
                    try:
                        parsed_dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        parsed_dt = datetime.strptime(value, '%Y-%m-%d')

                if parsed_dt.tzinfo is None:
                    return timezone.make_aware(parsed_dt, timezone=timezone.utc)
                else:
                    return parsed_dt
            else:
                return value
        except Exception as e:
            logger.warning(f"Ошибка преобразования datetime: {e}")
            return value


database_export_service = DatabaseExportService()
