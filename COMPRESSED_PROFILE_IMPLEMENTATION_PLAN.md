# 🚀 План внедрения Compressed Profile Optimization

> **Проект:** Psycho Diary
> **Дата создания:** 2026-04-09
> **Дата обновления:** 2026-04-09
> **Статус:** 🔄 Этапы 1-6 ЗАВЕРШЕНЫ, бэкфилл выполнен на production
> **Контекст:** ~295 пользователей, ~90+ с данными профиля, ~20 активных

---

## 📊 Итоги дня (2026-04-09)

### ✅ Выполнено (Этапы 1-6)

| Этап | Что сделано | Файлы | Статус |
|------|------------|-------|--------|
| **1. Миграции** | 2 новых поля в БД | `users/migrations/0036`, `diary/migrations/0095` | ✅ |
| **2. Compressed сервис** | Heuristic-сжатие профиля без AI | `diary/services/compressed_profile_service.py` (565 строк) | ✅ |
| **3. Day context сервис** | Перепаковка DailyAnalysis → day_context_summary | `diary/services/day_context_service.py` (380 строк) | ✅ |
| **4. Интеграция compressed** | Авто-генерация при user_profile_analysis | `diary/services/user_profile_analysis_service.py` (+17 строк) | ✅ |
| **5. Интеграция day_context** | Авто-генерация при full_day_analysis | `diary/services/full_day_analysis_service.py` (+14 строк) | ✅ |
| **6. Бэкфилл + админка** | Management command + поля в админке | `backfill_compressed_data.py`, `users/admin.py`, `diary/admin.py` | ✅ |

### 📈 Результаты бэкфилла на production

```
── Шаг 1: compressed_psych_profile ──
Всего пользователей: 295
  Обработано: 295
  Сгенерировано: 0 (у 204 нет данных, у 91 уже был)
  Уже есть: 91
  Нет данных: 204
  Ошибки: 0

── Шаг 2: day_context_summary ──
CombinedDiaryEntry за последние 30 дней: 46
  Обработано: 46
  Сгенерировано: 0
  Уже есть: 46 (заполнены daily analysis)
  Нет данных: 0
  Ошибки: 0
```

### ✅ Тесты

| Файл | Результат |
|------|-----------|
| `test_compressed_profile_service.py` | 13 passed, 5 skipped (async) |
| `test_diary_models.py` | 37 passed, 3 pre-existing failures |
| End-to-end на реальных данных | ✅ |

### 📋 Что осталось (Этапы 7-11)

| Этап | Что делать | Когда |
|------|-----------|-------|
| **7. LITE v2 промпты** | Новые промпты incremental_day_analysis_lite_v2 + full_day_analysis_lite_v2 | Следующий раз |
| **8. Feature flag** | Переключатель USE_LITE_V2 + fallback | После промптов |
| **9. ai_state_data** | Привести к единой структуре | После промптов |
| **10. Мониторинг** | Логи, метрики, A/B тест | После переключения |
| **11. Очистка** | Убрать старые пути (через 2-4 недели) | Позже |

---

## 📋 Общая стратегия

Переход от **Data-heavy AI** → **State-aware AI**:
- Вместо передачи всех сырых данных каждый раз — передаём сжатый контекст
- 2 новых слоя данных: `compressed_psych_profile` (раз в неделю) + `day_context_summary` (каждый день)
- LITE-режим экономит 30-50% токенов, Premium не меняется

**Главный принцип:** ничего не ломаем. Оба пути (старый и новый) работают параллельно.

---

## 🗺️ Этапы (по порядку, каждый автономный)

---

### ЭТАП 1: Миграции БД

**Цель:** Добавить 2 новых поля. Только добавить. Не использовать.

**Файлы:**
- `users/migrations/00XX_user_compressed_psych_profile.py`
- `diary/migrations/00XX_combineddiaryentry_day_context_summary.py`

**Что делаем:**

**1.1. Добавить поле в User:**
```python
compressed_psych_profile = models.JSONField(
    null=True,
    blank=True,
    default=dict,
    verbose_name="Сжатый психологический профиль",
    help_text="Сжатое представление профиля для LITE-анализов. Генерируется weekly analysis."
)
```

**1.2. Добавить поле в CombinedDiaryEntry:**
```python
day_context_summary = models.JSONField(
    null=True,
    blank=True,
    default=dict,
    verbose_name="Контекст дня (сжатый)",
    help_text="Сжатое представление контекста дня. Генерируется при анализе дня."
)
```

**Структуры данных:**

