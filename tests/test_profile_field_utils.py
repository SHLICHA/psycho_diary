"""
Тесты для core/profile_field_utils.py
Тестируют утилиты очистки полей профиля — безопасность, дедупликацию, статистику.

Запуск: python manage.py test tests.test_profile_field_utils
"""

import sys
import os
import unittest
import importlib.util

# Загружаем модуль напрямую, минуя core/__init__.py (который импортирует celery)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODULE_PATH = os.path.join(_PROJECT_ROOT, 'core', 'profile_field_utils.py')

_spec = importlib.util.spec_from_file_location('profile_field_utils', _MODULE_PATH)
_pfu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pfu)

# Экспортируем функции для тестов
deduplicate_list = _pfu.deduplicate_list
find_similar_items = _pfu.find_similar_items
merge_similar_items_in_list = _pfu.merge_similar_items_in_list
cleanup_profile_fields = _pfu.cleanup_profile_fields
get_profile_field_stats = _pfu.get_profile_field_stats


class FakeUser:
    """Фейковый пользователь для тестов (без Django)."""
    def __init__(self, **kwargs):
        self.telegram_id = kwargs.get('telegram_id', 'test_user')
        self.life_facts = kwargs.get('life_facts', [])
        self.hobbies = kwargs.get('hobbies', [])
        self.core_values = kwargs.get('core_values', [])
        self.triggers = kwargs.get('triggers', [])
        self.strengths = kwargs.get('strengths', [])
        self.areas_for_growth = kwargs.get('areas_for_growth', [])
        self.habits = kwargs.get('habits', [])
        self.skills = kwargs.get('skills', [])
        self.aspirations = kwargs.get('aspirations', [])
        self.personality_traits = kwargs.get('personality_traits', {})
        self.personality_insights = kwargs.get('personality_insights', {})


class TestDeduplicateList(unittest.TestCase):
    """Тесты дедупликации списков."""

    def test_empty_list(self):
        self.assertEqual(deduplicate_list([]), [])

    def test_no_duplicates(self):
        self.assertEqual(deduplicate_list(['a', 'b', 'c']), ['a', 'b', 'c'])

    def test_exact_string_duplicates(self):
        items = ['факт1', 'факт2', 'факт1', 'факт3', 'факт2']
        result = deduplicate_list(items)
        self.assertEqual(result, ['факт1', 'факт2', 'факт3'])

    def test_dict_duplicates(self):
        items = [
            {'value': 'test', 'action': 'add'},
            {'value': 'other', 'action': 'remove'},
            {'value': 'test', 'action': 'add'},  # дубликат
        ]
        result = deduplicate_list(items)
        self.assertEqual(len(result), 2)

    def test_mixed_types(self):
        items = ['str', 1, 2, 'str', 1, None]
        result = deduplicate_list(items)
        self.assertEqual(result, ['str', 1, 2, None])

    def test_preserves_order(self):
        items = ['c', 'a', 'b', 'a', 'c']
        result = deduplicate_list(items)
        self.assertEqual(result, ['c', 'a', 'b'])


class TestFindSimilarItems(unittest.TestCase):
    """Тесты поиска похожих элементов."""

    def test_no_similar_items(self):
        items = ['яблоко', 'стул', 'машина']
        result = find_similar_items(items, similarity_threshold=0.8)
        self.assertEqual(result, [])

    def test_similar_items_found(self):
        items = ['управление стрессом', 'управление стрессом']
        result = find_similar_items(items, similarity_threshold=0.8)
        self.assertGreater(len(result), 0)

    def test_empty_list(self):
        self.assertEqual(find_similar_items([]), [])

    def test_single_item(self):
        self.assertEqual(find_similar_items(['один']), [])


class TestCleanupProfileFields(unittest.TestCase):
    """Тесты очистки полей профиля."""

    def test_removes_duplicates_from_list_field(self):
        user = FakeUser(
            life_facts=['факт1', 'факт1', 'факт2'],
        )
        result = cleanup_profile_fields(user)
        self.assertIn('life_facts', result)
        self.assertEqual(result['life_facts'], 1)
        self.assertEqual(user.life_facts, ['факт1', 'факт2'])

    def test_removes_none_and_empty_strings(self):
        user = FakeUser(
            life_facts=['факт', None, '  ', 'факт'],
            personality_traits={'valid': 0.5, 'empty': None, 'space': ''},
        )
        result = cleanup_profile_fields(user)
        self.assertNotIn(None, user.life_facts)
        self.assertNotIn('', user.life_facts)
        self.assertNotIn('  ', user.life_facts)
        self.assertNotIn('empty', user.personality_traits)
        self.assertNotIn('space', user.personality_traits)

    def test_no_changes_if_clean(self):
        user = FakeUser(
            life_facts=['факт1', 'факт2'],
            hobbies=['хобби1'],
            core_values=['ценность'],
            personality_traits={'trait': 0.5},
        )
        result = cleanup_profile_fields(user)
        self.assertEqual(result, {})

    def test_handles_missing_fields(self):
        """Модуль должен корректно обрабатывать отсутствующие поля."""
        # Создаём минимальный объект без многих полей
        minimal_user = type('MinimalUser', (), {
            'telegram_id': 'minimal_user',
            'life_facts': ['факт1', 'факт1'],
        })()
        # Убедимся, что функция не падает
        try:
            cleanup_profile_fields(minimal_user)
        except Exception as e:
            self.fail(f'cleanup_profile_fields raised {e}')

    def test_removes_duplicates_preserves_order(self):
        user = FakeUser(
            strengths=['сила1', 'сила2', 'сила1', 'сила3', 'сила2'],
        )
        result = cleanup_profile_fields(user)
        self.assertEqual(user.strengths, ['сила1', 'сила2', 'сила3'])


class TestGetProfileFieldStats(unittest.TestCase):
    """Тесты статистики полей профиля."""

    def test_returns_dict_for_all_fields(self):
        user = FakeUser(
            life_facts=['факт1', 'факт1', 'факт2'],
            core_values=['ценность', 'ценность'],
            strengths=['сила'],
            personality_traits={'trait1': 0.5},
        )
        stats = get_profile_field_stats(user)
        self.assertIn('life_facts', stats)
        self.assertIn('core_values', stats)
        # core_values: 2 total, 1 unique, 1 duplicate
        self.assertEqual(stats['core_values']['total'], 2)
        self.assertEqual(stats['core_values']['unique'], 1)
        self.assertEqual(stats['core_values']['duplicates'], 1)

    def test_handles_none_fields(self):
        user = FakeUser(
            life_facts=None,
            personality_traits=None,
        )
        stats = get_profile_field_stats(user)
        self.assertEqual(stats['life_facts']['total'], 0)
        self.assertEqual(stats['life_facts']['unique'], 0)


class TestMergeSimilarItems(unittest.TestCase):
    """Тесты объединения похожих элементов."""

    def test_no_merging_needed(self):
        items = ['бег', 'плавание', 'йога']
        result = merge_similar_items_in_list(items, similarity_threshold=0.8)
        # Не должно быть потерь
        self.assertEqual(len(result), len(items))

    def test_empty_list(self):
        self.assertEqual(merge_similar_items_in_list([]), [])


if __name__ == '__main__':
    unittest.main()
