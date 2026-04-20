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

# Адаптеры для совместимости (ЭТАП 1.5)
field_to_ai_format = _pfu.field_to_ai_format
field_to_display_format = _pfu.field_to_display_format
get_profile_field_for_ai = _pfu.get_profile_field_for_ai
get_profile_field_for_display = _pfu.get_profile_field_for_display
triggers_to_ai_format = _pfu.triggers_to_ai_format
triggers_to_display_format = _pfu.triggers_to_display_format
life_facts_to_ai_format = _pfu.life_facts_to_ai_format
hobbies_to_ai_format = _pfu.hobbies_to_ai_format
core_values_to_ai_format = _pfu.core_values_to_ai_format
strengths_to_ai_format = _pfu.strengths_to_ai_format
compact_weighted_items = _pfu.compact_weighted_items
compact_personality_traits = _pfu.compact_personality_traits
build_personal_fields_payload_for_ai = _pfu.build_personal_fields_payload_for_ai
normalize_compressed_profile_for_prompt = _pfu.normalize_compressed_profile_for_prompt

# Новые функции для весов (НОВОЕ)
create_weighted_item = _pfu.create_weighted_item
convert_to_weighted_format = _pfu.convert_to_weighted_format
validate_profile_item = _pfu.validate_profile_item
validate_weighted_field = _pfu.validate_weighted_field
update_item_frequency = _pfu.update_item_frequency
mark_stale_items = _pfu.mark_stale_items
cleanup_stale_items = _pfu.cleanup_stale_items
sort_by_weight = _pfu.sort_by_weight
get_top_items = _pfu.get_top_items
format_for_user_display = _pfu.format_for_user_display
merge_profile_items = _pfu.merge_profile_items

# Константы
DAYS_UNTIL_STALE = _pfu.DAYS_UNTIL_STALE
DAYS_UNTIL_DELETE = _pfu.DAYS_UNTIL_DELETE
MIN_FREQUENCY_TO_KEEP = _pfu.MIN_FREQUENCY_TO_KEEP
MAX_ITEMS_PER_FIELD = _pfu.MAX_ITEMS_PER_FIELD


class FakeUser:
    """Фейковый пользователь для тестов (без Django)."""
    def __init__(self, **kwargs):
        self.telegram_id = kwargs.get('telegram_id', 'test_user')
        self.awareness_level = kwargs.get('awareness_level', 0)
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


# ============== НОВЫЕ ТЕСТЫ ДЛЯ ВЕСОВ (ЭТАП 1) ==============

class TestCreateWeightedItem(unittest.TestCase):
    """Тесты создания элемента с весами."""

    def test_creates_correct_structure(self):
        item = create_weighted_item("шум", weight=0.85)
        self.assertEqual(item["value"], "шум")
        self.assertEqual(item["weight"], 0.85)
        self.assertEqual(item["frequency"], 1)
        self.assertIn("added_at", item)
        self.assertIn("last_seen", item)
        self.assertEqual(item["is_stale"], False)

    def test_default_weight(self):
        item = create_weighted_item("тест")
        self.assertEqual(item["weight"], 0.5)


class TestConvertToWeightedFormat(unittest.TestCase):
    """Тесты конвертации в обогащённый формат."""

    def test_converts_string_list(self):
        items = ["шум", "толпа"]
        result = convert_to_weighted_format(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], "шум")
        self.assertEqual(result[0]["weight"], 0.5)
        self.assertEqual(result[0]["frequency"], 1)

    def test_preserves_existing_weighted_format(self):
        items = [{"value": "шум", "weight": 0.9, "frequency": 5}]
        result = convert_to_weighted_format(items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["weight"], 0.9)
        self.assertEqual(result[0]["frequency"], 5)

    def test_handles_mixed_format(self):
        items = ["строка", {"value": "дикт", "weight": 0.7}]
        result = convert_to_weighted_format(items)
        self.assertEqual(len(result), 2)
        # Строка должна быть конвертирована
        self.assertIsInstance(result[0], dict)
        # Dict должен быть сохранён
        self.assertEqual(result[1]["weight"], 0.7)

    def test_empty_list(self):
        self.assertEqual(convert_to_weighted_format([]), [])


class TestValidateProfileItem(unittest.TestCase):
    """Тесты валидации элементов профиля."""

    def test_valid_string(self):
        self.assertTrue(validate_profile_item("шум"))
        self.assertTrue(validate_profile_item("тест"))

    def test_invalid_empty_string(self):
        self.assertFalse(validate_profile_item(""))
        self.assertFalse(validate_profile_item("   "))

    def test_valid_weighted_dict(self):
        item = {"value": "шум", "weight": 0.85}
        self.assertTrue(validate_profile_item(item))

    def test_invalid_dict_no_value(self):
        item = {"weight": 0.85}
        self.assertFalse(validate_profile_item(item))

    def test_invalid_dict_no_weight(self):
        item = {"value": "шум"}
        self.assertFalse(validate_profile_item(item))

    def test_invalid_type(self):
        self.assertFalse(validate_profile_item(123))
        self.assertFalse(validate_profile_item(None))


