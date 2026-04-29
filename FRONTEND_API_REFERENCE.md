# Psycho Diary — API Reference для frontend-разработчика

> **Версия документа:** 1.0 | **Дата:** апрель 2026 | **API версия:** v1

---

## О продукте

**Psycho Diary** — сервис психологического дневника с AI-анализом. Пользователь ведёт текстовые записи о своём состоянии, мыслях и событиях. AI анализирует каждую запись, формирует персональный психологический профиль и сопровождает пользователя на пути к самопониманию.

### Визуальная концепция

Стиль — **дневник / рукописная тетрадь**: тёплые тона бумаги, рукописные шрифты, ощущение живого записанного момента. Логотип и ключевой образ — **старое дерево, под которым сидит мальчик с книгой**. Мотивы: уют, укрытие, рефлексия, рост.

### Каналы

Продукт существует в двух форматах:
- **Telegram-бот** (основной, уже работает)
- **Веб-приложение** (разрабатывается, этот документ — для него)

Оба канала используют одно и то же REST API.

---

## Сущности и их связи

```
User
 ├── DiaryEntry          — отдельная запись дневника (текст + AI-анализ)
 │    └── PsychoAnalysis — результат AI-анализа записи (mood, comment, recommendation)
 ├── CombinedDiaryEntry  — агрегат всех записей за один день (среднее mood, объединённый текст)
 ├── WeeklyAnalysis      — AI-отчёт за неделю
 ├── TherapyTask         — персональное задание от AI
 │    └── TaskCompletion — запись о выполнении (текст + ощущения)
 └── UserActivity        — лента событий активности
```

---

## Пользовательский сценарий

1. **Регистрация / вход** — email + пароль или deep-link из Telegram.
2. **Главный экран** — лента дней со средним настроением, текущий streak, кнопка новой записи.
3. **Новая запись** — пользователь пишет текст → `POST /entries/` или `POST /entries/create_with_analysis/` (с моментальным AI-анализом).
4. **Карточка записи** — текст + результат AI: `mood_score`, `comment`, `recommendation`, `analysis_text`. Пользователь может добавить свой комментарий.
5. **День** — агрегированная запись (`CombinedDiaryEntry`) со средним mood за день.
6. **Прогресс** — streak, график настроения (daily/weekly/monthly), сводка задач и записей.
7. **Задания** — список AI-заданий с фильтрами по статусу и типу; можно выполнить, пропустить, восстановить.
8. **Профиль** — психологический портрет (формируется AI), `awareness_level`, баланс токенов, реферальная ссылка.
9. **Еженедельный отчёт** — автоматически генерируется AI каждую неделю, доступен только для чтения.

---

## Ключевая бизнес-логика

| Аспект | Детали |
|--------|--------|
| **Язык** | `"ru"` / `"en"`. Хранится в профиле; влияет на язык AI-ответов. При смене в профиле (`PATCH /profile/`) — новые записи анализируются на новом языке. |
| **Часовой пояс** | IANA-строка (`"Europe/Moscow"`). Дата записи (`entry_date`) считается **на сервере** с учётом TZ пользователя, зафиксированного в момент создания. Frontend не вычисляет дату — берёт готовое поле `entry_date`. |
| **AI-анализ (асинхронный)** | `POST /entries/` создаёт запись, анализ готовится фоном. `is_processed: false` — анализ ещё не готов. Frontend должен поллить `GET /entries/<id>/analysis/` до `200` или показывать лоадер. |
| **AI-анализ (синхронный)** | `POST /entries/create_with_analysis/` — создаёт запись и сразу возвращает анализ. Время ответа 5–30 с. Рекомендуется для UX с мгновенным результатом. |
| **mood_score** | Целое число 1–10. Пока анализ не готов — поле `null` или отсутствует. |
| **is_primary** | Один раз в сутки одна запись помечается основной (`true`). Остальные — дополнительные. |
| **Streak** | Дней подряд с хотя бы одной записью. За 7 / 30 / 365 дней — автоначисление токенов. Можно восстановить пропущенный день через `POST /progress/restore_streak/` (за токены). |
| **Токены** | Внутренняя валюта. Начисляются за streak, задания, реферальных друзей. Тратятся на AI-функции без Premium. |
| **Premium** | `is_premium: true` + `premium_expires_at` в будущем → подписка активна. Без Premium — платные AI-вызовы идут за токены. |
| **awareness_level** | 1–10, автоматически растёт с активностью. Влияет на суточный лимит AI-заданий (`max_ai_tasks_per_day`). |
| **Шифрование** | Все текстовые поля (текст записей, email, поля профиля) зашифрованы в БД. API возвращает уже расшифрованные значения — никаких дополнительных действий на фронте не нужно. |
| **Пагинация** | Все списки: 20 элементов на страницу. Управляется параметром `?page=N`. Ответ содержит `count`, `next`, `previous`. |

