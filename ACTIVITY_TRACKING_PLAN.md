# План единой фиксации активности (UserActivity)

Статус: **P0–P2 реализовано** (осталась стендовая проверка AI-выборки)  
Дата фиксации: 2026-08-13  
Обновлено: 2026-08-13 — P2: сняты шумовые TG-декораторы, события на фактических действиях  
Связанные места: `bot/decorators/analytics_decorator.py`, `diary/models.py` (`UserActivity`), `core/constants.py` (`ACTIVITY_TYPES`), `diary/tasks/ai_activity_filter.py`, `bot/utils/activity_chart.py`, `bot/handlers/max/dispatcher.py`

---

## Цель

Единый паттерн записи активности для **Telegram**, **MAX** и (позже) **Web**:

1. Корректный AI-фильтр неактивных (`UserActivity` + fallback `last_activity` / `last_entry`).
2. Админ-графики активности.
3. Осмысленная продуктовая аналитика без шума.

---

## Текущее состояние

| Канал | Механизм | Проблема |
|-------|----------|----------|
| Telegram | `@log_user_activity` на ~80 хендлерах | Шум: каждый подраздел help, промежуточные settings, `entry_process` поверх `entry_created` |
| MAX | нет | Клики/команды не пишутся в `UserActivity`; `last_activity` обновляется в основном при создании записи |
| Web API | нет единого паттерна | Вне скоупа первой итерации |

Декоратор завязан на `kwargs['user']` (aiogram middleware) — напрямую на MAX-handlers не переносится.

---

## Единый паттерн

### 1. Сервис

Файл (предложение): `diary/services/activity_service.py` (альтернатива: `bot/services/activity_service.py`).

```python
async def record_user_activity(
    user,
    activity_type: str,
    *,
    platform: str,  # 'telegram' | 'max' | 'web'
    metadata: dict | None = None,
    touch_last_activity: bool = True,
) -> None:
    ...
```

Поведение:

- пишет `UserActivity` (ошибки глотать, handler не ронять);
- в `metadata` всегда есть `platform`, опционально `context` / `handled` / `payload`;
- при `touch_last_activity=True` обновляет `user.last_activity`;
- типы вне allowlist — не писать в `UserActivity` (или мапить в общий тип по явному решению);
- режим `touch_only` (опционально): обновить только `last_activity` без строки `UserActivity` (для «тихой» навигации, если понадобится для AI-фильтра).

### 2. Allowlist значимых событий

**Оставляем (писать в UserActivity):**

| Тип | Смысл |
|-----|--------|
| `entry_created` | Новая запись |
| `entry_comment` | Комментарий к анализу |
| `entry_rate` | Оценка анализа |
| `entry_edit` | Редактирование записи |
| `entry_deleted` / `day_entry_delete` | Удаление |
| `entry_viewed` | Просмотр записи |
| `analysis_viewed` | Просмотр анализа дня |
| `archive_viewed` | Открытие архива/календаря |
| `task_completed` / `task_skipped` / `task_deleted` | Задания |
| `settings_changed` | Факт изменения настроек |
| `command` | `/start`, deep-link |
| `chat` | Сообщение в терапии |
| `onboarding` | Вехи: agree, timezone done, first entry |
| `show_profile` | Открытие профиля (один раз на заход, не каждое поле) |
| `referral` | Рефералка |
| `message_voice` | Голос (если нужен отдельно от entry) |

**Убираем / не пишем (шум в Telegram сейчас):**

- каждый `help_open` по подразделам;
- `settings` (просто открытие меню);
- `entry_process`, `entry_invalide`;
- `fallback`, `button` на каждый Back / main_menu;
- `task` (просто список), `task_chart_viewed`;
- промежуточные `edit_profile` / `delete_profile` клики → в конце успеха один `profile_updated` (или оставить точечно по решению при реализации).

Детали сценария — только в `metadata`, не размножать `activity_type`.

### 3. Точки вызова (transport-thin)