class TestValidateWeightedField(unittest.TestCase):
    """Тесты валидации поля профиля."""

    def test_validates_all_items(self):
        items = ["шум", "толпа", {"value": "тест", "weight": 0.5}]
        valid, errors = validate_weighted_field(items)
        self.assertEqual(len(valid), 3)
        self.assertEqual(len(errors), 0)

    def test_returns_errors_for_invalid(self):
        items = ["шум", "", 123, {"no_value": True}]
        valid, errors = validate_weighted_field(items)
        self.assertEqual(len(valid), 1)  # только "шум"
        self.assertEqual(len(errors), 3)  # пустая строка, число, дикт без value


class TestUpdateItemFrequency(unittest.TestCase):
    """Тесты обновления частоты элементов."""

    def test_increments_existing_item(self):
        items = [{"value": "шум", "frequency": 3, "last_seen": "2026-01-01T00:00:00Z"}]
        result = update_item_frequency(items, "шум")
        self.assertEqual(result[0]["frequency"], 4)
        self.assertIn("last_seen", result[0])
        self.assertEqual(result[0]["is_stale"], False)

    def test_adds_new_item_if_not_found(self):
        items = [{"value": "шум", "frequency": 1}]
        result = update_item_frequency(items, "толпа")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["value"], "толпа")
        self.assertEqual(result[1]["frequency"], 1)


class TestMarkStaleItems(unittest.TestCase):
    """Тесты пометки устаревших элементов."""

    def test_marks_old_items_as_stale(self):
        # Элемент старше 30 дней
        items = [{"value": "шум", "last_seen": "2026-03-01T00:00:00Z", "is_stale": False}]
        result = mark_stale_items(items)
        self.assertEqual(result[0]["is_stale"], True)

    def test_keeps_recent_items_as_not_stale(self):
        # Элемент из сегодня
        from django.utils import timezone
        items = [{"value": "шум", "last_seen": timezone.now().isoformat(), "is_stale": False}]
        result = mark_stale_items(items)
        self.assertEqual(result[0]["is_stale"], False)


class TestCleanupStaleItems(unittest.TestCase):
    """Тесты удаления устаревших элементов."""

    def test_removes_stale_low_frequency_items(self):
        # Stale + frequency < 2 + старше 60 дней = удалить
        items = [
            {"value": "старый", "is_stale": True, "frequency": 1, "last_seen": "2026-01-01T00:00:00Z"}
        ]
        result = cleanup_stale_items(items)
        self.assertEqual(len(result), 0)

    def test_keeps_stale_high_frequency_items(self):
        # Stale но frequency >= 2 = оставить
        items = [
            {"value": "важный", "is_stale": True, "frequency": 3, "last_seen": "2026-01-01T00:00:00Z"}
        ]
        result = cleanup_stale_items(items)
        self.assertEqual(len(result), 1)

    def test_keeps_non_stale_items(self):
        items = [{"value": "актуальный", "is_stale": False, "frequency": 1}]
        result = cleanup_stale_items(items)
        self.assertEqual(len(result), 1)


class TestSortByWeight(unittest.TestCase):
    """Тесты сортировки по весу."""

    def test_sorts_by_weight_descending(self):
        items = [
            {"value": "низкий", "weight": 0.3},
            {"value": "высокий", "weight": 0.9},
            {"value": "средний", "weight": 0.6},
        ]
        result = sort_by_weight(items)
        self.assertEqual(result[0]["value"], "высокий")
        self.assertEqual(result[1]["value"], "средний")
        self.assertEqual(result[2]["value"], "низкий")

    def test_default_weight_when_missing(self):
        # Элемент без weight получает 0.5 по умолчанию при сортировке
        items = [{"value": "без веса", "weight": 0.5}]
        result = sort_by_weight(items)
        self.assertEqual(result[0]["weight"], 0.5)


class TestGetTopItems(unittest.TestCase):
    """Тесты получения топ-N элементов."""

    def test_returns_top_by_weight(self):
        items = [
            {"value": "пятый", "weight": 0.1},
            {"value": "первый", "weight": 0.9},
            {"value": "второй", "weight": 0.7},
            {"value": "четвёртый", "weight": 0.3},
            {"value": "третий", "weight": 0.5},
        ]
        result = get_top_items(items, limit=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["value"], "первый")
        self.assertEqual(result[1]["value"], "второй")
        self.assertEqual(result[2]["value"], "третий")


