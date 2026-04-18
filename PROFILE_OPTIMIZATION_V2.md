# Профиль пользователя v2.2 — Подробный план оптимизации

> **Версия:** 2.2  
> **Дата:** 2026-04-18  
> **Статус:** 🔄 Готов к реализации

---

## 🎯 Цели

1. **Добавить веса** к полям профиля (triggers, life_facts, hobbies и т.д.)
2. **Добавить TTL** — автоматическая очистка устаревших данных
3. **Улучшить compressed_psych_profile** — использовать веса для AI
4. **Плавная миграция** — без потери данных, без простоев

---

## ⚠️ Главное требование

**Полный профиль (`triggers`, `life_facts`, `hobbies` и т.д.) остаётся для чтения пользователю** — мы его НЕ удаляем и НЕ меняем структуру.

---

## 📊 Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                     ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ⚠️ ВАРИАНТ РЕАЛИЗАЦИИ: Изолированные поля                     │
│  Каждое поле мигрируется отдельно — если одно сломается,       │
│  остальные работают как прежде                                  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📖 ПОЛЯ ПРОФИЛЯ (постепенно мигрируют)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ triggers: [{"value": "шум", "weight": 0.85,            │   │
│  │             "frequency": 12, "last_seen": ...}]        │   │
│  │ life_facts: [{"value": "...", "weight": 0.6, ...}]     │   │
│  │ hobbies: [{"value": "...", "weight": 0.7, ...}]        │   │
│  │ core_values: [...], strengths: [...], и т.д.           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  🤖 COMPRESSED PROFILE (генерируется из полей)                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ compressed_psych_profile: {                             │   │
│  │   "psych_summary": "...",                               │   │
│  │   "core_patterns": [{"pattern": "...", "weight": 0.9}],│   │
│  │   "main_triggers": [{"trigger": "...", "weight": 0.8}],│   │
│  │   ...                                                   │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Безопасность

| Принцип | Реализация |
|---------|------------|
| **Изоляция полей** | Каждое поле (`triggers`, `life_facts`...) — отдельно |
| **Постепенность** | Мигрируем поле за полем, не всё сразу |
| **Валидация на входе** | AI возвращает JSON → проверяем перед сохранением |
| **Fallback** | Если формат сломался — сохраняем как строку, логируем ошибку |

---

## 📋 Этапы реализации (Вариант В)

### Этап 1: Подготовка (Дни 1-2)

**Что делаем:** Создаём утилиты для работы с новым форматом

**Структура элемента:**
```python
{
    "value": "шум",                    # основное значение (строка)
    "weight": 0.85,                    # 0-1: важность (дефолт: 0.5)
    "frequency": 12,                   # сколько раз встречался
    "added_at": "2026-01-15T10:00:00Z",# когда добавлено
    "last_seen": "2026-04-18T08:00:00Z",# последний раз виден
    "is_stale": False                  # помечается при TTL
}
```

**Поля для миграции (в порядке приоритета):**
1. `triggers` — самые важные для AI
2. `life_facts` — важный контекст
3. `hobbies`, `core_values` — средний приоритет
4. `strengths`, `areas_for_growth`, `habits`, `skills`, `aspirations` — низкий приоритет

**Файлы:**
- `core/profile_field_utils.py` — утилиты для конвертации и валидации ✅

---

### Этап 1.5: Адаптеры совместимости (Дни 2-3)

**Что делаем:** Создаём адаптеры для безопасной миграции без слома анализа

**Зачем:** AI промпты ожидают `["шум", "толпа"]`, а после миграции будет `[{"value": "шум", ...}]`

**Адаптеры:**
```python
# core/profile_field_utils.py

# Для AI промптов — возвращаем только value
field_to_ai_format(triggers) → ["шум", "толпа"]

# Для отображения — форматируем с весами
field_to_display_format(triggers) → ["шум (важность: 85%, встречается 12 раз)"]

# Универсальные функции
get_profile_field_for_ai(user, 'triggers')
get_profile_field_for_display(user, 'triggers')
```

**Тесты:** 17 новых тестов для адаптеров ✅

---

### Этап 2: Миграция triggers (Дни 3-5)

**Что делаем:** Мигрируем первое поле — `triggers`

**Процесс:**
```
1. Создать временное поле triggers_temp
2. Конвертировать: ["шум", "толпа"] → [{"value": "шум", "weight": 0.5, ...}]
3. Валидация: проверить что все элементы имеют нужные поля
4. Заменить: triggers = triggers_temp
5. Удалить временное поле
```

**Валидация:**
```python
def validate_profile_item(item) -> bool:
    """Проверяет элемент профиля."""
    if isinstance(item, str):
        return True  # старый формат — пропускаем
    if isinstance(item, dict):
        return 'value' in item and isinstance(item.get('weight'), (int, float))
    return False
```

**Тестирование:**
- Мигрировать 10 пользователей вручную
- Проверить что бот работает
- Проверить что AI анализ работает

**Файлы:**
- `diary/tasks/migrate_triggers.py` — **НОВЫЙ** — миграция первого поля

---

### Этап 3: Миграция остальных полей (Дни 6-10)

**Что делаем:** Мигрируем остальные поля по очереди

| День | Поле | notes |
|------|------|-------|
| 6 | `life_facts` | важный контекст |
| 7 | `hobbies`, `core_values` | средний приоритет |
| 8 | `strengths`, `areas_for_growth` | |
| 9 | `habits`, `skills` | |
| 10 | `aspirations` | последнее |

**Каждое поле:**
- Отдельная задача
- Логирование прогресса
- Возможность pause/resume

---

### Этап 3.5: Логика накопления весов и частоты (Дни 10-12)

**Что делаем:** Реализуем автоматический подсчёт весов при каждом анализе

**Два механизма:**

#### 3.5.1 AI-указанные веса (приоритетный)
AI может явно указать вес в ответе:
```json
{
  "triggers": [
    {"value": "шум", "weight": 0.9},
    {"value": "толпа", "weight": 0.6}
  ]
}
```

**Реализация:**
- Обновить промпты чтобы AI возвращал веса
- В `_update_user_profile` добавить парсинг весов от AI

#### 3.5.2 Автоматический подсчёт (fallback)
Если AI не указал вес — считаем автоматически:
```python
def merge_profile_items(existing_items: List[Dict], new_items: List[str]) -> List[Dict]:
    """
    Обновляет веса на основе частоты появления.
    
    Логика:
    - frequency += 1 при каждом появлении
    - weight = min(1.0, frequency / 10)  # 10 появлений = weight 1.0
    - last_seen = текущая дата
    """
```

**Правила накопления:**
| Параметр | Логика |
|----------|--------|
| `frequency` | +1 при каждом упоминании в анализе |
| `weight` | `min(1.0, frequency / 10)` — 10 упоминаний = 100% |
| `added_at` | Дата первого появления (не меняется) |
| `last_seen` | Обновляется при каждом упоминании |
| `is_stale` | `True` если не было упоминаний 30 дней |

**Файлы:**
- `diary/services/profile_update_service.py` — **НОВЫЙ** — логика обновления весов
- `core/profile_field_utils.py` — добавить `merge_profile_items`, `update_item_frequency`

**Интеграция:**
```python
# В full_day_analysis_service.py _update_user_profile
from core.profile_field_utils import merge_profile_items

for field_name in list_field_names:
    current_items = getattr(user, field_name, [])
    new_items_from_ai = profile_updates.get(field_name, [])
    
    # Используем merge вместо простого добавления
    updated_items = merge_profile_items(current_items, new_items_from_ai)
    setattr(user, field_name, updated_items)
```

---

### Этап 4: TTL и автоочистка (Дни 13-14)

**Что делаем:** Добавляем TTL логику

**Правила:**
| Параметр | Значение |
|----------|----------|
| `days_until_stale` | 30 дней |
| `days_until_delete` | 60 дней (только при frequency=1) |
| `min_frequency_to_keep` | 2 |

**Вызов очистки:**
- При каждом weekly analysis
- Celery задача раз в неделю

**Файлы:**
- `diary/services/profile_cleanup_service.py` — **НОВЫЙ**
- `diary/tasks/profile_cleanup.py` — **НОВЫЙ**

---

### Этап 4.5: Обновление AI промптов для работы с весами (Дни 14-16)

**Что делаем:** Адаптируем промпты для использования нового формата

#### 4.5.1 Инструкция для AI о формате весов
Добавить в системные промпты:
```
При возврате данных о профиле используй формат с весами:
{
  "triggers": [
    {"value": "триггер", "weight": 0.0-1.0, "reason": "почему это важно"}
  ]
}

 weight: 0.0-1.0 — важность (1.0 = максимальная)
 reason: краткое объяснение выбора
```

#### 4.5.2 Промпты для разных типов анализа

**user_profile_analysis** — должен возвращать веса:
```python
# В промпте добавить:
"Когда добавляешь новые элементы в профиль, укажи их важность:
- weight: 0.0-1.0 (0.9+ = критически важно, 0.7+ = важно, 0.5 = обычное)
- reason: причина почему это добавляется"
```

**full_day_analysis** — обновление профиля с весами:
```python
# user_profile_updates должен быть:
{
  "triggers": [
    {"value": "шум", "weight": 0.8},  # AI указал вес
    "толпа"  # AI не указал — будет рассчитано автоматически
  ]
}
```

**weekly_analysis** — агрегация весов:
```python
# При обновлении профиля учитывать существующие веса:
# - Если элемент уже есть: weight = max(старый_вес, новый_вес)
# - frequency += 1
```

#### 4.5.3 Список промптов для обновления

| Промпт | Изменение |
|--------|-----------|
| `user_profile_analysis` | Добавить инструкцию о весах |
| `full_day_analysis` | Обработка `weight` в `user_profile_updates` |
| `weekly_analysis` | Агрегация весов между неделями |
| `profile_change_analysis` | Учитывать динамику весов |

**Файлы:**
- `prompts/templates/user_profile_analysis.py` — добавить инструкцию о весах
- `prompts/templates/full_day_analysis.py` — парсинг весов
- `prompts/templates/weekly_analysis.py` — агрегация весов

#### 4.5.4 Feature flag для поэтапного включения

```python
# core/settings.py
PROFILE_WEIGHTS_ENABLED = config('PROFILE_WEIGHTS_ENABLED', default=False)
```

**Этапы включения:**
1. `PROFILE_WEIGHTS_ENABLED = False` — AI игнорирует веса, работает автоматический подсчёт
2. `PROFILE_WEIGHTS_ENABLED = True` — AI начинает указывать веса

---

### Этап 5: Compressed Profile с весами (Дни 17-18)

**Что делаем:** Обогащаем `compressed_psych_profile` весами

**Использование весов:**
```python
# Сортировка по weight для AI
top_triggers = sorted(triggers, key=lambda x: x.get('weight', 0.5), reverse=True)[:5]
```

**Файлы:**
- `diary/services/compressed_profile_service.py` — обновить

---

### Этап 6: LITE v2 промпты (Дни 19-20)

**Что делаем:** Создаём промпты с весами

**Feature flag:**
```python
USE_LITE_V2 = config('USE_LITE_V2', default=False)
```

**Файлы:**
- `core/settings.py` — добавить flag
- `prompts/templates/incremental_day_analysis_lite.py`
- `prompts/templates/full_day_analysis_lite.py`

---

### Этап 7: Удаление адаптеров (Дни 21-22)

**Что делаем:** Убираем адаптеры после полной миграции

**Когда:** После того как все поля мигрированы и протестированы

**Что делаем:**
1. Обновить все места использования полей профиля напрямую
2. Убрать вызовы `field_to_ai_format()`, `field_to_display_format()`
3. Удалить адаптеры из `core/profile_field_utils.py`
4. Убедиться что AI промпты работают с новым форматом

**Места для обновления:**
- `diary/services/user_profile_service.py` — display профиля
- `prompts/templates/*.py` — формирование user_profile для AI
- Любые другие места где используются поля профиля

---

## 🔧 Технические детали

### Константы (для настройки)

```python
# diary/services/profile_weight_service.py

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

# TTL константы
DAYS_UNTIL_STALE = 30
DAYS_UNTIL_DELETE = 60
MIN_FREQUENCY_TO_KEEP = 2
MAX_ITEMS_PER_FIELD = 10
```

### Функция конвертации

```python
def convert_to_weighted(values: list) -> list:
    """Конвертирует старый формат ['шум', 'толпа'] в новый с весами."""
    now = timezone.now()
    result = []
    
    for value in values:
        if isinstance(value, str):
            result.append({
                "value": value,
                "weight": 0.5,  # дефолтный вес
                "frequency": 1,
                "added_at": now.isoformat(),
                "last_seen": now.isoformat(),
                "is_stale": False
            })
        elif isinstance(value, dict):
            # Уже новый формат
            result.append(value)
    
    return result
```

---

## ✅ Гарантии

| Гарантия | Как обеспечивается |
|----------|-------------------|
| **Профиль читаем** | Те же поля `triggers`, `life_facts` остаются без изменений |
| **Обратная совместимость** | Старые промпты работают как прежде |
| **Без потери данных** | Metadata добавляется, не заменяет |
| **Плавная миграция** | Батчи по 50 пользователей, feature flag |
| **Нет простоев** | Background tasks, не блокируют пользователей |

---

## 📁 Файлы для изменения

| Файл | Изменение | Этап |
|------|-----------|------|
| `core/profile_field_utils.py` | **НОВЫЙ** — утилиты конвертации и валидации | 1 |
| `diary/tasks/migrate_triggers.py` | **НОВЫЙ** — миграция triggers | 2 |
| `diary/tasks/migrate_life_facts.py` | **НОВЫЙ** — миграция life_facts | 3 |
| `diary/tasks/migrate_hobbies.py` | **НОВЫЙ** — миграция hobbies, core_values | 3 |
| `diary/tasks/migrate_strengths.py` | **НОВЫЙ** — миграция strengths, areas_for_growth | 3 |
| `diary/tasks/migrate_habits.py` | **НОВЫЙ** — миграция habits, skills | 3 |
| `diary/tasks/migrate_aspirations.py` | **НОВЫЙ** — миграция aspirations | 3 |
| `diary/services/profile_cleanup_service.py` | **НОВЫЙ** — TTL логика | 4 |
| `diary/tasks/profile_cleanup.py` | **НОВЫЙ** — Celery задача очистки | 4 |
| `diary/services/compressed_profile_service.py` | Использовать веса | 5 |
| `core/settings.py` | `USE_LITE_V2` flag | 6 |
| `prompts/templates/incremental_day_analysis_lite.py` | **НОВЫЙ** | 6 |
| `prompts/templates/full_day_analysis_lite.py` | **НОВЫЙ** | 6 |

---

## 📊 Ожидаемый результат

| Метрика | До | После |
|---------|-----|-------|
| Токены на LITE анализ | 100% | 30-50% |
| Структура полей | Простые списки `["шум", "толпа"]` | Обогащённые `[{"value": "шум", "weight": 0.85, ...}]` |
| Изоляция | Нет | Каждое поле мигрируется отдельно |
| TTL | Нет | 30 дней → stale, 60 дней → удаление |
| Вес полей | Нет | 0-1 (важность) |
| Частота упоминаний | Нет | Отслеживается |

---

## 🚀 Запуск

1. **Этап 1-2** можно делать параллельно с другими задачами
2. **Этап 4** (миграция) — после того как накопится достаточно данных в metadata
3. **Этап 5** (LITE v2) — включить через feature flag после тестирования

---

*Документ обновлён: 2026-04-18*