---

## Базовый URL

```
https://<host>/api/v1/
```

Интерактивная документация (ReDoc):

```
GET https://<host>/api/v1/schema/    → OpenAPI JSON
GET https://<host>/api/v1/docs/      → ReDoc UI
```

---

## Аутентификация

Используется **JWT Bearer**:

```
Authorization: Bearer <access_token>
```

Access-токен живёт ограниченное время, обновляется через refresh.

---

## Эндпоинты — Auth

### Регистрация по email

```
POST /api/v1/register/
```

**Тело:**
```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "Str0ng!Pass",
  "password_confirm": "Str0ng!Pass"
}
```

**Ответ `201`:**
```json
{
  "user": { "id": 1, "email": "user@example.com", "username": "user123" },
  "access": "<JWT access>",
  "refresh": "<JWT refresh>"
}
```

**Валидация:** пароли должны совпадать; email должен быть уникальным.

---

### Логин по email + паролю

```
POST /api/v1/login/
```

**Тело:**
```json
{ "email": "user@example.com", "password": "Str0ng!Pass" }
```

> Принимается `email` (не `username`). Внутри подставляется нужный username автоматически.

**Ответ `200`:**
```json
{ "access": "<JWT access>", "refresh": "<JWT refresh>" }
```

---

### Обновление access-токена

```
POST /api/v1/refresh/
```

```json
{ "refresh": "<JWT refresh>" }
```

**Ответ `200`:**
```json
{ "access": "<новый access>" }
```

---

### Logout (выход из сессии)

```
POST /api/v1/logout/
Authorization: Bearer <access>
```

```json
{ "refresh": "<JWT refresh>" }
```

**Ответ `200`:**
```json
{ "detail": "Logged out successfully." }
```

**Что делает endpoint:**
- добавляет переданный refresh-токен в blacklist;
- после этого этот refresh нельзя использовать для `/api/v1/refresh/`.

**Ошибки:**
- `400 refresh_required` — не передан `refresh`;
- `400 invalid_refresh_token` — токен невалидный/просроченный;
- `401 not_authenticated` — нет access токена в заголовке.

---

### Авторизация через Telegram (deep-link)

Пользователь переходит из Telegram-бота — бот выдаёт одноразовый `token`.

```
GET /api/v1/telegram/?token=<telegram_token>
```

**Ответ `200`:**
```json
{
  "user": {
    "id": 1,
    "email": null,
    "username": "tg_123456789",
    "telegram_id": 123456789,
    "first_name": "Иван"
  },
  "access": "<JWT access>",
  "refresh": "<JWT refresh>"
}
```

> Email у Telegram-пользователей изначально `null`. Установить — через `/complete-registration/`.

---

### Завершение регистрации (добавить email к Telegram-аккаунту)

```
POST /api/v1/complete-registration/
Authorization: Bearer <access>
```

```json
{
  "email": "user@example.com",
  "password": "Str0ng!Pass",
  "password_confirm": "Str0ng!Pass"
}
```

**Ответ `200`:** возвращает обновлённые `user`, `access`, `refresh`.

---

### Генерация ссылки для привязки Telegram

```
POST /api/v1/generate-link/
Authorization: Bearer <access>
```

*(Алиас: `POST /api/v1/link-telegram/`)*

**Ответ `200`:**
```json
{
  "link": "https://t.me/<bot>?start=link_<token>",
  "expires_in": 600
}
```

Пользователь переходит по ссылке в Telegram — аккаунты связываются.

---

### Рекомендуемая стратегия авторизации на frontend

1. После `login/register/telegram` сохраняйте `access` и `refresh`.
2. Каждый API-запрос отправляйте с `Authorization: Bearer <access>`.
3. При `401` на защищённом endpoint: один раз вызовите `/api/v1/refresh/` и повторите исходный запрос.
4. Если `/api/v1/refresh/` тоже вернул `401/400` — очистите токены и перенаправьте пользователя на экран входа.
5. При явном выходе пользователя вызывайте `/api/v1/logout/` с `refresh`, затем локально очищайте токены.