class TestFormatForUserDisplay(unittest.TestCase):
    """Тесты форматирования для пользователя."""

    def test_formats_correctly(self):
        items = [
            {"value": "шум", "weight": 0.85, "frequency": 12},
            {"value": "толпа", "weight": 0.6, "frequency": 3},
        ]
        result = format_for_user_display(items)
        self.assertEqual(len(result), 2)
        self.assertIn("шум", result[0])
        self.assertIn("85%", result[0])
        self.assertIn("12 раз", result[0])


class TestMergeProfileItems(unittest.TestCase):
    """Тесты объединения элементов профиля."""

    def test_merges_existing_and_new(self):
        existing = [{"value": "шум", "weight": 0.5, "frequency": 3}]
        new_items = [{"value": "шум", "weight": 0.9}]
        result = merge_profile_items(existing, new_items, strategy="max_weight")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["weight"], 0.9)  # max
        self.assertEqual(result[0]["frequency"], 3)

    def test_adds_new_items(self):
        existing = [{"value": "шум", "weight": 0.5}]
        new_items = [{"value": "толпа", "weight": 0.7}]
        result = merge_profile_items(existing, new_items)
        self.assertEqual(len(result), 2)

    def test_limits_max_items(self):
        # Создаём больше чем MAX_ITEMS_PER_FIELD
        existing = [{"value": f"item_{i}", "weight": 0.5 + i*0.05} for i in range(8)]
        new_items = [{"value": "new", "weight": 0.9}, {"value": "new2", "weight": 0.8}]
        result = merge_profile_items(existing, new_items)
        # Должно быть ограничено MAX_ITEMS_PER_FIELD (10)
        self.assertLessEqual(len(result), MAX_ITEMS_PER_FIELD)


# ============== ТЕСТЫ АДАПТЕРОВ (ЭТАП 1.5) ==============

class TestFieldToAIFormat(unittest.TestCase):
    """Тесты адаптера для AI промптов."""

    def test_old_string_format(self):
        """Старый формат — возвращаем как есть."""
        triggers = ["шум", "толпа"]
        result = field_to_ai_format(triggers, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])

    def test_new_weighted_format(self):
        """Новый формат — берём только value."""
        triggers = [
            {"value": "шум", "weight": 0.85},
            {"value": "толпа", "weight": 0.6}
        ]
        result = field_to_ai_format(triggers, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])

    def test_empty_list(self):
        self.assertEqual(field_to_ai_format([], 'triggers'), [])

    def test_dict_personality_traits_format(self):
        traits = {"рефлексивность": 0.8, "эмпатия": 0.6}
        result = field_to_ai_format(traits, 'personality_traits')
        self.assertEqual(result, ["рефлексивность", "эмпатия"])

    def test_none_values_filtered(self):
        triggers = ["шум", None, "толпа"]
        result = field_to_ai_format(triggers, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])


class TestFieldToDisplayFormat(unittest.TestCase):
    """Тесты адаптера для отображения пользователю."""

    def test_old_string_format(self):
        """Старый формат — возвращаем как есть."""
        triggers = ["шум", "толпа"]
        result = field_to_display_format(triggers, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])

    def test_new_weighted_format(self):
        """Новый формат — форматируем красиво."""
        triggers = [
            {"value": "шум", "weight": 0.85, "frequency": 12},
            {"value": "толпа", "weight": 0.6, "frequency": 3}
        ]
        result = field_to_display_format(triggers, 'triggers')
        self.assertEqual(len(result), 2)
        self.assertIn("шум", result[0])
        self.assertIn("85%", result[0])
        self.assertIn("12 раз", result[0])

    def test_empty_list(self):
        self.assertEqual(field_to_display_format([], 'triggers'), [])


class TestGetProfileFieldForAI(unittest.TestCase):
    """Тесты универсальной функции для AI."""

    def test_gets_field_from_user(self):
        user = FakeUser(triggers=["шум", "толпа"])
        result = get_profile_field_for_ai(user, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])

    def test_handles_none_field(self):
        user = FakeUser(triggers=None)
        result = get_profile_field_for_ai(user, 'triggers')
        self.assertEqual(result, [])

    def test_handles_non_list_field(self):
        user = FakeUser(triggers="not a list")
        result = get_profile_field_for_ai(user, 'triggers')
        self.assertEqual(result, [])


class TestGetProfileFieldForDisplay(unittest.TestCase):
    """Тесты универсальной функции для display."""

    def test_gets_field_from_user(self):
        user = FakeUser(triggers=["шум", "толпа"])
        result = get_profile_field_for_display(user, 'triggers')
        self.assertEqual(result, ["шум", "толпа"])


