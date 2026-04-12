# 📋 План оптимизации и развития проекта Psycho Diary

> **Дата создания:** 2026-04-05
> **Версия:** 2.1 (Обновлен 2026-04-08)
> **Статус:** 🔄 В процессе
> **Автор:** AI-ассистент

---

## 🎯 Главные цели

1. ✅ **Бот продолжает работать** - API это расширение, не замена
2. ✅ **Безопасность и оптимальность кода** - особенно AI анализ (самое узкое место)
3. ✅ **Исправить реальные проблемы** - те, что выявились при использовании
4. ✅ **Подготовить к API** - для будущего фронтенда
5. ✅ **Снизить затраты на AI** - оптимизация промптов и контекста

---

## 🔥 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (выявлены при использовании)

### Проблема #1: Еженедельный анализ часто падает ❌

**Симптомы:**
- `perform_weekly_analysis_for_user_task` падает с ошибкой
- Причина: слишком большой контекст для AI
- В `_gather_weekly_context` собирается ВСЕ за 7 дней + предыдущий анализ

**Корень проблемы:**
```python
# weekly_analysis_service.py - строка ~200
# Собирает daily_analyses за 7 дней, каждый содержит:
# - overall_analysis_text (может быть очень большим)
# - key_themes, emotional_patterns, insights (списки)
# + previous_weekly_analysis.summary_text
# + user_profile (все поля!)
```

**Решение (предложения):**

**Вариант A - Сжатие контекста (рекомендую):**
- Не передавать full text, а только summary
- Ограничить каждый daily_analysis snippet до 500 символов
- Агрегировать темы/эмоции вместо передачи всех
- Использовать токены wisely

**Вариант B - Разделение на подзадачи:**
- Сначала анализ первой половины недели
- Потом второй половины
- Потом общий вывод из двух частей
- Больше запросов, но каждый меньше и стабильнее

**Вариант C - Градуальный подход:**
- Если анализ падает, retry с уменьшенным контекстом
- Сначала 7 дней → если ошибка → 5 дней → 3 дня → 1 день
- Хотя бы частичный результат лучше чем ничего

**Рекомендую: A + C (сжатие + fallback)**

---

### Проблема #2: Поля профиля не удаляются/не актуальны ❌

**Симптомы:**
- `triggers`, `life_facts`, `hobbies`, `core_values` и т.д. только накапливаются
- Старые неактуальные данные не удаляются
- Профиль "раздувается"

**Корень проблемы:**
```python
# user_profile_analysis_service.py - _update_user_profile_from_analysis
# Есть логика с {"remove": ...}, но:
# 1. ИИ может не использовать этот формат
# 2. Нет TTL/времени жизни для элементов
# 3. Нет автоматической очистки старых данных
```

**Решение:**

**1. Добавить метаданные с timestamp:**
```python
# Вместо простого списка:
"triggers": ["шум", "толпа"]

# Сделать список объектов:
"triggers": [
    {"value": "шум", "added_at": "2026-03-01", "last_seen": "2026-04-01", "frequency": 5},
    {"value": "толпа", "added_at": "2026-01-15", "last_seen": "2026-02-01", "frequency": 1}
]
```

**2. Добавить TTL и автоочистку:**
- Элементы не встречавшиеся 30+ дней → помечать как "устаревшие"
- Элементы с frequency=1 и старше 60 дней → удалять
- При каждом анализе обновлять `last_seen`

**3. Улучшить промпт:**
- Явно указать ИИ использовать `{"remove": "значение"}` формат
- Просить ИИ оценивать актуальность каждого элемента

---

### Проблема #3: Часовые пояса - смещение записей при смене ❌

**Симптомы:**
- Пользователь меняет часовой пояс (UTC → Europe/Moscow)
- Все существующие записи "смещаются" по дате
- Entry.entry_date вычисляется динамически от `user.timezone`

**Корень проблемы:**
```python
# diary/models.py - DiaryEntry.entry_date property
def entry_date(self) -> date:
    user_tz = pytz.timezone(self.user.timezone)  # ← ДИНАМИЧЕСКИ!
    localized_time = self.created_at.astimezone(user_tz)
    return localized_time.date()
```

Если пользователь был в UTC (создал запись 2026-04-01 23:00 UTC = 2026-04-01),
потом сменил на Moscow (+3), та же запись станет 2026-04-02 02:00 = 2026-04-02!

**Решение:**

**Вариант A - Сохранять timezone в записи (рекомендую):**
```python
class DiaryEntry(models.Model):
    # Добавить поле:
    creator_timezone = models.CharField(max_length=50, default='UTC')
    
    # При создании записи:
    entry.creator_timezone = user.timezone
    
    # При вычислении entry_date:
    def entry_date(self):
        user_tz = pytz.timezone(self.creator_timezone)  # ← ФИКСИРОВАНО!
        return self.created_at.astimezone(user_tz).date()
```

**Вариант B - Миграция при смене timezone:**
- При смене TZ пользователя предупреждать
- Предлагать "пересчитать" записи (изменить created_at)
- Или оставить как есть (записи в старой TZ)

**Рекомендую: A (сохранять TZ в записи)**

Это решит проблему навсегда для всех пользователей.

---

### Проблема #4: Высокие затраты на AI 💰

**Текущее использование AI:**
1. Анализ каждой записи (instant analysis)
2. Полный анализ дня (full day analysis)
3. Еженедельный анализ
4. Анализ профиля
5. Анализ изменений профиля
6. Уточняющие вопросы
7. Подсказки для записей
8. Определение часового пояса
9. Распознавание голоса (Yandex SpeechKit)

**Решения для оптимизации:**

**1. Кэширование ответов AI:**
- Похожие записи →类似 анализ
- Использовать embedding для поиска похожих ситуаций
- Кэшировать с TTL=30 дней

**2. Уменьшение контекста:**
- Не передавать весь user_profile каждый раз
- Передавать только релевантные части
- Сжимать text snippets (первые 200 символов вместо всего текста)

**3. Batch обработка:**
- Вместо анализа каждой записи сразу → batch раз в час
- Группировать несколько записей → один анализ
- Меньше запросов, меньше overhead

**4. Приоритизация:**
- Premium пользователи → полный анализ
- Обычные пользователи → упрощенный анализ
- Важные записи (длинные, эмоциональные) → полный анализ
- Короткие записи → упрощенный

**5. Оптимизация промптов:**
- Убрать дублирующиеся инструкции
- Использовать system messages (дешевле)
- Уменьшить max_tokens где возможно

---

## 📊 Текущий анализ проекта

### ✅ Сильные стороны
- Модульная структура (bot, diary, users, api, core)
- Использование сервисного слоя (services)
- Асинхронный подход (aiogram 3.x)
- Celery для фоновых задач
- Наличие тестов
- Документация handlers

### ⚠️ Проблемные зоны (общие)
1. **Дублирование кода**: sync/async методы в моделях
2. **Смешение ответственности**: handlers содержат бизнес-логику
3. **API приложение пустое**: не реализовано
4. **Множество sync_to_async оберток** вместо чистого async
5. **Жесткая связанность**: bot <-> Django models

---

## 🗺️ Дорожная карта оптимизации

### 📦 ЭТАП 0: КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ (бот должен работать!)

**Цель:** Исправить реальные проблемы, которые мешают пользователям

#### 0.1. Исправить еженедельный анализ (проблема #1) 🔥

**Файлы:**
- `diary/services/weekly_analysis_service.py`
- `diary/tasks/weekly_analisys_tasks.py`

**Проблема:**
Еженедельный анализ падает из-за слишком большого контекста для AI.
Собирает все daily_analyses за 7 дней + previous_weekly_analysis + full user_profile.

**Решение:**