> Важно: access сам по себе не отзывается мгновенно (он истекает по TTL). Logout инвалидирует refresh и блокирует продление сессии.

---

### Примеры ошибок авторизации

**Неверный логин/пароль (`POST /api/v1/login/`):**
```json
{
  "detail": "No active account found with the given credentials"
}
```

**Просроченный/невалидный refresh (`POST /api/v1/refresh/`):**
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

**Logout без refresh (`POST /api/v1/logout/`):**
```json
{
  "error": {
    "code": "refresh_required",
    "message": "Refresh token is required"
  }
}
```

**Logout с невалидным refresh (`POST /api/v1/logout/`):**
```json
{
  "error": {
    "code": "invalid_refresh_token",
    "message": "Refresh token is invalid or expired"
  }
}
```

---

## Эндпоинты — Пользователь

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

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | Внутренний ID |
| `email` | string\|null | Email (зашифрован в БД, возвращается расшифрованным) |
| `language` | `"ru"` \| `"en"` | Язык пользователя |
| `timezone` | string | Часовой пояс (IANA) |
| `is_premium` | bool | Признак активной Premium-подписки |
| `awareness_level` | int 1–10 | Уровень психологической осознанности |
| `token_balance` | int | Баланс токенов |

---

## Эндпоинты — Профиль

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
  "compressed_psych_profile": {
    "psych_summary": "...",
    "core_patterns": "...",
    "emotional_style": "...",
    "main_triggers": "...",
    "coping_style": "...",
    "current_focus": "..."
  }
}
```

Используйте для хедера / аватара / кратких виджетов.

---

### Полный профиль

```
GET /api/v1/profile/full/
Authorization: Bearer <access>
```

Включает все AI-профильные поля (read-only, формируются автоматически):

| Поле | Тип | Описание |
|------|-----|----------|
| `id`, `email`, `username`, `first_name`, `last_name` | — | Базовые данные |
| `language`, `timezone`, `is_premium`, `awareness_level`, `date_of_birth` | — | Настройки |
| `token_balance`, `created_at` | — | Финансы и дата |
| `personality_description` | string | Текстовое описание личности |
| `personality_traits` | object | Черты характера (ключ → значение) |
| `life_facts` | array[string] | Значимые факты из жизни |
| `hobbies` | array[string] | Увлечения |
| `core_values` | array[string] | Ключевые ценности |
| `triggers` | array[string] | Психологические триггеры |
| `strengths` | array[string] | Сильные стороны |
| `areas_for_growth` | array[string] | Зоны роста |
| `personality_insights` | object | Глубинные инсайты AI |
| `practical_patterns` | array | Поведенческие паттерны и привычки |
| `aspirations` | array[string] | Стремления |
| `compressed_psych_profile` | object | Сжатый AI-профиль |
| `full_psych_profile` | object | Полный AI-профиль (summary, traits, values и т.д.) |

> Все эти поля **read-only** — заполняет AI. Для редактирования базовых данных используйте `PATCH /profile/`.

---

### Обновление профиля

```
PATCH /api/v1/profile/<id>/
Authorization: Bearer <access>
Content-Type: application/json
```

*(Для получения `<id>` используйте `GET /api/v1/profile/` — список возвращает текущего пользователя)*

Поддерживаемые обновляемые поля:

| Поле | Тип | Валидация |
|------|-----|-----------|
| `first_name` | string | — |
| `last_name` | string | — |
| `date_of_birth` | `YYYY-MM-DD` | — |
| `language` | `"ru"` \| `"en"` | только эти два значения |
| `timezone` | string | IANA-строка (`"Europe/Moscow"`) |
| `notifications_enabled` | bool | — |
| `auto_analysis_enabled` | bool | — |
| `max_ai_tasks_per_day` | int | 1–10 |
| `hobbies` | array | — |
| `life_facts` | array | — |

**Пример:**
```json
{
  "first_name": "Иван",
  "language": "en",
  "timezone": "Europe/Berlin",
  "notifications_enabled": true,
  "max_ai_tasks_per_day": 3
}
```

**Ответ `200`:** полный профиль (`ProfileFullSerializer`).

**Ошибки:**
```json
{ "language": ["Допустимые значения: en, ru."] }
{ "timezone": ["Неверный часовой пояс."] }
{ "max_ai_tasks_per_day": ["Допустимые значения: от 1 до 10."] }
```

---

### Реферальная ссылка

```
GET /api/v1/profile/referral/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "referral_link": "https://t.me/<bot>?start=ref_<code>",
  "invited_count": 3,
  "reward_info": "За каждого приглашённого друга — 50 токенов"
}
```

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

### История изменений профиля

```
GET /api/v1/profile/history/
Authorization: Bearer <access>
```

Пагинированный список снимков (`UserProfileHistory`) — как менялся AI-профиль со временем.

**Один снимок:**
```json
{
  "id": 15,
  "created_at": "2026-04-14T09:00:00Z",
  "awareness_level": 3,
  "personality_traits": { ... },
  "life_facts": [ ... ],
  "hobbies": [ ... ],
  "core_values": [ ... ],
  "triggers": [ ... ],
  "strengths": [ ... ],
  "areas_for_growth": [ ... ],
  "personality_insights": { ... },
  "practical_patterns": [ ... ],
  "aspirations": [ ... ],
  "personality_description": "..."
}
```

---

### Баланс токенов

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

---

### История транзакций

```
GET /api/v1/profile/transactions/
Authorization: Bearer <access>
```

```json
{
  "token_transactions": [
    {
      "id": 10,
      "amount": 50,
      "transaction_type": "streak_reward",
      "description": "Серия 7 дней",
      "created_at": "2026-04-14T00:00:00Z"
    }
  ],
  "payments": [
    {
      "id": 3,
      "yookassa_payment_id": "pay_xxx",
      "amount_rub": 299.0,
      "payment_type": "subscription",
      "tokens_granted": 0,
      "subscription_days_granted": 30,
      "status": "succeeded",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ]
}
```

`amount` в токенах: положительное — начисление, отрицательное — списание.

---

## Эндпоинты — Записи дневника

### Список записей

```
GET /api/v1/entries/
Authorization: Bearer <access>
```

**Query-параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `language` | `"ru"` \| `"en"` | Фильтр по языку записи |
| `is_processed` | bool | `true` — только обработанные AI |
| `is_primary` | bool | `true` — только основные записи дня |
| `date_from` | `YYYY-MM-DD` | Начало периода |
| `date_to` | `YYYY-MM-DD` | Конец периода |
| `ordering` | string | `created_at`, `-created_at` (по умолч.), `word_count`, `-word_count` |
| `page` | int | Страница (размер 20) |

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

**Поля записи:**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | ID записи |
| `text` | string | Текст записи (расшифрованный) |
| `created_at` | datetime | Время создания (UTC) |
| `entry_date` | date | Дата записи **в часовом поясе пользователя** |
| `language` | string | Язык записи |
| `word_count` | int | Количество слов |
| `is_processed` | bool | Завершён ли AI-анализ |
| `is_primary` | bool | Является ли основной записью дня |
| `user_comment` | string\|null | Комментарий пользователя к анализу |

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

> Throttle: 30 запросов/минуту.

**Ответ `201`:** сериализованная запись (без анализа — он асинхронный).

После создания — поллить `GET /api/v1/entries/<id>/analysis/` каждые 2–5 с до `is_processed: true`.

---

### Создать запись с моментальным AI-анализом

```
POST /api/v1/entries/create_with_analysis/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{ "text": "Текст записи..." }
```

> Время ответа: **5–30 секунд**. Показывайте пользователю прогресс/лоадер.

**Ответ `201`:**
```json
{
  "entry": {
    "id": 101,
    "text": "Текст записи...",
    "entry_date": "2026-04-20",
    "is_processed": true,
    ...
  },
  "analysis": {
    "mood_score": 7,
    "comment": "Запись позитивная с элементами тревоги...",
    "recommendation": "Попробуйте технику 5-4-3-2-1...",
    "analysis_text": "Подробный анализ текста..."
  },
  "needs_clarification": false,
  "clarification_questions": []
}
```

**Поле `needs_clarification: true`** — AI хочет задать уточняющие вопросы. Список вопросов в `clarification_questions`. Frontend может предложить пользователю ответить на них.

**Ошибка `400`:**
```json
{ "error": { "code": "entry_invalid", "message": "Запись слишком короткая или нерелевантна." } }
```

---

### Подсказка для следующей записи

```
GET /api/v1/entries/next-prompt/
Authorization: Bearer <access>
```

Возвращает сгенерированную AI подсказку на **сегодня**, если она ещё не использована.

**Ответ `200` — подсказка есть:**
```json
{
  "has_prompt": true,
  "prompt": {
    "id": 12,
    "text": "Расскажи, что сегодня дало тебе ощущение контроля над ситуацией?",
    "target_date": "2026-04-28",
    "created_at": "2026-04-28T07:00:00Z"
  }
}
```

**Ответ `200` — подсказки нет:**
```json
{ "has_prompt": false, "prompt": null }
```

Подсказки генерируются AI автоматически. Если на текущий день подсказки нет — значит, она ещё не была создана (пользователь недавно зарегистрировался или AI не сгенерировал её в этот день).

---

### Отметить подсказку использованной

```
POST /api/v1/entries/next-prompt/mark-used/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{ "prompt_id": 12 }
```

Вызывайте после того, как пользователь прочитал подсказку и начал писать запись (или закрыл её). После этого `GET /entries/next-prompt/` вернёт `has_prompt: false` до следующего дня.

**Ответ `200`:**
```json
{ "marked_used": true, "prompt_id": 12 }
```

**Ошибки:**
- `400 prompt_id_required` — не передан `prompt_id`
- `404 prompt_not_found` — подсказка не найдена или принадлежит другому пользователю

---

### Записи за конкретную дату

```
GET /api/v1/entries/date/2026-04-20/
Authorization: Bearer <access>
```

Возвращает все записи пользователя за указанную дату (по `entry_date`).

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
  "comment": "Запись отражает спокойное состояние с лёгкой тревогой...",
  "recommendation": "Обратите внимание на паттерн избегания...",
  "analysis_text": "Подробный текст AI-анализа...",
  "processing_time": 3.2,
  "insights_extracted": 4,
  "created_at": "2026-04-20T10:31:00Z"
}
```

**Ответ `404`** — анализ ещё не готов (или запись не обработана):
```json
{ "error": { "code": "analysis_not_found", "message": "Analysis not found for this entry." } }
```

| Поле | Тип | Описание |
|------|-----|----------|
| `mood_score` | int 1–10 | Оценка настроения |
| `comment` | string | Краткий комментарий AI |
| `recommendation` | string | Персональная рекомендация |
| `analysis_text` | string | Развёрнутый текст анализа |
| `insights_extracted` | int | Количество извлечённых инсайтов |
| `processing_time` | float | Время обработки в секундах |

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
  "entry": { ...полная запись... }
}
```

---

### Получить / обновить / удалить запись

```
GET    /api/v1/entries/<id>/
PUT    /api/v1/entries/<id>/
PATCH  /api/v1/entries/<id>/
DELETE /api/v1/entries/<id>/
```

---

## Эндпоинты — Дни (CombinedDiaryEntry)

Агрегированный объект: один объект = один день. Только чтение.

```
GET /api/v1/days/
Authorization: Bearer <access>
```

**Query-параметры:** `date_from`, `date_to` (YYYY-MM-DD), `page`.

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
      "created_at": "2026-04-20T23:00:00Z",
      "updated_at": "2026-04-20T23:00:00Z"
    }
  ]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `date` | date | Дата дня |
| `entries_count` | int | Количество записей за день |
| `average_mood` | float | Среднее настроение за день |
| `daily_mood_scores` | array[int] | Все оценки mood за день |

---

## Эндпоинты — Еженедельный анализ

Только чтение. Генерируется AI автоматически.

```
GET /api/v1/weekly/
GET /api/v1/weekly/<id>/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "id": 10,
  "user": 1,
  "week_start_date": "2026-04-14",
  "summary_text": "Эта неделя была насыщенной эмоционально...",
  "progress_insights": { "key_insight": "..." },
  "statistics": { "avg_mood": 6.8, "entries_count": 7 },
  "comparison_with_previous": { "mood_change": "+0.4" },
  "created_at": "2026-04-20T08:00:00Z"
}
```

| Поле | Описание |
|------|----------|
| `week_start_date` | Понедельник недели |
| `summary_text` | Текстовое резюме от AI |
| `progress_insights` | Ключевые выводы и инсайты |
| `statistics` | Агрегированная статистика за неделю |
| `comparison_with_previous` | Сравнение с предыдущей неделей |

---

## Эндпоинты — Задания

### Список заданий

```
GET /api/v1/tasks/
Authorization: Bearer <access>
```

**Query-параметры:**

| Параметр | Значения | Описание |
|----------|----------|----------|
| `status` | `pending`, `completed`, `skipped`, `expired` | Фильтр по статусу |
| `type` | `daily`, `reflection`, `cognitive`, `creative`, `behavioral`, `mindfulness` | Тип задания |
| `complexity` | `low`, `medium`, `high` | Сложность |
| `assigned_from` | `YYYY-MM-DD` | Назначено от |
| `assigned_to` | `YYYY-MM-DD` | Назначено до |
| `completed` | bool | `true` — только с `completed_at`, `false` — только без |
| `ordering` | `assigned_at`, `-assigned_at`, `completed_at`, `-completed_at` | Сортировка |

**Запись задания:**
```json
{
  "id": 5,
  "user": 1,
  "title": "Утренняя медитация",
  "description": "5 минут осознанного дыхания перед зеркалом...",
  "type": "mindfulness",
  "status": "pending",
  "assigned_at": "2026-04-20T00:00:00Z",
  "completed_at": null,
  "complexity": "low"
}
```

**Статусы задания:**

| Статус | Описание |
|--------|----------|
| `pending` | Ожидает выполнения (начальный статус) |
| `completed` | Выполнено |
| `skipped` | Пропущено пользователем |
| `expired` | Истёк срок (автоматически) |

---

### Завершить задание

```
POST /api/v1/tasks/<id>/complete/
Authorization: Bearer <access>
```

**Тело (опционально):**
```json
{
  "completion_text": "Я провёл медитацию утром, это заняло 10 минут.",
  "feelings_text": "Почувствовал спокойствие и ясность."
}
```

Если переданы оба текстовых поля — запускается AI-анализ выполнения (с начислением токенов). Без текстов — просто меняется статус.

**Ответ `200`:**
```json
{
  "status": "completed",
  "task": { ...полное задание... }
}
```

---

### Пропустить задание

```
POST /api/v1/tasks/<id>/skip/
Authorization: Bearer <access>
```

Допустимо только из статусов `pending` / `in_progress` / `active`.

**Ответ `200`:**
```json
{ "status": "skipped", "task": { ... } }
```

---

### Восстановить пропущенное задание

```
POST /api/v1/tasks/<id>/restore/
Authorization: Bearer <access>
```

Только для задания в статусе `skipped`. Переводит обратно в `active`.

**Ответ `200`:**
```json
{ "status": "restored", "task": { ... } }
```

---

### История задач

```
GET /api/v1/tasks/history/
Authorization: Bearer <access>
```

Возвращает только задания со статусом `completed`, `skipped`, `expired`.

---

## Эндпоинты — Прогресс

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

| Поле | Описание |
|------|----------|
| `current_streak` | Текущая непрерывная серия дней |
| `max_streak` | Рекорд за всё время |
| `active_days_last_30` | Дней с записями за последние 30 дней |

---

### Восстановление серии

```
POST /api/v1/progress/restore_streak/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{ "target_date": "2026-04-18" }
```

> Требуется наличие токенов у пользователя.

**Ответ `200`:**
```json
{
  "success": true,
  "message": "Серия восстановлена за 18 апреля.",
  "updated_date": "2026-04-18"
}
```

**Ошибки:**
- `400 target_date_required` — не передана дата
- `400 invalid_date_format` — неверный формат (нужен YYYY-MM-DD)
- `200 success: false` — не хватает токенов или дата недоступна для восстановления

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

| Режим | Формат | Пример |
|-------|--------|--------|
| `daily` | `YYYY-MM-DD` | `"2026-04-20"` |
| `weekly` | `YYYY-WNN` | `"2026-W16"` |
| `monthly` | `YYYY-MM` | `"2026-04"` |

---

### Активность пользователя

```
GET /api/v1/progress/activity/
Authorization: Bearer <access>
```

```json
{
  "summary": {
    "entry_created": 87,
    "task_completed": 23,
    "weekly_analysis": 6
  },
  "recent": [
    {
      "id": 200,
      "activity_type": "entry_created",
      "timestamp": "2026-04-20T10:30:00Z",
      "metadata": {}
    }
  ]
}
```

`recent` — последние 20 событий. `summary` — суммарно по типам.

**Типы активности (`activity_type`):**

| Значение | Описание |
|----------|----------|
| `entry_created` | Создана запись |
| `task_completed` | Выполнено задание |
| `task_skipped` | Пропущено задание |
| `profile_updated` | Обновлён профиль |
| `settings_changed` | Изменены настройки |
| `archive_viewed` | Просмотрен архив |
| `analysis_viewed` | Просмотрен анализ дня |
| `entry_comment` | Добавлен комментарий к записи |

---

### Недельные анализы (через progress)

```
GET /api/v1/progress/weekly/
Authorization: Bearer <access>
```

Алиас `GET /api/v1/weekly/` — возвращает тот же формат WeeklyAnalysis.

---

---

## Эндпоинты — Напоминания

Управление настройками push-уведомлений (доставляются через Telegram-бот).

### Статус напоминаний

```
GET /api/v1/reminders/
Authorization: Bearer <access>
```

**Ответ `200`:**
```json
{
  "notifications_enabled": true,
  "auto_analysis_enabled": true,
  "timezone": "Europe/Moscow"
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `notifications_enabled` | bool | Включены ли push-уведомления в Telegram |
| `auto_analysis_enabled` | bool | Включён ли автоматический AI-анализ |
| `timezone` | string | Часовой пояс пользователя (IANA) |

---

### Обновить настройки напоминаний

```
PATCH /api/v1/reminders/
Authorization: Bearer <access>
Content-Type: application/json
```

Оба поля опциональны — передавайте только то, что нужно изменить.

```json
{
  "notifications_enabled": false
}
```

**Ответ `200`:**
```json
{
  "updated": { "notifications_enabled": false },
  "notifications_enabled": false,
  "auto_analysis_enabled": true
}
```

**Ошибки:**
- `400 invalid_value` — переданное значение не булево

> Те же поля (`notifications_enabled`, `auto_analysis_enabled`) доступны через `PATCH /api/v1/profile/<id>/`. Эндпоинт `/reminders/` удобнее для страниц настроек.

---

## Эндпоинты — Обратная связь

```
POST /api/v1/feedback/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{ "message": "Хочу предложить функцию..." }
```

**Валидация:** длина `message` — от 5 до 4000 символов.

**Ответ `201`:**
```json
{ "id": 5, "message": "Обратная связь принята. Спасибо!" }
```

---

## Формат ошибок

Все ошибки возвращаются в единой структуре:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "Token is invalid or expired",
    "details": {}
  }
}
```

**Типичные коды:**

| HTTP | `code` | Ситуация |
|------|--------|----------|
| 400 | `token_required` | Отсутствует обязательный token |
| 400 | `invalid_token` | Токен истёк или неверен |
| 400 | `invalid_date_format` | Неверный формат даты (нужен YYYY-MM-DD) |
| 400 | `invalid_period` | Период не `daily`/`weekly`/`monthly` |
| 400 | `user_comment_required` | Пустой комментарий |
| 400 | `entry_invalid` | Запись не прошла AI-валидацию |
| 400 | `text_required` | Поле `text` пустое |
| 400 | `target_date_required` | Не передан `target_date` |
| 400 | `task_not_skippable` | Статус задачи не позволяет пропустить |
| 400 | `task_not_restorable` | Задача не в статусе `skipped` |
| 401 | `not_authenticated` | Отсутствует или устарел JWT |
| 403 | `permission_denied` | Нет доступа к ресурсу |
| 404 | `user_not_found` | Пользователь не найден |
| 404 | `analysis_not_found` | AI-анализ для записи ещё не готов |
| 429 | `throttled` | Превышен лимит запросов |

> DRF validation errors (ошибки полей формы) возвращаются без обёртки `"error"`, в формате `{"field_name": ["Сообщение об ошибке."]}`.

---

## Rate Limits

| Scope | Лимит | Применяется к |
|-------|-------|---------------|
| `auth` | **10/мин** | `/register/`, `/login/`, `/telegram/` |
| `refresh` | **20/мин** | `/refresh/` |
| `link_generation` | **6/час** | `/generate-link/`, `/link-telegram/` |
| `entry_mutation` | **30/мин** | POST/PUT/PATCH/DELETE `/entries/` |
| `task_mutation` | **30/мин** | POST/PUT/PATCH/DELETE `/tasks/` |
| `monitoring` | **30/мин** | `/monitoring/metrics/` |
| `monitoring_heavy` | **10/мин** | `/monitoring/prometheus/`, `/monitoring/stats/` |

При превышении — `HTTP 429` с заголовком `Retry-After`.

---

## Пагинация

```json
{
  "count": 87,
  "next": "https://.../api/v1/entries/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Размер страницы: **20** элементов. Параметр: `?page=N`.

---

## Полный список эндпоинтов

### Auth

| Метод | URL | Описание | Auth |
|-------|-----|----------|------|
| POST | `/api/v1/register/` | Регистрация | нет |
| POST | `/api/v1/login/` | Логин по email | нет |
| POST | `/api/v1/logout/` | Logout + blacklist refresh | да |
| POST | `/api/v1/refresh/` | Обновление токена | нет |
| GET | `/api/v1/telegram/?token=` | Auth через Telegram | нет |
| POST | `/api/v1/complete-registration/` | Добавить email к TG-аккаунту | да |
| POST | `/api/v1/generate-link/` | Ссылка привязки TG | да |
| POST | `/api/v1/link-telegram/` | Алиас generate-link | да |

### Пользователь

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/users/` | Список (только текущий) |
| GET | `/api/v1/users/<id>/` | Детали |
| GET | `/api/v1/users/me/` | Текущий пользователь |

### Профиль

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/profile/` | Compact список (текущий) |
| GET | `/api/v1/profile/<id>/` | Полный профиль |
| PUT/PATCH | `/api/v1/profile/<id>/` | Обновление профиля |
| GET | `/api/v1/profile/full/` | Полный профиль (action) |
| GET | `/api/v1/profile/compact/` | Компактный профиль |
| GET | `/api/v1/profile/statistics/` | Статистика |
| GET | `/api/v1/profile/history/` | История AI-снимков |
| GET | `/api/v1/profile/tokens/` | Баланс токенов |
| GET | `/api/v1/profile/transactions/` | История транзакций |
| GET | `/api/v1/profile/referral/` | Реферальная ссылка |

### Записи

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/entries/` | Список с фильтрами |
| POST | `/api/v1/entries/` | Создать запись |
| GET | `/api/v1/entries/<id>/` | Получить запись |
| PUT/PATCH | `/api/v1/entries/<id>/` | Обновить запись |
| DELETE | `/api/v1/entries/<id>/` | Удалить запись |
| GET | `/api/v1/entries/date/<YYYY-MM-DD>/` | Записи за дату |
| GET | `/api/v1/entries/<id>/analysis/` | AI-анализ записи |
| POST | `/api/v1/entries/<id>/comment/` | Добавить комментарий |
| POST | `/api/v1/entries/create_with_analysis/` | Создать + получить анализ синхронно |
| GET | `/api/v1/entries/next-prompt/` | Подсказка для следующей записи |
| POST | `/api/v1/entries/next-prompt/mark-used/` | Отметить подсказку использованной |

### Дни

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/days/` | Список дней |
| GET | `/api/v1/days/<id>/` | Детали дня |

### Еженедельные анализы

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/weekly/` | Список |
| GET | `/api/v1/weekly/<id>/` | Детали |

### Задания

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/tasks/` | Список с фильтрами |
| POST | `/api/v1/tasks/` | Создать задание |
| GET | `/api/v1/tasks/<id>/` | Получить задание |
| PUT/PATCH | `/api/v1/tasks/<id>/` | Обновить задание |
| DELETE | `/api/v1/tasks/<id>/` | Удалить задание |
| POST | `/api/v1/tasks/<id>/complete/` | Выполнить |
| POST | `/api/v1/tasks/<id>/skip/` | Пропустить |
| POST | `/api/v1/tasks/<id>/restore/` | Восстановить |
| GET | `/api/v1/tasks/history/` | История |

### Прогресс

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/progress/` | Сводка |
| GET | `/api/v1/progress/streak/` | Серия |
| POST | `/api/v1/progress/restore_streak/` | Восстановить серию |
| GET | `/api/v1/progress/mood/<period>/` | График настроения |
| GET | `/api/v1/progress/activity/` | Лента активности |
| GET | `/api/v1/progress/weekly/` | Недельные анализы |

### Прочее

| Метод | URL | Описание |
|-------|-----|----------|
| GET/PATCH | `/api/v1/reminders/` | Статус и настройки напоминаний |
| POST | `/api/v1/feedback/` | Обратная связь |
| GET | `/api/v1/schema/` | OpenAPI JSON |
| GET | `/api/v1/docs/` | ReDoc UI |


---
