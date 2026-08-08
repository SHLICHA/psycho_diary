# IMPLEMENTATION_PLAN.md

Документ: единый план внедрения VK MAX, синхронизации Telegram/MAX и правила ведения работ.

Дата создания: 2026-06-29
Статус: в работе

---

## 1) Инструкции для AI-агента

1. Не делать ничего нового без уточнения у заказчика.
2. Все чувствительные переменные выносить в файл переменных окружения.
3. Все действия фиксировать в этом документе.
4. Если действие выполнено, обязательно отмечать это в чекбоксе и журнале.
5. Важно ничего не потерять: перед любыми изменениями проверять влияние на существующие требования, данные и поведение.
6. По любым спорным действиям задавать вопросы заказчику до выполнения.
7. Обязательное тестирование: каждое изменение должно сопровождаться тестами и/или прогоном релевантных тестов.
8. Обязательное разделение логики: Telegram/MAX-бот остается thin client, бизнес-логика и доменные правила живут только в проекте (API/сервисы).
9. Обязательное оформление Django Admin: при создании или изменении моделей необходимо добавлять/обновлять регистрацию в админке (list_display, list_filter, search_fields и релевантные ограничения доступа).

---

## 2) Правила ведения работ

- Любая задача выполняется только после явного подтверждения.
- Любое изменение кода сопровождается:
- обновлением статуса в чекбоксах плана;
- записью в журнал действий;
- отметкой о рисках и затронутых требованиях (если есть).
- Нельзя удалять/переписывать требования из TZ без согласования.
- Любые секреты и ключи в коде запрещены.
- Для новых переменных окружения обновлять шаблон .env.example и описание в документации.
- Каждая переменная в .env.example должна сопровождаться кратким комментарием о назначении.
- Комментарии в .env.example, проектную документацию и подписи в Django Admin вести на русском языке.
- Любой merge-блокер: отсутствие обязательных тестов для внесенных изменений.
- Запрещено переносить бизнес-логику в Telegram/MAX-бота; бот работает только как транспортный слой и UI-команды.
- Структура backend должна быть модульной: отдельные приложения по отдельным зонам ответственности (bounded contexts).
- Каждое приложение отвечает только за свой фронт работ и не содержит чужую доменную логику.

После завершения шага:

- Проставить отметку "выполнено".
- Добавить запись в журнал действий.
- Зафиксировать, что не потеряны существующие требования и данные.
- Выполнить и зафиксировать тестирование (unit/integration/contract по релевантности).

---

## 3) Критически важные ограничения production

- Проект уже работает на боевом сервере с боевой базой данных.
- Любые изменения структуры данных делать только в режиме zero-downtime.
- Применять стратегию expand -> migrate/backfill -> switch -> contract.
- Не выполнять опасные операции в одной миграции с функциональными изменениями.
- Запрещены блокирующие/долгоиграющие миграции без предварительной оценки lock impact.
- Каждый релиз должен иметь rollback-план.

### 3.1 Обязательные правила миграций

- Сначала только расширяющие изменения (nullable поля, новые таблицы, новые индексы).
- Ужесточение ограничений (NOT NULL, UNIQUE, удаление legacy) только после стабилизации.
- Backfill выполнять батчами и отдельно от релиза схемы.
- Проверять дубли и конфликты данных до включения строгих ограничений.

---

## 4) Архитектурная цель внедрения MAX

Цель: единый продукт с двумя мессенджерными интерфейсами (Telegram и MAX), где:

- transport-слой (боты) тонкий и не содержит доменной логики;
- бизнес-логика живет в API/сервисах/use cases;
- identity-контур общий через email bridge;
- изменения в функционале вносятся одновременно в оба мессенджера.

### 4.1 Принципы

- Один use case -> два transport-адаптера.
- Один источник бизнес-правил.
- Единый контракт входа/выхода для Telegram и MAX.
- Единые правила тестирования и parity-контроль для двух каналов.

---

## 5) Подробный поэтапный план действий

### Phase 0. Подготовка и governance

- [ ] Зафиксировать архитектурный контракт слоев (thin transport, shared business layer).
- [ ] Ввести обязательный Migration Safety Review для каждого PR.
- [ ] Ввести parity-checklist Telegram/MAX для каждого изменения.
- [ ] Зафиксировать release/rollback runbook.

Результат фазы: прозрачные правила изменений, исключающие хаотичную доработку.

### Phase 1. Безопасная data-база для внедрения

- [x] Выполнить аудит текущей схемы и зависимостей по user identity.
- [x] Подготовить безопасные expand-миграции для MAX identity.
- [x] Подготовить план backfill (батчи, метрики, остановка/продолжение).
- [x] Подготовить dual-read/dual-write стратегию при переключении.
- [x] Подготовить карту всех мест, где platform identity использует telegram_id (permissions, payments, referrals, middleware, service logs).

Результат фазы: база готова к новому каналу без риска потери данных.

#### 1.1 Результаты аудита identity baseline (2026-06-29)

##### Текущее состояние схемы

- [x] В `users.User` есть `telegram_id` (unique, nullable) и отсутствует `max_id`.
- [x] Email хранится в encrypted field, поиск/уникальность реализованы через `email_hash`.
- [x] В `users.User.save()` есть генерация `referral_link`, завязанная на `telegram_id`.

##### Ключевые точки связности (identity coupling)

- [x] Регистрация/обновление пользователя и рефералы завязаны на Telegram event model в `diary/services/user_service.py`.
- [x] В `bot/middlewares/user_middleware.py` логика создания/поиска пользователя опирается на `event.from_user.id` и реферальный шаблон `/start ref_*`.
- [x] API auth/registration flow опирается на `email_hash` и частично возвращает `telegram_id` (`api/serializers.py`, `api/views.py`).
- [x] Monitoring permission привязана к сравнению `DEVELOPER_CHAT_ID` и `request.user.telegram_id` (`api/permissions.py`).
- [x] Payment metadata отправляет `user_id = telegram_id` (`bot/utils/payment_utils.py`).

##### Риски при добавлении MAX identity

- [x] Риск коллизий identity, если смешать transport id и системный user id без отдельного `max_id`.
- [x] Риск регресса реферальной механики, так как ссылка и парсинг сейчас Telegram-centric.
- [x] Риск регресса мониторинговых прав при появлении пользователей без `telegram_id`.
- [x] Риск некорректной корреляции платежей, если metadata останется только на `telegram_id`.

##### Обязательные требования к следующему шагу (expand only)

- [x] Добавлять `max_id` только как nullable + индекс (без немедленного UNIQUE/NOT NULL).
- [x] Не удалять и не ужесточать текущие поля `telegram_id`/`email_hash` на этапе expand.
- [x] Сначала подготовить код к dual-read/dual-write, затем отдельно backfill/ограничения.

#### 1.2 Выполненный expand-шаг MAX identity (2026-06-29)

##### Что реализовано

- [x] В модель `users.User` добавлено поле `max_id` (nullable, blank, db_index=True).
- [x] Сгенерирована миграция `users/migrations/0044_user_max_id.py` (только AddField, без опасных операций).
- [x] Django Admin обновлен под новое поле (`list_display`, `search_fields`, `fieldsets`, `add_fieldsets`).

##### Проверки безопасности миграции

- [x] Миграция соответствует стратегии expand (без NOT NULL/UNIQUE/удалений/переездов данных).
- [x] `manage.py check` без ошибок.
- [x] `makemigrations --check --dry-run` подтверждает консистентность состояния миграций.

##### Rollback-подход

- [x] Откат шага возможен обратной миграцией `users` до `0043_remove_habits_skills`.
- [x] Так как backfill и switch не выполнялись, rollback не требует миграции данных.

#### 1.3 Дополнения по результатам аудита (чтобы ничего не упустить)

##### Контроль идентификаторов

- [ ] Ввести единый термин: internal_user_id (PK users.User) как главный идентификатор домена.
- [ ] Зафиксировать transport identity как отдельные поля/структуры: telegram_id, max_id, source_chat_id.
- [ ] Запретить использование transport id как единственного ключа в межсервисных интеграциях.

##### Рефералы

- [x] Убрать жесткую зависимость генерации referral_link от telegram_id.
- [x] Ввести fallback-генерацию referral_link для пользователей без telegram_id.
- [x] Проверить совместимость шаблона /start ref_* с будущим MAX flow (без изменения действующих Telegram ссылок).

##### Платежи

- [x] Перевести payment metadata на internal_user_id.
- [x] Сохранить platform и transport id в metadata как дополнительные атрибуты (для трассировки).
- [x] Добавить проверку обратной совместимости для платежей, созданных со старой metadata схемой.

##### Доступ и безопасность

- [x] Убрать зависимость мониторинговых прав от request.user.telegram_id.
- [x] Перевести доступ мониторинга на роли/привилегии + опциональный allowlist по internal_user_id.

##### Миграции и ограничения

- [ ] На этапе contract подготовить частичные уникальные ограничения для max_id (только где max_id IS NOT NULL).
- [ ] Отдельно оценить lock impact и стратегию создания индексов (CONCURRENTLY для production, где применимо).
- [ ] Запретить добавление NOT NULL/UNIQUE на max_id до завершения switch и стабилизации метрик.

#### 1.4 Карта telegram_id-зависимостей (фактическая инвентаризация, 2026-06-29)

##### Критичный приоритет (P0: влияет на identity и кросс-канальную совместимость)

- [x] Middleware регистрации и привязки пользователя: `bot/middlewares/user_middleware.py`, `diary/services/user_service.py`.
- [x] Старт/линковка web-аккаунта и проверка конфликтов: `bot/handlers/start.py`.
- [x] Точки доступа админа/разработчика в bot-слое: `core/services/admin_service.py`, `core/services/feedback_service.py`, `bot/handlers/feedback.py`.
- [x] API auth payload, где наружу возвращается `telegram_id`: `api/views.py`.

##### Высокий приоритет (P1: transport routing и доставка)