**MAX (предпочтительно центрально):**

- один вызов в конце `dispatch_max_update` по `result['handled']` + `event.event_type`;
- таблица маппинга `handled` → `activity_type` (см. ниже);
- не размазывать `record_user_activity` по десяткам MAX-handlers.

**Telegram:**

- декоратор перевести на вызов сервиса с `platform='telegram'`;
- срезать декораторы по allowlist (P2).

**Web API (позже):**

- тот же сервис в use-case / views при значимых действиях.

### 4. Черновик маппинга MAX

| handled / event | activity_type |
|-----------------|---------------|
| `bot_started` / start | `command` |
| diary entry saved | `entry_created` |
| `rate_analysis` | `entry_rate` |
| comment saved | `entry_comment` |
| task complete / skip / delete | `task_*` |
| settings toggle / change | `settings_changed` |
| therapy message | `chat` |
| onboarding milestones | `onboarding` |
| main_menu / help / чистая навигация | **не писать** UserActivity (при необходимости только `touch_last_activity`) |
| archive / progress open | `archive_viewed` (или отдельный тип progress — уточнить при реализации) |

Для AI-фильтра и админ-графиков достаточно любой записи активности за период; навигационный шум не обязателен.

---

## Этапы реализации

### P0 — инфраструктура

- [x] Сервис `record_user_activity` (`diary/services/activity_service.py`)
- [x] `platform` в metadata (`telegram` / `max` / `web`)
- [x] обновление `last_activity`
- [x] unit-тесты сервиса (`tests/test_activity_service.py`)
- [x] тип `onboarding` в `ACTIVITY_TYPES` + миграция

### P1 — MAX

- [x] Хук в `dispatch_max_update` после успешного routing
- [x] Маппинг `handled` → allowlist (+ touch_only для навигации)
- [ ] Проверка на стенде: MAX-only пользователь попадает в утреннюю/вечернюю выборку при кликах без новых записей

### P2 — Telegram cleanup

- [x] Декоратор → тонкая обёртка над сервисом (`platform='telegram'`)
- [x] Снять лишние `@log_user_activity` (help/fallback/main_menu/settings open/task list/entry_process/edit_profile…)
- [x] Значимые события перенесены на факт действия (`entry_created` на save, `entry_comment`/`entry_edit`/`entry_deleted`, `profile_updated` после update)
- [x] Тест `tests/test_activity_decorator_allowlist.py`
- [x] Сохранить поведение «после handler»

### P3 — выравнивание и документация

- [ ] Одинаковые типы на TG и MAX
- [ ] Краткая секция в `BOTS_TECHNICAL_GUIDE.md`
- [ ] При желании подчистить неиспользуемые `ACTIVITY_TYPES` (миграция не обязательна)

---

## Риски и решения

| Риск | Решение |
|------|---------|
| Рост таблицы `UserActivity` | Allowlist уменьшит объём относительно текущего TG |
| Старые отчёты по `help_open` | Станут реже; админ-графики агрегатные — ок |
| Логирование admin/broadcast | Не писать как пользовательскую активность |
| Падение handler из-за Redis/БД | Как сейчас: try/except вокруг записи |
| Двойной учёт entry (service + decorator) | При P2 оставить одну точку (декоратор или service-layer, не оба) |

---

## Явно не делаем в первой итерации

- Переписывать историю старых `UserActivity`
- Обязательную миграцию на урезанный `ACTIVITY_TYPES`
- Полный product analytics pipeline / внешние системы
- Throttle «1 событие в N минут» — опционально позже, если понадобится

---

## Решение к возврату

1. Делаем **сервис + allowlist**.
2. Сначала **P0 → P1 (MAX)**, cleanup Telegram — **P2**.
3. Навигацию (main_menu / help subsections) **не пишем** в `UserActivity` по умолчанию.
4. `archive_viewed` / progress — оставить в allowlist (уточнить при коде).

Когда вернёмся: начать с P0 в Agent mode.
