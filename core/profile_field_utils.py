"""
Утилиты для очистки и поддержки актуальности полей психологического профиля.

Подход: безопасная очистка без изменения структуры данных и без миграций.
- Не меняет формат хранения (списки остаются списками, словари — словарями)
- Основные принципы:
  1. ИИ сам должен решать, что удалить (через {"remove": ...} маркеры)
  2. Автоматическая чистка — только для ЯВНЫХ дубликатов (точное текстовое совпадение)
  3. Консервативно: лучше оставить лишнее, чем удалить нужное
"""

import logging
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def deduplicate_list(items: List[Any]) -> List[Any]:
    """
    Удаляет точные дубликаты из списка, сохраняя порядок.
    
    Works with both strings and dict items.
    For dicts, uses JSON-like comparison for simple cases.
    
    Args:
        items: Список элементов
        
    Returns:
        Список без дубликатов
    """
    seen = []
    result = []
    
    for item in items:
        # Для dicts используем frozenset как ключ
        if isinstance(item, dict):
            key = ('dict', tuple(sorted(item.items())))
        else:
            key = (type(item).__name__, item)
        
        if key not in seen:
            seen.append(key)
            result.append(item)
    
    return result


def find_similar_items(
    items: List[str],
    similarity_threshold: float = 0.8
) -> List[Tuple[str, str]]:
    """
    Находит похожие элементы в списке (для логирования и подсказок ИИ).
    
    Использует простую метрику: Jaccard similarity по словам.
    
    Args:
        items: Список строк
        similarity_threshold: Порог похожести (0.0 - 1.0)
        
    Returns:
        Список пар (item1, item2) с похожими значениями
    """
    similar_pairs = []
    
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _are_similar(items[i], items[j], similarity_threshold):
                similar_pairs.append((items[i], items[j]))
    
    return similar_pairs