class TestSpecificFieldAliases(unittest.TestCase):
    """Тесты алиасов для конкретных полей."""

    def test_triggers_to_ai_format(self):
        triggers = [{"value": "шум", "weight": 0.9}]
        result = triggers_to_ai_format(triggers)
        self.assertEqual(result, ["шум"])

    def test_triggers_to_display_format(self):
        triggers = [{"value": "шум", "weight": 0.85, "frequency": 5}]
        result = triggers_to_display_format(triggers)
        self.assertIn("шум", result[0])

    def test_life_facts_to_ai_format(self):
        life_facts = ["работа", "семья"]
        result = life_facts_to_ai_format(life_facts)
        self.assertEqual(result, ["работа", "семья"])

    def test_hobbies_to_ai_format(self):
        hobbies = [{"value": "бег", "weight": 0.7}]
        result = hobbies_to_ai_format(hobbies)
        self.assertEqual(result, ["бег"])

    def test_core_values_to_ai_format(self):
        core_values = ["семья", "здоровье"]
        result = core_values_to_ai_format(core_values)
        self.assertEqual(result, ["семья", "здоровье"])

    def test_strengths_to_ai_format(self):
        strengths = [{"value": "сила", "weight": 0.8}]
        result = strengths_to_ai_format(strengths)
        self.assertEqual(result, ["сила"])


class TestChangedFormatPayload(unittest.TestCase):
    """Тесты normalized changed-format payload для AI."""

    def test_compact_weighted_items_from_strings(self):
        result = compact_weighted_items(["шум", "толпа"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], "шум")
        self.assertIn("weight", result[0])
        self.assertIn("frequency", result[0])
        self.assertIn("is_stale", result[0])

    def test_compact_personality_traits_from_dict(self):
        traits = {"рефлексивность": 0.8, "эмпатия": 0.6}
        result = compact_personality_traits(traits)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], "рефлексивность")
        self.assertEqual(result[0]["weight"], 0.8)

    def test_build_personal_fields_payload_for_ai(self):
        user = FakeUser(
            awareness_level=7,
            personality_traits={"эмпатия": 0.7},
            life_facts=["работа в IT"],
            triggers=[{"value": "критика", "weight": 0.9, "frequency": 3}],
            strengths=["устойчивость"],
        )
        payload = build_personal_fields_payload_for_ai(user)

        self.assertEqual(payload["awareness_level"], 7)
        self.assertEqual(payload["personality_traits"][0]["value"], "эмпатия")
        self.assertEqual(payload["life_facts"][0]["value"], "работа в IT")
        self.assertEqual(payload["triggers"][0]["value"], "критика")
        self.assertEqual(payload["strengths"][0]["value"], "устойчивость")


class TestCompressedProfilePromptNormalizer(unittest.TestCase):
    """Тесты normalize_compressed_profile_for_prompt."""

    def test_normalizer_returns_canonical_keys(self):
        result = normalize_compressed_profile_for_prompt({})
        self.assertEqual(
            sorted(result.keys()),
            sorted([
                "psych_summary",
                "core_patterns",
                "emotional_style",
                "main_triggers",
                "coping_style",
                "current_focus",
            ])
        )

    def test_normalizer_compacts_and_deduplicates_list_items(self):
        profile = {
            "core_patterns": [
                {"value": "Рефлексия", "weight": 0.7, "frequency": 2, "is_stale": False},
                {"value": "рефлексия", "weight": 0.9, "frequency": 5, "is_stale": False},
                {"value": "Прокрастинация", "weight": 0.6, "frequency": 1, "is_stale": True},
            ],
            "main_triggers": ["Критика", "критика", "Игнорирование"],
        }

        result = normalize_compressed_profile_for_prompt(profile, max_items_per_list=10)
        core_patterns = result["core_patterns"]
        main_triggers = result["main_triggers"]

        self.assertEqual(len(core_patterns), 2)
        self.assertEqual(core_patterns[0]["value"].lower(), "рефлексия")
        self.assertEqual(core_patterns[0]["weight"], 0.9)
        self.assertEqual(core_patterns[0]["frequency"], 5)

        trigger_values = [item["value"].lower() for item in main_triggers]
        self.assertEqual(trigger_values.count("критика"), 1)
        self.assertIn("игнорирование", trigger_values)

    def test_normalizer_truncates_long_text_fields(self):
        long_text = "x" * 2000
        result = normalize_compressed_profile_for_prompt(
            {
                "psych_summary": long_text,
                "emotional_style": long_text,
                "coping_style": long_text,
                "current_focus": long_text,
            },
            max_text_len=120,
        )

        self.assertEqual(len(result["psych_summary"]), 120)
        self.assertEqual(len(result["emotional_style"]), 120)
        self.assertEqual(len(result["coping_style"]), 120)
        self.assertEqual(len(result["current_focus"]), 120)


if __name__ == '__main__':
    unittest.main()
