# Psycho Diary — API Reference для frontend-разработчика

---

## Что такое Psycho Diary

**Psycho Diary** — это сервис психологического дневника с AI-анализом. Пользователь ведёт текстовые записи о своём состоянии, мыслях и событиях — AI анализирует их в реальном времени, формирует персональный психологический профиль и сопровождает пользователя на пути к лучшему самопониманию.

Планируется визуал в виде дневника, тетради. 

Аватар в телегра: Дерево, дремнее, под ним мальчик с книгой.

Поэтому важны такие мотивы.

Далее идет технические моменты

Продукт существует в двух каналах: **Telegram-бот** (основной) и **веб-приложение** (разрабатывается). Оба используют одно REST API.

---

## Основные сущности и их связи

```
User
 ├── DiaryEntry          — отдельная запись дневника (текст, mood, AI-анализ)
 ├── CombinedDiaryEntry  — агрегат всех записей за один день
 ├── WeeklyAnalysis      — AI-отчёт за неделю
 ├── TherapyTask         — персональное задание от AI
 ├── PsychoAnalysis      — детальный AI-разбор конкретной записи
 └── UserActivity        — лента событий активности
```

---

## Пользовательский сценарий (что видит frontend)

1. **Онбординг** — регистрация/вход (email или через Telegram deep-link).
2. **Главный экран** — лента дней с настроением, текущий streak, кнопка новой записи.
3. **Новая запись** — пользователь пишет текст → API принимает → AI анализирует асинхронно (бот/фоновая задача).
4. **Карточка записи** — текст записи + результат AI-анализа: `mood_score`, `comment`, `recommendation`, `analysis_text`. Пользователь может добавить свой комментарий.
5. **День** — агрегированная запись дня со средним настроением за все записи.
6. **Прогресс** — streak, график настроения (daily/weekly/monthly), сводка.
7. **Задания** — список AI-заданий с фильтрами по статусу и типу, отметка выполнения.
8. **Профиль** — психологический портрет (формируется AI из записей), уровень осознанности 1–10, баланс токенов.
9. **Еженедельный отчёт** — автоматически генерируется AI, доступен только чтение.

---

## Бизнес-логика, важная для frontend

| Аспект | Детали |
|--------|--------|
| **Язык** | `ru` / `en`. Хранится в профиле пользователя, влияет на язык AI-ответов. |
| **Часовой пояс** | IANA-строка (`Europe/Moscow`). Дата записи (`entry_date`) рассчитывается на стороне сервера с учётом TZ пользователя. |
| **AI-анализ** | Создаётся асинхронно после сохранения записи. `is_processed: false` означает, что анализ ещё не готов. Поллить `GET /entries/<id>/analysis/` до появления результата. |
| **mood_score** | Целое число 1–10. `0` или отсутствие — анализ не завершён. |
| **is_primary** | Каждый день одна запись помечается как основная (`true`). Остальные — дополнительные. |
| **Streak** | Количество дней подряд с записями. За 7/30/365 дней начисляются токены. Можно восстановить пропущенный день (за токены). |
| **Токены** | Внутренняя валюта. Тратятся на AI-функции без подписки. Начисляются за выполнение заданий и streak. |
| **Premium** | `is_premium: true` + `premium_expires_at` в будущем → подписка активна. Расширяет лимиты AI-функций. |
| **awareness_level** | 1–10, растёт с активностью. Влияет на лимит заданий в день. |
| **Шифрование** | Все текстовые поля (текст записей, email, профиль) зашифрованы на сервере. Клиент получает расшифрованные значения — никаких дополнительных действий не нужно. |

---

## Базовый URL

```
https://<host>/api/v1/
```

Все ресурсные эндпоинты: `/api/v1/<resource>/`  
Все auth-эндпоинты: `/api/v1/auth/<action>/`

Swagger / ReDoc-документация (интерактивная):
- Schema JSON: `GET /api/v1/auth/schema/`
- ReDoc UI: `GET /api/v1/auth/docs/`

---

## Аутентификация

Используется **JWT (Bearer)**. Токен передаётся в заголовке:

```
Authorization: Bearer <access_token>
```

### Регистрация по email

```
POST /api/v1/auth/register/
Content-Type: application/json
```

**Тело запроса:**
```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "StrongPassword1!"
}
```

**Ответ `201`:**
```json
{
  "user": { "id": 1, "email": "user@example.com", "username": "user123" },
  "access": "<JWT access token>",
  "refresh": "<JWT refresh token>"
}
```

---

### Логин по email/паролю

```
POST /api/v1/auth/login/
Content-Type: application/json
```

**Тело запроса:**
```json
{
  "email": "user@example.com",
  "password": "StrongPassword1!"
}
```