`compressed_psych_profile`:
```json
{
  "psych_summary": "Краткое описание личности (5-7 предложений)",
  "core_patterns": ["самокритика", "поиск одобрения", "избегание конфликтов"],
  "emotional_style": "склонен подавлять эмоции, но испытывает внутреннее напряжение",
  "main_triggers": ["критика", "игнорирование"],
  "coping_style": "избегание + рационализация",
  "current_focus": "работа"
}
```

`day_context_summary`:
```json
{
  "emotional_arc": "тревога → раздражение → усталость",
  "key_topics": ["работа", "самооценка"],
  "main_conflict": "ожидания vs реальность",
  "dominant_pattern": "катастрофизация",
  "trend": "declining"
}
```

**Проверка:**
- [ ] `python manage.py makemigrations`
- [ ] `python manage.py showmigrations` — обе миграции видны
- [ ] `python manage.py migrate` — применились
- [ ] Проверить в БД: поля добавлены, nullable

**Риск:** Нулевой. Nullable поля, без данных.
**Время:** 30 минут.
**Откат:** Удалить миграции.

---

### ЭТАП 2: Сервис для сжатия профиля (heuristic)

**Цель:** Создать сервис, который генерирует `compressed_psych_profile` из текущих полей User — БЕЗ AI. Работает для пользователей с минимальными данными.

**Файлы:**
- `diary/services/compressed_profile_service.py` (новый)
- `tests/test_compressed_profile_service.py` (новый)

**Что делаем:**

**2.1. Создать `CompressedProfileService`:**

```python
class CompressedProfileService:
    """Генерирует compressed_psych_profile из текущих полей User."""

    def generate_from_user(self, user: User) -> dict:
        """
        Собирает compressed профиль из полей User.
        Без AI. heuristic-подход.

        Returns: dict или None если данных недостаточно.
        """

    def generate_from_full_profile(self, full_profile: dict) -> dict:
        """
        Собирает compressed профиль из полного профиля
        (после user_profile_analysis, когда есть personality_description).
        """

    def _extract_top_items(items: list, top: int = 5) -> list:
        """Берёт топ-N элементов из списка."""

    def _infer_emotional_style(triggers: list, traits: dict) -> str:
        """Выводит эмоциональный стиль из триггеров и черт."""

    def _infer_coping_style(areas: list, strengths: list) -> str:
        """Выводит coping style из зон роста и сильных сторон."""

    def _get_current_focus(life_facts: list, aspirations: list) -> str:
        """Определяет текущий фокус из фактов жизни и стремлений."""
```

**2.2. Логика заполнения:**

| Если у пользователя есть... | Стратегия |
|---------------------------|-----------|
| `personality_description` + WeeklyAnalysis | Берём description[:500] + топ-5 из каждого поля |
| Только базовые поля (traits, facts, triggers) | Собираем из них |
| Только имя | Возвращаем минимальный профиль |
| Ничего | Возвращаем `None` (пропустить) |

**2.3. Тесты:**
- Тест: пользователь с полным профилем → сжатый профиль корректен
- Тест: пользователь с минимальными данными → минимальный профиль
- Тест: пользователь без данных → `None`
- Тест: структура результата соответствует схеме

**Проверка:**
- [ ] Файл создан
- [ ] Тесты написаны и проходят
- [ ] Ручная проверка на 3-5 реальных пользователях через shell

**Риск:** Нулевой. Сервис только читает и возвращает dict.
**Время:** 2-3 часа.

---

### ЭТАП 3: Генерация day_context_summary из DailyAnalysis

**Цель:** Создать утилиту, которая перепаковывает данные из `DailyAnalysis` в `day_context_summary`. Без AI.

**Файлы:**
- `diary/services/day_context_service.py` (новый)
- `tests/test_day_context_service.py` (новый)

**Что делаем:**

**3.1. Создать `DayContextService`:**

```python
class DayContextService:
    """Генерирует day_context_summary из DailyAnalysis."""

    def generate_from_daily_analysis(self, daily_analysis) -> dict:
        """
        Перепаковывает DailyAnalysis в day_context_summary.
        """

    def generate_from_mood_and_state(self, mood_scores: list, ai_state_data: str) -> dict:
        """
        Генерирует из оценок настроения и ai_state_data
        (fallback если нет DailyAnalysis).
        """

    def _build_emotional_arc(mood_scores: list) -> str:
        """Строит строку эмоциональной дуги: '7 → 5 → 3 → 4'."""

    def _infer_main_conflict(key_themes: list, emotional_patterns: list) -> str:
        """Выводит основной конфликт из тем и эмоций."""
```