- [x] Отправка сообщений и блокировки пользователя через `chat_id=user.telegram_id`: `bot/utils/message_utils.py`, `diary/tasks/*` (напоминания/scheduler), `bot/handlers/tasks.py`, `bot/handlers/feedback.py`.
- [x] Вспомогательные state/lookup по `telegram_id`: `bot/utils/state_manager.py`, выборки в отдельных handlers (`calendar.py`, `feedback.py`, `admin.py`).

##### Средний приоритет (P2: сервисы/команды/операционная поддержка)

- [x] Management commands с входом по Telegram ID: `core/management/commands/run_weekly_analysis.py`, `run_profile_change_analysis.py`, `run_user_profile_analysis.py`.
- [x] Base service utilities и вспомогательные интерфейсы: `core/services/base_service.py`.
- [x] Профильные сервисы/экспорт, где `telegram_id` участвует в форматировании/логике: `diary/services/user_profile_service.py`.

##### Низкий приоритет (P3: логи/админка/диагностика)

- [x] Логирование с `user.telegram_id` во множестве сервисов/тасков (`diary/services/*`, `diary/tasks/*`, `bot/services/*`).
- [x] Django Admin `search_fields/list_display` по `telegram_id`: `users/admin.py`, `diary/admin.py`.

##### Решение по миграции (зафиксировано)

- [x] На P0/P1 вводить dual-read (по platform + transport id) и dual-write (telegram_id + max_id при наличии).
- [x] Внешние/межсервисные контракты переводить на internal_user_id как primary key домена.
- [x] Telegram-specific поля/логи не удалять до завершения rollout MAX и стабилизации.

#### 1.7 Выполненный технический шаг dual-read миграции (2026-06-29)

##### Management commands (P2)

- [x] `run_user_profile_analysis` поддерживает `--user-id` (internal id) и legacy `telegram_id`.
- [x] `run_profile_change_analysis` поддерживает `--user-id` (internal id) и legacy `telegram_id`.
- [x] `run_weekly_analysis` поддерживает `--user-id` (internal id) и legacy `telegram_id`.
- [x] Валидация аргументов: запрещено передавать оба идентификатора одновременно.
- [x] Обратная совместимость сохранена для существующих запусков через `telegram_id`.

#### 1.5 План backfill для MAX identity (операционный runbook)

##### Цель

- [x] Обеспечить безопасное дозаполнение `max_id` без простоя и без потери текущих Telegram-сценариев.

##### Источники данных для backfill

- [x] Источник A: явная привязка через flow account linking (email bridge).
- [x] Источник B: события MAX webhook/polling после включения MAX transport.
- [x] Источник C: ручная верифицированная привязка через admin-инструмент (ограниченный доступ).

##### Батчинг и идемпотентность

- [x] Батч-процесс только upsert-подобный: заполнять `max_id` только если NULL.
- [x] Размер батча: 500 записей (регулируемый), sleep между батчами 100-300ms.
- [x] Повторный запуск безопасен: уже заполненные `max_id` пропускаются.

##### Метрики и контроль качества

- [x] Метрики прогресса: `total_processed`, `linked_count`, `conflict_count`, `skipped_count`, `error_count`.
- [x] Метрика целостности: количество конфликтов (один `max_id` -> несколько user) должно быть 0 перед switch.
- [x] Метрика производительности: p95 времени батча и lock-wait.

##### Stop/Resume правила

- [x] Stop-condition: `error_rate > 1%` на 3 подряд батчах.
- [x] Stop-condition: обнаружен конфликт identity (дубли `max_id`) выше порога 0.
- [x] Resume: продолжение с последнего обработанного internal_user_id/checkpoint.

##### Rollback

- [x] На этапе backfill rollback не меняет схему; выполняется откат логики switch + ручной разбор конфликтов.
- [x] Никаких destructive update/delete в backfill job.

#### 1.6 Dual-read / dual-write стратегия (переключение)

##### Фаза DR0 (подготовка)

- [x] Все новые write-paths пишут `internal_user_id` как primary identity в доменных операциях.
- [x] Telegram и MAX id хранятся как transport identity (в соответствующих полях/контексте).

##### Фаза DR1 (dual-read)

- [x] Поиск пользователя по приоритету: internal_user_id -> explicit platform/id -> legacy telegram fallback.
- [x] Если найдено несколько кандидатов, операция не выполняется автоматически; требуется explicit confirm flow.

##### Фаза DW1 (dual-write)

- [x] При подтвержденном identity-linking обновлять transport-поля атомарно.
- [x] Логировать source_platform/source_user_id/source_chat_id для аудита.

##### Фаза SW (switch)

- [x] Для интеграций/метаданных (payments, monitoring, support routing) primary key только `internal_user_id`.
- [x] Legacy telegram-проверки остаются за feature flag до стабилизации.

##### Критерии готовности к contract-фазе

- [x] Конфликтов `max_id` нет.
- [x] Все P0/P1 read/write пути переведены на dual-read/dual-write.
- [x] Набор regression + parity тестов стабильно проходит.

### Phase 2. Identity Foundation (email bridge)

- [x] Добавить/подготовить max_id в модели пользователя (без ломки текущего поведения).
- [x] Вынести логику связки аккаунтов в единый identity service.
- [x] Реализовать политики merge/конфликтов по email.
- [x] Убедиться, что flow применим для Telegram, MAX и будущего frontend.
- [x] Ввести identity resolution policy (priority): linked account -> email_hash -> explicit confirm flow.
- [x] Ввести audit trail для account linking/unlinking (кто, когда, источник, причина).
- [x] Подготовить idempotent link операции (повторный webhook/event не меняет результат).
- [x] Ввести единый email claim pipeline для всех точек ввода email: web complete-registration, Telegram profile edit, payment receipt email.
- [x] Запретить прямое обновление email в transport-слое без вызова identity policy service.
- [x] Обеспечить единый explicit confirm flow и audit trail для конфликтов email во всех каналах.

#### 2.1 Двусторонний confirm flow Telegram/MAX (без зависимости от web)

- [x] Зафиксировать целевой симметричный сценарий подтверждения в обе стороны: Telegram -> MAX и MAX -> Telegram.
- [x] Запустить безопасный первый срез в доменном сервисе: dual-transport state machine для merge-request (инициатор подтвердил / ожидание второго канала / подтверждено / отклонено).
- [x] Добавить тесты на оба направления и статусы pending_target_confirmation / pending_requester_confirmation / rejected.
- [x] Подключить transport-доставку подтверждения во второй канал сообщениями с inline-кнопками Да/Нет. (Telegram и MAX transport-outbound)
- [x] Перевести подтверждение из web endpoint на Telegram/MAX callbacks как primary flow (web оставить опциональным fallback).

Результат фазы: единый пользовательский контур для всех каналов.

### Phase 3. Вынос бизнес-логики из Telegram handlers

- [x] Инвентаризировать handlers, где есть ORM/доменная логика.
- [x] Вынести бизнес-ветвления в use cases/services.
- [x] Оставить в handlers только transport parsing + вызов use case + render/send.
- [x] Зафиксировать anti-regression тесты Telegram после выноса.

#### 3.1 Инвентаризация Telegram handlers (2026-06-30)

##### P0 (наибольший доменный вес, высокий приоритет выноса)

- [x] `bot/handlers/diary.py`: прямые ORM-операции с `DiaryEntry`, `CombinedDiaryEntry`, `PsychoAnalysis` (`aget`, `select_related`) внутри transport-веток.
- [x] `bot/handlers/tasks.py`: прямые ORM-операции с `TherapyTask` в callback flow.

##### P1 (заметные transport+domain смешения)

- [x] `bot/handlers/admin.py`: ORM-доступ к `User` в обработчике команд.
- [x] `bot/handlers/feedback.py`: точечные ORM-вызовы (`User`, `Feedback`) внутри handler-сценариев.
- [x] `bot/handlers/calendar.py`: lookup пользователя через `User.objects.aget(...)` в callback.

##### P2 (контрольные точки)

- [x] `bot/handlers/start.py`, `bot/handlers/payments.py`: импорт моделей сохранен; требуется проверка, что доменная логика уже вынесена в сервисы и не возвращается обратно в handlers.

##### Решение на следующий шаг

- [x] Начать Phase 3 migration wave с `diary.py` и `tasks.py` (вынос ORM + бизнес-ветвлений в use cases/services, handlers оставить transport-only).

#### 3.2 Первый кодовый срез (2026-06-30)

- [x] `bot/handlers/calendar.py`: заменен прямой ORM lookup `User.objects.aget(...)` на сервисный вызов `BaseService.get_user_by_telegram_id(...)`.
- [x] Добавлена безопасная обработка отсутствующего пользователя без падения handler.
- [x] Регрессия календаря и роутинга подтверждена тестами.

#### 3.3 Второй кодовый срез (2026-06-30)

- [x] `bot/handlers/feedback.py`: прямые lookup `User`/`Feedback` переведены на `BaseService.get_user_by_telegram_id(...)` и `feedback_service.get_feedback_by_id(...)`.
- [x] `bot/handlers/admin.py`: lookup администратора для графиков переведен на `BaseService.get_user_by_telegram_id(...)`.
- [x] Добавлены fail-safe ветки для сценариев отсутствия пользователя в БД.
- [x] Сервисная и bootstrap-регрессия подтверждена тестами.

#### 3.4 Третий кодовый срез (2026-06-30)

- [x] `diary/services/task_management_service.py`: добавлен сервисный lookup `get_user_task_by_id(...)` (класс + удобный экспорт-функция).
- [x] `bot/handlers/tasks.py`: прямые ORM-запросы `TherapyTask.objects.aget(...)` в `view_specific_task`, `start_task_completion`, `paginate_task_history` заменены на сервисный lookup.
- [x] Сохранены текущие UX-ветки ошибок (`task_not_found`) и диагностическое логирование.
- [x] Регрессия задач и bootstrap подтверждена тестами.

#### 3.5 Четвертый кодовый срез (2026-06-30)

- [x] `bot/services/diary_service.py`: добавлены сервисные lookup-методы `get_user_entry_by_id`, `get_combined_entry_with_analysis_for_date`, `get_analysis_for_entry` + удобные экспорт-функции.
- [x] `bot/handlers/diary.py`: серия прямых ORM lookup (`DiaryEntry/CombinedDiaryEntry/PsychoAnalysis`) переведена на `diary_service`.
- [x] Сохранены текущие user-facing ветки ошибок (`entry_not_found`, `error_generic`) и fallback-клавиатуры.
- [x] Регрессия diary use-case/display/bootstrap подтверждена тестами.

