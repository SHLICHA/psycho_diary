"""
Утилиты для работы с полями психологического профиля.

Включает:
1. Очистка от дубликатов (существующая функциональность)
2. Конвертация в обогащённый формат с весами (НОВОЕ)
3. Валидация элементов профиля (НОВОЕ)
4. TTL логика (НОВОЕ)
"""

import logging
from typing import Any, Dict, List, Set, Tuple, Optional
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

# Константы для TTL
DAYS_UNTIL_STALE = 30
DAYS_UNTIL_DELETE = 60
MIN_FREQUENCY_TO_KEEP = 2
MAX_ITEMS_PER_FIELD = 10

# Поля профиля для миграции
PROFILE_FIELDS = [
    'triggers',
    'life_facts',
    'hobbies',
    'core_values',
    'strengths',
    'areas_for_growth',
    'habits',
    'skills',
    'aspirations'
]


# ============== АДАПТЕРЫ ДЛЯ СОВМЕСТИМОСТИ (ЭТАП 1.5) ==============

def field_to_ai_format(field_data: List[Any], field_name: str) -> List[str]:
    """
    Конвертирует данные поля в формат для AI промптов.
    
    Старый формат: ["шум", "толпа"] → возвращаем как есть
    Новый формат: [{"value": "шум", ...}] → берём только value
    
    Args:
        field_data: Данные поля (строки или dict)
        field_name: Имя поля для логирования
        
    Returns:
        Список строк для AI
    """
    if not field_data:
        return []
    
    # Определяем формат по первому элементу
    if isinstance(field_data[0], str):
        # Старый формат — возвращаем как есть
        return [str(item) for item in field_data if item]
    
    if isinstance(field_data[0], dict):
        # Новый формат — берём только value
        result = []
        for item in field_data:
            value = item.get("value")
            if value:
                result.append(str(value))
        return result
    
    # Неизвестный формат — логируем и возвращаем как есть
    logger.warning(f"[field_to_ai_format] Неизвестный формат поля {field_name}: {type(field_data[0])}")
    return [str(item) for item in field_data if item]


def field_to_display_format(field_data: List[Any], field_name: str) -> List[str]:
    """
    Конвертирует данные поля в формат для отображения пользователю.
    
    Старый формат: ["шум", "толпа"] → возвращаем как есть
    Новый формат: [{"value": "шум", "weight": 0.85, "frequency": 12}] → форматируем
    
    Args:
        field_data: Данные поля (строки или dict)
        field_name: Имя поля для логирования
        
    Returns:
        Список строк для отображения
    """
    if not field_data:
        return []
    
    if isinstance(field_data[0], str):
        # Старый формат — возвращаем как есть
        return [str(item) for item in field_data if item]
    
    if isinstance(field_data[0], dict):
        # Новый формат — используем format_for_user_display
        return format_for_user_display(field_data)
    
    # Неизвестный формат
    logger.warning(f"[field_to_display_format] Неизвестный формат поля {field_name}: {type(field_data[0])}")
    return [str(item) for item in field_data if item]


def get_profile_field_for_ai(user, field_name: str) -> List[str]:
    """
    Получает данные поля профиля в формате для AI.
    
    Универсальная функция для любого поля профиля.
    
    Args:
        user: Объект User
        field_name: Имя поля (triggers, life_facts, etc.)
        
    Returns:
        Список строк для AI
    """
    field_data = getattr(user, field_name, None)
    if not field_data or not isinstance(field_data, list):
        return []
    
    return field_to_ai_format(field_data, field_name)


def get_profile_field_for_display(user, field_name: str) -> List[str]:
    """
    Получает данные поля профиля в формате для отображения.
    
    Универсальная функция для любого поля профиля.
    
    Args:
        user: Объект User
        field_name: Имя поля (triggers, life_facts, etc.)
        
    Returns:
        Список строк для отображения
    """
    field_data = getattr(user, field_name, None)
    if not field_data or not isinstance(field_data, list):
        return []
    
    return field_to_display_format(field_data, field_name)


# Алиасы для конкретных полей (удобство)
def triggers_to_ai_format(triggers) -> List[str]:
    """Конвертирует triggers для AI промптов."""
    return field_to_ai_format(triggers, 'triggers')


def triggers_to_display_format(triggers) -> List[str]:
    """Конвертирует triggers для отображения пользователю."""
    return field_to_display_format(triggers, 'triggers')


def life_facts_to_ai_format(life_facts) -> List[str]:
    """Конвертирует life_facts для AI промптов."""
    return field_to_ai_format(life_facts, 'life_facts')


def life_facts_to_display_format(life_facts) -> List[str]:
    """Конвертирует life_facts для отображения пользователю."""
    return field_to_display_format(life_facts, 'life_facts')


def hobbies_to_ai_format(hobbies) -> List[str]:
    """Конвертирует hobbies для AI промптов."""
    return field_to_ai_format(hobbies, 'hobbies')


