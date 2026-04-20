# Глубокий анализ кодовой базы psycho_diary

## 1. Цель документа
Этот документ дает полное инженерное представление о системе:
- архитектура и точки входа;
- модули и зоны ответственности;
- ключевые data-flow сценарии с явными входами и выходами;
- модели данных и фоновые процессы;
- внешние интеграции и операционные зависимости;
- текущие риски/узкие места для планирования следующих изменений.

Документ ориентирован на практическое проектирование изменений в живом продукте.

---

## 2. Архитектура системы

### 2.1 Технологический стек
- Backend: Django 4.2.7
- Telegram bot: aiogram 3.1.1
- Async workers: Celery 5.5.3 + django-celery-beat
- DB: PostgreSQL 15
- Cache/Broker: Redis
- AI: DeepSeek Chat Completions API
- Auth API: DRF + JWT (simplejwt)
- Инфраструктура: Docker Compose (web, bot, worker, beat, nginx)

### 2.2 Основные runtime-компоненты
- `telegram_bot` сервис: получает события Telegram, обрабатывает FSM-сценарии.
- `web` сервис: REST API и admin.
- `celery_worker`: асинхронные задачи анализа/напоминаний/очистки.
- `celery_beat`: периодический запуск задач по расписанию.
- `db` и `redis`: состояние и очереди.

### 2.3 Точки входа
- Telegram:
  - polling в `bot/main.py`
  - запуск через `python manage.py runbot` (`core/management/commands/runbot.py`)
- REST API:
  - маршруты в `core/urls.py` и `api/urls.py`
- Periodic jobs:
  - расписание в `core/settings.py` -> `CELERY_BEAT_SCHEDULE`

---

## 3. Карта модулей и ответственности

### 3.1 `bot/`
- `handlers/`: пользовательские сценарии (start, diary, tasks, settings, profile, payments, progress, help, onboarding, feedback).
- `middlewares/`: user/language/rate-limit/premium/db.
- `services/`:
  - `diary_service.py`: центральная оркестрация создания и анализа записей;
  - `deepseek_api.py`: транспорт и парсинг AI-ответов;
  - экспорт, speechkit, object storage.
- `states/`: FSM-состояния.
- `keyboards/`, `utils/`: UI и вспомогательные механики.

### 3.2 `diary/`
- `models.py`: доменная модель дневника, анализов, задач, рейтингов.
- `services/`: бизнес-логика домена (daily/full/weekly/profile/task/payment/progress и т.д.).
- `tasks/`: celery-задачи (scheduler, reminders, weekly, cleanup, GC, expiration).

### 3.3 `users/`
- `models.py`: пользователь, история профиля, транзакции токенов, платежи, feedback.
- `services/auth_token_service.py`: токены для web<->telegram связывания через Redis.

### 3.4 `api/`
- DRF viewsets для пользователя/профиля/записей/дней/недель/задач.
- auth endpoints: register/login/refresh/telegram auth/complete-registration/generate-link.

### 3.5 `core/`
- `settings.py`: конфигурация приложений, celery schedule, cache, JWT, feature flags.
- `encrypted_fields.py`: шифрование чувствительных полей моделей.
- `profile_field_utils.py`: унификация profile payload для AI и weighted-format утилиты.

### 3.6 `prompts/`
- `get_prompt.py`: единый реестр шаблонов и рендер placeholders.
- `templates/*`: промпты для incremental/full/weekly/clarification/comment/task/chat/reminders.

---

## 4. Доменные сущности (модель данных)

## 4.1 Пользователь и профиль (`users.User`)
Ключевые поля:
- идентичность: `telegram_id`, `username`, `first_name`, `last_name`, `email`, `email_hash`;
- поведение: `language`, `timezone`, `notifications_enabled`, `auto_analysis_enabled`;
- монетизация: `is_premium`, `premium_expires_at`, `token_balance`;
- профиль: `personality_traits`, `triggers`, `strengths`, `life_facts`, `hobbies`, `core_values`, `areas_for_growth`, `habits`, `skills`, `aspirations`, `personality_description`;
- агрегаты профиля: `compressed_psych_profile`, `full_psych_profile`.

I/O:
- вход: telegram event, API registration/login, profile edit, weekly AI обновления;
- выход: персонализация промптов, меню/настройки, auth tokens, фильтры задач.