#### 3.6 Quality gate после extraction-срезов (2026-06-30)

- [x] Подтверждено отсутствие прямых ORM-вызовов в Telegram handlers (`grep -RIn "\.objects\." bot/handlers` -> без совпадений).
- [x] Выполнен контрольный anti-regression прогон Telegram handler-наборов.
- [x] Поведение ключевых пользовательских сценариев (help/calendar/tasks/bootstrap) стабильно после выноса ORM lookup в сервисный слой.

#### 3.7 Пятый кодовый срез (2026-06-30)

- [x] `diary/services/diary_display_service.py`: добавлен orchestration-метод `build_full_day_analysis_view(...)`, инкапсулирующий ветвления full-day analysis (not_found / no-analysis / success).
- [x] `bot/handlers/diary.py`: `view_full_day_analysis` упрощен до transport orchestration (parse callback -> service call -> render/answer).
- [x] Добавлены unit-тесты на новый orchestration-метод и подтверждена регрессия дневниковых сценариев.

#### 3.8 Шестой кодовый срез (2026-06-30)

- [x] `diary/services/diary_display_service.py`: добавлен orchestration-метод `build_day_entries_view(...)` для единого формирования payload сценариев `entries/empty`.
- [x] `bot/handlers/diary.py`: ветвления render после `process_entry_edit`, `confirm_delete_specific_entry`, `cancel_delete_specific_entry` переведены на единый сервисный payload `build_day_entries_view(...)`.
- [x] Добавлены unit-тесты `build_day_entries_view` (entries/empty), подтверждена регрессия diary/bootstrap.

#### 3.9 Седьмой кодовый срез (2026-06-30)

- [x] `diary/services/diary_display_service.py`: добавлен orchestration-метод `build_entry_delete_confirmation_view(...)` (режимы `confirm/not_found`).
- [x] `bot/handlers/diary.py`: `entry_delete_confirm` и `request_delete_specific_entry` переведены на единый service payload, удалено дублирование веток.
- [x] Исправлена потенциальная ошибка порядка аргументов при построении клавиатуры подтверждения удаления (централизовано в сервисе).
- [x] Добавлены unit-тесты `build_entry_delete_confirmation_view`, подтверждена регрессия diary/bootstrap.

#### 3.10 Восьмой кодовый срез (2026-06-30)

- [x] `bot/services/diary_service.py`: добавлен универсальный `process_entry_edit_use_case(...)` с единым ServiceResponse-контрактом (update + resolve target date + day view payload).
- [x] `bot/handlers/diary.py`: `process_entry_edit` переведен на вызов use-case в сервисе; handler оставлен transport-first (парсинг/валидация input + render).
- [x] `tests/test_diary_entry_use_case.py`: добавлены unit-тесты на success / update_failed / invalid_target_date для нового use-case.
- [x] Регрессия diary/display/bootstrap подтверждена тестами.

#### 3.11 Финальный кодовый срез (2026-06-30)

- [x] `bot/services/diary_service.py`: добавлены use-case методы `process_delete_specific_entry_use_case(...)` и `process_cancel_delete_specific_entry_use_case(...)` для удаления/отмены удаления конкретной записи с единым ServiceResponse-контрактом.
- [x] `bot/handlers/diary.py`: `confirm_delete_specific_entry` и `cancel_delete_specific_entry` переведены на service use-cases; в handlers оставлены transport parsing + вызов use-case + render/send.
- [x] `tests/test_diary_entry_use_case.py`: добавлены unit-тесты success / invalid_target_date / day_view_build_failed для новых delete/cancel use-cases.
- [x] Финальная anti-regression проверка Phase 3 подтверждена тестами.

#### 3.12 Дочистка diary domain leftovers (2026-08-08)

- [x] `bot/services/diary_service.py`: добавлены `schedule_clarification_for_entry(...)` и `build_clarification_answers_map(...)`; schedule clarification встроен в `process_new_entry_use_case`.
- [x] `process_user_comment_logic`: перенесён side-effect обновления `CombinedDiaryEntry` из handler.
- [x] `bot/presenters/diary_presenter.py`: добавлен `build_entry_saved_view(...)` для render уже сохранённого анализа.
- [x] `bot/handlers/diary.py`: убраны ORM-мутации clarification timers и `_process_analysis_result` (двойная доменная запись); clarification/comment handlers оставлены transport + render/FSM.
- [x] Добавлены/обновлены unit-тесты use-case и presenter; anti-regression bootstrap подтверждена.

#### 3.13 Onboarding + profile domain extraction (2026-08-08)

- [x] `process_first_onboarding_entry_use_case`: завершение онбординга (`is_onboarding_completed`) перенесено из handler в use case.
- [x] `bot/handlers/onboarding.py`: убраны ORM-мутации пользователя; handler оставлен transport + render/FSM.
- [x] `UserProfileService`: добавлены `validate_profile_field_input`, `process_profile_field_update`, `prepare_list_field_for_edit`.
- [x] `bot/handlers/profile.py`: убраны `asave`, приватные `_filter_*`/`_format_*` и локальные валидаторы; edit-flow через сервисные use-case методы.
- [x] Добавлены unit-тесты `tests/test_user_profile_field_use_case.py` и обновлены onboarding use-case тесты.

#### 3.14 Tasks completion orchestration extraction (2026-08-08)

- [x] `TaskManagementService`: добавлены `complete_task_with_feelings_use_case` и `analyze_completed_task_for_notification_use_case`.
- [x] `TaskDisplayService`: добавлены `build_active_tasks_view` и `build_task_history_view`.
- [x] `bot/handlers/tasks.py`: completion/notify/show/skip/history переведены на use-case/view payload; transport оставлен для voice/FSM/send.
- [x] Добавлены unit-тесты `tests/test_task_completion_use_case.py`.

#### 3.15 Payments / progress / feedback / full-day reanalysis extraction (2026-08-08)

- [x] `full_day_analysis_service`: добавлен `build_full_day_reanalysis_notification(...)`; diary handler `_run_full_analysis_and_notify` оставлен transport-only.
- [x] `PaymentService`: добавлены `build_premium_menu_view`, `build_payment_link_message`, `build_payment_initiation_view`; `bot/handlers/payments.py` переведён на view payload.
- [x] `ProgressService`: добавлены `build_progress_screen_view`, `build_weekly_analysis_page_view`, `build_restore_streak_request_view`; `bot/handlers/progress.py` переведён на view builders.
- [x] `FeedbackService`: добавлены `build_admin_feedback_list_keyboard`, `build_admin_feedback_item_view`, `build_admin_reply_prompt_view`; admin/list/reply handlers упрощены до transport.
- [x] Добавлены unit-тесты `tests/test_phase315_view_builders.py`.

#### 3.16 Critical domain out of transport (2026-08-08)

- [x] `TherapyChatService`: `build_therapy_chat_welcome_view`, `build_therapy_chat_error_recovery_view` (error-path через `build_main_menu_data`).
- [x] `SettingsService`: `build_task_settings_view`, `build_task_limit_update_view`, `build_city_timezone_lookup_view`, `set_timezone_and_resolve_next_step`.
- [x] `OnboardingService`: `resolve_start_routing_use_case`, `build_onboarding_timezone_prompt_view`, `build_first_onboarding_entry_result_view`.
- [x] Handlers `therapy_chat` / `settings` / `start` / `onboarding` переведены на use-case/view payload.
- [x] Тесты: `tests/test_phase316_view_builders.py`.

#### 3.17 Admin + profile screen builders (2026-08-08)

- [x] `AdminService`: `build_admin_stats_report`, `get_admin_stats_bundle`; cleanup model imports в `admin.py`.
- [x] `UserProfileService`: `build_profile_screen_view`, `build_psychology_profile_view`, `build_edit_profile_menu_view`, `build_list_field_edit_prompt`, `build_account_deletion_menu_view`, `build_referral_link_view`.
- [x] Тесты: `tests/test_phase317_view_builders.py`.

#### 3.18 Diary leftovers + feedback use cases (2026-08-08)

- [x] Diary: `build_new_entry_outcome_view`, `start_add_comment_use_case`, `build_day_first_entry_view`, `submit_analysis_rating_use_case`, delete-day / reanalysis use cases.
- [x] Feedback: `submit_user_feedback_use_case`, `process_admin_feedback_reply_use_case` (persist после send), `compute_admin_feedback_nav_index`.
- [x] Тесты: `tests/test_phase318_diary_view_builders.py`, `tests/test_phase318_feedback_use_cases.py`.

#### 3.19 Remaining P2 polish (2026-08-08)

- [x] Tasks: page/detail/start-completion views + `restore_skipped_task_use_case`.
- [x] Payments: email result / token options views + `is_payment_cancel_command`.
- [x] Progress: `confirm_streak_restoration_use_case`.
- [x] Calendar: `resolve_calendar_anchor_day` / `build_year_selected_calendar_view`.
- [x] Identity merge: requester/target merge result views.
- [x] Тесты: `tests/test_phase319_view_builders.py`.

#### 3.20 Quality gate «ноль бизнес-логики» (2026-08-08)

- [x] Grep-гейт: нет `.objects.` / `.asave` / `.save` в `bot/handlers`; нет runtime-веток по `is_premium` / `token_balance` / `awareness_level` / `is_onboarding_completed`.
- [x] Model imports в handlers только под `TYPE_CHECKING` (type hints).
- [x] Anti-regression: `pytest -q tests/test_phase315_view_builders.py … tests/test_phase319_view_builders.py tests/test_bot_main.py` → **79 passed**.
- [x] Phase 3 Done: Telegram handlers = transport-only (parse → use case/view → FSM/send).

#### 3.21 Hygiene sprint перед Phase 7 / MAX (2026-08-08)