def hobbies_to_display_format(hobbies) -> List[str]:
    """Конвертирует hobbies для отображения пользователю."""
    return field_to_display_format(hobbies, 'hobbies')


def core_values_to_ai_format(core_values) -> List[str]:
    """Конвертирует core_values для AI промптов."""
    return field_to_ai_format(core_values, 'core_values')


def core_values_to_display_format(core_values) -> List[str]:
    """Конвертирует core_values для отображения пользователю."""
    return field_to_display_format(core_values, 'core_values')


def strengths_to_ai_format(strengths) -> List[str]:
    """Конвертирует strengths для AI промптов."""
    return field_to_ai_format(strengths, 'strengths')


def strengths_to_display_format(strengths) -> List[str]:
    """Конвертирует strengths для отображения пользователю."""
    return field_to_display_format(strengths, 'strengths')


# ============== НОВЫЕ ФУНКЦИИ ДЛЯ ВЕСОВ И TTL ==============

def create_weighted_item(value: str, weight: float = 0.5) -> Dict[str, Any]:
    """
    Создаёт элемент профиля в обогащённом формате с весами.
    
    Args:
        value: Основное значение (строка)
        weight: Вес/важность (0-1), дефолт 0.5
        
    Returns:
        Dict с metadata
    """
    now = timezone.now()
    return {
        "value": value,
        "weight": weight,
        "frequency": 1,
        "added_at": now.isoformat(),
        "last_seen": now.isoformat(),
        "is_stale": False
    }


def convert_to_weighted_format(items: List[Any]) -> List[Dict[str, Any]]:
    """
    Конвертирует список элементов профиля в обогащённый формат с весами.
    
    Старый формат: ["шум", "толпа"]
    Новый формат: [{"value": "шум", "weight": 0.5, "frequency": 1, ...}]
    
    Args:
        items: Список элементов (строки или dict)
        
    Returns:
        Список элементов в новом формате
    """
    result = []
    now = timezone.now()
    
    for item in items:
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
            # Уже новый формат — проверяем и дополняем
            if "value" in item:
                # Дополняем missing fields
                enriched = {
                    "value": item.get("value", ""),
                    "weight": item.get("weight", 0.5),
                    "frequency": item.get("frequency", 1),
                    "added_at": item.get("added_at", now.isoformat()),
                    "last_seen": item.get("last_seen", now.isoformat()),
                    "is_stale": item.get("is_stale", False)
                }
                result.append(enriched)
            else:
                # Dict без value — логируем и пропускаем
                logger.warning(f"[convert_to_weighted] Пропущен элемент без 'value': {item}")
        else:
            # Неизвестный формат — логируем и пропускаем
            logger.warning(f"[convert_to_weighted] Пропущен элемент неизвестного типа: {type(item)}")
    
    return result


def validate_profile_item(item: Any) -> bool:
    """
    Валидирует элемент профиля.
    
    Args:
        item: Элемент (строка или dict)
        
    Returns:
        True если валидный
    """
    if isinstance(item, str):
        return bool(item and item.strip())
    if isinstance(item, dict):
        return "value" in item and isinstance(item.get("weight"), (int, float))
    return False


def validate_weighted_field(items: List[Any]) -> Tuple[List[Dict], List[str]]:
    """
    Валидирует поле профиля, возвращает валидные и ошибки.
    
    Args:
        items: Список элементов
        
    Returns:
        (valid_items, error_messages)
    """
    valid = []
    errors = []
    
    for i, item in enumerate(items):
        if validate_profile_item(item):
            if isinstance(item, dict):
                valid.append(item)
            else:
                # Конвертируем строку в dict
                valid.append(create_weighted_item(item))
        else:
            errors.append(f"Элемент {i}: невалидный формат — {item}")
    
    return valid, errors


def update_item_frequency(items: List[Dict], value: str) -> List[Dict]:
    """
    Обновляет frequency для элемента с указанным value.
    
    Если элемент найден — увеличиваем frequency и обновляем last_seen.
    Если не найден — добавляем новый.
    
    Args:
        items: Список элементов в weighted формате
        value: Значение для поиска/обновления
        
    Returns:
        Обновлённый список
    """
    now = timezone.now()
    found = False
    
    for item in items:
        if item.get("value") == value:
            item["frequency"] = item.get("frequency", 0) + 1
            item["last_seen"] = now.isoformat()
            item["is_stale"] = False
            found = True
            break
    
    if not found:
        # Добавляем новый элемент
        items.append(create_weighted_item(value, weight=0.5))
    
    return items