def _are_similar(text1: str, text2: str, threshold: float) -> bool:
    """Проверяет, похожи ли два текста по Jaccard similarity."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return False
    
    intersection = words1 & words2
    union = words1 | words2
    
    if not union:
        return False
    
    jaccard = len(intersection) / len(union)
    return jaccard >= threshold


def cleanup_profile_fields(user) -> Dict[str, int]:
    """
    Очищает поля профиля пользователя от явных дубликатов.
    
    Выполняет:
    1. Удаление точных дубликатов из списков
    2. Удаление пустых/None элементов
    3. В словарных полях — удаление записей с пустыми/None значениями
    
    Это полностью безопасная операция, не зависящая от внешних данных.
    
    Args:
        user: Объект User
        
    Returns:
        Dict[field_name, removed_count]
    """
    list_fields = [
        'life_facts', 'hobbies', 'core_values',
        'triggers', 'strengths', 'areas_for_growth',
        'habits', 'skills', 'aspirations'
    ]
    
    dict_fields = [
        'personality_traits', 'personality_insights'
    ]
    
    removed: Dict[str, int] = {}
    
    for field_name in list_fields:
        current_data = getattr(user, field_name, None)
        if not current_data or not isinstance(current_data, list):
            continue
        
        original_len = len(current_data)
        
        # Фильтруем None и пустые строки
        cleaned = [
            item for item in current_data
            if item is not None and item != "" and (not isinstance(item, str) or item.strip())
        ]
        
        # Удаляем точные дубликаты
        cleaned = deduplicate_list(cleaned)
        
        # Обновляем поле если были изменения
        if len(cleaned) < original_len:
            setattr(user, field_name, cleaned)
            removed[field_name] = original_len - len(cleaned)
            logger.debug(
                f"[cleanup_profile_fields] '{field_name}': "
                f"удалено {removed[field_name]} дубликатов/пустых элементов "
                f"(было {original_len}, стало {len(cleaned)})"
            )
    
    for field_name in dict_fields:
        current_data = getattr(user, field_name, None)
        if not current_data or not isinstance(current_data, dict):
            continue
        
        original_len = len(current_data)
        
        # Удаляем записи с пустыми/None значениями
        cleaned = {
            k: v for k, v in current_data.items()
            if v is not None and v != "" and (not isinstance(v, str) or v.strip())
        }
        
        if len(cleaned) < original_len:
            setattr(user, field_name, cleaned)
            removed[field_name] = original_len - len(cleaned)
            logger.debug(
                f"[cleanup_profile_fields] '{field_name}': "
                f"удалено {removed[field_name]} пустых записей"
            )
    
    if removed:
        total = sum(removed.values())
        logger.info(
            f"[cleanup_profile_fields] Пользователь {user.telegram_id}: "
            f"всего удалено {total} элементов: {removed}"
        )
    
    return removed


def merge_similar_items_in_list(
    items: List[str],
    similarity_threshold: float = 0.8
) -> List[str]:
    """
    Объединяет похожие элементы списка, оставляя самый длинный вариант.
    
    Например: ["бег", "бег по утрам", "маунтинбайк"] 
    → ["бег по утрам", "маунтинбайк"]
    
    Args:
        items: Список строк
        similarity_threshold: Порог похожести
        
    Returns:
        Список с объединёнными элементами
    """
    if not items:
        return []
    
    # Группируем похожие элементы
    groups: List[List[str]] = []
    
    for item in items:
        added_to_group = False
        
        for group in groups:
            if _are_similar(item, group[0], similarity_threshold):
                group.append(item)
                added_to_group = True
                break
        
        if not added_to_group:
            groups.append([item])
    
    # Из каждой группы берём самый длинный элемент
    result = []
    for group in groups:
        longest = max(group, key=len)
        result.append(longest)
    
    return result


def get_profile_field_stats(user) -> Dict[str, Dict[str, int]]:
    """
    Возвращает статистику по полям профиля (для мониторинга).
    
    Args:
        user: Объект User
        
    Returns:
        Dict[field_name, {"total": int, "unique": int}]
    """
    list_fields = [
        'life_facts', 'hobbies', 'core_values',
        'triggers', 'strengths', 'areas_for_growth',
        'habits', 'skills', 'aspirations'
    ]
    
    stats = {}
    
    for field_name in list_fields:
        current_data = getattr(user, field_name, [])
        if not isinstance(current_data, list):
            current_data = []
        
        cleaned = [
            item for item in current_data
            if item is not None and item != "" and (not isinstance(item, str) or item.strip())
        ]
        
        unique = len(set(str(i) for i in cleaned))
        
        stats[field_name] = {
            "total": len(cleaned),
            "unique": unique,
            "duplicates": len(cleaned) - unique,
        }
    
    dict_fields = ['personality_traits', 'personality_insights']
    
    for field_name in dict_fields:
        current_data = getattr(user, field_name, {})
        if not isinstance(current_data, dict):
            current_data = {}
        
        stats[field_name] = {
            "total": len(current_data),
        }
    
    return stats


# Singleton
_profile_field_utils_instance = None

def get_profile_field_utils():
    """Возвращает singleton экземпляр утилит."""
    global _profile_field_utils_instance
    if _profile_field_utils_instance is None:
        _profile_field_utils_instance = ProfileFieldUtils()
    return _profile_field_utils_instance


class ProfileFieldUtils:
    """Обёртка над функциями для удобного вызова."""

    def cleanup_user_profile(self, user) -> Dict[str, int]:
        """
        Выполняет безопасную очистку профиля от явных дубликатов.
        
        Returns:
            Dict[field_name, removed_count]
        """
        return cleanup_profile_fields(user)

    def get_stats(self, user) -> Dict[str, Dict[str, int]]:
        """Возвращает статистику полей профиля."""
        return get_profile_field_stats(user)

    def find_similar(self, field_name: str, user) -> List[Tuple[str, str]]:
        """Находит похожие элементы в указанном поле."""
        items = getattr(user, field_name, [])
        if not isinstance(items, list):
            return []
        
        string_items = [
            item if isinstance(item, str) 
            else item.get("value", str(item)) if isinstance(item, dict) 
            else str(item)
            for item in items
        ]
        
        return find_similar_items(string_items)