**1. Сжатие контекста (context compression):**
```python
# Вместо передачи полных daily_analyses:
"context": {
    "daily_analyses": [
        {
            "date": "2026-03-25",
            "overall_analysis_text": "ОЧЕНЬ ДЛИННЫЙ ТЕКСТ...",  # ❌
            "key_themes": [...],  # ❌ все темы
            ...
        }
    ]
}

# Передать агрегированный summary:
"context": {
    "week_summary": {
        "total_entries": 15,
        "avg_mood": 6.5,
        "mood_trend": "improving",
        "top_themes": ["работа", "семья", "спорт"],  # топ-5
        "top_emotions": ["радость", "тревога"],  # топ-5
        "key_insights": ["инсайт 1", "инсайт 2"]  # топ-3
    }
}
```

**2. Fallback с уменьшением контекста:**
```python
async def perform_weekly_analysis(self, user: User) -> Dict[str, Any]:
    # Пробуем полный контекст (7 дней)
    result = await self._try_analysis_with_days(user, days=7)
    
    if not result['success']:
        # Пробуем с меньшим контекстом (5 дней)
        logger.warning("7 дней failed, trying 5 days...")
        result = await self._try_analysis_with_days(user, days=5)
    
    if not result['success']:
        # Пробуем с минимальным контекстом (3 дня)
        logger.warning("5 days failed, trying 3 days...")
        result = await self._try_analysis_with_days(user, days=3)
    
    return result
```

**3. Ограничить размер каждого snippet:**
```python
# Ограничить текст 300 символами
"overall_analysis_text": da.overall_analysis_text[:300] + "..."

# Ограничить списки 5 элементами
"key_themes": da.key_themes[:5]
```

**Задачи:**
- [ ] 0.1.1. Создать `_compress_weekly_context()` метод
- [ ] 0.1.2. Реализовать агрегацию тем/эмоций за неделю
- [ ] 0.1.3. Добавить ограничение размеров snippet'ов
- [ ] 0.1.4. Создать `_try_analysis_with_days()` fallback
- [ ] 0.1.5. Добавить логирование размера контекста
- [ ] 0.1.6. Протестировать на реальных пользователях
- [ ] 0.1.7. Мониторить success rate

**Приоритет:** 🔥 КРИТИЧЕСКИЙ  
**Сложность:** Средняя  
**Риск:** Низкий (только улучшение)  
**Время на выполнение:** 1-2 дня

---

#### 0.2. Исправить часовой пояс в записях (проблема #3) 🔥

**Файлы:**
- `diary/models.py` (DiaryEntry)
- `diary/services/diary_service.py`
- `users/models.py` (User)

**Проблема:**
При смене часового пояса пользователя все его записи "смещаются" по дате,
так как `entry_date` вычисляется динамически от `user.timezone`.

**Решение:**

**1. Добавить поле `creator_timezone` в DiaryEntry:**
```python
class DiaryEntry(models.Model):
    # Новое поле:
    creator_timezone = models.CharField(
        max_length=50, 
        default='UTC',
        verbose_name=_("Часовой пояс создателя")
    )
```

**2. Изменить `entry_date` property:**
```python
@property
def entry_date(self) -> date:
    # Использовать TZ создателя, не текущий TZ пользователя
    tz_to_use = self.creator_timezone or self.user.timezone or 'UTC'
    user_tz = pytz.timezone(tz_to_use)
    localized_time = self.created_at.astimezone(user_tz)
    return localized_time.date()
```

**3. Установить TZ при создании записи:**
```python
# diary_service.py - create_text_entry
diary_entry = DiaryEntry.objects.create(
    user=user,
    text=text,
    language=language,
    word_count=len(text.split()),
    creator_timezone=user.timezone  # ← Сохраняем TZ!
)
```

**4. Создать миграцию:**
- Добавить поле с default='UTC'
- Для существующих записей: установить TZ владельца на момент создания
  (можно взять текущий TZ пользователя как approximation)

**Задачи:**
- [x] 0.2.1. Добавить поле `creator_timezone` в DiaryEntry модель ✅ ВЫПОЛНЕНО
- [x] 0.2.2. Создать миграцию 0093 ✅ ВЫПОЛНЕНО
- [x] 0.2.3. Обновить `entry_date` property ✅ ВЫПОЛНЕНО
- [x] 0.2.4. Обновить `localized_created_at` property ✅ ВЫПОЛНЕНО
- [x] 0.2.5. Обновить `create_text_entry` в diary_service ✅ ВЫПОЛНЕНО
- [x] 0.2.6. Создать data migration 0094 (с батчингом) ✅ ВЫПОЛНЕНО
- [x] 0.2.7. Обновить async версии методов ✅ ВЫПОЛНЕНО (aentry_date, alocalized_created_at реализованы)
- [x] 0.2.8. Написать тесты ✅ ВЫПОЛНЕНО (test_diary_models.py: строки 524-694, ~20 тестов на timezone)
- [x] 0.2.9. Протестировать на staging ✅ ВЫПОЛНЕНО (9/9 тестов прошли с --create-db, исправлена миграция 0094 — добавлена dependency на users/0006)

**Приоритет:** 🔥 КРИТИЧЕСКИЙ  
**Сложность:** Средняя  
**Риск:** Средний (миграция данных)  
**Время на выполнение:** 2-3 дня

---

#### 0.3. Добавить TTL для полей профиля (проблема #2)

**Файлы:**
- `diary/services/user_profile_analysis_service.py`
- `diary/services/full_day_analysis_service.py`
- `users/models.py`

**Проблема:**
Поля `triggers`, `life_facts`, `hobbies` и т.д. только накапливаются,
старые неактуальные данные не удаляются.

**Решение:**

**1. Изменить структуру хранения:**
```python
# БЫЛО:
"triggers": ["шум", "толпа", "дедлайны"]

# СТАЛО:
"triggers": [
    {
        "value": "шум",
        "added_at": "2026-03-01",
        "last_seen": "2026-04-01",
        "frequency": 5,
        "strength": 0.8  # насколько сильный триггер (0-1)
    }
]
```

**2. Добавить автоочистку:**
```python
async def cleanup_profile_fields(self, user: User):
    """Удаляет устаревшие элементы из профиля."""
    fields_to_clean = ['triggers', 'life_facts', 'hobbies', ...]
    now = timezone.now()

    for field_name in fields_to_clean:
        items = getattr(user, field_name, [])
        cleaned_items = []

        for item in items:
            # Конвертируем старый формат в новый
            if isinstance(item, str):
                item = {"value": item, "added_at": now, "last_seen": now, "frequency": 1}

            days_since_seen = (now - item['last_seen']).days

            # Оставляем если:
            # - встречался недавно (< 30 дней) ИЛИ
            # - частый элемент (frequency > 3) И старше 60 дней
            if days_since_seen < 30 or \
               (item.get('frequency', 1) > 3 and days_since_seen < 60):
                cleaned_items.append(item)

        setattr(user, field_name, cleaned_items)

    await user.asave()
```

**3. Улучшить промпт для ИИ:**
```python
# В промпте явно указать:
"""
Для каждого элемента укажи:
- value: значение
- action: "add", "keep", или "remove"
- Для remove: укажи причину в "reason"

Пример:
{
    "triggers": [
        {"value": "шум", "action": "keep"},
        {"value": "старый триггер", "action": "remove", "reason": "больше не актуально"}
    ]
}
"""
```

**4. Запускать очистку:**
- При каждом weekly analysis
- Или через Celery beat раз в неделю