- [x] Dead noise: устаревшие маркеры (`СТАРАЯ`/`КОНЕЦ`), unused imports, выровнены module docstrings handlers.
- [x] Exception hygiene: убраны bare `except:` и silent `except Exception: pass` в `diary`/`tasks`/`profile` (cleanup → `logger.debug`).
- [x] Logging convention: prefix `[module.action]`, identity через `user.id`, снижен шум hot-path в diary/tasks/feedback/settings.
- [x] Checklist hygiene: нет bare `except:` / stale markers / `.objects.` в `bot/handlers`.
- [x] Anti-regression: `pytest -q tests/test_phase315…319 + test_bot_main` → **79 passed**.

Результат фазы: Telegram становится transport-адаптером.

### Phase 4. Единые контракты для двух transport-слоев

- [x] Ввести normalized input model (actor, command, payload, context).
- [x] Ввести normalized output model (text, buttons, attachments, state transitions).
- [x] Ввести единый send port interface.
- [x] Подключить Telegram к новым контрактам без UX-регресса.

#### 4.1 Первый кодовый срез (2026-06-30)

- [x] Добавлены общие transport-контракты `NormalizedInput`/`NormalizedOutput` и связанные модели (`actor/buttons/attachments/state transition`) в `bot/transports/contracts.py`.
- [x] Добавлен единый `SendPort` интерфейс и результат доставки `SendResult` в `bot/transports/send_port.py`.
- [x] Реализован `UnifiedSendPort` для Telegram/MAX в `bot/transports/unified_send_port.py`.
- [x] `bot/transports/identity_merge_dispatcher.py` переведен на normalized output + send port без изменения пользовательского поведения.
- [x] Регрессия transport-dispatch и MAX client подтверждена тестами.

#### 4.2 Второй кодовый срез (2026-06-30)

- [x] `bot/utils/message_utils.py`: общий путь `send_message_to_user(...)` подключен к `UnifiedSendPort` через normalized output (с fallback на legacy send для неподдержанных клавиатур/режимов).
- [x] `bot/transports/unified_send_port.py`: добавлены детализированные причины Telegram-ошибок для корректной block/unblock логики.
- [x] `tests/test_message_utils_transport_port.py`: добавлены unit-тесты на normalized output builder и отправку через send port без вызова legacy bot.send_message.
- [x] Регрессия Telegram/MAX transport-сценариев подтверждена тестами.

Результат фазы: готовый фундамент для "одна логика -> два мессенджера".

### Phase 5. Инфраструктура MAX (transport)

- [x] Реализовать MAX client (send, parse webhook/polling events, register webhook, close session).
- [x] Реализовать MAX webhook/polling coordinator.
- [x] Добавить rate limiting для MAX.
- [x] Добавить chunking для длинных сообщений и fallback отправки.
- [x] Добавить MAX state storage (cache/Redis, TTL, clear policy).

#### 5.1 Обязательные технические особенности MAX (чек-лист)

##### API и транспорт

- [x] Учтена взаимоисключаемость webhook и polling (одновременно не использовать).
- [ ] Реализован webhook-first режим для production.
- [x] Реализован polling режим только для dev.
- [x] Авторизация только через заголовок Authorization.
- [x] Отправка сообщений учитывает, что chat_id/user_id передаются как query-параметры.
- [x] Учтен формат ответа MAX без обертки response.
- [x] Добавлена регистрация webhook с корректными update_types.

##### Входящие события и парсинг

- [x] Поддержан webhook-формат входящих событий.
- [x] Поддержан polling-формат входящих событий.
- [x] Нормализация входящих событий в единый internal event model.
- [x] Обработаны event types: message_created, bot_started, message_callback.
- [x] Корректно извлекаются user_id и chat_id из альтернативных веток payload.
- [x] Корректно извлекается текст сообщения (включая body.text).

##### Надежность отправки

- [x] Добавлен fallback с chat_id на user_id при ошибках поиска чата.
- [x] Включен chunking длинных сообщений (лимит MAX + safe margin).
- [x] Кнопки/вложения отправляются корректно в конце chunk-последовательности.
- [x] Добавлена повторная отправка без клавиатуры при ошибке payload-кнопок (если применимо).

##### Сессии, лимиты, состояние

- [x] Закрытие aiohttp session гарантировано в finally.
- [x] Реализован token bucket rate limiting (RPS/Burst из env).
- [x] Реализовано state-хранилище MAX в cache/Redis с TTL.
- [x] Реализован сброс state и обработка протухших состояний.

##### Безопасность и эксплуатация

- [x] Добавлена проверка MAX webhook secret.
- [x] Добавлены переменные окружения MAX в .env.example с русскими комментариями.
- [x] Добавлены preflight-проверки конфигурации MAX перед запуском.
- [x] Добавлены health/check endpoint и диагностические проверки MAX webhook.

Результат фазы: работоспособный MAX transport-слой.

### Phase 6. API и runtime wiring

- [x] Добавить endpoint webhook для MAX.
- [x] Добавить валидацию входящего секрета и защиту от невалидных payload.
- [x] Добавить настройки MAX в core/settings.py и .env.example.
- [x] Добавить режимы запуска (webhook/polling) и интеграцию в docker-compose.
- [x] Включение только через feature flag.

Результат фазы: MAX подключен к runtime безопасно и управляемо.

### Phase 7. Пошаговая миграция хендлеров (parity waves)

#### Wave 1: базовые сценарии

##### Telegram handlers (Wave 1)

- [ ] /start (cmd_start)
- [ ] onboarding (согласия, timezone, first entry)
- [ ] /help и help callbacks
- [ ] /settings и изменение email
- [ ] fallback handler (текст/голос вне контекста)
- [ ] Изменение email в settings/profile переведено на единый identity policy + explicit confirm flow.

##### MAX handlers (Wave 1)

- [ ] /start
- [ ] onboarding flow (email/skip)
- [ ] /help
- [ ] /settings
- [ ] fallback на неизвестные команды/сообщения
- [ ] Изменение email в settings переведено на единый identity policy + explicit confirm flow.

##### Общие проверки parity (Wave 1)

- [ ] Одинаковые тексты и кнопки по сценарию старт/онбординг.
- [ ] Одинаковые состояния завершения onboarding.
- [ ] Одинаковая логика email-linking и conflict prompt.
- [ ] Одинаковая логика конфликтов email (confirm required) в web/profile/settings.

#### Wave 2: пользовательские сценарии

##### Telegram handlers (Wave 2)

- [ ] создание дневниковой записи (текст)
- [ ] создание дневниковой записи (голос)
- [ ] редактирование/удаление/комментарий к записи
- [ ] календарь и навигация
- [ ] /history и пагинация истории
- [ ] /progress (серии, агрегаты, графики)

##### MAX handlers (Wave 2)

- [ ] обработка входящего текста как дневниковой записи
- [ ] поддержка ключевых callback-переходов по дневнику
- [ ] /history и пагинация (history_page)
- [ ] /progress

##### Общие проверки parity (Wave 2)

- [ ] Одинаковый расчет и отображение истории.
- [ ] Одинаковые правила доступа к history/progress (onboarding gate).
- [ ] Одинаковая доменная обработка записей и аналитики.

#### Wave 3: коммерческий контур

##### Telegram handlers (Wave 3)

- [ ] /premium
- [ ] выбор пакета токенов
- [ ] ввод email для чека (если требуется)
- [ ] обработка статуса оплаты
- [ ] Ввод email для чека использует единый identity policy + explicit confirm flow при конфликте.

##### MAX handlers (Wave 3)

- [ ] /premium
- [ ] callback premium:token_amount
- [ ] callback premium_receipt:yes|no:token_amount
- [ ] ввод email для чека и подтверждение оплаты
- [ ] Ввод email для чека использует единый identity policy + explicit confirm flow при конфликте.

##### Общие проверки parity (Wave 3)

- [ ] Одинаковые бизнес-правила premium/token purchase.
- [ ] Одинаковая идемпотентность webhook-обновлений оплаты.
- [ ] Одинаковые пост-эффекты (баланс/статус/уведомления).
- [ ] Одинаковая обработка конфликтов email в платёжном флоу (confirm required).

#### Wave 4: коммуникации

##### Telegram handlers (Wave 4)

- [ ] /feedback
- [ ] отправка текстового feedback
- [ ] отправка голосового feedback
- [ ] отправка feedback с фото
- [ ] /support и создание тикета

##### MAX handlers (Wave 4)

- [ ] feedback flow
- [ ] support flow
- [ ] reply flow для пользовательских ответов

##### Общие проверки parity (Wave 4)

- [ ] Одинаковая логика создания/маршрутизации тикетов.
- [ ] Source-aware корректность (platform, source_user_id, source_chat_id).
- [ ] Одинаковые статусы и жизненный цикл обращений.

#### Wave 5: админ-контур

##### Telegram handlers (Wave 5)

- [ ] /admin
- [ ] /stats
- [ ] /status
- [ ] /health
- [ ] /open_tickets
- [ ] /broadcast + состояние ожидания сообщения
- [ ] /reply

##### MAX handlers (Wave 5)

- [ ] /admin
- [ ] /stats
- [ ] /status
- [ ] /health
- [ ] /open_tickets
- [ ] /broadcast + STATE_WAITING_FOR_BROADCAST_MESSAGE
- [ ] /reply

##### MAX callback handlers (обязательный перечень)

- [ ] skip_email_registration
- [ ] cancel_settings_email
- [ ] reenter_email
- [ ] link_by_email:{email}
- [ ] feedback:up:{nm_id}
- [ ] feedback:down:{nm_id}
- [ ] premium:{token_amount}
- [ ] premium_receipt:{yes|no}:{token_amount}
- [ ] history_page:{N}
- [ ] broadcast_cancel

##### Общие проверки parity

- [ ] Одинаковые права доступа admin-only.
- [ ] Одинаковая статистика платформ и health-диагностика.
- [ ] Одинаковая логика рассылок и отмены broadcast-состояния.

Результат фазы: функциональная идентичность MAX и Telegram.

#### 7.1 Глобальный чек-лист покрытия хендлеров (ничего не пропустить)

##### Telegram

- [ ] start
- [ ] onboarding
- [ ] help
- [ ] settings
- [ ] diary
- [ ] calendar
- [ ] tasks
- [ ] progress
- [ ] profile
- [ ] payments
- [ ] feedback
- [ ] support
- [ ] admin
- [ ] fallback

