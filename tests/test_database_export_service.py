"""
Тесты для database_export_service.py
"""
import pytest
from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import override_settings
from django.utils import timezone as django_timezone

from core.services.database_export_service import database_export_service, DatabaseExportService, MODELS_ORDER
from users.models import User, CityTimezone, Feedback


# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
from model_bakery import baker
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


class TestDatabaseExportServiceIsDeveloper:
    """Тесты для is_developer."""

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_developer_correct_id(self):
        assert database_export_service.is_developer(12345) is True

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_developer_wrong_id(self):
        assert database_export_service.is_developer(99999) is False

    @override_settings(DEVELOPER_CHAT_ID=None)
    def test_is_developer_no_setting(self):
        assert database_export_service.is_developer(12345) is False

    @override_settings(DEVELOPER_CHAT_ID='12345')
    def test_is_developer_string_comparison(self):
        # Проверяет что сравнение работает со строками
        assert database_export_service.is_developer(12345) is True


class TestDatabaseExportServiceGenerateFilename:
    """Тесты для generate_excel_filename."""

    def test_filename_format(self):
        filename = database_export_service.generate_excel_filename()
        assert filename.startswith("database_backup_")
        assert filename.endswith(".xlsx")
        # Проверяем что дата часть корректна
        parts = filename.replace("database_backup_", "").replace(".xlsx", "").split("_")
        assert len(parts) == 2  # date and time


class TestDatabaseExportServiceParseDatetime:
    """Тесты для _parse_datetime."""

    def test_parse_none_value(self):
        result = database_export_service._parse_datetime(None)
        assert result is None

    def test_parse_pd_na(self):
        result = database_export_service._parse_datetime(pd.NaT)
        assert result is None

    def test_parse_aware_datetime(self):
        import pytz
        utc_tz = pytz.UTC
        dt = datetime(2026, 4, 12, 12, 0, 0, tzinfo=utc_tz)
        result = database_export_service._parse_datetime(dt)
        assert result.tzinfo is not None

    def test_parse_naive_datetime(self):
        dt = datetime(2026, 4, 12, 12, 0, 0)
        result = database_export_service._parse_datetime(dt)
        assert result.tzinfo is not None  # Должен стать aware

    def test_parse_iso_string(self):
        dt_str = "2026-04-12T12:00:00+00:00"
        result = database_export_service._parse_datetime(dt_str)
        assert result.tzinfo is not None

    def test_parse_simple_datetime_string(self):
        dt_str = "2026-04-12 12:00:00"
        result = database_export_service._parse_datetime(dt_str)
        assert result.tzinfo is not None

    def test_parse_date_string(self):
        dt_str = "2026-04-12"
        result = database_export_service._parse_datetime(dt_str)
        assert result.tzinfo is not None

    def test_parse_non_datetime_value(self):
        result = database_export_service._parse_datetime("not_a_date")
        assert result == "not_a_date"