**3.2. Логика:**
```python
{
    "emotional_arc": "7 → 5 → 3 → 4",  # из daily_mood_scores
    "key_topics": ["работа", "семья"],   # из DailyAnalysis.key_themes[:3]
    "main_conflict": "...",              # inferred или ""
    "dominant_pattern": "...",           # из DailyAnalysis.emotional_patterns[0]
    "trend": "declining"                 # из DailyAnalysis.mood_trend
}
```

**Проверка:**
- [ ] Файл создан
- [ ] Тесты написаны и проходят
- [ ] Ручная проверка на реальных записях

**Риск:** Нулевой. Только чтение + формирование dict.
**Время:** 1-2 часа.

---

### ЭТАП 4: Обновление `user_profile_analysis` — генерация compressed через AI

**Цель:** Добавить в существующий `user_profile_analysis` генерацию `compressed_psych_profile` как часть output.

**Файлы:**
- `diary/services/user_profile_analysis_service.py` (изменить)
- `prompts/templates/user_profile_analysis.py` (изменить — добавить секцию в промпт)

**Что делаем:**

**4.1. Добавить в промпт `user_profile_analysis`:**

В секцию OUTPUT добавить:
```
10. **Сформируй `compressed_psych_profile`** — сжатое представление профиля:
    - psych_summary: 5-7 предложений, цельное описание
    - core_patterns: 3-5 ключевых паттернов
    - emotional_style: 1 предложение
    - main_triggers: до 5 триггеров
    - coping_style: 1 предложение
    - current_focus: 1-2 слова
```

**4.2. Обновить сервис — сохранение:**

```python
# В user_profile_analysis_service.py, после сохранения профиля:
compressed = parsed_result.get('compressed_psych_profile')
if compressed:
    user.compressed_psych_profile = compressed
    await user.asave(update_fields=['compressed_psych_profile'])
```

**4.3. НЕ удалять старую логику:**
- Все текущие поля профиля продолжают обновляться
- compressed_psych_profile — ДОПОЛНЕНИЕ, не замена

**Проверка:**
- [ ] Промпт обновлён (ru + en)
- [ ] Сервис сохраняет compressed_psych_profile
- [ ] Тест: weekly analysis → compressed обновляется
- [ ] Проверить на 2-3 реальных пользователях

**Риск:** Низкий. Добавляем поле, не меняем существующую логику.
**Время:** 2-3 часа.

---

### ЭТАП 5: Обновление `full_day_analysis` — генерация day_context_summary

**Цель:** Добавить в существующий `full_day_analysis` генерацию `day_context_summary` для CombinedDiaryEntry.

**Файлы:**
- `diary/services/full_day_analysis_service.py` (изменить)

**Что делаем:**

**5.1. После сохранения DailyAnalysis — сгенерировать day_context_summary:**

```python
# После сохранения DailyAnalysis:
day_context = await day_context_service.generate_from_daily_analysis(daily_analysis)
if day_context:
    combined_entry.day_context_summary = day_context
    await combined_entry.asave(update_fields=['day_context_summary'])
```

**5.2. НЕ менять промпт full_day_analysis:**
- day_context_summary генерируется из результатов анализа (на backend)
- Промпт остаётся как есть

**Проверка:**
- [ ] Сервис сохраняет day_context_summary
- [ ] Тест: full_day_analysis → day_context_summary заполнен
- [ ] Проверить на реальных записях

**Риск:** Низкий. Добавляем поле, не меняем существующую логику.
**Время:** 1-2 часа.

---

### ЭТАП 6: Бэкфилл существующих данных

**Цель:** Заполнить compressed_psych_profile и day_context_summary для существующих пользователей.

**Файлы:**
- `diary/management/commands/backfill_compressed_data.py` (новый management command)

**Что делаем:**

**6.1. Создать management command:**

```bash
python manage.py backfill_compressed_data --dry-run    # посмотреть что будет
python manage.py backfill_compressed_data --run         # запустить
python manage.py backfill_compressed_data --run --batch-size=20 --sleep=3
```

**6.2. Логика скрипта:**