##### MAX

- [ ] start
- [ ] onboarding
- [ ] help
- [ ] settings
- [ ] diary/messages
- [ ] history
- [ ] progress
- [ ] payments/premium
- [ ] feedback
- [ ] support
- [ ] admin
- [ ] callbacks
- [ ] fallback

### Phase 8. Тестирование и quality gates

- [ ] Unit-тесты shared use cases.
- [ ] Unit-тесты Telegram/MAX adapters.
- [ ] Integration-тесты webhook/polling MAX.
- [ ] Contract-тесты normalized I/O.
- [ ] Parity-тесты Telegram vs MAX (по ключевым флоу).
- [ ] Обязательный прогон релевантного набора тестов в каждом PR.
- [ ] Тесты identity conflict resolution (email уже привязан, разные transport ids).
- [ ] Тесты конфликтов email при редактировании профиля (Telegram/MAX settings).
- [ ] Тесты конфликтов email при вводе email в оплате (Telegram/MAX payments).
- [ ] Parity-тесты единого результата для complete-registration, profile edit и payment email flow.
- [x] Тесты обратной совместимости платежей (старая/новая metadata).
- [x] Тесты мониторингового доступа без зависимости от telegram_id.
- [x] Тесты реферального flow для пользователей без telegram_id.

Результат фазы: контроль качества перед масштабным rollout.

### Phase 9. Поэтапный rollout и стабилизация

- [ ] Canary rollout MAX.
- [ ] Мониторинг ошибок доставки, latency, merge-конфликтов, платежей.
- [ ] Поэтапное расширение охвата.
- [ ] Отдельный contract-этап (cleanup legacy, ужесточение ограничений) только после стабильности.

Результат фазы: безопасный выход в прод без потери текущей стабильности.

---

## 6) Обязательный parity-контроль (Telegram/MAX)

Для каждой новой фичи:

- [ ] Реализован shared use case.
- [ ] Подключен Telegram adapter.
- [ ] Подключен MAX adapter.
- [ ] Добавлены/обновлены тесты на оба канала.
- [ ] Проверен одинаковый бизнес-результат в обоих каналах.
- [ ] Добавлена запись в журнал действий.

---

## 7) Merge-blockers (запрет на слияние)

- [ ] Нет явного подтверждения заказчика на задачу.
- [ ] Нет обновления чекбоксов плана.
- [ ] Нет записи в журнал действий.
- [ ] Нет фиксации рисков и влияния на требования.
- [ ] Нет тестов/прогона релевантных тестов.
- [ ] Новые env-переменные не внесены в .env.example с русскими комментариями.
- [ ] Изменена модель Django, но не обновлена Django Admin.

---

## 8) Шаблон записи о выполненном шаге

Использовать при закрытии каждого шага:

- Шаг/задача:
- Дата/время:
- Исполнитель:
- Что сделано:
- Какие требования затронуты:
- Какие риски проверены:
- Подтверждение, что данные и поведение не потеряны:
- Какие тесты выполнены:
- Результат тестов:
- Ссылки на коммит/PR:

---

## 9) Журнал действий