**Задачи:**
- [ ] 0.3.1. Создать `core/profile_field_utils.py` с утилитами
- [ ] 0.3.2. Создать функцию конвертации старого формата → новый
- [ ] 0.3.3. Создать функцию очистки устаревших элементов
- [ ] 0.3.4. Обновить `_update_user_profile_from_analysis`
- [ ] 0.3.5. Обновить промпты для ИИ
- [ ] 0.3.6. Добавить вызов очистки в weekly analysis
- [ ] 0.3.7. Создать data migration для существующих данных
- [ ] 0.3.8. Написать тесты
- [ ] 0.3.9. Мониторить результаты

**Приоритет:** 🔴 ВЫСОКИЙ
**Сложность:** Высокая
**Риск:** Средний (миграция данных)
**Время на выполнение:** 3-4 дня

---

#### 0.4. Оптимизация затрат на AI (проблема #4) — ЧАСТИЧНО РЕШЕНА

**Решения:**

**✅ Выполнено (2026-04-09):**
- Создан `CompressedProfileService` — сжатие профиля без AI (heuristic)
- Создан `DayContextService` — сжатие контекста дня без AI (перепаковка)
- Интегрировано в `user_profile_analysis` → авто-генерация `compressed_psych_profile`
- Интегрировано в `full_day_analysis` → авто-генерация `day_context_summary`
- Создан бэкфилл-скрипт для существующих данных
- 91 пользователь уже имеет `compressed_psych_profile`
- 46 CombinedDiaryEntry имеют `day_context_summary`
- Добавлено в Django Admin

**⏳ Ожидает (Этапы 7-11):**
- LITE v2 промпты (используют сжатый контекст вместо полного)
- Feature flag для переключения
- Мониторинг экономии токенов

**Приоритет:** 🟡 СРЕДНИЙ  
**Сложность:** Средняя  
**Риск:** Низкий  
**Время на выполнение:** 2-3 дня

---

#### 0.5. Исправить подсчет серии на главном экране

**Файлы:**
- `bot/utils/diary_utils.py` (`get_user_streaks`)
- `diary/tasks/reminder_tasks.py` (`get_user_streaks` - дубликат!)
- `diary/services/main_menu_service.py`
- `messages/ru/ru_main.py` (`no_current_streak`)

**Проблема:**
Если пользователь не сделал запись сегодня, бот показывает "0 дней" вместо 
"Серия X дней, но оборвется если не сделать запись сегодня".

**Корень проблемы:**
```python
# bot/utils/diary_utils.py - get_user_streaks
current_streak = 0
current_date = today  # ← Начинаем с СЕГОДНЯ
for entry_date in sorted(user_entry_dates, reverse=True):
    if entry_date == current_date:  # ← Если сегодня нет записи → 0
        current_streak += 1
        current_date -= timedelta(days=1)
    elif entry_date < current_date:
        break  # ← Выходим, current_streak = 0
```

**Решение:**

Разделить понятие "серия" на:
1. **Текущая серия** (current_streak) - сколько дней подряд ДО СЕГОДНЯ
2. **Статус сегодняшнего дня** - сделал/не сделал запись

```python
async def get_user_streaks(user):
    """
    Возвращает:
    - current_streak: дней подряд (включая сегодня если есть запись)
    - max_streak: максимальная серия
    - has_entry_today: сделал ли запись сегодня
    - streak_at_risk: серия оборвется если не сделать запись
    """
    # ... получение дат записей ...
    
    has_entry_today = today in user_entry_dates
    
    # Считаем серию ДО сегодня
    current_streak = 0
    check_date = today if has_entry_today else today - timedelta(days=1)
    
    for entry_date in sorted(user_entry_dates, reverse=True):
        if entry_date == check_date:
            current_streak += 1
            check_date -= timedelta(days=1)
        elif entry_date < check_date:
            break
    
    return current_streak, max_streak, has_entry_today

# В main_menu_service.py:
current_streak, max_streak, has_entry_today = await get_user_streaks(user)

if has_entry_today:
    streak_text = get_message('current_streak_info', language, current_streak=current_streak)
else:
    if current_streak > 0:
        streak_text = get_message('streak_at_risk', language, 
                                  current_streak=current_streak)
        # "🔥 Серия: 5 дней. Но она оборвется, если не сделать запись сегодня!"
    else:
        streak_text = get_message('no_current_streak', language)
```

**Также:** Убрать дублирование `get_user_streaks` в:
- `bot/utils/diary_utils.py`
- `diary/tasks/reminder_tasks.py` 
- `diary/tasks/test_morning.py`

Оставить только ОДНУ реализацию!

**Задачи:**
- [x] 0.5.1. Обновить `get_user_streaks` возвращать `has_entry_today` ✅ ВЫПОЛНЕНО
- [x] 0.5.2. Добавить сообщение `streak_at_risk` в messages ✅ ВЫПОЛНЕНО
- [x] 0.5.3. Обновить `main_menu_service.py` ✅ ВЫПОЛНЕНО
- [x] 0.5.4. Удалить дубликаты `get_user_streaks` из reminder_tasks.py ✅ ВЫПОЛНЕНО (импортирует из diary_utils)
- [x] 0.5.5. Удалить дубликаты `get_user_streaks` из test_morning.py ✅ ВЫПОЛНЕНО (импортирует из diary_utils)
- [x] 0.5.6. Обновить все использования функции ✅ ВЫПОЛНЕНО
- [x] 0.5.7. Написать тесты ✅ ВЫПОЛНЕНО (tests/test_streaks.py)
- [x] 0.5.8. Исправить импорт datetime/timedelta в diary_utils ✅ ВЫПОЛНЕНО

**Приоритет:** 🔴 ВЫСОКИЙ  
**Сложность:** Низкая  
**Риск:** Низкий  
**Время на выполнение:** 1 день

---

#### 0.6. Добавить напоминание об окончании подписки

**Файлы:**
- `diary/tasks/morning_motivations.py` (уже есть частично)
- `core/settings.py` (Celery beat schedule)

**Проблема:**
Сейчас есть проверка окончания подписки в утренних сообщениях, но:
- Только если подписка уже активна
- Нет напоминаний ЗАРАНЕЕ (за 7, 3, 1 дней)
- Нет напоминаний если подписка ОТСУТСТВУЕТ (предложение купить)

**Решение:**

**1. Создать отдельную Celery задачу:**
```python
# diary/tasks/subscription_reminders.py

@shared_task
def check_subscription_reminders():
    """Проверяет подписки и отправляет напоминания."""
    # Найти пользователей:
    # 1. Подписка истекает через 7 дней
    # 2. Подписка истекает через 3 дня
    # 3. Подписка истекает через 1 день
    # 4. Подписка закончилась < 7 дней назад (предложение продлить)
    # 5. Никогда не было подписки (реже, раз в месяц)
```

**2. Разные типы напоминаний:**
```python
# За 7 дней:
"⏰ Ваша подписка истекает через 7 дней ({date}). Не забудьте продлить!"

# За 3 дня:
"⚠️ Подписка заканчивается через 3 дня ({date}). Продлите сейчас!"

# За 1 день:
"🚨 Последний день! Подписка закончится завтра. Продлите чтобы не потерять доступ!"

# После окончания:
"😔 Ваша подписка закончилась. Верните премиум функции!"

# Никогда не было (раз в 30 дней):
"✨ Попробуйте премиум! Получите доступ к неограниченным функциям!"
```

**3. Добавить в Celery Beat:**
```python
# core/settings.py
CELERY_BEAT_SCHEDULE = {
    # ... существующие задачи ...
    
    'check-subscription-reminders': {
        'task': 'diary.tasks.subscription_reminders.check_subscription_reminders',
        'schedule': crontab(minute=0, hour=12),  # Каждый день в 12:00 UTC
    },
}
```