## 4.2 Записи и анализы (`diary`)
- `DiaryEntry`: атомарная запись (text/voice->text), language, word_count, обработка, уточнения, creator_timezone.
- `PsychoAnalysis`: анализ одной записи (mood, comment, recommendation, analysis_text, api_response).
- `CombinedDiaryEntry`: состояние дня (aggregated text, entry_count, ai_state_data, mood list/avg, day_context_summary, is_analyzed).
- `DailyAnalysis`: финальный анализ дня (themes, patterns, insights, recommendations, overall text).
- `WeeklyAnalysis`: итог недели + статистика + comparison + consolidated profile summary.
- `AnalysisRating`: пользовательская оценка анализа.

## 4.3 Терапевтические задания
- `TherapyTask`: назначенное задание (status/type/complexity/expires_at/related_entry).
- `TaskCompletion`: выполнение задания.
- `TaskCompletionAnalysis`: AI-анализ эффекта выполнения + tokens_awarded.

## 4.4 Финансы
- `TokenTransaction`: ledger операций токенов.
- `Payment`: платеж ЮKassa и его жизненный цикл (pending/succeeded/...)

---

## 5. Сквозные бизнес-сценарии (входы -> обработка -> выходы)

## 5.1 Онбординг и вход пользователя
Компоненты:
- `bot/handlers/start.py`, `bot/middlewares/user_middleware.py`, `diary/services/user_service.py`

Вход:
- `/start` команда (в т.ч. ref и link токены).

Обработка:
1. Middleware находит/создает пользователя, обновляет базовые поля.
2. При новом пользователе: приветственные токены + optional referral.
3. FSM-ветка онбординга: соглашения -> timezone -> первая запись.
4. После завершения: main menu data.

Выход:
- сообщение/клавиатура онбординга или главное меню;
- новый user в БД и стартовая финансовая транзакция;
- возможная привязка web-аккаунта через `link_` токен.

## 5.2 Создание дневниковой записи (основной путь)
Компоненты:
- `bot/handlers/diary.py::process_any_entry`
- `bot/services/diary_service.py::process_new_entry_logic`
- `bot/services/deepseek_api.py`
- `diary/services/daily_state_service.py`

Вход:
- текст или voice message пользователя, user context (timezone/lang/profile/subscription).

Обработка:
1. Валидация входа + rate-limit.
2. Voice: STT, далее как text.
3. Создание `DiaryEntry`.
4. Получение/обновление `CombinedDiaryEntry` (состояние дня).
5. Выбор prompt режима:
   - premium: `incremental_day_analysis`
   - free LITE v2: `incremental_day_analysis_lite_v2` при flags+данных
   - fallback LITE v1: `incremental_day_analysis_lite`
6. Вызов DeepSeek, parse JSON, fallback при context_length_exceeded.
7. Если AI mark invalid: удаление записи и возврат validation message.
8. Если valid:
   - upsert `PsychoAnalysis`
   - update `ai_state_data` (структурированный JSON)
   - optional создание `TherapyTask`
   - начисление streak бонуса
   - optional clarification flow (FSM + таймеры)

Выход:
- пользователю: mood/comment/recommendation/task info/clarification prompts;
- в БД: `DiaryEntry`, `PsychoAnalysis`, `CombinedDiaryEntry`, optional `TherapyTask`, token transaction (бонусы).

## 5.3 Уточнения после анализа
Компоненты:
- `bot/handlers/diary.py::process_clarification_answers`
- `diary/tasks/reminder_ask_questions.py`

Вход:
- ответы на уточняющие вопросы (text/voice).

Обработка:
1. Сохранение `clarification_answers`.
2. Prompt `clarification_analysis` (personal_fields + compressed_profile).
3. Update/finish `PsychoAnalysis`, update day state.
4. Сброс reminder/force_process таймеров.

Выход:
- обновленный анализ пользователю;
- запись переводится в processed состояние (или остается незавершенной при ошибке API).

## 5.4 Комментарий пользователя к анализу
Компоненты:
- `bot/services/diary_service.py::process_user_comment_logic`

Вход:
- user comment для существующей записи.

Обработка:
1. Сохранение `DiaryEntry.user_comment`.
2. Сброс `CombinedDiaryEntry.is_analyzed`.
3. Prompt `comment_analysis`.
4. Обновление `PsychoAnalysis`.

Выход:
- переформулированный анализ;
- день помечается требующим повторного full analysis.

## 5.5 Полный анализ дня
Компоненты:
- `diary/services/full_day_analysis_service.py`
- `diary/tasks/scheduler_tasks.py`

Вход:
- пользователь + target_date (ручной запуск или scheduled midnight flow).

Обработка:
1. Сбор контекста дня: тексты, entry analyses, mood scores, task completions.
2. Выбор prompt: full / lite v2 / lite v1.
3. DeepSeek анализ.
4. Upsert `DailyAnalysis`.
5. Update профиля (weighted merge), awareness_level.
6. Mark `CombinedDiaryEntry.is_analyzed = True`.
7. Generate `day_context_summary` + next prompt.

