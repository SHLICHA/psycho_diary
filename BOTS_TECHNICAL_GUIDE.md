# Техническое руководство по ботам WB Analyzer

Данный документ описывает техническую архитектуру, особенности работы и детали реализации обоих мессенджерных каналов: **Telegram** и **VK MAX**.

---

## Содержание

1. [Общая архитектура](#1-общая-архитектура)
2. [Telegram-бот](#2-telegram-бот)
3. [VK MAX-бот](#3-vk-max-бот)
4. [Общая бизнес-логика (Shared Layer)](#4-общая-бизнес-логика-shared-layer)
5. [Пользователи и идентификация](#5-пользователи-и-идентификация)
6. [Транспорт и API](#6-транспорт-и-api)
7. [Работа с состоянием (FSM)](#7-работа-с-состоянием-fsm)
8. [Обработка платежей](#8-обработка-платежей)
9. [Запуск и окружения](#9-запуск-и-окружения)
10. [Переносим другой бота в MAX: Пошаговая инструкция](#10-переносим-другой-бота-в-max-пошаговая-инструкция)
11. [Синхронизация данных между каналами](#11-синхронизация-данных-между-каналами)
12. [Известные ограничения и особенности](#12-известные-ограничения-и-особенности)

---

## 1. Общая архитектура

Проект реализует **один продукт с двумя мессенджерными интерфейсами**. Оба канала используют одну БД, одни use cases, один анализ, один Premium-контур.

### Актуальная экономика доступа (token-first)

- Базовый free-tier: `1` анализ в день при нулевом балансе токенов.
- Если у пользователя есть токены: анализ работает в транзакционной схеме `reserve(1)` -> анализ -> успешная отправка -> `commit`.
- При ошибке на любом шаге после резерва выполняется `rollback`.
- Stale-резервы откатываются периодической Celery-задачей.
- Приветственные токены выдаются всем после завершения onboarding.
- Реферальный бонус пригласившему начисляется один раз, после первого успешного анализа приглашенного.

```
┌─────────────────┐   ┌─────────────────┐
│  Telegram Bot   │   │   VK MAX Bot    │
│  (aiogram 3.x)  │   │  (aiohttp/poll) │
└────────┬────────┘   └────────┬────────┘
         │                     │
         ▼                     ▼
┌──────────────────────────────────────┐
│         bot/handlers/                │
│  Telegram handlers  │  MAX handlers  │
│  (commands.py etc)  │  (max/*.py)    │
└──────────────────────────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────────────────────────┐
│         bot/use_cases/               │
│  PremiumPurchaseUseCase              │
│  SupportTicketUseCase                │
│  FeedbackUseCase                     │
└──────────────────────────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────────────────────────┐
│  Django apps: users / payments /     │
│  products / analysis / common        │
└──────────────────────────────────────┘
```

**Ключевой принцип:** handlers зависят только от `send_func(text, buttons)` — async callable. Это позволяет один и тот же код бизнес-логики вызывать из Telegram и из MAX, не изменяя его.

---

## 2. Telegram-бот

### 2.1 Технологии

| Компонент          | Решение                          |
|--------------------|----------------------------------|
| Фреймворк          | [aiogram 3.x](https://docs.aiogram.dev/) |
| Транспорт          | Long Polling (`dp.start_polling`) |
| FSM                | aiogram `FSMContext` (MemoryStorage / RedisStorage) |
| Middleware         | Admin check, rate limiting       |
| Entry point        | `run_bot.py` → `manage.py runbot` |

### 2.2 Структура handlers

```
bot/handlers/
├── commands.py     # /start, /history, /premium, /support, /settings
├── messages.py     # Обработка входящих URL/ID товаров
├── callbacks.py    # InlineKeyboard callback queries
├── support.py      # Тикеты техподдержки
└── admin.py        # /stats, /status, /health, /open_tickets, /broadcast
```

### 2.3 Жизненный цикл входящего сообщения

```
Telegram API → aiogram Dispatcher
    ↓
Middleware (admin check, rate limit)
    ↓
Router (тип сообщения: команда / текст / callback)
    ↓
Handler (commands.py / messages.py / callbacks.py)
    ↓
Use Case (PremiumPurchaseUseCase / FeedbackUseCase / etc.)
    ↓
Django ORM / external API (WB, DeepSeek, YooKassa)
    ↓
bot.send_message(chat_id, text, reply_markup=...)
```

### 2.4 Команды

| Команда        | Handler                   | Описание                              |
|----------------|---------------------------|---------------------------------------|
| `/start`       | `cmd_start`               | Приветствие + запуск onboarding (email/skip) |
| `/settings`    | `cmd_settings`            | Управление email аккаунта             |
| `/history`     | `cmd_history`             | Карточка истории с пагинацией          |
| `/premium`     | `cmd_premium`             | Пакеты токенов и оплата               |
| `/referral`    | `cmd_referral`            | Персональная реферальная ссылка/код   |
| `/support`     | `cmd_support`             | Создание тикета (доступно до onboarding) |
| `/admin`       | `cmd_admin` (protected)   | Панель администратора                 |
| `/stats`       | `cmd_stats` (protected)   | Статистика по платформам              |
| `/status`      | `cmd_status` (protected)  | Состояние сервисов                    |
| `/open_tickets`| (protected)               | Неотвеченные обращения пользователей  |
| `/broadcast`   | `cmd_broadcast` (protected) | Массовая рассылка (режим ожидания текста) |

### 2.5 Анализ товара (основной флоу)

```
Пользователь → URL / ID товара WB
    ↓
Парсинг nm_id из текста
    ↓
Проверка quota (free/premium)
    ↓
WB API: fetch_product_info, fetch_reviews
    ↓
AI (DeepSeek): анализ отзывов через ReviewWorkflow
    ↓
Сохранение в analysis.WBProductAnalysis
    ↓
Отправка результата + кнопки feedback (👍/👎)
```

### 2.6 Особенности Telegram реализации

- **Rate limiting**: встроен middleware, защищающий от спама командами.
- **Proxy**: поддерживается SOCKS5 прокси через `TELEGRAM_PROXY_URL` в `.env` — для работы через промежуточный сервер.
- **FSM States**: `RegistrationStates.waiting_for_email`, `confirming_email_link` — для email-регистрации.
- **Admin middleware**: команды `/stats`, `/admin`, `/open_tickets`, `/broadcast` доступны только пользователям с `is_admin=True` в БД.
- **Quota check**: перед анализом проверяется `token_balance`; при нулевом балансе действует лимит `TOKENLESS_DAILY_ANALYSIS_LIMIT`.

---

## 3. VK MAX-бот

### 3.1 Технологии

| Компонент          | Решение                              |
|--------------------|--------------------------------------|
| API                | [platform-api2.max.ru](https://dev.max.ru/docs-api) |
| HTTP-клиент        | `aiohttp.ClientSession`              |
| Транспорт          | Webhook (prod) / Long Polling (dev)  |
| FSM                | Redis cache (`max_reg_state:{max_id}`, TTL 3600s) |
| Rate Limiting      | Token Bucket (10 req/sec по умолчанию) |
| Entry point        | `run_bot_max.py`                     |

### 3.2 Режимы транспорта

MAX API **не поддерживает одновременное использование Webhook и Polling** — выбирается один режим.

| Режим    | Env `MAX_TRANSPORT_MODE` | Когда использовать       |
|----------|--------------------------|--------------------------|
| `webhook`  | `webhook` (default)    | Production-сервер с HTTPS |
| `polling`  | `polling`              | Локальная разработка без публичного IP |

**Webhook (production):**
```
VK MAX API → POST /api/max/webhook/ → Django View
    ↓
MaxWebhookHandler.process_webhook(data)
    ↓
MaxClient.parse_webhook_event(data) → MaxWebhookEvent
    ↓
handle_max_webhook_event(event)
```

**Long Polling (dev):**
```
MaxClient.start_polling() loop
    ↓
GET https://platform-api2.max.ru/updates?timeout=30&marker=N
    ↓
parse_webhook_event(update) → MaxWebhookEvent
    ↓
handle_max_webhook_event(event)
```

### 3.3 MaxClient: ключевые методы

```python
class MaxClient:
    # Отправка сообщения
    # chat_id или user_id — query-параметр URL, text — в теле JSON
    async def send_message(message: MaxMessage) -> dict

    # Регистрация webhook с MAX
    # POST /subscriptions {"url": ..., "update_types": [...]}
    async def register_webhook(callback_path: str) -> bool

    # Long Polling: GET /updates?timeout=30&marker=N&types=...
    async def fetch_updates(marker, timeout, types) -> (updates, next_marker)

    # Запуск цикла Long Polling с graceful stop
    async def start_polling(event_handler, stop_event)

    # Парсинг входящего update в нормализованный MaxWebhookEvent
    def parse_webhook_event(webhook_data: dict) -> MaxWebhookEvent | None

    # Закрытие aiohttp-сессии (обязательно вызывать в finally)
    async def close()
```

### 3.4 Формат API-вызовов (особенности MAX API)

**Отправка сообщения (POST /messages):**
```
# chat_id или user_id передаются в URL query-параметрах, НЕ в теле
POST https://platform-api2.max.ru/messages?chat_id=12345678
Authorization: {token}
Content-Type: application/json

{"text": "Текст сообщения", "attachments": [...]}

# Для direct-диалога допустим и target по user_id
POST https://platform-api2.max.ru/messages?user_id=321090518
```

**Авторизация:**
```
# Токен передаётся только через заголовок (query-параметры не поддерживаются)
Authorization: {token}
```

**Формат ответа:**
```
# MAX возвращает объект напрямую, без обёртки "response"
{"message_id": "...", "text": "...", ...}
# НЕ {"response": {...}}
```

### 3.5 Формат входящих событий (Update)

В Long Polling формат события отличается от webhook-формата:

```json
// message_created (polling)
{
    "update_type": "message_created",
    "timestamp": 1234567890,
    "message": {
        "sender": {"user_id": 14366448, "name": "..."},
        "recipient": {"chat_id": 321090518},
        "body": {"text": "привет"},
        "timestamp": 1234567890
    }
}
```

Парсер (`parse_webhook_event`) нормализует оба формата в `MaxWebhookEvent`:
- `event_type`: `"message"` / `"button_click"` / `"confirmation"`
- `user_id`: из `message.sender.user_id` / `message.from_id` / `source.user_id`
- `chat_id`: из `message.recipient.chat_id` / `message.chat_id`
- `payload.text`: из `message.body.text` / `message.text`

### 3.6 Обработка кнопок

```python
# Формат кнопки при отправке
{"text": "Кнопка", "payload": "action_name"}

# Payload может быть строкой или словарём:
# Строка:  "skip_email_registration"
# Словарь: {"action": "link_by_email:user@email.com"}

# Парсер нормализует:
if isinstance(callback_payload, str):
    callback_payload = {"action": callback_payload}
```

Поддерживаемые payload-действия:

| Payload                        | Действие                                |
|--------------------------------|-----------------------------------------|
| `skip_email_registration`      | Пропустить привязку email               |
| `cancel_settings_email`        | Отменить изменение email из /settings   |
| `reenter_email`                | Ввести другой email                     |
| `link_by_email:{email}`        | Связать аккаунты по email               |
| `feedback:up:{nm_id}`          | Положительный фидбек по анализу         |
| `feedback:down:{nm_id}`        | Отрицательный фидбек по анализу         |
| `premium:{token_amount}`       | Купить пакет токенов                    |
| `premium_receipt:{yes|no}:{token_amount}` | Выбор чека перед оплатой      |
| `history_page:{N}`             | Открыть N-ю страницу истории            |
| `broadcast_cancel`             | Отменить режим массовой рассылки        |

### 3.7 Управление сессией aiohttp

Одна `aiohttp.ClientSession` создаётся на всё событие и закрывается в `finally`:

```python
# В handle_max_webhook_event:
max_client = MaxClient(api_token=...)
try:
    # обработка события и send_func используют тот же клиент
    ...
except Exception:
    ...
finally:
    close_result = max_client.close()
    if asyncio.iscoroutine(close_result):
        await close_result  # корректное закрытие без "Unclosed session"
```

### 3.8 Rate Limiting

Реализован Token Bucket алгоритм:
- Скорость пополнения: `MAX_RATE_LIMIT_RPS` (default: 10 req/sec)
- Максимальный burst: `MAX_RATE_LIMIT_BURST` (default: 50)
- Каждый `_api_call` вызывает `await rate_limiter.acquire()` перед запросом

### 3.9 Команды в MAX

| Команда         | Handler               | Описание                             |
|-----------------|-----------------------|--------------------------------------|
| `/start`        | `handle_start`        | Приветствие + запуск onboarding (email/skip) |
| `/settings`     | `handle_settings`     | Показ email + форма изменения        |
| `/history`      | `handle_history`      | Карточка истории с пагинацией        |
| `/premium`      | `_show_premium_options` | Пакеты токенов и оплата            |
| `/support`      | `handle_support_request` | Тикет в поддержку (доступно до onboarding) |
| `/admin`        | `_show_admin_panel`   | Панель администратора                |
| `/status`       | `_show_admin_status`  | Состояние сервисов и системные метрики |
| `/health`       | `_show_admin_health`  | Детальная проверка здоровья компонентов |
| `/stats`        | `_show_admin_stats`   | Админская статистика по боту и платформам |
| `/open_tickets` | `_show_open_tickets`  | Список неотвеченных обращений        |
| `/reply`        | `_route_text_message` | Ответ пользователю по тикету         |
| `/broadcast`    | `_handle_broadcast_command` | Включение режима массовой рассылки |
| ID / URL WB     | `handle_product_analysis` | Запуск анализа товара            |

### 3.10 История в MAX (parity с Telegram)

`/history` в MAX использует тот же сервис истории, что и Telegram:

- формат карточки через `build_history_text(...)`;
- одна карточка на сообщение;
- навигация кнопками `history_page:{N}` (`⬅️ Назад` / `Вперёд ➡️`);
- проверка onboarding перед показом истории.

За счёт этого отображение истории в MAX и Telegram синхронизировано по данным и структуре ответа.

---

## 4. Общая бизнес-логика (Shared Layer)

### 4.1 Use Cases

```
bot/use_cases/
├── premium_purchase_use_case.py  # start_premium_payment(), check_can_purchase_premium()
├── support_ticket_use_case.py   # create_support_ticket() → SupportTicketResult
├── feedback_use_case.py          # save_analysis_feedback() → FeedbackResult
└── product_analysis_use_case.py  # ProductAnalysisUseCase
```

Оба бота вызывают одни и те же use cases. Разница только в том, что передаётся в `send_func`.

### 4.2 Отправка ответа через send_func

```python
# Telegram:
async def send_func(text, buttons=None):
    await message.answer(text, reply_markup=build_keyboard(buttons))

# MAX:
async def send_func(text, buttons=None):
    await max_client.send_message(MaxMessage(
        chat_id=target_chat_id,
        text=text,
        keyboard=buttons,
    ))
```

### 4.3 Platform Stats

Команда `/stats` для администратора показывает:

```
👥 Статистика платформ
📊 Всего пользователей: N
  • 📱 Telegram: N
  • 💬 VK MAX: N
  • 🔗 Связаны (оба канала): N
  • 💎 Premium: N
  • 🟢 Активны сегодня: N
📈 Анализов в базе: N
```

Сервис: `bot/services/platform_stats.py` — запросы к `CustomUser`, `WBProductAnalysis`.

Celery Beat каждый час создаёт snapshot в Redis (`analysis.tasks.platform_stats_snapshot_task`).

---

## 5. Пользователи и идентификация

### 5.1 Модель CustomUser

```python
# users/models.py
class CustomUser(AbstractUser):
    telegram_id   = BigIntegerField(null=True, unique=True)  # Telegram user ID
    max_id        = BigIntegerField(null=True, unique=True)  # VK MAX user_id
    email         = EmailField(null=True, unique=True)       # Cross-platform ключ
    onboarding_completed = BooleanField(default=False)        # Завершён ли onboarding
    is_admin      = BooleanField(default=False)
    is_premium    = BooleanField(default=False)
    premium_until = DateTimeField(null=True)
    requests_today     = IntegerField(default=0)
    last_request_date  = DateField(null=True)
```

> **Важно**: `max_id` хранит именно `user_id` из MAX payload, не `chat_id`.

### 5.2 Создание / поиск пользователя

```python
# Get-only (без создания)
user = get_user_by_telegram_id_or_none(telegram_id)
user = get_user_by_max_id_or_none(max_id)

# Создание выполняется только в точках завершения onboarding:
# - подтверждённый email
# - skip email
# - /support до onboarding
```

### 5.3 Deferred user creation (onboarding-first)

Пользователь больше не создаётся автоматически на `/start` и на feature-callback'ах.

Создание `CustomUser` происходит только после одного из событий:
- пользователь ввёл и успешно сохранил email;
- пользователь нажал skip email;
- пользователь обратился в `/support` до onboarding (создаётся минимальный профиль).

Гейт доступа к функциям (`/history`, `/premium`, аналоги, feedback и др.) использует:
- `ensure_onboarding_completed(...)` и/или
- проверки `user and user.onboarding_completed`.

### 5.4 Привязка расширения до onboarding

Если пользователь запускает `/link CODE` до завершения onboarding:
- код не подтверждается сразу;
- в cache сохраняется `pending_extension_link:{telegram_id}` (TTL 3600s);
- после завершения onboarding код подтверждается автоматически.

### 5.3 Связывание аккаунтов по email

```
Пользователь вводит email
    ↓
has_email_conflict(email) ?
    ↓ Нет          ↓ Да
Сохранить email    Предложить связать аккаунты
                       ↓ Подтвердил
                   link_max_to_telegram_account(max_id, existing_user.id)
                   max_id и telegram_id → один CustomUser
                       ↓ Отказался
                   Создать новый аккаунт без email
```

---

## 6. Транспорт и API

### 6.1 Webhook endpoint-ы

| URL                           | Метод | Назначение                                    |
|-------------------------------|-------|-----------------------------------------------|
| `/api/max/webhook/`           | POST  | Входящие события от VK MAX                    |
| `/api/max/webhook/`           | GET   | Возвращает 405 (тест доступности)             |
| `/api/webhook/payment/`       | POST  | Webhook от YooKassa (HMAC-SHA256 валидация)   |

### 6.2 Регистрация MAX webhook

```bash
# Команда регистрирует URL webhook у MAX API
./start.sh register-webhook

# Под капотом:
POST https://platform-api2.max.ru/subscriptions
Authorization: {token}
{"url": "https://your-domain.ru/api/max/webhook/", "update_types": [...]}
```

Поддерживаемые `update_types`: `message_created`, `bot_started`, `message_callback`.

### 6.3 Платёжный webhook (YooKassa)

```python
# api/views.py: payment_webhook_handler
# 1. Извлечь raw body
# 2. Вычислить HMAC-SHA256(WEBHOOK_SECRET, raw_body)
# 3. Сравнить с заголовком X-Webhook-Signature
# 4. При совпадении — обработать событие
# 5. Идемпотентность: проверить yookassa_payment_id в БД
```

### 6.4 Extension Auth API: onboarding_required

`POST /api/v1/auth/verify-code/` теперь возвращает `409` с кодом ошибки `onboarding_required`, если:
- пользователь не найден в БД (ещё не создан из-за deferred flow), или
- пользователь найден, но `onboarding_completed=False`.

Это ожидаемое поведение onboarding-first контракта для extension auth.

---

## 7. Работа с состоянием (FSM)

### 7.1 Telegram FSM

Используется встроенный `aiogram.FSMContext`:

```python
class RegistrationStates(StatesGroup):
    waiting_for_email    = State()  # Ожидание ввода email
    confirming_email_link = State() # Подтверждение связывания
```

Хранение: `MemoryStorage` (dev) или `RedisStorage` (prod).

### 7.2 MAX FSM

Хранится в Django cache (Redis):

```python
# Ключ: max_reg_state:{max_id}
# TTL: 3600 секунд (1 час)
# Структура: {"state": "waiting_for_email", "email": "...", "conflict_user_id": N}

await aget_registration_state(max_id)      # Получить
await aset_registration_state(max_id, ...) # Установить
await aclear_registration_state(max_id)    # Сбросить
```

Состояния MAX FSM:

| Константа                  | Значение                           |
|----------------------------|------------------------------------|
| `STATE_WAITING_FOR_EMAIL`  | Ожидание ввода email               |
| `STATE_CONFIRMING_EMAIL_LINK` | Ожидание подтверждения связки   |
| `STATE_PREMIUM_RECEIPT_CHOICE` | Выбор нужен ли чек             |
| `STATE_PREMIUM_EMAIL_INPUT` | Ввод email для чека               |
| `STATE_WAITING_FOR_SUPPORT_MESSAGE` | Ожидание сообщения в поддержку |
| `STATE_WAITING_FOR_BROADCAST_MESSAGE` | Ожидание текста массовой рассылки |

Режим `/broadcast` реализован как двухшаговый FSM-сценарий:
- администратор запускает `/broadcast`;
- бот сохраняет состояние ожидания и показывает кнопку `Отмена`;
- следующий текст администратора отправляется как массовая рассылка;
- нажатие кнопки `Отмена` сбрасывает состояние.

### 7.3 Pending-link cache (Telegram extension)

Для deferred linking используется отдельный cache-ключ:

```python
# Ключ: pending_extension_link:{telegram_id}
# TTL: 3600 секунд
# Данные: {"code": "ABC123"}
```

Ключ создаётся при `/link CODE` до onboarding и удаляется после успешного/неуспешного финального подтверждения.

---

## 8. Обработка платежей

### 8.1 Создание платежа

```
Пользователь → /premium → выбор пакета токенов
    ↓
PremiumPurchaseUseCase.start_premium_payment(user, days, send_func)
    ↓
YooKassa API: создать Payment object
    ↓
Отправить пользователю ссылку на оплату
```

Примечание: в сигнатуре use case аргумент пока называется `days` (legacy), но фактически передаётся `token_amount`.

### 8.2 Подтверждение оплаты

**Через webhook (preferred):**
```
YooKassa → POST /api/webhook/payment/
    ↓
Валидация подписи (HMAC-SHA256)
    ↓
payment.status == "succeeded"
    ↓
Активировать premium (user.is_premium=True, user.premium_until=...)
    ↓
Уведомить пользователя в боте
```

**Fallback через Celery (reconciliation):**
```
Celery Beat → check_pending_payments_task (периодически)
    ↓
Найти Payment.status == "pending" && created_at > threshold
    ↓
Запросить статус у YooKassa API
    ↓
Обновить статус и активировать при необходимости
```

---

## 9. Запуск и окружения

### 9.1 Переменные окружения

**Общие:**

| Переменная           | Описание                      | Обязательна |
|----------------------|-------------------------------|-------------|
| `SECRET_KEY`         | Django secret key             | ✅ |
| `DB_PASSWORD`        | Пароль к PostgreSQL           | ✅ |
| `DEBUG`              | True/False                    | — |
| `ALLOWED_HOSTS`      | Список хостов через запятую   | — |
| `REDIS_URL`          | Redis подключение             | — |

**Telegram:**

| Переменная           | Описание                      | Обязательна |
|----------------------|-------------------------------|-------------|
| `BOT_TOKEN`          | Токен из @BotFather           | ✅ |
| `BOT_USERNAME`       | Username бота (без @)         | — |
| `TELEGRAM_PROXY_URL` | SOCKS5-прокси (если нужен)    | — |

**VK MAX:**

| Переменная              | Описание                                      | Обязательна |
|-------------------------|-----------------------------------------------|-------------|
| `BOT_PUBLIC_DOMAIN`     | Единый публичный домен проекта (приоритет)    | webhook ✅ |
| `MAX_API_TOKEN`         | Bot-токен из настроек бота MAX                | ✅ |
| `MAX_API_BASE_URL`      | Базовый URL MAX Bot API (`platform-api2`)     | — |
| `MAX_API_CA_CERT_PATHS` | Пути к CA-сертификатам для TLS (через запятую)| — |
| `MAX_TRANSPORT_MODE`    | `webhook` (prod) / `polling` (dev)            | — |
| `MAX_WEBHOOK_DOMAIN`    | Legacy fallback домен для MAX webhook         | — |
| `MAX_WEBHOOK_SECRET`    | Секрет для верификации входящих запросов      | — |
| `MAX_RATE_LIMIT_RPS`    | Запросов в секунду (default: 10)              | — |
| `MAX_RATE_LIMIT_BURST`  | Burst size (default: 50)                      | — |
| `MAX_POLL_TIMEOUT_SEC`  | Таймаут Long Polling запроса (default: 30)    | — |
| `MAX_POLL_BACKOFF_MAX_SEC` | Макс. backoff при ошибках (default: 60)   | — |

Для `platform-api2.max.ru` в цепочке TLS требуется intermediate сертификат `Russian Trusted Sub CA` (например `russian_trusted_sub_ca_rsa2024.crt`) вместе с корневым `russian_trusted_root_ca_pem.crt`.

**Платежи:**

| Переменная             | Описание                        | Обязательна |
|------------------------|---------------------------------|-------------|
| `YOOKASSA_SHOP_ID`     | ID магазина YooKassa            | ✅ |
| `YOOKASSA_SECRET_KEY`  | Секретный ключ YooKassa         | ✅ |
| `TOKEN_PACKAGES_JSON`  | JSON пакетов токенов (`токены=цена`) | — |
| `PREMIUM_PRICES`       | Legacy JSON цен premium-дней (обратная совместимость) | — |
| `WEBHOOK_SECRET`       | HMAC-секрет для webhook подписи | — |
| `WEBHOOK_PAYMENT_URL`  | Legacy fallback URL webhook     | — |

**AI:**

| Переменная            | Описание                        | Обязательна |
|-----------------------|---------------------------------|-------------|
| `DEEPSEEK_API_KEY`    | Ключ DeepSeek API               | ✅ |
| `DEEPSEEK_TIMEOUT`    | Таймаут AI-запроса (default: 120s) | — |

### 9.2 Команды запуска

```bash
./start.sh                  # Запуск всего стека (telegram + max + celery + web)
./start.sh telegram         # Только Telegram (+ web/celery)
./start.sh max              # Только MAX (режим по MAX_TRANSPORT_MODE)
./start.sh both             # То же, что без аргументов
./start.sh docker           # docker compose: оба бота + инфраструктура
./start.sh register-webhook # Зарегистрировать webhook у MAX API (один раз)
./start.sh check-webhook    # Диагностика webhook endpoint
./start.sh stop             # Остановка локальных процессов (runbot/runmaxbot/celery/runserver)
./start.sh help             # Справка
```

Локально MAX поднимается через `python manage.py runmaxbot`. В режиме `both`
у процесса `runbot` принудительно `MAX_TRANSPORT_ENABLED=false`, чтобы не дублировать polling.

### 9.3 Диагностика WB URL и HAR

Для воспроизведения реального поведения WB-страницы используется Playwright-скрипт `capture_wb_har.py`.

```bash
python capture_wb_har.py --nm-id 82386836 --out wb_82386836.har
```

Скрипт открывает карточку товара в Chromium, при необходимости прокликивает отзывы и сохраняет HAR с embedded content. В проекте это нужно для проверки фактических WB-запросов и схем URL без ручного перебора.

Текущий контур WB URL:
- отзывы: сначала резолвер `feedback-bt.wildberries.ru/feedback/api/v2/host?imt=...`, затем `feedback-view-XX.wb.ru/feedbacks/v2/{imt}`;
- legacy `feedbacks{num}.wb.ru/feedbacks/v2/{imt}` оставлен как fallback;
- корзина: URL по-прежнему строится из `nm_id -> vol/part`, а выбор `basket-{num}` оптимизирован эвристиками и кэшем, но отдельный стабильный resolver для basket в захваченных body не найден.

Для работы скрипта нужен установленный браузерный движок Playwright:

```bash
python -m playwright install chromium
```

### 9.3 Как работает режим `max` в зависимости от `MAX_TRANSPORT_MODE`

```bash
# Локально (.env: MAX_TRANSPORT_MODE=polling):
./start.sh max
# → python run_bot_max.py --mode polling
# → GET /updates loop (без Django web-сервера)

# Production (.env: MAX_TRANSPORT_MODE=webhook):
./start.sh max
# → python manage.py runserver 0.0.0.0:8000
# → принимает POST /api/max/webhook/
```

### 9.4 Единый домен для webhook

Приоритетная настройка — `BOT_PUBLIC_DOMAIN` (пример: `https://www.psychodiary.ru`).

- Пустой домен → MAX `polling`, payment webhook выключен.
- Заданный домен → MAX `webhook` + payment webhook (если `MAX_TRANSPORT_MODE` не задан явно).

Авто-URL:
- MAX: `{BOT_PUBLIC_DOMAIN}/api/max/webhook/`
- ЮKassa: `{BOT_PUBLIC_DOMAIN}/api/payments/webhook/`

Явные override: `MAX_TRANSPORT_MODE`, `MAX_WEBHOOK_URL`, `PAYMENT_WEBHOOK_URL`.

Флаг `PAYMENT_WEBHOOK_ENABLED` = true, когда итоговый payment URL непустой.

### 9.5 Docker

```bash
docker-compose up           # Запуск всего стека
docker-compose up web       # Только Django
docker-compose up max_bot   # Только MAX polling
```

---

## 10. Переносим другой бота в MAX: Пошаговая инструкция

### Предварительные условия

Вы уже имеете:
- ✅ Работающий Telegram-бот (например, в aiogram)
- ✅ Бизнес-логику (use cases, services, models)
- ✅ Django-приложение или готовность его организовать

**Сложность переноса:** средняя (1–2 дня для простого бота). Максимум изменений в transport-слое, бизнес-логика переиспользуется.

### Фаза 1: Архитектурное разделение Transport ↔ Business Logic

**Цель:** Выделить бизнес-логику в независимый слой, который не знает о Telegram или MAX.

**Что менять:**

1. **Выделите send_func callback:**
   ```python
   # ДО (не переносимо):
   async def handle_start(message: Message):
       await message.answer("Привет!")
   
   # ПОСЛЕ (переносимо):
   async def handle_start(user_id, send_func):
       await send_func("Привет!")
   ```

2. **Создайте adapter layer для MAX:**
   ```python
   # bot/handlers/max/send_adapter.py
   async def build_send_func(max_id, max_client):
       async def send_func(text, buttons=None, text_format=None):
           await max_client.send_message(
               MaxMessage(
                   user_id=str(max_id),
                   text=text,
                   keyboard=buttons,
                   text_format=text_format or 'markdown',
               )
           )
       return send_func
   
   # А в webhook handler:
   send_func = await build_send_func(event.user_id, max_client)
   await handle_start(event.user_id, send_func)
   ```

3. **Нормализируйте identifiers:**
   ```python
   # Используйте единую модель пользователя для обоих каналов
   class CustomUser(AbstractUser):
       telegram_id = BigIntegerField(null=True, unique=True)
       max_id = BigIntegerField(null=True, unique=True)
       email = EmailField(null=True, unique=True)  # Cross-platform ключ
   ```

### Фаза 2: Реализуйте MAX Client

**Эталон:** [bot/infrastructure/max_client.py](bot/infrastructure/max_client.py)

**Минимальный набор методов:**

```python
class MaxClient:
    async def send_message(message: MaxMessage) -> dict:  # query-params: chat_id или user_id
    async def register_webhook(callback_path: str) -> bool
    async def fetch_updates(marker, timeout, types) -> (updates, next_marker)  # для polling
    def parse_webhook_event(webhook_data: dict) -> MaxWebhookEvent | None
    async def close()  # гарантированное закрытие aiohttp session
```

**Типичные ошибки при реализации:**

1. ❌ Передача `chat_id` в теле JSON вместо query-параметра
   - ✅ **Правильно:** `POST /messages?chat_id=123` с `{"text": "..."}` в body
   
2. ❌ Попытка переиспользовать одну MaxClient session для всех событий
   - ✅ **Правильно:** создать новый MAX-клиент в webhook handler, закрыть в `finally`
   
3. ❌ Забыть о `user_id` как альтернативе `chat_id` для direct dialogs
   - ✅ **Правильно:** обе целевые поля поддерживаются; используйте `user_id` для fallback при `chat.not.found`
   
4. ❌ Передать `text_format='html'` вместо MAX-формата (поддерживает только `markdown`)
   - ✅ **Правильно:** используйте `text_format='markdown'` или `None` (default)
   
5. ❌ Не закрыть aiohttp session
   - ✅ **Правильно:** всегда вызывайте `close()` в `finally`; это избегает "Unclosed connector" ошибок

### Фаза 3: Webhook & Event Parsing

**Django endpoint для webhook:**

```python
# api/views.py
@csrf_exempt
async def max_webhook_handler(request):
    if request.method == 'GET':
        return JsonResponse({'ok': True})  # MAX ping
    
    body = json.loads(request.body)
    max_client = MaxClient(api_token=settings.MAX_API_TOKEN)
    try:
        event = max_client.parse_webhook_event(body)
        if event.event_type == 'message':
            await handle_message(event.user_id, event.payload['text'], max_client)
        elif event.event_type == 'button_click':
            await handle_callback(event.user_id, event.payload['payload'], max_client)
    finally:
        await max_client.close()  # КРИТИЧНО: без этого будут утечки сессий
    
    return JsonResponse({'ok': True})
```

**Регистрация webhook:**

```bash
# Один раз при первом запуске
./start.sh register-webhook

# Эквивалент:
POST https://platform-api2.max.ru/subscriptions
Authorization: your-community-token
{
    "url": "https://yourdomain.ru/api/max/webhook/",
    "update_types": ["message_created", "message_callback", "bot_started"]
}
```

### Фаза 4: FSM & State Management

**Telegram:** aiogram встроенный FSMContext
**MAX:** Redis cache (так как нет встроенного FSM)

```python
# bot/handlers/max/state.py
async def aget_registration_state(max_id):
    return cache.get(f'max_reg_state:{max_id}')

async def aset_registration_state(max_id, state_dict):
    cache.set(f'max_reg_state:{max_id}', state_dict, timeout=3600)

async def aclear_registration_state(max_id):
    cache.delete(f'max_reg_state:{max_id}')
```

**Важно:** регулярно сбрасывайте state в Celery job, чтобы не накапливались мёртвые данные.

### Фаза 5: Message Chunking для MAX (4000 char limit)

**MAX API ограничивает text до 4000 символов.** Для больших сообщений нужно разбивать:

```python
MAX_TEXT_LIMIT = 4000
MAX_SAFE_TEXT_LIMIT = 3900  # safe margin

async def send_message_chunked(send_func, text, buttons=None):
    chunks = [text[i:i+MAX_SAFE_TEXT_LIMIT] for i in range(0, len(text), MAX_SAFE_TEXT_LIMIT)]
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        await send_func(chunk, buttons=buttons if is_last else None)
```

### Фаза 6: Source-aware Features (для обоих каналов)

**Проблема:** Одно действие должно работать в обоих каналах, но идентификаторы разные (telegram_id vs max_id).

**Решение:** Используйте `source_platform` и `source_user_id` в моделях:

```python
class SupportTicket(Model):
    source_platform = CharField(choices=[('telegram', 'Telegram'), ('max', 'MAX')])
    source_user_id = BigIntegerField()  # telegram_id или max_id
    source_chat_id = BigIntegerField(null=True)  # chat_id в MAX
```

При открытии списка тикетов, выводите source-aware информацию:

```python
def build_ticket_view_item(ticket):
    return {
        'platform': ticket.source_platform,
        'user_id': ticket.source_user_id,
        'username': ticket.user.username,
        # ...
    }
```

### Фаза 7: Тестирование

**Unit-тесты:** Мокируйте `send_func` для бизнес-логики

```python
@pytest.mark.asyncio
async def test_handle_start_sends_greeting():
    send_func = AsyncMock()
    await handle_start(max_id=123, send_func=send_func)
    send_func.assert_awaited_once()
    assert 'Привет' in send_func.call_args.args[0]
```

**Integration-тесты:** Используйте фиксированные webhook payloads

```python
def test_webhook_parses_message():
    client = MaxClient(api_token='test')
    event = client.parse_webhook_event({
        'type': 'message_created',
        'object': {
            'message': {
                'from_id': 123,
                'text': 'привет',
                'chat_id': 456,
            }
        }
    })
    assert event.user_id == '123'
    assert event.chat_id == '456'
```

### Фаза 8: Troubleshooting

**Проблема:** Сообщение не доходит, 404 `chat.not.found`
- **Причина:** `chat_id` может быть невалидным. В MAX для direct dialogs используется `user_id`.
- **Решение:** Используйте `user_id` как fallback:
  ```python
  try:
      await max_client.send_message(MaxMessage(chat_id=target))
  except MaxClientException as e:
      if 'chat.not.found' in str(e):
          await max_client.send_message(MaxMessage(user_id=target))
  ```

**Проблема:** "Unclosed connector" ошибки в логах
- **Причина:** MaxClient session не закрыта после использования.
- **Решение:** Всегда вызывайте `close()` в `finally`:
  ```python
  max_client = MaxClient(...)
  try:
      ...
  finally:
      await max_client.close()
  ```

**Проблема:** Сообщение режется посередине
- **Причина:** Превышен лимит 4000 символов MAX API.
- **Решение:** Разбивайте текст на chunks:
  ```python
  await send_message_chunked(send_func, long_text, buttons=buttons)
  ```

**Проблема:** Кнопки не приходят
- **Причина:** Неправильный формат payload или очень длинное сообщение.
- **Решение:**
  - Проверьте формат: `[{"text": "Кнопка", "payload": "action_name"}]`
  - Убедитесь, что text + кнопки меньше 4000 символов
  - Кнопки передавайте только в последнем chunk

---

## 11. Синхронизация данных между каналами

### 11.1 Premium & Платежи

- Один платеж → активирует premium для обоих каналов
- Квота: считается по пользователю (email), не по каналу
- Использованные анализы видны в `/history` на обоих каналах

### 11.2 Email как Identity Bridge

```
Пользователь в Telegram          →  Email (вводит или пропускает)
Пользователь в MAX               →  Email (вводит или пропускает)
                                        ↓
               Если email совпадает → Merge в один CustomUser
                                        ↓
                 Оба канала имеют доступ к истории и премиуму
```

**Важно:** Email уникален в БД (`unique=True`). При попытке связать разные аккаунты через одинаковый email:
- Предложить merge (объединить)
- Или создать новый аккаунт без email

### 11.3 Deferred User Creation

Пользователь НЕ создаётся на `/start`. Создание происходит ТОЛЬКО когда:
- Пользователь ввёл и сохранил email
- Пользователь нажал "Пропустить email"
- Пользователь создал ticket в `/support` (даже до onboarding)

**Зачем?** Снижает нагрузку на БД, позволяет боту работать без привязки к конкретным пользователям на ранних стадиях.

### 11.4 Support Tickets: Source-aware

```
Тикет создан пользователем в Telegram
  ↓
Админ отвечает в MAX (используя /reply <ticket_id>)
  ↓
Ответ доходит в Telegram (путём fallback на telegram_id)
```

**Реализация:** функция `deliver_support_reply()` в [bot/services/support/support_delivery.py](bot/services/support/support_delivery.py) маршрутизирует ответ по `source_platform` и `source_user_id`, не завися от текущего админского канала.

---

## 12. Известные ограничения и особенности

### 10.1 MAX API

| Ограничение                        | Подробности                                                        |
|------------------------------------|--------------------------------------------------------------------|
| **Webhook и Polling взаимоисключают** | Если бот подписан на webhook — `GET /updates` не отдаёт события |
| **Rate limit**                     | MAX документирует до 30 req/sec, мы используем 10 req/sec с burst 50 |
| **Long Polling не для production** | MAX явно ограничивает скорость и срок хранения событий в polling   |
| **`chat_id` — URL query param**    | При `POST /messages` передаётся как `?chat_id=N`, не в JSON-теле  |
| **Нет обёртки `response`**         | MAX API возвращает объект напрямую, не `{"response": {...}}`       |
| **Формат body.text**               | Текст сообщения лежит в `message.body.text` (не `message.text`) при получении |
| **Авторизация только через header**| `Authorization: {token}` — query-параметры токена не поддерживаются |
| **Только HTTPS для webhook**       | С 25 мая 2026 HTTP и самоподписные сертификаты запрещены          |

### 10.2 Telegram

| Особенность                    | Подробности                                          |
|--------------------------------|------------------------------------------------------|
| **Proxy support**              | `TELEGRAM_PROXY_URL` — SOCKS5 прокси для Bot API    |
| **Long Polling**               | Единственный поддерживаемый режим в этом проекте     |
| **FSM через aiogram**          | `MemoryStorage` в dev, для prod рекомендован `RedisStorage` |
| **Admin middleware**           | Проверяет `user.is_admin` до выполнения команд       |

### 10.3 Общие

| Особенность                      | Подробности                                                   |
|----------------------------------|---------------------------------------------------------------|
| **Email как cross-platform ключ** | Единственный способ связать Telegram и MAX аккаунты          |
| **Email не обязателен**          | Пользователь может пропустить email и пользоваться ботом      |
| **Onboarding-first**             | Пользователь создаётся только после email/skip/support         |
| **Конфликт email — не блокировка** | При занятом email создаётся новый аккаунт без email          |
| **Idempotent payments**          | Webhook `payment.succeeded` безопасно получать несколько раз  |
| **aiohttp session leak**         | MaxClient создаётся один раз на событие, закрывается в `finally` |
| **MAX state TTL**                | Redis-состояние FSM живёт 3600 секунд, потом сбрасывается     |
| **Celery Beat**                  | Platform stats snapshot каждый час, reconciliation платежей    |

### 10.4 Тестирование

```bash
# Полный suite
pytest --no-cov -q

# Только MAX
pytest tests/unit/test_max_client_parser.py tests/unit/test_max_handlers.py -q --no-cov

# Только регистрация
pytest tests/unit/test_registration_service.py -q --no-cov

# Статистика
pytest tests/unit/test_platform_stats.py -q --no-cov
```

Тестовый контур фиксирован на `config.settings_test`:
- БД: SQLite (in-memory)
- Cache: LocMemCache
- Celery: eager (задачи выполняются синхронно)

---

*Документ актуален на 2026-06-25. Содержит полный техгайд, инструкцию по переносу других ботов в MAX, описание распространённых ошибок и их решения. При изменении API VK MAX или Telegram Bot API необходимо обновить соответствующие разделы. Используйте этот документ как инструкцию для разработки, не только как справку.*