```
Шаг 1: compressed_psych_profile для всех пользователей
├── Для каждого пользователя (батчами по 50):
│   ├── Если есть personality_description или weekly_analyses:
│   │   └── AI-промпт compressed_psych_profile_v1 (~$0.003/пользователь)
│   ├── Если только базовые поля:
│   │   └── Heuristic (CompressedProfileService, бесплатно)
│   └── Если ничего нет:
│       └── Пропустить, залогировать
│
Шаг 2: day_context_summary для всех CombinedDiaryEntry
├── Для каждой записи (батчами по 100):
│   ├── Если есть DailyAnalysis:
│   │   └── Перепаковать из DailyAnalysis (бесплатно)
│   └── Если нет:
│       └── Пропустить
│
Шаг 3: Отчёт
├── Сгенерировано compressed_psych_profile: N пользователей
├── Сгенерировано day_context_summary: M записей
├── Пропущено: K (нет данных)
└── Стоимость AI: $X.XX
```

**6.3. Параметры:**
| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--batch-size` | 50 | Размер батча для БД |
| `--sleep` | 2 | Пауза между AI-вызовами (сек) |
| `--days-back` | 30 | Сколько дней бэкфиллить day_context_summary |
| `--dry-run` | False | Только лог, без записи |

**6.4. Безопасность:**
- Пропускает уже заполненные поля (idempotent)
- При ошибке логирует и идёт дальше (не падает)
- Можно Ctrl+C и продолжить
- `--dry-run` для проверки

**6.5. Расчёт стоимости:**
```
Активные (с полным профилем):  20 × $0.003 = $0.06
Пассивные (heuristic):          80 × $0     = $0.00
─────────────────────────────────────────────
ИТОГО AI:                                      $0.06
Время выполнения:                              ~15 мин
```

**Проверка:**
- [ ] `--dry-run` запущен, результаты логичны
- [ ] `--run` запущен, прогресс виден
- [ ] После завершения: проверить в БД заполненность
- [ ] Проверить 3-5 случайных compressed профилей на качество

**Риск:** Низкий. Только добавляет данные, не удаляет.
**Время:** 3-4 часа (написание + запуск).

---

### ЭТАП 7: LITE v2 промпты

**Цель:** Создать новые промпты для LITE-режима. НЕ заменять старые.

**Файлы:**
- `prompts/templates/incremental_day_analysis.py` (добавить lite_v2)
- `prompts/templates/full_day_analysis.py` (добавить lite_v2)
- `prompts/get_prompt.py` (добавить маппинг)

**Что делаем:**

**7.1. Добавить промпт `incremental_day_analysis_lite_v2`:**

Вход:
```python
{
  "new_entry_text": "...",
  "new_entry_creation_time_local": "...",
  "compressed_psych_profile": {...},   # вместо полного профиля
  "day_context_summary": {...},        # вместо всех записей
  "ai_state_data": {...}
}
```

Выход: тот же JSON-контракт (mood_score, comment, recommendation, analysis).

**7.2. Добавить промпт `full_day_analysis_lite_v2`:**

Вход:
```python
{
  "compressed_psych_profile": {...},
  "day_context_summary": {...},
  "compressed_entries_summary": "...",   # 1-2 предложения
  "mood_stats": {"min": 3, "max": 7, "avg": 5}
}
```

Выход: сокращённый JSON (mood_trend, key_themes, insights, overall_analysis_text).

**7.3. Регистрация в get_prompt.py:**
```python
PROMPTS = {
    ...
    'incremental_day_analysis_lite_v2': INCREMENTAL_DAY_ANALYSIS_LITE_V2_PROMPT,
    'full_day_analysis_lite_v2': FULL_DAY_ANALYSIS_LITE_V2_PROMPT,
}
```

**Проверка:**
- [ ] Оба промпта созданы (ru + en)
- [ ] `get_prompt('incremental_day_analysis_lite_v2', 'ru', ...)` работает
- [ ] `get_prompt('full_day_analysis_lite_v2', 'ru', ...)` работает
- [ ] Промпты вручную проверены на адекватность

**Риск:** Нулевой. Новые промпты, старые не тронуты.
**Время:** 3-4 часа.

---

### ЭТАП 8: Feature flag + переключение LITE на v2

**Цель:** Добавить механизм переключения. Старый код продолжает работать.

**Файлы:**
- `core/settings.py` (добавить настройку)
- `bot/services/diary_service.py` (изменить выбор промпта)
- `diary/services/full_day_analysis_service.py` (изменить выбор промпта)

**Что делаем:**

**8.1. Добавить feature flag в settings:**
```python
# compressed_profile.py или settings.py
COMPRESSED_PROFILE_ENABLED = True  # мастер-переключатель
USE_LITE_V2 = True                 # использовать v2 промпты
```

**8.2. Изменить выбор промпта в diary_service.py:**

```python
# БЫЛО:
if user.is_premium:
    prompt_key = 'incremental_day_analysis'