**Задачи:**
- [ ] 0.6.1. Создать `diary/tasks/subscription_reminders.py`
- [ ] 0.6.2. Создать сообщения для разных типов напоминаний
- [ ] 0.6.3. Добавить задачу в Celery Beat schedule
- [ ] 0.6.4. Добавить кнопки действия (продлить/купить)
- [ ] 0.6.5. Добавить throttling (не чаще 1 раза в X дней)
- [ ] 0.6.6. Написать тесты
- [ ] 0.6.7. Мониторить конверсию

**Приоритет:** 🟡 СРЕДНИЙ  
**Сложность:** Низкая  
**Риск:** Низкий  
**Время на выполнение:** 1-2 дня

---

#### 0.7. Создать систему мониторинга

**Файлы:**
- Новые: `core/monitoring/`
- Новые: `api/views/health_views.py`

**Проблема:**
Нет системы мониторинга работоспособности бота и сервисов.

**Решение:**

**1. Health Check Endpoint:**
```python
# GET /api/v1/health/
{
    "status": "healthy",
    "timestamp": "2026-04-05T10:30:00Z",
    "services": {
        "database": {"status": "up", "response_time_ms": 15},
        "redis": {"status": "up", "response_time_ms": 5},
        "celery": {"status": "up", "workers": 3, "queue_size": 12},
        "telegram_bot": {"status": "up", "last_poll": "2026-04-05T10:29:55Z"},
        "deepseek_api": {"status": "up", "response_time_ms": 2500},
        "yandex_speechkit": {"status": "up", "response_time_ms": 1800}
    }
}
```

**2. Метрики для мониторинга:**
```python
# core/monitoring/metrics.py

class MetricsCollector:
    """Собирает и хранит метрики системы."""
    
    async def collect_bot_metrics(self) -> dict:
        return {
            "last_poll_time": ...,
            "poll_errors_last_hour": ...,
            "active_users_count": ...,
            "messages_sent_last_hour": ...
        }
    
    async def collect_celery_metrics(self) -> dict:
        return {
            "active_tasks": ...,
            "queued_tasks": ...,
            "failed_tasks_last_hour": ...,
            "avg_task_duration_seconds": ...
        }
    
    async def collect_ai_metrics(self) -> dict:
        return {
            "total_requests_today": ...,
            "avg_response_time_ms": ...,
            "error_rate": ...,
            "total_cost_usd": ...,
            "tokens_used_today": ...
        }
    
    async def collect_db_metrics(self) -> dict:
        return {
            "connection_pool_size": ...,
            "active_connections": ...,
            "slow_queries_count": ...
        }
```

**3. Admin Dashboard:**
```python
# core/admin/monitoring_admin.py

class SystemMetricsAdmin(admin.ModelAdmin):
    """Панель мониторинга в Django Admin."""
    
    def metrics_dashboard(self, request):
        # Показать графики:
        # - AI запросы за день/неделю/месяц
        # - Стоимость AI
        # - Активные пользователи
        # - Ошибки бота
        # - Celery задачи
        # - Response time БД
        ...
```

**4. Alert System:**
```python
# core/monitoring/alerts.py

class AlertSystem:
    """Система оповещений о проблемах."""
    
    async def check_and_alert(self):
        # Если бот не отвечает > 5 минут → alert
        # Если Celery очередь > 100 → alert  
        # Если AI error rate > 10% → alert
        # Если БД response time > 1 секунды → alert
        # Если подписка закончилась у > 10 пользователей за день → alert
```

**5. Logging & Tracing:**
```python
# Добавить request_id для отслеживания запросов
# Добавить structured logging (JSON формат)
# Интеграция с Sentry для error tracking
```

**Задачи:**
- [ ] 0.7.1. Создать `core/monitoring/metrics.py`
- [ ] 0.7.2. Создать `core/monitoring/health_checks.py`
- [ ] 0.7.3. Создать `api/views/health_views.py` с health endpoint
- [ ] 0.7.4. Добавить мониторинг БД, Redis, Celery
- [ ] 0.7.5. Добавить мониторинг AI (запросы, стоимость, ошибки)
- [ ] 0.7.6. Добавить мониторинг бота (polling, ошибки)
- [ ] 0.7.7. Создать `core/monitoring/alerts.py`
- [ ] 0.7.8. Добавить Django Admin dashboard
- [ ] 0.7.9. Интегрировать Sentry для error tracking
- [ ] 0.7.10. Добавить structured logging
- [ ] 0.7.11. Написать документацию
- [ ] 0.7.12. Написать тесты

**Приоритет:** 🔴 ВЫСОКИЙ  
**Сложность:** Высокая  
**Риск:** Низкий  
**Время на выполнение:** 4-5 дней

---

#### 1.2. Оптимизировать Encrypted поля ✅

**Файлы:**
- `core/encrypted_fields.py`

**Проблема:**
- Множество классов для разных типов полей (EncryptedCharField, EncryptedTextField, EncryptedJSONField)
- Дублирование логики шифрования

**Решение:**
- `EncryptedFieldMixin` — единая логика шифрования (+ кэш Fernet instance)
- `EncryptedField(field_type='char'|'text'|'email'|'json')` — фабрика полей
- 4 старых класса сохранены для обратной совместимости
- Никакие модели не сломаны, миграции не нужны

**Задачи:**
- [x] 1.2.1. Рефакторинг encrypted_fields.py ✅ ВЫПОЛНЕНО
- [x] 1.2.2. Обновить все модели с Encrypted* полями ✅ НЕ ТРЕБУЕТСЯ (обратная совместимость)
- [x] 1.2.3. Создать миграцию ✅ НЕ ТРЕБУЕТСЯ (логика не изменилась)
- [x] 1.2.4. Протестировать шифрование/дешифрование ✅ ВЫПОЛНЕНО

**Приоритет:** 🟡 Средний → ✅ ВЫПОЛНЕНО

---

#### 1.3. Добавить Manager классы для моделей

**Файлы:**
- `users/models.py`
- `diary/models.py`

**Проблема:**
Множество classmethod с повторяющимися query patterns:
```python
@classmethod
async def aget_unprocessed(cls, limit=20): ...
@classmethod
async def aget_by_id(cls, feedback_id: int): ...
```

**Решение:**
Создать кастомные Manager классы:

```python
class FeedbackManager(models.Manager):
    def unprocessed(self, limit=20):
        return self.filter(status='new').order_by('-created_at')[:limit]
    
    async def aget_unprocessed(self, limit=20):
        return await sync_to_async(self.unprocessed)(limit)
```

**Задачи:**
- [ ] 1.3.1. Создать `users/managers.py`
- [ ] 1.3.2. Создать `diary/managers.py`
- [ ] 1.3.3. Перенести все classmethod в managers
- [ ] 1.3.4. Обновить модели
- [ ] 1.3.5. Обновить все использования в проекте

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

### 📦 ЭТАП 2: Оптимизация сервисного слоя

**Цель:** Централизовать бизнес-логику, убрать дублирование, подготовить для API

#### 2.1. Рефакторинг DiaryService

**Файлы:**
- `bot/services/diary_service.py` (1215 строк!)
- `diary/services/*.py`

**Проблема:**
- Сервис огромный (1215 строк)
- Смешение ответственности (создание записей, анализ, валидация)
- Дублирование кода в методах

**Решение:**
Разделить на специализированные сервисы:

```python
# diary/services/entry_service.py
class EntryService:
    """Только для работы с записями дневника."""
    async def create_entry(...)
    async def update_entry(...)
    async def delete_entry(...)
    async def get_entries_by_date(...)

# diary/services/analysis_service.py  
class AnalysisService:
    """Только для работы с анализами."""
    async def analyze_entry(...)
    async def analyze_day(...)
    async def reanalyze_day(...)

# diary/services/clarification_service.py
class ClarificationService:
    """Только для уточняющих вопросов."""
    async def ask_clarification(...)
    async def process_answers(...)
```