Выход:
- `DailyAnalysis` + обновленный `CombinedDiaryEntry` + потенциальный профильный апдейт.

## 5.6 Еженедельный цикл
Компоненты:
- `diary/tasks/weekly_analisys_tasks.py`
- `diary/services/weekly_analysis_service.py`
- `diary/services/user_profile_analysis_service.py`
- `diary/services/user_profile_change_analysis_service.py`
- `diary/services/profile_cleanup_service.py`

Вход:
- расписание в понедельник по локальному TZ пользователя.

Обработка:
1. Сбор недельного контекста (daily analyses, mood, tasks, streak).
2. Prompt `weekly_analysis` (premium vs lite profile view).
3. Создание `WeeklyAnalysis`.
4. Генерация `full_psych_profile`.
5. Дополнительно: profile analysis + cleanup + profile change analysis.

Выход:
- агрегированный weekly snapshot для прогресса и персонализации следующих анализов.

## 5.7 Терапевтические задания
Компоненты:
- `bot/handlers/tasks.py`
- `diary/services/task_management_service.py`

Вход:
- действия пользователя: complete/skip/delete/restore.

Обработка:
1. CRUD жизненного цикла `TherapyTask`.
2. На completion: `TaskCompletion`.
3. Фоновый AI-анализ эффекта `task_effect_analysis`.
4. Создание `TaskCompletionAnalysis` и начисление токенов.

Выход:
- обновленный статус задания, анализ эффекта, токены.

## 5.8 Напоминания и мотивации
Компоненты:
- `diary/tasks/reminder_tasks.py`
- `diary/tasks/morning_motivations.py`
- `diary/tasks/scheduler_tasks.py::send_timezone_reminder`

Вход:
- periodic celery tick.

Обработка:
- выбор пользователей по notifications_enabled/is_blocked/timezone;
- персонализированное сообщение через DeepSeek (или fallback);
- отправка в Telegram.

Выход:
- сообщения пользователям, логи delivery/failures.

## 5.9 Платежи и токены
Компоненты:
- `bot/handlers/payments.py`
- `diary/services/payment_service.py`
- `users.models.Payment`, `users.models.TokenTransaction`

Вход:
- выбор подписки/пакета токенов + email.

Обработка:
1. Инициация платежа в ЮKassa.
2. Создание `Payment` в pending.
3. Track status.
4. При success: активация premium и/или пополнение token balance.

Выход:
- confirmation URL, обновление баланса/подписки, транзакция.

## 5.10 REST API
Базовый префикс:
- `/api/v1/auth/` (router и auth endpoints объединены)

Основные endpoints:
- `GET /users/me/`
- `GET /profile/full/`, `GET /profile/compact/`, `GET /profile/statistics/`
- CRUD `/entries/`
- RO `/days/`, `/weekly/`
- CRUD `/tasks/` + `POST /tasks/{id}/complete/`
- Auth:
  - `POST /register/`
  - `POST /login/`
  - `POST /refresh/`
  - `GET /telegram/?token=...`
  - `POST /complete-registration/`
  - `POST /generate-link/`

Вход:
- JWT access token (кроме публичных auth endpoints).

Выход:
- JSON сериализованные объекты user/profile/entries/tasks/statistics.

---

## 6. AI-подсистема и prompt-контракты

## 6.1 Prompt реестр
Роутинг шаблонов: `prompts/get_prompt.py`

Ключевые template-группы:
- incremental: `incremental_day_analysis*`
- full day: `full_day_analysis*`
- weekly/profile: `weekly_analysis`, `user_profile_analysis`, `profile_change_analysis`
- support: `clarification_analysis`, `comment_analysis`, `task_effect_analysis`, `therapy_chat`
- utility: punctuation/timezone/reminders/morning

## 6.2 Контракт unified personalization
Ключевая тенденция к унификации:
- `compressed_psych_profile_json`
- `personal_fields_json`
- weighted list items (value/weight/frequency/is_stale)

LITE v2 incremental использует отдельные compact поля:
- `user_personality_traits`
- `user_triggers`
- `user_strengths`

## 6.3 Failover
- retry при сетевых сбоях;
- fallback prompt при context overflow;
- системные default-ответы при API-error;
- HTML sanitization для AI output.

---

## 7. Фоновые задачи (операционная карта)

