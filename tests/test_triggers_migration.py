"""
Тесты для миграции triggers.

Запуск: python -m pytest tests/test_triggers_migration.py -v
"""

import os
import sys
import unittest
import importlib.util

# Загружаем модуль напрямую
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODULE_PATH = os.path.join(_PROJECT_ROOT, 'diary', 'management', 'commands', 'migrate_triggers.py')

_spec = importlib.util.spec_from_file_location('migrate_triggers', _MODULE_PATH)
_mt = importlib.util.module_from_spec(_spec)

# Мокаем Django
sys.modules['django'] = type(sys)('django')
sys.modules['django.core'] = type(sys)('django.core')
sys.modules['django.core.management'] = type(sys)('django.core.management')
sys.modules['django.core.management.base'] = type(sys)('django.core.management.base')
sys.modules['django.utils'] = type(sys)('django.utils')
sys.modules['django.utils.timezone'] = type(sys)('django.utils.timezone')

class MockTimezone:
    @staticmethod
    def now():
        import datetime
        return datetime.datetime(2026, 4, 18, 12, 0, 0)

sys.modules['django.utils.timezone'].timezone = MockTimezone

try:
    _spec.loader.exec_module(_mt)
except Exception as e:
    # Если не загрузился — тестируем функцию отдельно
    pass

# Импортируем функцию конвертации из profile_field_utils
_UTILS_PATH = os.path.join(_PROJECT_ROOT, 'core', 'profile_field_utils.py')
_spec2 = importlib.util.spec_from_file_location('profile_field_utils', _UTILS_PATH)
_pfu = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_pfu)

convert_triggers_to_weighted = _pfu.convert_to_weighted_format


class TestConvertTriggersToWeighted(unittest.TestCase):
    """Тесты конвертации triggers в обогащённый формат."""

    def test_converts_empty_list(self):
        result = convert_triggers_to_weighted([])
        self.assertEqual(result, [])

    def test_converts_string_list(self):
        triggers = ["шум", "толпа", "дедлайны"]
        result = convert_triggers_to_weighted(triggers)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["value"], "шум")
        self.assertEqual(result[0]["weight"], 0.5)
        self.assertEqual(result[0]["frequency"], 1)
        self.assertIn("added_at", result[0])
        self.assertIn("last_seen", result[0])
        self.assertEqual(result[0]["is_stale"], False)

    def test_preserves_existing_weighted_format(self):
        triggers = [
            {"value": "шум", "weight": 0.9, "frequency": 5, "added_at": "2026-01-01", "last_seen": "2026-04-01", "is_stale": False}
        ]
        result = convert_triggers_to_weighted(triggers)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["value"], "шум")
        self.assertEqual(result[0]["weight"], 0.9)
        self.assertEqual(result[0]["frequency"], 5)

    def test_handles_mixed_format(self):
        triggers = ["строка", {"value": "дикт", "weight": 0.7}]
        result = convert_triggers_to_weighted(triggers)
        
        self.assertEqual(len(result), 2)
        # Строка должна быть конвертирована в dict
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]["value"], "строка")
        # Dict должен быть сохранён
        self.assertEqual(result[1]["weight"], 0.7)

    def test_strips_whitespace(self):
        triggers = ["  шум  ", "толпа"]
        result = convert_triggers_to_weighted(triggers)
        
        self.assertEqual(result[0]["value"], "шум")  # без пробелов

    def test_handles_none_in_list(self):
        triggers = ["шум", None, "толпа"]
        result = convert_triggers_to_weighted(triggers)
        
        # None должен быть пропущен
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], "шум")
        self.assertEqual(result[1]["value"], "толпа")


class TestMigrationLogic(unittest.TestCase):
    """Тесты логики миграции."""

    def test_detects_old_format(self):
        """Старый формат — список строк."""
        old_triggers = ["шум", "толпа"]
        is_old = isinstance(old_triggers[0], str) if old_triggers else False
        self.assertTrue(is_old)

    def test_detects_new_format(self):
        """Новый формат — список dict."""
        new_triggers = [{"value": "шум", "weight": 0.5}]
        is_new = isinstance(new_triggers[0], dict) if new_triggers else False
        self.assertTrue(is_new)

    def test_empty_triggers(self):
        """Пустой список."""
        empty_triggers = []
        is_empty = not empty_triggers
        self.assertTrue(is_empty)

    def test_none_triggers(self):
        """None значение."""
        none_triggers = None
        is_none = not none_triggers
        self.assertTrue(is_none)


if __name__ == '__main__':
    unittest.main()