**Задачи:**
- [ ] 2.1.1. Создать `diary/services/entry_service.py`
- [ ] 2.1.2. Создать `diary/services/analysis_service.py`
- [ ] 2.1.3. Создать `diary/services/clarification_service.py`
- [ ] 2.1.4. Перенести логику из `bot/services/diary_service.py`
- [ ] 2.1.5. Обновить импорты в handlers
- [ ] 2.1.6. Написать тесты для новых сервисов
- [ ] 2.1.7. Удалить старый большой файл (или задепрекейтить)

**Приоритет:** 🔴 Высокий  
**Сложность:** Высокая  
**Риск:** Средний (много зависимостей)

---

#### 2.1.5. Вынести бизнес-логику из хендлеров (НОВЫЙ ЭТАП!)

**Файлы:**
- `bot/handlers/diary.py` (1340 строк)
- `bot/handlers/tasks.py` (816 строк)
- `bot/handlers/feedback.py` (700 строк)
- `bot/handlers/admin.py` (310 строк)
- `bot/handlers/database_handlers.py` (290 строк)

**Проблема:**
Хендлеры содержат бизнес-логику:
- Прямые ORM запросы (`User.objects`, `DiaryEntry.objects`)
- Вычисления и преобразования данных
- Форматирование для отображения
- Валидацию
- Работу с внешними API

**Решение:**
Создать НОВЫЕ сервисы (подробный план в `HANDLERS_REFACTORING_PLAN.md`):

1. **diary_display_service.py** - rating buttons, star display, pagination
2. **feedback_service.py** - все Feedback ORM запросы
3. **admin_service.py** - stats (85 строк), broadcast
4. **task_display_service.py** - analysis notification (126 строк)
5. **calendar_service.py** - date arithmetic, FIX bug
6. **Дополнить user_profile_service.py** - utilities, validation

**Задачи:**
- [ ] 2.1.5.1. Создать `diary/services/diary_display_service.py`
- [ ] 2.1.5.2. Создать `diary/services/feedback_service.py`
- [ ] 2.1.5.3. Создать `core/services/admin_service.py`
- [ ] 2.1.5.4. Создать `diary/services/task_display_service.py`
- [ ] 2.1.5.5. Создать `core/services/calendar_service.py`
- [ ] 2.1.5.6. Дополнить `user_profile_service.py`
- [ ] 2.1.5.7. Унифицировать `is_admin` / `is_developer`
- [ ] 2.1.5.8. Создать `core/services/base_service.py`
- [ ] 2.1.5.9. Написать тесты для всех сервисов

**Приоритет:** 🔴 ВЫСОКИЙ  
**Сложность:** Высокая  
**Риск:** Низкий (только вынос, без изменения логики)  
**Время на выполнение:** 3 недели

---

#### 2.2. Стандартизировать возврат данных из сервисов ✅

**Проблема:**
Разные сервисы возвращают данные в разных форматах:
```python
return {'success': True, 'entry': entry, 'analysis': analysis}
return True
return entry
```

**Решение:**
Создан единый Response класс:

```python
# core/service_response.py
# Использование:
return ServiceResponse.ok(data={'entry': entry, 'analysis': analysis})
return ServiceResponse.fail(error='not_found', message='Запись не найдена')
```

**Задачи:**
- [x] 2.2.1. Создать `core/service_response.py` ✅ ВЫПОЛНЕНО
- [ ] 2.2.2. Обновить все сервисы для использования ServiceResponse (постепенно, по мере рефакторинга)
- [ ] 2.2.3. Обновить handlers для работы с ServiceResponse (постепенно)
- [x] 2.2.4. Добавить валидацию в ServiceResponse ✅ (is_error, has_data, get, __bool__)

**Создано:**
- `ServiceResponse` — dataclass с методами `ok()`, `fail()`, `make_error()`, `is_error()`, `has_data()`, `get()`, `__bool__`
- `ServiceResponseList` — контейнер для батч-операций с подсчётом success/error
- Тесты: `tests/test_service_response.py` (21 тест)

**Приоритет:** 🔴 Высокий → ✅ ВЫПОЛНЕНО

---

#### 2.3. Вынести бизнес-логику из handlers

**Файлы:**
- `bot/handlers/diary.py` (1361 строка!)
- `bot/handlers/*.py`

**Проблема:**
Handlers содержат:
- Бизнес-логику
- Форматирование сообщений
- Работу с БД
- FSM управление

**Решение:**
Четкое разделение:
```
handlers/     # Только: receive event -> call service -> format response -> send
services/     # Только: бизнес-логика
formatters/   # Только: форматирование для Telegram/API
```

**Задачи:**
- [ ] 2.3.1. Создать `bot/formatters/` директорию
- [ ] 2.3.2. Создать `bot/formatters/entry_formatter.py`
- [ ] 2.3.3. Создать `bot/formatters/analysis_formatter.py`
- [ ] 2.3.4. Вынести форматирование из handlers в formatters
- [ ] 2.3.5. Упростить handlers (максимум 30-40 строк)
- [ ] 2.3.6. Написать тесты

**Приоритет:** 🟡 Средний  
**Сложность:** Высокая  
**Риск:** Средний

---

### 📦 ЭТАП 3: Подготовка базы для API

**Цель:** Создать foundation для REST API, отделить bot-specific logic

#### 3.1. Рефакторинг архитектуры: разделение Bot и Core

**Проблема:**
Сейчас bot/services напрямую работает с Django models. Нет слоя абстракции.

**Решение:**
Создать `core/services/` - независимые от бота сервисы:

```
core/
  services/
    entry_service.py        # Не зависит от aiogram
    analysis_service.py     # Не зависит от aiogram
    user_service.py         # Не зависит от aiogram
    progress_service.py     # Не зависит от aiogram

bot/
  services/
    telegram_service.py     # Только Telegram-specific логика
    notification_service.py # Только уведомления в Telegram
```

**Задачи:**
- [ ] 3.1.1. Создать `core/services/` директорию
- [ ] 3.1.2. Переместить независимые сервисы из `diary/services/` в `core/services/`
- [ ] 3.1.3. Переместить независимые сервисы из `bot/services/` в `core/services/`
- [ ] 3.1.4. Обновить импорты везде
- [ ] 3.1.5. Убедиться что core.services не импортирует aiogram
- [ ] 3.1.6. Написать тесты

**Приоритет:** 🔴 Высокий  
**Сложность:** Высокая  
**Риск:** Средний

---

#### 3.2. Создать валидаторы данных

**Файлы:**
- `bot/utils/validation_utils.py` (есть, но слабая)

**Проблема:**
Валидация только в handlers, нет единой системы валидации для API

**Решение:**
Создать систему валидации на основе Pydantic (уже есть в requirements):

```python
# core/validators.py
from pydantic import BaseModel, validator

class EntryCreateValidator(BaseModel):
    text: str
    language: str = 'ru'
    entry_datetime: Optional[datetime] = None
    
    @validator('text')
    def text_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Текст не может быть пустым')
        if len(v) > 4000:
            raise ValueError('Текст слишком длинный')
        return v

class EntryUpdateValidator(EntryCreateValidator):
    entry_id: int
```

**Задачи:**
- [ ] 3.2.1. Создать `core/validators.py`
- [ ] 3.2.2. Создать валидаторы для всех основных сущностей
- [ ] 3.2.3. Интегрировать в сервисы
- [ ] 3.2.4. Интегрировать в API serializers
- [ ] 3.2.5. Написать тесты для валидаторов

**Приоритет:** 🔴 Высокий  
**Сложность:** Низкая  
**Риск:** Низкий

---

#### 3.3. Создать единую систему ошибок