else:
    prompt_key = 'incremental_day_analysis_lite'

# СТАЛО:
if user.is_premium:
    prompt_key = 'incremental_day_analysis'  # НЕ МЕНЯЕМ
else:
    if settings.USE_LITE_V2 and user.compressed_psych_profile:
        prompt_key = 'incremental_day_analysis_lite_v2'
    else:
        prompt_key = 'incremental_day_analysis_lite'  # fallback
```

**8.3. Аналогично для full_day_analysis:**

```python
if user.is_premium:
    prompt_key = 'full_day_analysis'  # НЕ МЕНЯЕМ
else:
    if settings.USE_LITE_V2 and user.compressed_psych_profile:
        prompt_key = 'full_day_analysis_lite_v2'
    else:
        prompt_key = 'full_day_analysis_lite'  # fallback
```

**8.4. Логирование переключения:**
```python
logger.info(f"[LiteV2] User {user.id}: using lite_v2, "
            f"compressed={bool(user.compressed_psych_profile)}, "
            f"day_context={bool(combined_entry.day_context_summary)}")
```

**Проверка:**
- [ ] Premium пользователи: промпт НЕ изменился
- [ ] Free с compressed_psych_profile: используется v2
- [ ] Free без compressed_psych_profile: fallback на старый
- [ ] `USE_LITE_V2 = False` → все на старых промптах
- [ ] Логи показывают какой промпт используется

**Риск:** Низкий. Feature flag позволяет мгновенный откат.
**Время:** 2-3 часа.

---

### ЭТАП 9: Обновление ai_state_data

**Цель:** Привести `ai_state_data` к единой структуре, которую используют v2 промпты.

**Файлы:**
- `bot/services/diary_service.py` (изменить формат ai_state_data)

**Что делаем:**

**9.1. Новая структура ai_state_data:**

```json
{
  "current_mood": 7,
  "mood_trend": "stable",
  "dominant_emotion": "радость",
  "dominant_pattern": "продуктивность после планирования",
  "last_event_impact": "утренняя встреча повысила тревожность"
}
```

**9.2. При каждом incremental анализе — обновлять:**
- `current_mood` = mood_score из ответа
- `mood_trend` = из ответа (или вычислить из истории)
- `dominant_emotion` = inferred из mood_score + comment
- `dominant_pattern` = из day_context_summary.dominant_pattern
- `last_event_impact` = краткое описание из comment

**9.3. Обратная совместимость:**
- Если ai_state_data в старом формате — парсить как строку
- При обновлении конвертировать в новый формат

**Проверка:**
- [ ] ai_state_data сохраняется в новом формате
- [ ] Старые записи с ai_state_data-строкой продолжают работать
- [ ] v2 промпты корректно используют новую структуру

**Риск:** Средний. Меняем формат хранимых данных.
**Время:** 2-3 часа.

---

### ЭТАП 10: Мониторинг и проверка

**Цель:** Убедиться что всё работает, качество не упало, токены экономятся.

**Что делаем:**

**10.1. Логирование:**
```
[LiteV2] User 123: using lite_v2, compressed=True, day_context=True
[LiteV2] User 456: fallback to lite_v1, compressed=False
[LiteV2] User 789: using lite_v2_full_day, tokens_used=1800
```

**10.2. Метрики для отслеживания:**
| Метрика | Где смотреть | Цель |
|---------|-------------|------|
| % пользователей на v2 | Логи / БД | > 80% активных |
| Средние токены на запрос | Логи API | Снижение на 30-50% |
| Ошибки парсинга JSON | Логи | Не больше чем было |
| Рейтинги анализа (1-5) | БД: AnalysisRating | Не ниже чем было |
| Retention | БД: активность | Не ниже чем было |

**10.3. A/B проверка (ручная):**
- Взять 5 последних LITE-анализов на v1 и 5 на v2
- Сравнить качество: comment, recommendation, mood_score
- Если v2 хуже → откатить `USE_LITE_V2 = False`

**Время:** 1-2 часа настройки + мониторинг в течение недели.

---

### ЭТАП 11: Очистка (через 2-4 недели)

**Цель:** Убрать старые промпты и пути, если v2 стабилен.

**Что делаем (ТОЛЬКО если v2 стабилен 2+ недели):**

**11.1. Удалить fallback на старые LITE-промпты:**
```python
# Было:
if user.compressed_psych_profile:
    use_v2()