Из `CELERY_BEAT_SCHEDULE`:
- ежедневный scheduler full-day analysis;
- timezone reminders;
- hourly entry reminders;
- weekly analyses scheduler;
- profile cleanup;
- clarification reminder + force-process;
- morning motivation;
- task expiration;
- garbage collector.

Особенности:
- закрытие DB-коннектов на task pre/post run в `core/celery.py`.

---

## 8. Безопасность и приватность

## 8.1 Шифрование
- чувствительные поля моделей на кастомных encrypted fields (`core/encrypted_fields.py`).
- шифруются text/json/email профиля и контент анализа/дневника.

## 8.2 Auth
- JWT в REST API.
- redis-based short-lived tokens для Telegram/Web link сценариев.

## 8.3 Ограничения
- rate limiting на сообщения.
- token/premium gates для некоторых сценариев.

---

## 9. Конфигурация и feature flags

Ключевые флаги:
- `COMPRESSED_PROFILE_ENABLED`
- `USE_LITE_V2`

Критичные env:
- DB, Redis/Celery, Telegram token, DeepSeek key, Yookassa keys, Crypto key.

---

## 10. Тестовая карта

Наблюдаемое покрытие:
- unit/integration тесты по сервисам, handlers, middleware, tasks, models.
- отдельный блок контрактов промптов (`tests/test_prompt_contracts.py`) на placeholders и unified payload.

Текущий фокус качества:
- prompt rendering consistency;
- auth token flows;
- сервисный слой diary/task/profile.

---

## 11. Важные зависимости и связи

Ключевые сильные связи:
- `diary_service` <-> `deepseek_api` <-> `daily_state_service` <-> prompts
- `full_day_analysis_service` <-> `weekly_analysis_service` <-> profile services
- handlers сильно завязаны на сервисные фасады и FSM state manager
- payment lifecycle пересекает bot utils + diary services + users models

Границы контекстов:
- Telegram UX: `bot/*`
- Domain logic: `diary/services/*`
- Persistence and identity: `users/*`, `diary/models.py`
- Public API: `api/*`

---

## 12. Риски, технический долг и точки для улучшений

## 12.1 Потенциальные риски
- Высокая сложность `bot/services/diary_service.py` (большой orchestration-монолит).
- Сильная связанность Telegram-слоя и доменной логики в отдельных сценариях.
- Параллельная поддержка нескольких prompt-режимов (premium/lite_v1/lite_v2) усложняет тестирование.
- Много синхронно-асинхронных переходов (`sync_to_async`/`async_to_sync`), риск скрытых latency/locking эффектов.

## 12.2 Обнаруженные несоответствия на уровне контрактов
- В `api/serializers.py` для `TherapyTaskSerializer` используются поля `task_type`, `effect_rating`, тогда как в модели `TherapyTask` поля `type`, `complexity`.
  Это потенциальный источник runtime/serialization ошибок и требует сверки контрактов API.

## 12.3 Операционные риски
- Глубокая зависимость UX от внешнего AI API.
- Необходимость строгой защиты от context overflow и нестабильности API.

---

## 13. Матрица «где менять» по крупным направлениям

Если цель: оптимизация AI и контекста
- `bot/services/diary_service.py`
- `diary/services/full_day_analysis_service.py`
- `diary/services/weekly_analysis_service.py`
- `core/profile_field_utils.py`
- `prompts/templates/*`

Если цель: стабилизация платежей
- `diary/services/payment_service.py`
- `bot/utils/payment_utils.py`
- `users/models.py` (`Payment`, `TokenTransaction`)

Если цель: API консистентность
- `api/serializers.py`
- `api/views.py`
- `api/urls.py`
- тесты API

Если цель: рефакторинг домена задач
- `diary/services/task_management_service.py`
- `bot/handlers/tasks.py`
- `diary/models.py` (Task* сущности)

---

## 14. Рекомендуемый порядок планирования изменений
1. Зафиксировать базовые контракты (API serializers, prompt placeholders, model-field mapping).
2. Выделить критические production-сценарии и регрессионные тесты (entry creation, daily analysis, weekly cycle, payments).
3. Декомпозировать `diary_service` на orchestration + domain steps (без изменения UX).
4. Провести унификацию AI payload (один canonical schema для prompt input).
5. Укрепить observability: structured logs по latency/tokens/failover paths.

---

## 15. Краткий вывод
Текущая система функционально богата и зрелая по сценариям (дневник, AI-анализы, задания, прогресс, монетизация, web auth). Главная сложность находится в orchestration-слое анализа и в многоуровневой персонализации prompt-контрактов. Для безопасных изменений нужен контракт-first подход: сначала унифицировать интерфейсы и тесты, затем рефакторить внутреннюю композицию сервисов.