**Проблема:**
Разные части проекта по-разному обрабатывают ошибки

**Решение:**
```python
# core/exceptions.py

class PsychoDiaryError(Exception):
    """Базовый класс исключений."""
    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)

class EntryNotFoundError(PsychoDiaryError):
    def __init__(self, entry_id: int):
        super().__init__(
            message=f"Запись {entry_id} не найдена",
            code="ENTRY_NOT_FOUND",
            status_code=404
        )

class InsufficientTokensError(PsychoDiaryError):
    def __init__(self, required: int, available: int):
        super().__init__(
            message=f"Недостаточно токенов. Требуется: {required}, доступно: {available}",
            code="INSUFFICIENT_TOKENS",
            status_code=402
        )
```

**Задачи:**
- [ ] 3.3.1. Создать `core/exceptions.py`
- [ ] 3.3.2. Создать иерархию исключений
- [ ] 3.3.3. Обновить сервисы для использования исключений
- [ ] 3.3.4. Создать middleware для обработки исключений в API
- [ ] 3.3.5. Написать тесты

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

### 📦 ЭТАП 4: Разработка REST API

**Цель:** Полноценный REST API для фронтенда

#### 4.1. Реализовать Authentication API

**Файлы:**
- `api/views.py` (пустой)
- `api/serializers.py` (пустой)
- `api/urls.py` (пустой)

**Endpoint'ы:**
```
POST /api/v1/auth/login/          # Вход (email + password)
POST /api/v1/auth/register/       # Регистрация
POST /api/v1/auth/refresh/        # Обновление токена
POST /api/v1/auth/logout/         # Выход
GET  /api/v1/auth/me/             # Текущий пользователь
```

**Задачи:**
- [ ] 4.1.1. Создать `api/serializers.py` с Auth serializers
- [ ] 4.1.2. Создать `api/views/auth_views.py`
- [ ] 4.1.3. Настроить JWT authentication
- [ ] 4.1.4. Создать `api/urls.py` с роутингом
- [ ] 4.1.5. Добавить throttling/rate limiting
- [ ] 4.1.6. Написать тесты для auth
- [ ] 4.1.7. Добавить документацию (drf-spectacular или drf-yasg)

**Приоритет:** 🔴 Высокий  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 4.2. Реализовать Diary Entries API

**Endpoint'ы:**
```
GET    /api/v1/entries/              # Список записей (paginated)
POST   /api/v1/entries/              # Создать запись
GET    /api/v1/entries/{id}/         # Получить запись
PUT    /api/v1/entries/{id}/         # Обновить запись
DELETE /api/v1/entries/{id}/         # Удалить запись
GET    /api/v1/entries/date/{date}/  # Записи за дату
GET    /api/v1/entries/{id}/analysis/  # Анализ записи
POST   /api/v1/entries/{id}/comment/   # Добавить комментарий
```

**Задачи:**
- [ ] 4.2.1. Создать `api/serializers.py` с Entry serializers
- [ ] 4.2.2. Создать `api/views/entry_views.py`
- [ ] 4.2.3. Создать `api/views/analysis_views.py`
- [ ] 4.2.4. Добавить pagination, filtering, ordering
- [ ] 4.2.5. Добавить permissions (только свои записи)
- [ ] 4.2.6. Написать тесты
- [ ] 4.2.7. Добавить документацию

**Приоритет:** 🔴 Высокий  
**Сложность:** Высокая  
**Риск:** Средний

---

#### 4.3. Реализовать User Profile API

**Endpoint'ы:**
```
GET    /api/v1/profile/              # Профиль пользователя
PUT    /api/v1/profile/              # Обновить профиль
GET    /api/v1/profile/statistics/   # Статистика
GET    /api/v1/profile/history/      # История изменений профиля
GET    /api/v1/profile/tokens/       # Баланс токенов
GET    /api/v1/profile/transactions/ # История транзакций
```

**Задачи:**
- [ ] 4.3.1. Создать serializers для Profile
- [ ] 4.3.2. Создать views для Profile
- [ ] 4.3.3. Создать serializers для TokenTransaction
- [ ] 4.3.4. Добавить endpoints
- [ ] 4.3.5. Написать тесты

**Приоритет:** 🟡 Средний  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 4.4. Реализовать Progress & Analytics API

**Endpoint'ы:**
```
GET    /api/v1/progress/             # Прогресс пользователя
GET    /api/v1/progress/streak/      # Серия дней
GET    /api/v1/progress/mood/{period}/  # График настроения
GET    /api/v1/progress/weekly/      # Недельные анализы
GET    /api/v1/progress/activity/    # Активность пользователя
```

**Задачи:**
- [ ] 4.4.1. Создать serializers для Progress
- [ ] 4.4.2. Создать views для Progress
- [ ] 4.4.3. Создать serializers для Mood charts
- [ ] 4.4.4. Добавить endpoints
- [ ] 4.4.5. Написать тесты

**Приоритет:** 🟡 Средний  
**Сложность:** Высокая  
**Риск:** Средний

---

#### 4.5. Реализовать Therapy Tasks API

**Endpoint'ы:**
```
GET    /api/v1/tasks/                # Список заданий
GET    /api/v1/tasks/{id}/           # Конкретное задание
POST   /api/v1/tasks/{id}/complete/  # Выполнить задание
GET    /api/v1/tasks/history/        # История заданий
```

**Задачи:**
- [ ] 4.5.1. Создать serializers для Tasks
- [ ] 4.5.2. Создать views для Tasks
- [ ] 4.5.3. Добавить endpoints
- [ ] 4.5.4. Написать тесты

**Приоритет:** 🟢 Низкий  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 4.6. Создать API документацию

**Задачи:**
- [ ] 4.6.1. Установить drf-spectacular или drf-yasg
- [ ] 4.6.2. Настроить автоматическую генерацию OpenAPI schema
- [ ] 4.6.3. Добавить Redoc/Swagger UI
- [ ] 4.6.4. Добавить примеры запросов/ответов
- [ ] 4.6.5. Написать документацию по аутентификации

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

### 📦 ЭТАП 5: Инфраструктура и производительность

**Цель:** Оптимизировать производительность, CI/CD, мониторинг

#### 5.1. Оптимизировать работу с БД

**Проблема:**
- N+1 query problem во многих местах
- Отсутствие индексов на часто используемых полях
- Неоптимальные запросы

**Решение:**
```python
# Оптимизированные querysets
class DiaryEntryQuerySet(models.QuerySet):
    def with_analysis(self):
        return self.select_related('analysis')
    
    def with_user(self):
        return self.select_related('user')
    
    def for_date(self, date):
        return self.filter(created_at__date=date)
```

**Задачи:**
- [ ] 5.1.1. Добавить кастомные QuerySet классы
- [ ] 5.1.2. Оптимизировать все запросы (select_related, prefetch_related)
- [ ] 5.1.3. Добавить индексы на часто используемые поля
- [ ] 5.1.4. Создать миграцию для индексов
- [ ] 5.1.5. Профилировать запросы (django-debug-toolbar)
- [ ] 5.1.6. Написать тесты производительности

**Приоритет:** 🔴 Высокий  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 5.2. Настроить кэширование

**Проблема:**
Redis есть, но используется минимально

**Решение:**
```python
# Кэширование часто запрашиваемых данных
- Статистика пользователя (кэш 5 мин)
- Графики настроения (кэш 15 мин)
- Список заданий (кэш 10 мин)
```

**Задачи:**
- [ ] 5.2.1. Определить hot paths (что кэшировать)
- [ ] 5.2.2. Создать `core/cache.py` с утилитами
- [ ] 5.2.3. Добавить кэширование в API views
- [ ] 5.2.4. Добавить cache invalidation логику
- [ ] 5.2.5. Мониторить hit/miss ratio
- [ ] 5.2.6. Написать тесты