| Дата | Шаг | Действие | Измененные файлы | Риски/влияние | Тестирование | Статус |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06-29 | Инициализация плана | Создан единый документ IMPLEMENTATION_PLAN.md на основе согласованной стратегии внедрения MAX и правил безопасной работы с прод-БД | IMPLEMENTATION_PLAN.md | Риск минимальный, код не изменялся | Не требуется (документация) | Выполнено |
| 2026-06-29 | Детализация плана | Добавлены обязательные технические особенности MAX (чек-лист) и расширенный поэтапный чек-лист хендлеров Telegram/MAX, включая MAX callbacks, чтобы исключить пропуски | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Phase 1 audit baseline | Выполнен аудит identity-схемы и зависимостей Telegram-centric, зафиксированы зоны связности и риски для безопасного внедрения MAX identity | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Phase 1 expand migration | Добавлен `max_id` в `users.User` как nullable+index, обновлен Django Admin, создана миграция `0044_user_max_id.py` | users/models.py, users/admin.py, users/migrations/0044_user_max_id.py, IMPLEMENTATION_PLAN.md | Низкий риск: только expand-изменение схемы без backfill/switch | `manage.py check`; `makemigrations --check --dry-run`; `pytest -q` (642 passed, 5 skipped) | Выполнено |
| 2026-06-29 | Усиление плана по аудиту | Добавлены обязательные контрольные пункты по identity coupling (payments, monitoring, referrals), ограничениям миграций и дополнительным quality gates для предотвращения пропусков | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Identity-safe monitoring/payments | Переведен мониторинговый доступ на internal user allowlist (с опциональной legacy-совместимостью), платежная metadata переведена на internal_user_id с сохранением legacy-ключа user_id; добавлены тесты на оба сценария | api/permissions.py, core/settings.py, .env.example, bot/utils/payment_utils.py, diary/services/payment_service.py, tests/test_phase5_rate_limit_api.py, tests/test_payment_utils_metadata.py, IMPLEMENTATION_PLAN.md | Низкий риск: обратная совместимость сохранена, поведение покрыто тестами | `pytest -q tests/test_phase5_rate_limit_api.py tests/test_payment_utils_metadata.py`; `pytest -q tests/test_monitoring_api.py tests/test_auth_api.py` | Выполнено |
| 2026-06-29 | Hybrid referral model | Внедрен transport-agnostic формат referral_link (`ref_u_*`) без привязки к telegram_id, добавлена совместимость обработки `/start` для legacy и нового форматов, добавлены тесты реферального flow для пользователей без telegram_id | users/models.py, bot/middlewares/user_middleware.py, tests/test_referral_links.py, IMPLEMENTATION_PLAN.md | Низкий риск: legacy-формат ссылок сохранен и покрыт тестами | `pytest -q tests/test_referral_links.py tests/test_user_middleware.py` | Выполнено |
| 2026-06-29 | Telegram ID dependency map | Зафиксирована полная карта `telegram_id`-зависимостей по слоям (P0..P3), определены зоны dual-read/dual-write и порядок миграции к internal_user_id | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Backfill + dual-read/write runbook | Зафиксированы операционный план backfill (`max_id`) и пошаговая стратегия dual-read/dual-write/switch с метриками, stop-conditions и критериями готовности к contract-фазе | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Dual-read migration in commands | Добавлена поддержка internal `--user-id` (с сохранением legacy `telegram_id`) в management-команды профиля/еженедельного анализа, включая валидацию аргументов и тесты обратной совместимости | core/management/commands/run_user_profile_analysis.py, core/management/commands/run_profile_change_analysis.py, core/management/commands/run_weekly_analysis.py, tests/test_run_user_profile_analysis_command.py, tests/test_run_profile_change_analysis_command.py, IMPLEMENTATION_PLAN.md | Низкий риск: интерфейсы расширены без удаления legacy режима | `pytest -q tests/test_run_user_profile_analysis_command.py tests/test_run_profile_change_analysis_command.py` | Выполнено |
| 2026-06-29 | P0 identity resolution for web-linking | Вынесена единая policy проверки конфликтов identity в `diary/services/user_service.py` и подключена в `/start link_...`; добавлены тесты на `web_user_not_found`/конфликты/idempotent linking | diary/services/user_service.py, bot/handlers/start.py, tests/test_identity_linking_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: поведение централизовано, legacy flow сохранен | `pytest -q tests/test_identity_linking_service.py tests/test_auth_token_service.py tests/test_auth_api.py` | Выполнено |
| 2026-06-29 | Phase 2 audit trail for account linking | Добавлена модель `IdentityLinkEvent` и интегрирована запись audit trail (link/unlink/rejected) в identity-service; обновлена админка и добавлены тесты на события конфликтов/успеха/idempotent unlink | users/models.py, users/migrations/0045_identitylinkevent.py, diary/services/user_service.py, users/admin.py, tests/test_identity_linking_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: expand-only схема + fail-safe логирование (ошибки аудита не ломают flow) | `pytest -q tests/test_identity_linking_service.py tests/test_auth_token_service.py tests/test_auth_api.py` | Выполнено |
| 2026-06-29 | Phase 2 email merge/conflict policy | Вынесена единая policy проверки claim по email в отдельный identity service (`resolve_email_claim`) и подключена в сериализаторы register/complete-registration без изменения API-контрактов; добавлены unit-тесты policy | users/services/identity_policy_service.py, api/serializers.py, tests/test_identity_policy_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: behavior сохранен, изменено только место принятия решения | `pytest -q tests/test_identity_policy_service.py tests/test_auth_api.py tests/test_identity_linking_service.py` | Выполнено |
| 2026-06-29 | Phase 2 transport-agnostic identity flow validation | Подтверждена применимость identity-flow к MAX/frontend: policy и аудит принимают `source_platform/source_context`; добавлен тест на запись non-telegram source в audit trail | diary/services/user_service.py, tests/test_identity_linking_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: проверка обратной совместимости + дополнительное покрытие тестами | `pytest -q tests/test_identity_linking_service.py tests/test_identity_policy_service.py tests/test_auth_api.py` | Выполнено |
| 2026-06-29 | Phase 2 explicit confirm flow for email conflicts | Реализован двухшаговый confirm flow: при конфликте email в complete-registration выдается `confirmation_token` (feature-flag), добавлен endpoint подтверждения `/auth/confirm-email-merge/`, модель `EmailMergeRequest`, админка и тесты успешного/неуспешного подтверждения | users/models.py, users/migrations/0046_emailmergerequest.py, users/services/email_merge_service.py, users/services/__init__.py, api/views.py, api/urls.py, api/serializers.py, tests/test_auth_api.py, .env.example, core/settings.py, IMPLEMENTATION_PLAN.md | Низкий риск: merge не выполняется автоматически, подтверждение фиксирует намерение без destructive-операций | `pytest -q tests/test_auth_api.py tests/test_identity_linking_service.py tests/test_identity_policy_service.py` | Выполнено |
| 2026-06-29 | Планирование unified email sync flows | В план добавлены обязательные работы по синхронизации/конфликтам email для profile edit и payment email flows (с единым identity policy + explicit confirm), а также соответствующие parity/quality тесты | IMPLEMENTATION_PLAN.md | Риск минимальный, изменена только документация | Не требуется (документация) | Выполнено |
| 2026-06-29 | Shared email-claim pipeline for profile/payment | Profile edit и payment receipt email переведены на единый identity policy + explicit confirm flow в сервисном слое (transport-agnostic для Telegram/MAX), Telegram-хендлеры обновлены под новые коды конфликтов, добавлены сервисные тесты конфликтов | diary/services/user_profile_service.py, diary/services/payment_service.py, users/services/identity_policy_service.py, users/services/email_merge_service.py, bot/handlers/profile.py, bot/handlers/payments.py, messages/messages_utils.py, tests/test_email_claim_pipeline_services.py, IMPLEMENTATION_PLAN.md | Низкий риск: изменена бизнес-логика только в направлении stricter conflict handling, destructive merge отсутствует | `pytest -q tests/test_email_claim_pipeline_services.py tests/test_auth_api.py tests/test_identity_linking_service.py tests/test_identity_policy_service.py` | Выполнено |
| 2026-06-29 | Phase 2 dual Telegram/MAX confirmation (slice 1) | Запущен первый безопасный срез двустороннего confirm-flow без web-зависимости: в `EmailMergeService` добавлена state machine в metadata (`dual_transport`) с симметричными статусами для Telegram/MAX и подтверждением второго канала; добавлены тесты на оба направления и отклонение target-side | users/services/email_merge_service.py, tests/test_email_merge_transport_confirmation.py, IMPLEMENTATION_PLAN.md | Низкий риск: схема БД не менялась, merge данных не выполняется, обратная совместимость endpoint сохранена | `pytest -q tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py tests/test_email_claim_pipeline_services.py` | Выполнено |
| 2026-06-29 | Phase 2 dual Telegram/MAX confirmation (slice 2 transport-first) | Реализован transport-first шаг: Telegram inline-confirmation для инициатора и target-side callbacks, добавлен dispatcher второго канала в новой папке `bot/transports`, подтверждение по `merge_request_id` (без передачи длинных токенов в callback), MAX-доставка отмечена как deferred с сохранением web fallback | bot/handlers/identity_merge.py, bot/handlers/profile.py, bot/handlers/payments.py, bot/handlers/__init__.py, bot/keyboards/identity_merge_keyboard.py, bot/transports/__init__.py, bot/transports/identity_merge_dispatcher.py, users/services/email_merge_service.py, diary/services/user_profile_service.py, diary/services/payment_service.py, messages/messages_utils.py, tests/test_email_merge_transport_confirmation.py, IMPLEMENTATION_PLAN.md | Низкий риск: схема БД не менялась, merge данных не выполняется, web fallback сохранен, callback ограничен scope пользователя | `pytest -q tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py tests/test_email_claim_pipeline_services.py` | Выполнено |
| 2026-06-29 | Phase 2 dual Telegram/MAX confirmation (slice 3 MAX transport minimal) | Реализован минимальный MAX transport для outbound подтверждений: добавлены настройки/feature-flag MAX, создан `MaxClient` (`aiohttp`, Authorization header, user_id query, inline buttons payload), dispatcher переведен с deferred на реальную отправку в MAX при включенном флаге; добавлены unit/integration-like тесты dispatcher/client | core/settings.py, .env.example, bot/transports/max/__init__.py, bot/transports/max/client.py, bot/transports/identity_merge_dispatcher.py, tests/test_max_transport_dispatcher.py, IMPLEMENTATION_PLAN.md | Низкий риск: по умолчанию выключено (`MAX_TRANSPORT_ENABLED=false`), обратная совместимость сохранена, web fallback остается | `pytest -q tests/test_max_transport_dispatcher.py tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py tests/test_email_claim_pipeline_services.py` | Выполнено |
| 2026-06-29 | Phase 6 MAX webhook endpoint + mode default polling | Добавлен runtime endpoint `/api/max/webhook/` (GET health + POST callbacks), включена проверка webhook-секрета, реализована минимальная inbound-обработка `message_callback` для `merge_target:yes\|no:{id}`, добавлен конфиг `MAX_TRANSPORT_MODE` с дефолтом `polling` и `MAX_WEBHOOK_SECRET`, расширено тестовое покрытие API webhook | api/views.py, core/urls.py, core/settings.py, .env.example, tests/test_max_webhook_api.py, IMPLEMENTATION_PLAN.md | Низкий риск: endpoint идемпотентно игнорирует нерелевантные события; без секрета работает в dev-режиме, с секретом требует валидный header; destructive merge отсутствует | `pytest -q tests/test_max_webhook_api.py tests/test_max_transport_dispatcher.py tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py` | Выполнено |
| 2026-06-29 | Phase 6 MAX runtime coordinator + compose wiring | Добавлен MAX runtime coordinator для режимов `polling`/`webhook` (взаимоисключаемо), подключен фоновой запуск в `runbot`, реализована общая inbound-обработка `message_callback` для merge-target и переиспользована в webhook view, расширен `MaxClient` методами `/updates`, `register_webhook`, `close`, добавлены env-параметры polling/webhook и wiring в `docker-compose` | bot/main.py, bot/transports/max/client.py, bot/transports/max/inbound.py, bot/transports/max/runtime.py, bot/transports/max/__init__.py, api/views.py, core/settings.py, .env.example, docker-compose.yml, tests/test_max_inbound_processing.py, tests/test_max_runtime_coordinator.py, tests/test_max_transport_dispatcher.py, IMPLEMENTATION_PLAN.md | Низкий риск: runtime gated через `MAX_TRANSPORT_ENABLED`, polling ограничен обработкой `message_callback`, webhook и polling не запускаются одновременно | `pytest -q tests/test_max_transport_dispatcher.py tests/test_max_inbound_processing.py tests/test_max_runtime_coordinator.py tests/test_max_webhook_api.py tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py` (44 passed) | Выполнено |
| 2026-06-29 | Phase 6 MAX preflight + runtime monitoring metrics | Добавлены preflight-проверки MAX-конфига перед запуском coordinator (`MAX_BOT_TOKEN`, `MAX_API_BASE_URL`, таймауты, `MAX_WEBHOOK_URL` для webhook-mode) и runtime-метрики transport bucket (`max_runtime_preflight`, `max_runtime_polling_iteration`, `max_runtime_webhook_register`) через `monitoring_service`; расширены тесты coordinator на preflight fail/success и запись метрик | bot/transports/max/runtime.py, tests/test_max_runtime_coordinator.py, IMPLEMENTATION_PLAN.md | Низкий риск: при invalid конфигурации runtime безопасно не стартует и не делает сетевых вызовов; метрики in-memory и fail-safe | `pytest -q tests/test_max_runtime_coordinator.py tests/test_max_inbound_processing.py tests/test_max_webhook_api.py tests/test_max_transport_dispatcher.py tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py` (45 passed) | Выполнено |
| 2026-06-29 | Phase 6 MAX runtime diagnostics in Prometheus | Добавлены явные диагностические gauge-метрики MAX runtime в Prometheus (`psycho_diary_max_runtime_polling_lag_ms`, `psycho_diary_max_runtime_polling_last_updates_count`, `psycho_diary_max_runtime_webhook_register_outcome`), formatter агрегирует их из transport bucket, добавлено outcome metadata (`success/failure`) для webhook registration в runtime coordinator, покрыто unit+integration тестами | core/services/prometheus_formatter.py, bot/transports/max/runtime.py, tests/test_prometheus_formatter.py, tests/test_prometheus_metrics_api.py, tests/test_max_runtime_coordinator.py, IMPLEMENTATION_PLAN.md | Низкий риск: метрики read-only, backward-compatible; существующие метрики не удалялись | `pytest -q tests/test_prometheus_formatter.py tests/test_prometheus_metrics_api.py tests/test_max_runtime_coordinator.py` (32 passed) | Выполнено |
| 2026-06-29 | Phase 6 launch readiness for dedicated MAX bot | Подготовлен полный запускной контур выделенного MAX-бота: вынесены preflight helper-функции, добавлены management-команды `check_max_bot_config` и `runmaxbot`, добавлен отдельный compose-сервис `max_bot`, обновлена документация запуска/проверки в README, добавлены тесты preflight и management-команд | bot/transports/max/preflight.py, bot/transports/max/runtime.py, bot/transports/max/__init__.py, core/management/commands/check_max_bot_config.py, core/management/commands/runmaxbot.py, docker-compose.yml, README.txt, tests/test_max_preflight.py, tests/test_max_management_commands.py, tests/test_bot_main.py, IMPLEMENTATION_PLAN.md | Низкий риск: запуск MAX изолирован в отдельной команде/сервисе, preflight блокирует запуск при невалидном конфиге | `pytest -q tests/test_max_preflight.py tests/test_max_management_commands.py tests/test_max_runtime_coordinator.py tests/test_max_inbound_processing.py tests/test_max_webhook_api.py tests/test_max_transport_dispatcher.py tests/test_prometheus_formatter.py tests/test_prometheus_metrics_api.py tests/test_bot_main.py` (61 passed) | Выполнено |
| 2026-06-29 | Phase 2 callback-first merge confirmation | Переведен merge-confirm flow в callback-first режим: в `complete-registration` при конфликте возвращается `merge_request_id` + `confirmation_mode=transport_callbacks_primary` вместо web-token-first ответа; endpoint `/auth/confirm-email-merge/` оставлен как опциональный fallback за новым флагом `EMAIL_MERGE_WEB_CONFIRM_FALLBACK_ENABLED` | api/views.py, core/settings.py, .env.example, tests/test_auth_api.py, IMPLEMENTATION_PLAN.md | Низкий риск: основной контур подтверждения теперь Telegram/MAX callbacks; web fallback управляется feature flag и по умолчанию выключен | `pytest -q tests/test_auth_api.py tests/test_email_merge_transport_confirmation.py tests/test_max_webhook_api.py tests/test_email_claim_pipeline_services.py` (38 passed) | Выполнено |
| 2026-06-29 | Phase 2 verification and closure | Выполнена контрольная верификация полного покрытия Фазы 2 по policy/linking/confirm flow и каналам Telegram/MAX/Web; закрыт последний чекбокс фазы по explicit confirm + audit trail во всех каналах | IMPLEMENTATION_PLAN.md | Низкий риск: изменена только документация статуса на основе фактических прогонов | `pytest -q tests/test_identity_linking_service.py tests/test_identity_policy_service.py tests/test_email_merge_transport_confirmation.py tests/test_auth_api.py` (40 passed); `pytest -q tests/test_email_claim_pipeline_services.py tests/test_max_webhook_api.py tests/test_max_transport_dispatcher.py` (12 passed) | Выполнено |
| 2026-06-30 | Phase 3 handlers inventory kickoff | Выполнена инвентаризация Telegram handlers с ORM/доменной логикой и приоритизация для выноса (P0: diary/tasks, P1: admin/feedback/calendar, P2: start/payments контроль) | IMPLEMENTATION_PLAN.md | Низкий риск: изменена только документация и план работ без изменения runtime-поведения | `grep -RInE "objects\\.\|from[[:space:]]+.*\\.models[[:space:]]+import\|from[[:space:]]+users\\.models[[:space:]]+import\|from[[:space:]]+diary\\.models[[:space:]]+import" bot/handlers` | Выполнено |
| 2026-06-30 | Phase 3 first extraction slice (calendar) | В `calendar` handler убран прямой ORM-доступ к `User`; lookup переведен на `BaseService.get_user_by_telegram_id`, добавлен fail-safe ответ при отсутствии пользователя | bot/handlers/calendar.py, IMPLEMENTATION_PLAN.md | Низкий риск: поведение неизменно для валидного пользователя, для отсутствующего пользователя добавлен контролируемый graceful-fallback | `pytest -q tests/test_calendar.py tests/test_bot_main.py` (14 passed) | Выполнено |
| 2026-06-30 | Phase 3 second extraction slice (feedback/admin) | В `feedback` handler прямые обращения к `User`/`Feedback` переведены на сервисные вызовы (`BaseService`, `feedback_service`), в `admin` handler lookup администратора переведен на `BaseService`; добавлены fail-safe ветки на отсутствие пользователя | bot/handlers/feedback.py, bot/handlers/admin.py, IMPLEMENTATION_PLAN.md | Низкий риск: изменен только путь доступа к данным без изменения бизнес-ветвлений и UX-сценариев | `pytest -q tests/test_feedback_service.py tests/test_admin_service.py tests/test_bot_main.py` (57 passed) | Выполнено |
| 2026-06-30 | Phase 3 third extraction slice (tasks) | Добавлен сервисный метод `get_user_task_by_id` в task-management слой и переведены ключевые task-handlers с прямого ORM (`TherapyTask.objects.aget`) на сервисный lookup | diary/services/task_management_service.py, bot/handlers/tasks.py, IMPLEMENTATION_PLAN.md | Низкий риск: изменен только путь чтения задания; существующие user-facing ветки и сообщения ошибок сохранены | `pytest -q tests/test_task_handlers.py tests/test_task_states.py tests/test_task_display_service.py tests/test_bot_main.py` (46 passed) | Выполнено |
| 2026-06-30 | Phase 3 fourth extraction slice (diary) | В diary-service добавлены централизованные lookup-методы записи/состояния/анализа; diary-handler переведен с прямых ORM запросов на вызовы `diary_service` в сценариях комментариев, редактирования, удаления и full-day анализа | bot/services/diary_service.py, bot/handlers/diary.py, IMPLEMENTATION_PLAN.md | Низкий риск: изменен только путь доступа к данным, UX-сообщения/клавиатуры и основная бизнес-логика не изменялись | `pytest -q tests/test_diary_entry_use_case.py tests/test_diary_display_service.py tests/test_diary_presenter.py tests/test_bot_main.py tests/test_calendar.py` (59 passed) | Выполнено |
| 2026-06-30 | Phase 3 extraction quality gate (handlers) | Зафиксирован контрольный статус после extraction-срезов: в `bot/handlers` отсутствуют прямые ORM-вызовы (`.objects.*`), выполнен расширенный anti-regression прогон Telegram handler-наборов | IMPLEMENTATION_PLAN.md | Низкий риск: изменена только документация статуса качества и фактические результаты прогонов | `grep -RIn "\.objects\." bot/handlers`; `pytest -q tests/test_bot_main.py tests/test_calendar.py tests/test_help_handlers.py tests/test_help_simple.py tests/test_help_unit.py tests/test_task_handlers.py tests/test_task_states.py tests/test_task_display_service.py` (72 passed) | Выполнено |
| 2026-06-30 | Phase 3 fifth extraction slice (full-day analysis orchestration) | Вынесено бизнес-ветвление full-day analysis из `diary` handler в `DiaryDisplayService`: новый метод `build_full_day_analysis_view(...)`; handler `view_full_day_analysis` упрощен до transport orchestration; добавлены unit-тесты на сценарии not_found/no_analysis/success | diary/services/diary_display_service.py, bot/handlers/diary.py, tests/test_diary_display_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: user-facing тексты/кнопки сохранены, изменена только точка принятия решения | `pytest -q tests/test_diary_display_service.py tests/test_diary_entry_use_case.py tests/test_diary_presenter.py tests/test_bot_main.py` (56 passed) | Выполнено |
| 2026-06-30 | Phase 3 sixth extraction slice (day entries orchestration) | Вынесен общий сценарий отображения записей дня (`entries/empty`) из diary handler в `DiaryDisplayService.build_day_entries_view(...)`; handler-ветки edit/delete/cancel стали тоньше и переиспользуют единый payload | diary/services/diary_display_service.py, bot/handlers/diary.py, tests/test_diary_display_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: пользовательские тексты/кнопки сохранены; изменена только точка orchestration ветвлений | `pytest -q tests/test_diary_display_service.py tests/test_diary_entry_use_case.py tests/test_diary_presenter.py tests/test_bot_main.py tests/test_calendar.py` (64 passed) | Выполнено |
| 2026-06-30 | Phase 3 seventh extraction slice (delete-confirm orchestration) | Вынесен сценарий подтверждения удаления записи в `DiaryDisplayService.build_entry_delete_confirmation_view(...)`; handlers `entry_delete_confirm` и `request_delete_specific_entry` переведены на единый payload; устранено расхождение порядка аргументов helper-клавиатуры за счет централизации вызова | diary/services/diary_display_service.py, bot/handlers/diary.py, tests/test_diary_display_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: пользовательские тексты/кнопки сохранены, изменен только orchestration слой + устранен потенциальный баг с неверным порядком аргументов | `pytest -q tests/test_diary_display_service.py tests/test_diary_entry_use_case.py tests/test_diary_presenter.py tests/test_bot_main.py tests/test_calendar.py` (66 passed) | Выполнено |
| 2026-06-30 | Phase 3 eighth extraction slice (entry-edit use-case) | Бизнес-ветвление редактирования записи вынесено из handler в `DiaryService.process_entry_edit_use_case(...)`; `process_entry_edit` переведен на service response orchestration, добавлены unit-тесты use-case (success/update_failed/invalid_target_date) | bot/services/diary_service.py, bot/handlers/diary.py, tests/test_diary_entry_use_case.py, IMPLEMENTATION_PLAN.md | Низкий риск: изменен orchestration-слой, пользовательские тексты/кнопки и flow редактирования сохранены | `pytest -q tests/test_diary_entry_use_case.py tests/test_diary_display_service.py tests/test_diary_presenter.py tests/test_bot_main.py tests/test_calendar.py` (69 passed) | Выполнено |
| 2026-06-30 | Phase 3 final extraction slice (delete/cancel use-cases) | Финализирован вынос бизнес-ветвлений удаления: добавлены `process_delete_specific_entry_use_case(...)` и `process_cancel_delete_specific_entry_use_case(...)`; handlers `confirm_delete_specific_entry` и `cancel_delete_specific_entry` переведены на сервисный orchestration-контракт; добавлены unit-тесты на новые use-cases | bot/services/diary_service.py, bot/handlers/diary.py, tests/test_diary_entry_use_case.py, IMPLEMENTATION_PLAN.md | Низкий риск: user-facing сообщения/клавиатуры сохранены, изменена точка принятия решений и централизован orchestration | `/home/shlicha/psycho_diary/venv/bin/python -m pytest -q tests/test_diary_entry_use_case.py tests/test_diary_display_service.py tests/test_diary_presenter.py tests/test_bot_main.py tests/test_calendar.py` (75 passed) | Выполнено |
| 2026-06-30 | Phase 4 first contract slice (normalized I/O + send port) | Запущена Фаза 4: добавлены normalized transport-контракты и единый send port, реализован `UnifiedSendPort` (Telegram/MAX), `identity_merge_dispatcher` переведен на новый контрактный слой; тесты dispatcher/client/bootstrap адаптированы и зелены | bot/transports/contracts.py, bot/transports/send_port.py, bot/transports/unified_send_port.py, bot/transports/identity_merge_dispatcher.py, tests/test_max_transport_dispatcher.py, IMPLEMENTATION_PLAN.md | Низкий риск: сохранено существующее поведение доставки merge-confirm, изменен только transport orchestration слой | `/home/shlicha/psycho_diary/venv/bin/python -m pytest -q tests/test_max_transport_dispatcher.py tests/test_max_client_phase5.py tests/test_bot_main.py` (14 passed) | Выполнено |
| 2026-06-30 | Phase 4 second contract slice (Telegram integration path) | Завершено подключение Telegram к unified контрактам: `send_message_to_user(...)` переведен на `UnifiedSendPort` с normalized output и безопасным legacy fallback; добавлены reason-коды Telegram-ошибок в send port; добавлены unit-тесты нового send-path | bot/utils/message_utils.py, bot/transports/unified_send_port.py, tests/test_message_utils_transport_port.py, IMPLEMENTATION_PLAN.md | Низкий риск: сохранен fallback на legacy send для неподдержанных клавиатур/режимов, block/unblock логика сохранена | `/home/shlicha/psycho_diary/venv/bin/python -m pytest -q tests/test_message_utils_transport_port.py tests/test_max_transport_dispatcher.py tests/test_bot_main.py` (14 passed) | Выполнено |
| 2026-08-08 | Phase 3.12 diary domain leftovers cleanup | Вынесены schedule clarification и mapping ответов в diary_service; удалён `_process_analysis_result` с дублирующей доменной записью; comment daily-state update перенесён в сервис; handler clarification/comment переведены на presenter `build_entry_saved_view` | bot/services/diary_service.py, bot/handlers/diary.py, bot/presenters/diary_presenter.py, bot/presenters/__init__.py, tests/test_diary_entry_use_case.py, tests/test_diary_presenter.py, bot/handlers/docs/diary_handlers.md, IMPLEMENTATION_PLAN.md | Низкий риск: убрана повторная запись анализа после clarification (исправляет overwrite structured AI state); comment daily-state side-effect сохранён в сервисе | `pytest -q tests/test_diary_entry_use_case.py tests/test_diary_presenter.py tests/test_bot_main.py` (41 passed) | Выполнено |
| 2026-08-08 | Phase 3.13 onboarding + profile extraction | Завершение онбординга перенесено в `process_first_onboarding_entry_use_case`; profile edit/validate/cleanup list-полей вынесены в `UserProfileService` (`process_profile_field_update`, `prepare_list_field_for_edit`); handlers очищены от ORM/валидаторов | bot/services/diary_service.py, bot/handlers/onboarding.py, diary/services/user_profile_service.py, bot/handlers/profile.py, tests/test_diary_entry_use_case.py, tests/test_user_profile_field_use_case.py, IMPLEMENTATION_PLAN.md | Низкий риск: UX сохранён; исправлены ask-message keys для retry валидации (`ask_new_name`/`ask_new_dob`) | `pytest -q tests/test_diary_entry_use_case.py tests/test_user_profile_field_use_case.py tests/test_bot_main.py` (43 passed) | Выполнено |
| 2026-08-08 | Phase 3.14 tasks completion orchestration | Вынесены use-cases завершения задания и анализа/notification payload; экраны active/history задач переведены на view-builders; handlers tasks оставлены transport-first | diary/services/task_management_service.py, diary/services/task_display_service.py, bot/handlers/tasks.py, tests/test_task_completion_use_case.py, IMPLEMENTATION_PLAN.md | Низкий риск: поведение completion/skip/history сохранено, изменена точка orchestration | `pytest -q tests/test_task_completion_use_case.py tests/test_task_handlers.py tests/test_bot_main.py` (24 passed) | Выполнено |
| 2026-08-08 | Phase 3.15 payments/progress/feedback/full-day extraction | Вынесены view/use-case builders для payments, progress, admin-feedback list/reply и full-day reanalysis notification; handlers оставлены transport-first | diary/services/payment_service.py, diary/services/progress_service.py, diary/services/full_day_analysis_service.py, core/services/feedback_service.py, bot/handlers/payments.py, bot/handlers/progress.py, bot/handlers/feedback.py, bot/handlers/diary.py, tests/test_phase315_view_builders.py, IMPLEMENTATION_PLAN.md | Низкий риск: UX-сообщения/кнопки сохранены, изменена точка orchestration | `pytest -q tests/test_phase315_view_builders.py tests/test_bot_main.py` (25 passed) | Выполнено |
| 2026-08-08 | Phase 3.16 therapy/settings/start/onboarding | Вынесены welcome/recovery therapy views, settings task-limit/TZ views, onboarding start routing + first-entry result view | diary/services/therapy_chat_service.py, diary/services/settings_service.py, diary/services/onboarding_service.py, bot/handlers/therapy_chat_handlers.py, bot/handlers/settings.py, bot/handlers/start.py, bot/handlers/onboarding.py, tests/test_phase316_view_builders.py, IMPLEMENTATION_PLAN.md | Низкий риск: UX сохранён | `pytest -q tests/test_phase316_view_builders.py tests/test_bot_main.py` (17 passed) | Выполнено |
| 2026-08-08 | Phase 3.17 admin/profile builders | Admin stats report/bundle; profile/psychology/edit/deletion/referral view builders | core/services/admin_service.py, diary/services/user_profile_service.py, bot/handlers/admin.py, bot/handlers/profile.py, tests/test_phase317_view_builders.py, IMPLEMENTATION_PLAN.md | Низкий риск | `pytest -q tests/test_phase317_view_builders.py tests/test_bot_main.py` (15+ unit passed) | Выполнено |
| 2026-08-08 | Phase 3.18 diary/feedback leftovers | Diary outcome/comment/rating/delete-day/reanalysis use cases; feedback submit/reply/nav use cases | bot/presenters/diary_presenter.py, bot/services/diary_service.py, diary/services/diary_display_service.py, core/services/feedback_service.py, bot/handlers/diary.py, bot/handlers/feedback.py, tests/test_phase318_*.py, IMPLEMENTATION_PLAN.md | Низкий риск; reply persist после send | diary 53 passed; feedback suite 35 passed | Выполнено |
| 2026-08-08 | Phase 3.19 P2 polish | Tasks/payments/progress/calendar/identity_merge view builders | task_*/payment/progress/calendar/email_merge services + handlers, tests/test_phase319_view_builders.py, IMPLEMENTATION_PLAN.md | Низкий риск | `pytest … phase319 + 315 + task_completion + bot_main` (52 passed) | Выполнено |
| 2026-08-08 | Phase 3.20 quality gate transport-only | Подтверждён grep-гейт и полный unit-прогон волн 3.15–3.19; model imports только TYPE_CHECKING; Phase 3 Done | bot/handlers/*, IMPLEMENTATION_PLAN.md | Низкий риск: документация + cleanup imports | `pytest -q tests/test_phase315…319 + test_bot_main` (**79 passed**) | Выполнено |
| 2026-08-08 | Phase 3.21 hygiene sprint | Вычищены stale comments/unused imports; bare except → явный Exception+debug; нормализованы log prefixes в handlers | bot/handlers/diary.py, tasks.py, feedback.py, settings.py, profile.py, admin.py, diary/services/therapy_chat_service.py, IMPLEMENTATION_PLAN.md | Низкий риск: UX/поведение не менялись | `pytest -q tests/test_phase315…319 + test_bot_main` (**79 passed**); grep bare except/stale/objects → OK | Выполнено |
| 2026-08-08 | API Layer Phase A (user parity) | Создан `API_LAYER_PLAN.md` (фазы A–E); thin views поверх use cases: settings/onboarding/therapy/day-by-date; diary comment→use case + clarifications/edit/delete/rate; progress restore-streak availability; `api/service_bridge.py`; `/reminders/` через SettingsService | API_LAYER_PLAN.md, api/service_bridge.py, api/views_phase_a.py, api/views.py, api/urls.py, api/throttling.py, tests/test_phase_a_api.py, FRONTEND_API_REFERENCE.md, AI_INSTRUCTIONS.md | Низкий/средний: comment endpoint теперь с AI (parity с ботом) | `pytest -q tests/test_phase_a_api.py` (**10 passed**) | Выполнено |
| 2026-08-08 | API Layer Phase B (payments) | REST payments: products/create/email/list/detail/sync/webhook; PaymentService.list_products + confirm_payment_by_yookassa_id + payment_id в create; alias `/api/payments/webhook/` | diary/services/payment_service.py, api/views_payments.py, api/urls.py, core/urls.py, api/throttling.py, tests/test_phase_b_payments_api.py, API_LAYER_PLAN.md, FRONTEND_API_REFERENCE.md | Средний: webhook без JWT; sync/webhook идемпотентны; bot poller сохранён | `pytest -q tests/test_phase_b_payments_api.py` (**5 passed**) | Выполнено |
| 2026-08-08 | API Layer Phase C (voice) | Общий `process_voice_bytes` + `POST /api/v1/entries/voice/` (multipart) → SpeechKit/DeepSeek → `process_new_entry_use_case`; Telegram `process_voice_message` переведён на общий helper | bot/utils/audio_utils.py, api/views.py, tests/test_phase_c_voice_api.py, API_LAYER_PLAN.md, FRONTEND_API_REFERENCE.md | Низкий: bot path через тот же STT helper; AI через существующий use case | `pytest -q tests/test_phase_c_voice_api.py` (**5 passed**) | Выполнено |
| 2026-08-08 | API Layer Phase D (admin) | Admin REST: feedback list/detail/reply, Excel export, stats; `AdminDeveloperPermission` + throttle `admin_mutation` | api/views_admin.py, api/permissions.py, api/urls.py, api/throttling.py, tests/test_phase_d_admin_api.py, API_LAYER_PLAN.md, FRONTEND_API_REFERENCE.md | Средний: строгий admin gate; reply persist даже при fail notify | `pytest -q tests/test_phase_d_admin_api.py` (**4 passed**) | Выполнено |
| 2026-08-08 | API Layer Phase E (legacy align) | Tasks complete через use case + AI analysis; progress list через ProgressService; serialize_task_completion_analysis | api/views.py, api/serializers.py, api/service_bridge.py, tests/test_phase_e_api.py, FRONTEND_API_REFERENCE.md, API_LAYER_PLAN.md | Средний: breaking — complete без текстов → 400 | `pytest -q tests/test_phase_e_api.py` + smoke/progress (**5 passed**) | Выполнено |

---

## 10) Ключевые файлы для контроля внедрения

- users/models.py
- users/migrations/
- diary/services/user_service.py
- bot/middlewares/user_middleware.py
- bot/handlers/start.py
- bot/handlers/diary.py
- bot/handlers/feedback.py
- core/settings.py
- api/views.py
- api/urls.py
- docker-compose.yml
- .env.example
- tests/

---

## 11) Напоминание о принципе безопасных изменений

Любое изменение выполняется только после ответа на 4 вопроса:

1. Что может сломаться в существующем поведении?
2. Какие требования затрагиваются?
3. Как проверяем отсутствие потери данных?
4. Какие тесты подтверждают корректность?

Если хотя бы один пункт не закрыт, задача не переводится в "выполнено".