def mark_stale_items(items: List[Dict]) -> List[Dict]:
    """
    Помечает элементы как stale (устаревшие) на основе TTL.
    
    Элемент становится stale если не встречался более DAYS_UNTIL_STALE дней.
    
    Args:
        items: Список элементов в weighted формате
        
    Returns:
        Список с обновлёнными is_stale флагами
    """
    now = timezone.now()
    stale_threshold = now - timedelta(days=DAYS_UNTIL_STALE)
    
    for item in items:
        last_seen_str = item.get("last_seen")
        if last_seen_str:
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                if last_seen < stale_threshold:
                    item["is_stale"] = True
            except (ValueError, TypeError):
                # Не удалось распарсить дату — не помечаем как stale
                pass
    
    return items


def cleanup_stale_items(items: List[Dict]) -> List[Dict]:
    """
    Удаляет устаревшие элементы на основе TTL.
    
    Удаляются если:
    - is_stale = True И
    - frequency < MIN_FREQUENCY_TO_KEEP И
    - старше DAYS_UNTIL_DELETE дней
    
    Args:
        items: Список элементов в weighted формате
        
    Returns:
        Очищенный список
    """
    now = timezone.now()
    delete_threshold = now - timedelta(days=DAYS_UNTIL_DELETE)
    
    result = []
    removed_count = 0
    
    for item in items:
        should_remove = False
        
        if item.get("is_stale"):
            frequency = item.get("frequency", 0)
            last_seen_str = item.get("last_seen")
            
            if frequency < MIN_FREQUENCY_TO_KEEP:
                # Проверяем возраст
                if last_seen_str:
                    try:
                        last_seen = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                        if last_seen < delete_threshold:
                            should_remove = True
                    except (ValueError, TypeError):
                        # Не удалось определить дату — не удаляем
                        pass
                else:
                    # Нет даты — удаляем
                    should_remove = True
        
        if should_remove:
            removed_count += 1
            logger.debug(f"[cleanup_stale] Удалён элемент: {item.get('value')}")
        else:
            result.append(item)
    
    if removed_count > 0:
        logger.info(f"[cleanup_stale] Удалено {removed_count} устаревших элементов")
    
    return result


def sort_by_weight(items: List[Dict], reverse: bool = True) -> List[Dict]:
    """
    Сортирует элементы по weight.
    
    Args:
        items: Список элементов в weighted формате
        reverse: Если True — по убыванию (самые важные first)
        
    Returns:
        Отсортированный список
    """
    return sorted(items, key=lambda x: x.get("weight", 0.5), reverse=reverse)


def get_top_items(items: List[Dict], limit: int = 5) -> List[Dict]:
    """
    Возвращает топ-N элементов по weight.
    
    Args:
        items: Список элементов в weighted формате
        limit: Количество элементов
        
    Returns:
        Топ-N элементов
    """
    sorted_items = sort_by_weight(items, reverse=True)
    return sorted_items[:limit]


def format_for_user_display(items: List[Dict]) -> List[str]:
    """
    Форматирует элементы для отображения пользователю.
    
    Args:
        items: Список элементов в weighted формате
        
    Returns:
        Список строк для отображения
    """
    result = []
    for item in items:
        value = item.get("value", "")
        weight = item.get("weight", 0.5)
        frequency = item.get("frequency", 1)
        
        # Форматируем: "шум (важность: 85%, встречается 12 раз)"
        weight_pct = int(weight * 100)
        result.append(f"{value} (важность: {weight_pct}%, встречается {frequency} раз)")
    
    return result


def merge_profile_items(
    existing: List[Dict],
    new_items: List[Dict],
    strategy: str = "max_weight"
) -> List[Dict]:
    """
    Объединяет существующие элементы с новыми.
    
    Strategies:
    - "max_weight": оставляем max weight
    - "sum_frequency": суммируем frequency
    - "replace": заменяем полностью
    
    Args:
        existing: Существующие элементы
        new_items: Новые элементы от AI
        strategy: Стратегия объединения
        
    Returns:
        Объединённый список
    """
    result = existing.copy()
    
    for new_item in new_items:
        new_value = new_item.get("value")
        if not new_value:
            continue
        
        # Ищем существующий элемент
        found = False
        for existing_item in result:
            if existing_item.get("value") == new_value:
                found = True
                
                if strategy == "max_weight":
                    # Оставляем max weight
                    existing_item["weight"] = max(
                        existing_item.get("weight", 0.5),
                        new_item.get("weight", 0.5)
                    )
                elif strategy == "sum_frequency":
                    # Суммируем frequency
                    existing_item["frequency"] = (
                        existing_item.get("frequency", 0) + 
                        new_item.get("frequency", 1)
                    )
                # Обновляем last_seen
                existing_item["last_seen"] = timezone.now().isoformat()
                existing_item["is_stale"] = False
                break
        
        if not found:
            # Добавляем новый элемент
            result.append(new_item)
    
    # Ограничиваем количество элементов
    if len(result) > MAX_ITEMS_PER_FIELD:
        result = sort_by_weight(result, reverse=True)[:MAX_ITEMS_PER_FIELD]
    
    return result


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