**Приоритет:** 🟡 Средний  
**Сложность:** Средняя  
**Риск:** Средний

---

#### 5.3. Добавить API versioning

**Задачи:**
- [ ] 5.3.1. Настроить URL versioning (`/api/v1/`)
- [ ] 5.3.2. Создать `api/v1/` структуру
- [ ] 5.3.3. Добавить документацию версионирования
- [ ] 5.3.4. Создать политику депрекейта версий

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

#### 5.4. Улучшить обработку ошибок в API

**Задачи:**
- [ ] 5.4.1. Создать exception handler middleware
- [ ] 5.4.2. Стандартизировать формат ошибок
- [ ] 5.4.3. Добавить логирование ошибок
- [ ] 5.4.4. Добавить Sentry или аналог
- [ ] 5.4.5. Написать тесты для error cases

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

#### 5.5. Создать административные API endpoints

**Endpoint'ы:**
```
GET    /api/v1/admin/users/          # Список пользователей
GET    /api/v1/admin/users/{id}/     # Профиль пользователя
PUT    /api/v1/admin/users/{id}/     # Обновить пользователя
GET    /api/v1/admin/feedbacks/      # Обратная связь
POST   /api/v1/admin/feedbacks/{id}/reply/  # Ответить
GET    /api/v1/admin/stats/          # Общая статистика
```

**Задачи:**
- [ ] 5.5.1. Создать admin permissions
- [ ] 5.5.2. Создать admin serializers
- [ ] 5.5.3. Создать admin views
- [ ] 5.5.4. Добавить endpoints
- [ ] 5.5.5. Написать тесты

**Приоритет:** 🟢 Низкий  
**Сложность:** Средняя  
**Риск:** Низкий

---

### 📦 ЭТАП 6: Тестирование и документация

#### 6.1. Расширить покрытие тестов

**Текущее покрытие:** ~30%  
**Целевое покрытие:** ~80%

**Задачи:**
- [ ] 6.1.1. Настроить pytest-cov
- [ ] 6.1.2. Написать unit тесты для всех сервисов
- [ ] 6.1.3. Написать integration тесты для API
- [ ] 6.1.4. Написать тесты для моделей
- [ ] 6.1.5. Написать тесты для validators
- [ ] 6.1.6. Написать тесты для exceptions
- [ ] 6.1.7. Настроить CI для запуска тестов
- [ ] 6.1.8. Настроить codecov или аналог

**Приоритет:** 🔴 Высокий  
**Сложность:** Высокая  
**Риск:** Низкий

---

#### 6.2. Создать документацию проекта

**Задачи:**
- [ ] 6.2.1. Создать `docs/` директорию
- [ ] 6.2.2. Написать `ARCHITECTURE.md` с описанием архитектуры
- [ ] 6.2.3. Написать `API_GUIDE.md` для разработчиков API
- [ ] 6.2.4. Написать `CONTRIBUTING.md` для контрибьюторов
- [ ] 6.2.5. Написать `DEPLOYMENT.md` для деплоя
- [ ] 6.2.6. Обновить `README.md`
- [ ] 6.2.7. Добавить docstrings во все модули
- [ ] 6.2.8. Настроить Sphinx или MkDocs

**Приоритет:** 🟡 Средний  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 6.3. Создать Postman/Swagger коллекцию

**Задачи:**
- [ ] 6.3.1. Экспортировать OpenAPI schema
- [ ] 6.3.2. Создать Postman коллекцию
- [ ] 6.3.3. Добавить примеры для всех endpoints
- [ ] 6.3.4. Добавить environment variables
- [ ] 6.3.5. Написать инструкцию по использованию

**Приоритет:** 🟡 Средний  
**Сложность:** Низкая  
**Риск:** Низкий

---

## 📊 Метрики успеха

### До оптимизации:
- ❌ Еженедельный анализ: часто падает (< 70% success rate)
- ❌ Часовые пояса: записи смещаются при смене TZ
- ❌ Поля профиля: раздуваются, не чистятся
- ❌ AI затраты: не мониторятся, высокие
- ❌ Серия дней: показывается 0 если не сделал запись сегодня
- ❌ Напоминания о подписке: только в утренних сообщениях
- ❌ Мониторинг: отсутствует полностью
- ❌ Покрытие тестов: ~30%
- ❌ Размер diary_service.py: 1215 строк
- ❌ API endpoints: 0

### После ЭТАПА 0 (критические исправления):
- ✅ Еженедельный анализ: > 95% success rate
- ✅ Часовые пояса: записи не смещаются
- ✅ Поля профиля: автоматически чистятся
- ✅ AI затраты: мониторятся, оптимизированы на 20-30%
- ✅ Серия дней: показывается корректно + предупреждение
- ✅ Напоминания о подписке: автоматические, своевременные
- ✅ Мониторинг: полная видимость системы
- ✅ Дублирование кода: устранено (get_user_streaks)

### После полной оптимизации:
- ✅ Покрытие тестов: >80%
- ✅ Максимальный размер сервиса: <300 строк
- ✅ Максимальный размер handler: <50 строк
- ✅ API endpoints: >30
- ✅ Дублирование кода: минимальное
- ✅ AI затраты: оптимизированы на 40-50%
- ✅ Monitoring dashboard: полная видимость

---

## 🎯 Рекомендуемый порядок выполнения

### 📍 Фаза 0: КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ (Недели 1-3) 🔥
1. ✅ ЭТАП 0.1: Исправить еженедельный анализ (сжатие контекста + fallback)
2. ✅ ЭТАП 0.2: Исправить часовой пояс в записях (добавить creator_timezone)
3. ✅ ЭТАП 0.3: Добавить TTL для полей профиля (автоочистка)
4. ✅ ЭТАП 0.4: Оптимизация затрат на AI (мониторинг + оптимизация)
5. ✅ ЭТАП 0.5: Исправить подсчет серии на главном экране
6. ✅ ЭТАП 0.6: Добавить напоминание об окончании подписки
7. ✅ ЭТАП 0.7: Создать систему мониторинга

**Результат:** Бот работает стабильно, пользователи довольны, есть мониторинг

### 📍 Фаза 1: Foundation (Недели 4-5)
8. ✅ ЭТАП 1.1: Убрать дублирование sync/async методов
9. ✅ ЭТАП 1.3: Добавить Manager классы
10. ✅ ЭТАП 3.3: Создать единую систему ошибок
11. ✅ ЭТАП 3.2: Создать валидаторы данных

**Результат:** Код чище, меньше дублирования

### 📍 Фаза 2: Рефакторинг (Недели 6-7)
12. ✅ ЭТАП 2.2: Стандартизировать возврат данных
13. ✅ ЭТАП 2.1: Рефакторинг DiaryService
14. ✅ ЭТАП 3.1: Разделение Bot и Core
15. ✅ ЭТАП 2.3: Вынести бизнес-логику из handlers

**Результат:** Код готов для API

### 📍 Фаза 3: API Development (Недели 8-10)
16. ✅ ЭТАП 4.1: Authentication API
17. ✅ ЭТАП 4.2: Diary Entries API
18. ✅ ЭТАП 4.3: User Profile API
19. ✅ ЭТАП 4.4: Progress & Analytics API
20. ✅ ЭТАП 4.5: Therapy Tasks API
21. ✅ ЭТАП 4.6: API документация

**Результат:** Полноценное REST API

### 📍 Фаза 4: Optimization (Недели 11-12)
22. ✅ ЭТАП 5.1: Оптимизировать работу с БД
23. ✅ ЭТАП 5.2: Настроить кэширование
24. ✅ ЭТАП 5.3: Добавить API versioning
25. ✅ ЭТАП 5.4: Улучшить обработку ошибок