> Поле `email` принимается вместо стандартного `username`.

**Ответ `200`:**
```json
{
  "access": "<JWT access token>",
  "refresh": "<JWT refresh token>"
}
```

---

### Обновление токена

```
POST /api/v1/auth/refresh/
Content-Type: application/json
```

```json
{ "refresh": "<JWT refresh token>" }
```

**Ответ `200`:**
```json
{ "access": "<новый access token>" }
```

> Примечание: в проекте также существуют совместимые JWT-эндпоинты:
>
> - `POST /api/v1/auth/token/`
> - `POST /api/v1/auth/token/refresh/`
>
> Для frontend рекомендуется использовать основной flow выше (`/auth/login/` и `/auth/refresh/`),
> но legacy-точки нужно учитывать при интеграции со старым клиентом.

---

### Авторизация через Telegram (deep-link)

Пользователь переходит из Telegram-бота — бот выдаёт одноразовый токен.

```
GET /api/v1/auth/telegram/?token=<telegram_token>
```

**Ответ `200`:**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user123",
    "telegram_id": 123456789,
    "first_name": "Иван"
  },
  "access": "<JWT access token>",
  "refresh": "<JWT refresh token>"
}
```

---

### Привязка Telegram к web-аккаунту

```
POST /api/v1/auth/generate-link/
Authorization: Bearer <access>
```

Алиас этого же метода:

```
POST /api/v1/auth/link-telegram/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "link": "https://t.me/<bot>?start=link_<token>",
  "expires_in": 600
}
```

Пользователь переходит по ссылке в Telegram — аккаунты связываются.

---

### Завершение регистрации (Telegram → добавить email)

```
POST /api/v1/auth/complete-registration/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{
  "email": "user@example.com",
  "password": "StrongPassword1!"
}
```

**Ответ `200`:**
```json
{
  "user": { "id": 1, "email": "user@example.com", "username": "user123" },
  "access": "<новый JWT access>",
  "refresh": "<новый JWT refresh>"
}
```

> Важно: `complete-registration` требует уже аутентифицированного пользователя (`Bearer access`).
> Обычно этот access получается на шаге `GET /api/v1/auth/telegram/?token=...`.

---

## Пользователь и профиль

### Текущий пользователь

```
GET /api/v1/users/me/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "user123",
  "first_name": "Иван",
  "last_name": "Иванов",
  "language": "ru",
  "timezone": "Europe/Moscow",
  "is_premium": false,
  "awareness_level": 3,
  "created_at": "2025-01-01T12:00:00Z",
  "token_balance": 150
}
```

**Поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | ID пользователя |
| `email` | string | Email (зашифрован в БД) |
| `language` | `"ru"` \| `"en"` | Язык интерфейса |
| `timezone` | string | Часовой пояс (IANA: `"Europe/Moscow"`) |
| `is_premium` | bool | Активная premium-подписка |
| `awareness_level` | int 1–10 | Уровень психологической осознанности |
| `token_balance` | int | Баланс внутренних токенов |

---

### Компактный профиль

```
GET /api/v1/profile/compact/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "id": 1,
  "first_name": "Иван",
  "language": "ru",
  "is_premium": false,
  "awareness_level": 3,
  "full_psych_profile_summary": "Человек с высоким уровнем рефлексии...",
  "compressed_psych_profile": { ... }
}
```

---

### Полный профиль

```
GET /api/v1/profile/full/
Authorization: Bearer <access>
```

Включает все психологические поля (все — read-only, формируются AI):

| Поле | Тип | Описание |
|------|-----|----------|
| `personality_traits` | object | Черты личности |
| `life_facts` | array | Значимые факты из жизни |
| `hobbies` | array | Увлечения |
| `core_values` | array | Ключевые ценности |
| `triggers` | array | Психологические триггеры |
| `strengths` | array | Сильные стороны |
| `areas_for_growth` | array | Зоны роста |
| `habits` | array | Привычки |
| `skills` | array | Навыки |
| `aspirations` | array | Стремления |
| `compressed_psych_profile` | object | Сжатый AI-профиль (для быстрых запросов) |
| `full_psych_profile` | object | Полный AI-профиль |

---

### Статистика профиля

```
GET /api/v1/profile/statistics/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "total_entries": 87,
  "days_with_entries": 42,
  "current_streak": 7,
  "max_streak": 14,
  "avg_mood_score": 6.4,
  "total_tasks_completed": 23,
  "weekly_analyses_count": 6,
  "last_entry_date": "2026-04-20"
}
```

---

### История профиля (снимки AI-изменений)

```
GET /api/v1/profile/history/
Authorization: Bearer <access>
```

Возвращает пагинированный список снимков профиля (как менялся AI-профиль со временем).

---

### Токены и транзакции

```
GET /api/v1/profile/tokens/
Authorization: Bearer <access>
```

```json
{
  "token_balance": 150,
  "total_earned": 500,
  "total_spent": 350,
  "transactions_count": 18
}
```

```
GET /api/v1/profile/transactions/
Authorization: Bearer <access>
```

```json
{
  "token_transactions": [
    { "id": 1, "amount": 50, "transaction_type": "reward", "description": "...", "created_at": "..." }
  ],
  "payments": [
    { "id": 1, "amount_rub": 299.0, "status": "succeeded", "tokens_granted": 200, "created_at": "..." }
  ]
}
```

---

## Записи дневника

### Список записей

```
GET /api/v1/entries/
Authorization: Bearer <access>
```

**Query параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `language` | `"ru"` \| `"en"` | Фильтр по языку |
| `is_processed` | bool | Фильтр по статусу обработки AI |
| `is_primary` | bool | Только основные записи дня |
| `date_from` | `YYYY-MM-DD` | Начало периода |
| `date_to` | `YYYY-MM-DD` | Конец периода |
| `ordering` | string | `created_at`, `-created_at`, `word_count`, `-word_count` |
| `page` | int | Номер страницы (размер страницы: 20) |

**Ответ `200`:**
```json
{
  "count": 87,
  "next": "https://.../api/v1/entries/?page=2",
  "previous": null,
  "results": [
    {
      "id": 101,
      "user": 1,
      "text": "Сегодня я почувствовал...",
      "created_at": "2026-04-20T10:30:00Z",
      "updated_at": "2026-04-20T10:30:00Z",
      "language": "ru",
      "word_count": 120,
      "is_processed": true,
      "entry_date": "2026-04-20",
      "is_primary": true,
      "user_comment": null
    }
  ]
}
```

---

### Создать запись

```
POST /api/v1/entries/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{
  "text": "Текст записи...",
  "language": "ru"
}
```

> Throttle: 30 записей/минуту

---

### Записи за конкретную дату

```
GET /api/v1/entries/date/<YYYY-MM-DD>/
Authorization: Bearer <access>
```

---

### AI-анализ записи

```
GET /api/v1/entries/<id>/analysis/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "entry_id": 101,
  "analysis_id": 55,
  "mood_score": 7,
  "comment": "Запись содержит признаки тревоги...",
  "recommendation": "Попробуйте практику дыхания...",
  "analysis_text": "Подробный анализ записи...",
  "processing_time": 3.2,
  "insights_extracted": true,
  "created_at": "2026-04-20T10:31:00Z"
}
```

---

### Добавить комментарий к записи

```
POST /api/v1/entries/<id>/comment/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{ "user_comment": "Я согласен с этим наблюдением." }
```

**Ответ `200`:**
```json
{
  "message": "Comment saved.",
  "entry": { ...serialized entry... }
}
```

---

## Объединённые записи дня (Days)

Агрегированные записи: одна запись на день + средний mood.

```
GET /api/v1/days/
Authorization: Bearer <access>
```

**Query параметры:** `date_from`, `date_to` (YYYY-MM-DD)

**Ответ `200`:**
```json
{
  "results": [
    {
      "id": 33,
      "user": 1,
      "date": "2026-04-20",
      "text": "Объединённый текст всех записей дня...",
      "entries_count": 2,
      "average_mood": 6.5,
      "daily_mood_scores": [6, 7],
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

> Только чтение (GET).

---

## Еженедельные анализы

```
GET /api/v1/weekly/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "results": [
    {
      "id": 10,
      "user": 1,
      "week_start_date": "2026-04-14",
      "summary_text": "На этой неделе наблюдались...",
      "progress_insights": { ... },
      "statistics": { ... },
      "comparison_with_previous": { ... },
      "created_at": "2026-04-20T08:00:00Z"
    }
  ]
}
```

> Только чтение (GET). Генерируются автоматически.

---

## Терапевтические задания

### Список заданий

```
GET /api/v1/tasks/
Authorization: Bearer <access>
```

**Query параметры:**

| Параметр | Значения | Описание |
|----------|----------|----------|
| `status` | `pending`, `completed`, `skipped`, `expired` | Фильтр по статусу |
| `type` | `daily`, `reflection`, `cognitive`, `creative`, `behavioral`, `mindfulness` | Тип задания |
| `complexity` | string | Сложность |
| `assigned_from` | `YYYY-MM-DD` | Дата назначения от |
| `assigned_to` | `YYYY-MM-DD` | Дата назначения до |
| `completed` | bool | Только выполненные/невыполненные |
| `ordering` | `assigned_at`, `-assigned_at`, `completed_at`, `-completed_at` | Сортировка |

**Запись задания:**
```json
{
  "id": 5,
  "user": 1,
  "title": "Утренняя медитация",
  "description": "5 минут осознанного дыхания...",
  "type": "mindfulness",
  "status": "pending",
  "assigned_at": "2026-04-20T00:00:00Z",
  "completed_at": null,
  "complexity": "easy"
}
```

---

### Выполнить задание

```
POST /api/v1/tasks/<id>/complete/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{ "status": "completed" }
```

---

### История заданий

```
GET /api/v1/tasks/history/
Authorization: Bearer <access>
```

Возвращает только задания со статусом `completed`, `skipped`, `expired`.

---

## Прогресс и аналитика

### Сводка прогресса

```
GET /api/v1/progress/
Authorization: Bearer <access>
```

```json
{
  "total_entries": 87,
  "total_days_with_entries": 42,
  "total_tasks_completed": 23,
  "weekly_analyses_count": 6,
  "avg_mood_score": 6.4
}
```

---

### Серия активности (streak)

```
GET /api/v1/progress/streak/
Authorization: Bearer <access>
```

```json
{
  "current_streak": 7,
  "max_streak": 14,
  "active_days_last_30": 20
}
```

---

### График настроения

```
GET /api/v1/progress/mood/<period>/
Authorization: Bearer <access>
```

`period`: `daily` | `weekly` | `monthly`

**Ответ `200`:**
```json
{
  "period": "weekly",
  "points": [
    { "period": "2026-W15", "avg_mood_score": 6.2, "entries_count": 5 },
    { "period": "2026-W16", "avg_mood_score": 7.0, "entries_count": 7 }
  ]
}
```

**Формат ключа `period`:**
- `daily` → `"2026-04-20"`
- `weekly` → `"2026-W16"`
- `monthly` → `"2026-04"`

---

### Недельные анализы (через progress)

```
GET /api/v1/progress/weekly/
Authorization: Bearer <access>
```

---

### Лента активности

```
GET /api/v1/progress/activity/
Authorization: Bearer <access>
```

```json
{
  "summary": {
    "diary_entry": 87,
    "task_completed": 23,
    "weekly_analysis": 6
  },
  "recent": [
    { "id": 200, "activity_type": "diary_entry", "timestamp": "2026-04-20T10:30:00Z", "metadata": {} }
  ]
}
```

---

## Формат ошибок

Все ошибки возвращаются в единой структуре:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "Token is invalid or expired",
    "details": { ... }  // опционально
  }
}
```

**Типичные коды ошибок:**

| HTTP | `code` | Ситуация |
|------|--------|----------|
| 400 | `token_required` | Не передан token |
| 400 | `invalid_token` | Токен истёк или неверен |
| 400 | `user_comment_required` | Пустой комментарий |
| 400 | `invalid_date_format` | Неверный формат даты (нужен YYYY-MM-DD) |
| 400 | `invalid_period` | Период не из daily/weekly/monthly |
| 401 | `not_authenticated` | Отсутствует или неверен JWT |
| 403 | `permission_denied` | Нет доступа к ресурсу |
| 404 | `user_not_found` | Пользователь не найден |
| 404 | `analysis_not_found` | AI-анализ для записи ещё не создан |
| 429 | `throttled` | Превышен лимит запросов |

---

## Rate Limits

| Scope | Лимит | Применяется к |
|-------|-------|---------------|
| `auth` | 10/минута | register, login, telegram auth |
| `refresh` | 20/минута | refresh токена |
| `link_generation` | 6/час | generate-link |
| `entry_mutation` | 30/минута | POST/PUT/PATCH/DELETE записей |
| `task_mutation` | 30/минута | POST/PUT/PATCH/DELETE заданий |
| `monitoring` | 30/минута | GET /monitoring/metrics/ |
| `monitoring_heavy` | 10/минута | GET /monitoring/prometheus/ |

При превышении лимита — `HTTP 429` с заголовком `Retry-After`.

---

## Пагинация

Все списочные эндпоинты возвращают:

```json
{
  "count": 87,
  "next": "https://.../api/v1/entries/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Размер страницы: **20 записей**. Управляется параметром `page`.

---

## Типы и константы

**Языки:** `"ru"` | `"en"`

**Типы заданий:** `daily`, `reflection`, `cognitive`, `creative`, `behavioral`, `mindfulness`

**Статусы заданий:** `pending`, `completed`, `skipped`, `expired`

**Типы активности (activity_type):** `diary_entry`, `task_completed`, `weekly_analysis`, и др.

**Уровень осознанности (awareness_level):** целое число 1–10

**mood_score:** целое число, обычно 1–10

**Часовые пояса:** строки IANA, например `"Europe/Moscow"`, `"UTC"`, `"America/New_York"`