@pytest.mark.django_db(transaction=True)
class TestDatabaseExportServiceCollectData:
    """Тесты для collect_all_models_data."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=55001, username="testexportuser")

    def test_collect_data_empty_db(self):
        """Тест: сбор данных из пустой БД."""
        data = database_export_service.collect_all_models_data()
        assert isinstance(data, dict)
        # Все модели должны присутствовать
        for model in MODELS_ORDER:
            assert model._meta.model_name in data

    def test_collect_data_with_user(self, test_user):
        """Тест: сбор данных с пользователем."""
        data = database_export_service.collect_all_models_data()
        assert 'user' in data
        assert len(data['user']) == 1
        assert data['user'][0]['telegram_id'] == 55001


@pytest.mark.django_db(transaction=True)
class TestDatabaseExportServiceWriteToExcel:
    """Тесты для write_data_to_excel."""

    @pytest.fixture
    def sample_data(self):
        return {
            'user': [{'id': 1, 'telegram_id': 12345, 'username': 'testuser'}],
            'citytimezone': []
        }

    def test_write_data_creates_valid_excel(self, sample_data):
        """Тест: запись создаёт валидный Excel файл."""
        output = BytesIO()
        result = database_export_service.write_data_to_excel(output, sample_data)
        # После записи указатель в конце, проверим что данные есть
        assert len(result.getvalue()) > 0

        # Проверяем что можно прочитать
        result.seek(0)
        excel_file = pd.ExcelFile(result)
        assert 'user' in excel_file.sheet_names


@pytest.mark.django_db(transaction=True)
class TestDatabaseExportServicePerformImport:
    """Тесты для perform_import."""

    @pytest.fixture
    def test_user(self):
        return baker.make(
            User, telegram_id=55002, username="importuser",
            first_name="Test", last_name="User",
            password="pbkdf2_sha256$test$hash"
        )

    def _create_excel_buffer(self, sheets_dict):
        """Создаёт BytesIO с Excel данными через openpyxl."""
        import openpyxl
        from datetime import datetime as dt
        wb = openpyxl.Workbook()
        # Удаляем дефолтный лист
        wb.remove(wb.active)
        for sheet_name, rows_data in sheets_dict.items():
            ws = wb.create_sheet(sheet_name)
            if rows_data:
                # Заголовки
                headers = list(rows_data[0].keys())
                ws.append(headers)
                for row_data in rows_data:
                    # openpyxl не поддерживает tzinfo в datetime, убираем
                    clean_row = []
                    for h in headers:
                        val = row_data.get(h)
                        if isinstance(val, dt) and val.tzinfo is not None:
                            val = val.replace(tzinfo=None)
                        clean_row.append(val)
                    ws.append(clean_row)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return pd.ExcelFile(output)

    def test_import_with_valid_excel(self):
        """Тест: импорт из валидного Excel файла."""
        excel_data = self._create_excel_buffer({
            'user': [{
                'id': 999,
                'telegram_id': 99999,
                'username': 'newimportuser',
                'first_name': 'Import',
                'last_name': 'Test',
                'password': 'pbkdf2_sha256$test$hash',
                'is_active': True,
                'is_superuser': False,
                'is_staff': False,
                'created_at': django_timezone.now(),
                'updated_at': django_timezone.now(),
                'deletion_status': 'active',
                'is_blocked': False,
                'language': 'ru',
                'timezone': 'UTC',
                'token_balance': 0,
                'awareness_level': 1,
                'notifications_enabled': True,
                'auto_analysis_enabled': False,
                'max_ai_tasks_per_day': 1,
                'current_calendar_year': 2026,
                'current_calendar_month': 4,
                'deleted_at': None,
                'date_of_birth': None,
                'email': '',
                'referral_link': None,
                'personality_description': '',
                'personality_traits': '',
                'life_facts': '',
                'hobbies': '',
                'core_values': '',
                'triggers': '',
                'strengths': '',
                'areas_for_growth': '',
                'compressed_psych_profile': '',
            }]
        })

        results = database_export_service.perform_import(excel_data)
        assert len(results) > 0
        assert any("импортировано" in r or "обновлено" in r for r in results)

    def test_import_skips_admin_user(self):
        """Тест: импорт пропускает пользователя admin."""
        excel_data = self._create_excel_buffer({
            'user': [{
                'id': 1,
                'telegram_id': 1,
                'username': 'admin',
                'first_name': 'Admin',
                'last_name': 'Admin',
                'password': None,
            }]
        })

        results = database_export_service.perform_import(excel_data)
        # admin должен быть пропущен
        assert any("пропущено" in r for r in results)

    def test_import_skips_user_without_password(self):
        """Тест: импорт пропускает пользователей без пароля."""
        excel_data = self._create_excel_buffer({
            'user': [{
                'id': 2,
                'telegram_id': 2,
                'username': 'nopassworduser',
                'first_name': 'No',
                'last_name': 'Password',
                'password': '',
            }]
        })

        results = database_export_service.perform_import(excel_data)
        assert any("пропущено" in r for r in results)
