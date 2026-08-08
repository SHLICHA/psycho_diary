# API Layer Plan

Документ: полный план покрытия доменных сервисов REST API с единой бизнес-логикой для Web, Telegram и MAX.

Дата создания: 2026-08-08  
Статус: Phase A–C выполнены; D–E planned

---

## 1) Цель

- Один источник бизнес-правил: существующие use case / сервисы.
- Transport-слои (Web REST, Telegram, MAX) — тонкие адаптеры.
- Web API не дублирует ORM-ветвления и не содержит доменных правил.

```text
Client (Web) ──► api/views ──► *_use_case / *Service ──► domain
Bot (TG/MAX) ──► handlers  ──┘
```

---

## 2) Контракты слоя

### Thin view

1. Валидация входа (обязательные поля, типы).
2. `run_async(service.use_case(...))`.
3. Маппинг `ServiceResponse` / dict → JSON.
4. Ошибки только через `api_error_response` → `{"error":{"code","message","details?"}}`.

Эталон: `DiaryEntryViewSet.create_with_analysis` → `process_new_entry_use_case`.

### Transport strip

Из ответов сервисов **не** отдавать: `reply_markup`, `keyboard`, `set_state`, `clear_state`, `fsm_*`, `show_alert`, `use_main_menu_keyboard`.  
Вместо них: `mode`, `next`, доменные DTO (`entry`, `analysis`, `history`, …).

### Auth / throttle / OpenAPI

- JWT `IsAuthenticated` по умолчанию.
- Мутации — scoped throttle (`entry_mutation`, `settings_mutation`, …).
- Каждый endpoint: `@extend_schema` + секция в `FRONTEND_API_REFERENCE.md`.

### Helper

`api/service_bridge.py`: `run_async`, `from_service_response`, `strip_transport`, `ensure_tokens`.

---

## 3) Матрица покрытия

| Зона | Сервис | Endpoint(s) | Фаза | Статус |
|------|--------|-------------|------|--------|
| Auth / identity | auth_token, identity_policy, email_merge | `/auth/*` | — | done |
| Profile read/update | User / profile serializers | `/users/me`, `/profile/*` | — | done |
| Entry create+AI | diary_service | `POST /entries/create_with_analysis/` | — | done |
| Tasks CRUD/actions | TaskManagementService | `/tasks/*` | E (align) | partial |
| Progress summary | ProgressService / ORM | `/progress/*` | E (align) | done |
| Feedback create | FeedbackSerializer | `POST /feedback/` | — | done |
| Monitoring | monitoring_service, stats | `/monitoring/*` | — | done |
| Settings | SettingsService | `/settings/*`, alias `/reminders/` | A | done |
| Onboarding | OnboardingService, diary_service | `/onboarding/*` | A | done |
| Clarifications | diary_service | `POST /entries/{id}/clarifications/` | A | done |
| Comment+AI | diary_service | `POST /entries/{id}/comment/` | A | done |
| Edit+AI | diary_service | `POST /entries/{id}/edit-with-analysis/` | A | done |
| Delete entry | diary_service | `POST /entries/{id}/confirm-delete/` | A | done |
| Rate analysis | DiaryDisplayService | `POST /entries/{id}/rate/` | A | done |
| Day by date | diary_display / diary_service | `GET|DELETE /days/date/{date}/` | A | done |
| Day reanalyze | full_day + diary_service | `POST /days/date/{date}/reanalyze/` | A | done |
| Therapy chat | TherapyChatService | `/therapy-chat/*` | A | done |
| Streak availability | ProgressService | `GET /progress/restore-streak/availability/` | A | done |
| Payments / Premium | PaymentService | `/payments/*` | B | done |
| Voice entry | SpeechKit + DeepSeek + diary | `POST /entries/voice/` | C | done |
| Admin feedback reply | FeedbackService | `/admin/feedback/*` | D | done |
| DB export | database_export_service | `/admin/export/` | D | done |
| Admin stats | AdminService | `/admin/stats/` | D | done |
| Calendar admin | calendar_service | — | D | skipped (нет admin surface) |
| Tasks complete→use case | TaskManagementService | align `/tasks/{id}/complete/` | E | done |
| Progress via ProgressService | ProgressService | align `/progress/` | E | done |

---

## 4) Фазы

### Phase A — User parity (текущая)

Onboarding, settings, clarifications, comment/edit/delete AI-path, day delete/reanalyze/rating, therapy chat, streak availability.

### Phase B — Monetization

YooKassa create/status, Premium subscription, token packs, webhook confirmation. Только через `PaymentService`.

**Сделано:**
- `GET /payments/products/`, `POST /payments/create/`, `POST /payments/email/`
- `GET /payments/`, `GET /payments/<id>/`, `POST /payments/<id>/sync/`
- `POST /payments/webhook/` (+ alias `/api/payments/webhook/`)
- `PaymentService.list_products`, `confirm_payment_by_yookassa_id`, return `payment_id` при create

### Phase C — Voice / media

Upload audio → SpeechKit → DeepSeek punctuation → `process_new_entry_use_case` (тот же путь, что text create_with_analysis).

**Сделано:**
- `process_voice_bytes` в `bot/utils/audio_utils.py` (общий STT для bot + API)
- `POST /api/v1/entries/voice/` multipart (`audio`, `duration?`)

### Phase D — Admin / ops

Admin feedback list/reply, DB export, admin stats. Calendar admin helpers пропущены (нет отдельного admin API surface в сервисе).

**Сделано:**
- `GET /admin/feedback/`, `GET /admin/feedback/<id>/`, `POST /admin/feedback/<id>/reply/`
- `POST /admin/export/` (xlsx)
- `GET /admin/stats/`
- `AdminDeveloperPermission` (staff/superuser / privileged IDs / `DEVELOPER_CHAT_ID`)

### Phase E — Legacy alignment

- Tasks `complete` без текста → всегда use case.
- Progress stats через `ProgressService.get_user_progress_statistics`.
- Убрать оставшиеся ORM-shortcuts в views.

**Сделано:**
- `POST /tasks/<id>/complete/` → `complete_task_with_feelings_use_case` + AI-анализ (оба текста обязательны)
- `GET /progress/` → `get_user_progress_statistics` (+ legacy-поля)
- `restore_streak` / skip / restore → `run_async` вместо прямого `asyncio.run`

---

## 5) Тестирование и parity

Для каждого нового endpoint:

1. Unit/API-тест с mock use case (успех + error codes).
2. Не менять сигнатуры сервисов без нужды.
3. Parity-checklist: тот же use case, что вызывает bot handler.
4. Обновить `FRONTEND_API_REFERENCE.md` и журнал ниже.

---

## 6) Журнал срезов

| Дата | Срез | Результат |
|------|------|-----------|
| 2026-08-08 | Документ + Phase A kickoff | Создан план; реализация thin views поверх сервисов |
| 2026-08-08 | Phase A complete | Settings/Onboarding/Therapy/Day/Diary parity endpoints + tests (10 passed) |
| 2026-08-08 | Phase B monetization | Payments products/create/email/detail/sync/webhook; PaymentService confirm + payment_id; tests (5 passed) |
| 2026-08-08 | Phase C voice | `process_voice_bytes` + `POST /entries/voice/` → STT → `process_new_entry_use_case`; tests (5 passed) |
| 2026-08-08 | Phase D admin | feedback list/detail/reply, export xlsx, stats; `AdminDeveloperPermission`; tests (4 passed) |
| 2026-08-08 | Phase E legacy align | tasks complete → use case + analysis; progress → ProgressService; tests (3 passed) |