else:
    use_old()  # ← удалить

# Стало:
use_v2()  # единственно
```

**11.2. Удалить избыточные поля из LITE-промптов:**
- personality_traits, hobbies, core_values, areas_for_growth — убрать из входа
- Оставить только compressed_psych_profile + day_context_summary

**11.3. НЕ удалять:**
- Старые поля в БД (могут понадобиться для истории)
- Premium промпты (не меняются)
- clarification_analysis, comment_analysis, therapy_chat (не менялись)

**Риск:** Средний. Удаление кода — необратимо.
**Время:** 2-3 часа.

---

## 📊 Сводная таблица этапов

| # | Этап | Зависит от | Время | Риск | AI-стоимость | Можно откатить? | Статус |
|---|------|-----------|-------|------|-------------|-----------------|--------|
| 1 | Миграции БД | — | 30 мин | 0 | $0 | ✅ Да (drop column) | ✅ **ВЫПОЛНЕНО** |
| 2 | Compressed сервис (heuristic) | 1 | 2-3 ч | 0 | $0 | ✅ Да (не используется) | ✅ **ВЫПОЛНЕНО** |
| 3 | Day context сервис | 1 | 1-2 ч | 0 | $0 | ✅ Да (не используется) | ✅ **ВЫПОЛНЕНО** |
| 4 | user_profile_analysis → compressed | 1, 2 | 2-3 ч | Низкий | $0 | ✅ Да (поле nullable) | ✅ **ВЫПОЛНЕНО** |
| 5 | full_day_analysis → day_context | 1, 3 | 1-2 ч | Низкий | $0 | ✅ Да (поле nullable) | ✅ **ВЫПОЛНЕНО** |
| 6 | Бэкфилл | 2, 3 | 3-4 ч | Низкий | ~$0.06 | ✅ Да (очистить поля) | ✅ **ВЫПОЛНЕНО** |
| 7 | LITE v2 промпты | — | 3-4 ч | 0 | $0 | ✅ Да (не вызываются) | ⏳ Ожидает |
| 8 | Feature flag + переключение | 4, 5, 6, 7 | 2-3 ч | Низкий | $0 | ✅ Да (flag = False) | ⏳ Ожидает |
| 9 | Обновление ai_state_data | 8 | 2-3 ч | Средний | $0 | ⚠️ Частично | ⏳ Ожидает |
| 10 | Мониторинг | 8 | 1-2 ч | 0 | $0 | — | ⏳ Ожидает |
| 11 | Очистка | 10 (2-4 недели) | 2-3 ч | Средний | $0 | ❌ Нет | ⏳ Ожидает |

---

## 🎯 Рекомендуемый порядок запуска

### День 1: Фундамент
- [ ] Этап 1: Миграции
- [ ] Этап 2: Compressed сервис
- [ ] Этап 3: Day context сервис

### День 2: Интеграция в существующие анализы
- [ ] Этап 4: user_profile_analysis → compressed
- [ ] Этап 5: full_day_analysis → day_context

### День 3: Бэкфилл + промпты
- [ ] Этап 6: Бэкфилл (--dry-run → --run)
- [ ] Этап 7: LITE v2 промпты

### День 4: Переключение
- [ ] Этап 8: Feature flag + переключение
- [ ] Этап 9: Обновление ai_state_data
- [ ] Этап 10: Мониторинг

### Через 2-4 недели:
- [ ] Этап 11: Очистка (если всё стабильно)

---

## ⚠️ Правила безопасности

1. **Каждый этап — отдельный коммит.** Можно откатить по одному.
2. **После каждого этапа — тесты.** Если падают — стоп и чинить.
3. **Бэкап БД перед Этапами 4, 6, 8, 9.**
4. **Feature flag — мгновенный откат.** Если что-то не так — `USE_LITE_V2 = False`.
5. **Premium НЕ меняется.** Ни один промпт Premium не трогается.
6. **clarification, comment, therapy_chat, task_effect — НЕ меняются.**

---

## 📉 Ожидаемые результаты

| Метрика | До | После (LITE) | После (Premium) |
|---------|-----|-------------|-----------------|
| Токены на запрос | 100% | 30-50% | 100% (без изменений) |
| Скорость ответа | Средняя | Выше | Без изменений |
| Качество анализа | Нестабильное | Стабильнее | Без изменений |
| Стоимость AI/день | $X | $0.5X-0.7X | Без изменений |

---

> **Следующий шаг:** Утвердить план → начать с Этапа 1 (миграции).