**Результат:** Высокая производительность

### 📍 Фаза 5: Testing & Docs (Недели 13-14)
26. ✅ ЭТАП 6.1: Расширить покрытие тестов
27. ✅ ЭТАП 6.2: Создать документацию
28. ✅ ЭТАП 6.3: Создать Postman коллекцию

**Результат:** Проект готов к production и масштабированию

---

## ⚠️ Важные замечания

1. **Тесты перед рефакторингом**: Перед каждым большим рефакторингом убедитесь, что текущие тесты проходят
2. **Постепенный подход**: Не делать все изменения сразу, двигаться маленькими шагами
3. **Code review**: Каждый этап должен проходить code review
4. **Backup**: Перед большими изменениями делать backup БД
5. **Миграции**: Все изменения моделей должны иметь миграции
6. **Документация изменений**: Вести CHANGELOG.md

---

## 🚀 Быстрый старт

Для начала работы рекомендую:

1. **Сначала утвердить этот план**
2. **Начать с Фазы 1** (самые безопасные изменения)
3. **Каждый этап завершать коммитом** с понятным сообщением
4. **Запускать тесты после каждого изменения**

---

## 📝 История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-04-05 | 1.0 | Первоначальная версия плана |
| 2026-04-08 | 2.1 | ✅ 0.5 завершена (серии дней). ✅ 0.2 на 90% (модель+миграции TZ). Исправлен import в diary_utils. Миграция 0094 переписана с батчингом |
| 2026-04-08 | 2.2 | ✅ LITE-промпты: incremental_day_analysis_lite + full_day_analysis_lite. Экономия ~50-65% токенов для обычных пользователей |
| 2026-04-08 | 2.3 | ✅ Синхронизированы сообщения RU/EN: добавлены 25 ключей в EN (transaction history в progress, analysis/day_analysis в profile, task_summary в tasks, entry_delete_cancelled, confirm_delete_entry_prompt, ask_analysis_time). Удалён лишний entry_delete_cancelled из en_main.py, task_summary_other из en_tasks.py |

---

## ✅ Статус выполнения

**Общий прогресс:** ~12%

### ЭТАП 0: КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ — 35%
- [ ] 0.1. Исправить еженедельный анализ
- [x] 0.2. Исправить часовой пояс в записях — 90% ✅ ГОТОВО К ДЕПЛОЮ (остались тесты)
- [ ] 0.3. Добавить TTL для полей профиля
- [ ] 0.4. Оптимизация затрат на AI
- [x] 0.5. Исправить подсчет серии на главном экране ✅ ЗАВЕРШЕНО
- [ ] 0.6. Добавить напоминание об окончании подписки
- [ ] 0.7. Создать систему мониторинга

### ЭТАП 1: Рефакторинг моделей — 0%
- [ ] 1.1. Убрать дублирование sync/async методов
- [ ] 1.2. Оптимизировать Encrypted поля
- [ ] 1.3. Добавить Manager классы

### ЭТАП 2: Оптимизация сервисов — 15%
- [ ] 2.1. Рефакторинг DiaryService
- [x] 2.1.5.1. Создать `diary/services/diary_display_service.py` ✅ ВЫПОЛНЕНО
- [x] 2.1.5.3. Создать `core/services/admin_service.py` ✅ ВЫПОЛНЕНО
- [ ] 2.1.5.2. Создать `diary/services/feedback_service.py`
- [ ] 2.1.5.4. Создать `diary/services/task_display_service.py`
- [ ] 2.1.5.5. Создать `core/services/calendar_service.py`
- [ ] 2.1.5.6. Дополнить `user_profile_service.py`
- [ ] 2.1.5.7-9. Унификация, base_service, тесты
- [ ] 2.2. Стандартизировать возврат данных
- [ ] 2.3. Вынести бизнес-логику из handlers

### ЭТАП 3: Подготовка для API — 0%
- [ ] 3.1. Разделение Bot и Core
- [ ] 3.2. Создать валидаторы данных
- [ ] 3.3. Создать единую систему ошибок

### ЭТАП 4: Разработка REST API — 0%
- [ ] 4.1. Authentication API
- [ ] 4.2. Diary Entries API
- [ ] 4.3. User Profile API
- [ ] 4.4. Progress & Analytics API
- [ ] 4.5. Therapy Tasks API
- [ ] 4.6. API документация

### ЭТАП 5: Инфраструктура — 0%
- [ ] 5.1. Оптимизировать работу с БД
- [ ] 5.2. Настроить кэширование
- [ ] 5.3. Добавить API versioning
- [ ] 5.4. Улучшить обработку ошибок

### ЭТАП 6: Тесты и документация — 0%
- [ ] 6.1. Расширить покрытие тестов
- [ ] 6.2. Создать документацию
- [ ] 6.3. Создать Postman коллекцию

---

> **Следующий шаг:** Утвердить план и начать с ЭТАПА 0.1 (исправить еженедельный анализ)

---

## 🗄️ Оптимизация работы с базой данных

### Текущие проблемы БД:

**1. N+1 Query Problem**
- Во многих местах нет `select_related` / `prefetch_related`
- Пример: получение записей с анализом → N+1 запросов

**2. Отсутствие индексов**
- Часто используемые поля не индексированы
- `DiaryEntry.created_at` - есть индекс ✅
- `DiaryEntry.user` - есть индекс ✅
- Но есть и проблемные места

**3. Неоптимальные запросы**
```python
# ПЛОХО:
async for entry in DiaryEntry.objects.filter(user=user):
    analysis = await entry.analysis  # ← Запрос на каждую итерацию!

# ХОРОШО:
entries = DiaryEntry.objects.select_related('analysis').filter(user=user)
async for entry in entries:
    #_analysis уже загружена
```

### Решения:

**1. Создать кастомные QuerySet классы:**
```python
class DiaryEntryQuerySet(models.QuerySet):
    def with_analysis(self):
        return self.select_related('analysis')
    
    def with_user(self):
        return self.select_related('user')
    
    def for_user_and_date(self, user, date):
        return self.filter(user=user, created_at__date=date)

class DiaryEntryManager(models.Manager):
    def get_queryset(self):
        return DiaryEntryQuerySet(self.model, using=self._db)
```

**2. Оптимизировать проблемные запросы:**
- `_gather_weekly_context` → использовать `prefetch_related`
- `_gather_user_context` → оптимизировать запросы
- `get_user_entries_for_date` → добавить `select_related`

**3. Добавить новые индексы:**
```python
class Meta:
    indexes = [
        # Уже есть:
        models.Index(fields=['user', 'created_at']),
        models.Index(fields=['user', 'day_group']),
        
        # Добавить:
        models.Index(fields=['user', 'is_processed']),
        models.Index(fields=['is_primary', 'created_at']),
        models.Index(fields=['user', 'is_recovered_streak', 'created_at']),
    ]
```

**4. Использовать database-level оптимизации:**
- `ONLY` clause для выбора только нужных полей
- `iterator()` для больших queryset
- Raw SQL для сложных агрегаций

**5. Мониторинг запросов:**
- Установить `django-debug-toolbar` для dev
- Использовать `django-silk` для profiling
- Логировать медленные запросы

### Задачи для БД оптимизации:

- [ ] Создать кастомные QuerySet для DiaryEntry
- [ ] Создать кастомные QuerySet для CombinedDiaryEntry
- [ ] Оптимизировать `_gather_weekly_context` запросы
- [ ] Добавить новые индексы
- [ ] Проверить все `async for` на N+1 problem
- [ ] Добавить database-level caching
- [ ] Настроить логирование медленных запросов
- [ ] Провести нагрузочное тестирование
