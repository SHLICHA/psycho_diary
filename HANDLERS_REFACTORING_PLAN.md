# 📋 План выноса бизнес-логики из хендлеров в сервисы

> **Дата создания:** 2026-04-05  
> **Версия:** 1.0  
> **Статус:** ⏳ Ожидает утверждения  
> **Приоритет:** ЭТАП 2 (после критических исправлений)

---

## 🎯 Цель

Создать **универсальные сервисы**, которые работают и для бота, и для API.  
Хендлеры должны стать тонким слоем: receive event → call service → format response → send.

---

## 📊 Анализ текущего состояния

### Критические файлы (бизнес-логика в хендлерах):

| Файл | Строки | Уровень | Приоритет | Что вынести |
|------|--------|---------|-----------|-------------|
| **diary.py** | 1340 | 🔴 VERY HIGH | CRITICAL | Rating buttons, star display, pagination, analysis display |
| **tasks.py** | 816 | 🔴 VERY HIGH | CRITICAL | Analysis notification (126 строк), task history, mood impact |
| **feedback.py** | 700 | 🔴 VERY HIGH | CRITICAL | ВСЕ Feedback ORM запросы, photo handling, pagination |
| **admin.py** (broadcast) | 310 | 🔴 VERY HIGH | CRITICAL | get_admin_stats (85 строк), broadcast sending |
| **database_handlers.py** | 290 | 🟠 HIGH | HIGH | Excel export/import (200+ строк) |
| **calendar.py** | 200 | 🟠 HIGH | HIGH | Date arithmetic, direct user access, BUG: missing save |
| **profile.py** | 687 | 🟡 MEDIUM | HIGH | Utility functions, validation, balance formatting |
| **settings.py** | 529 | 🟡 MEDIUM | MEDIUM | Timezone branching, pytz validation |
| **start.py** | 120 | 🟡 MEDIUM | MEDIUM | Onboarding state branching |
| **onboarding.py** | 198 | 🟡 MEDIUM | MEDIUM | Completion marking, result formatting |

---

## 🗺️ План выноса (поэтапный, безопасный)

### ФАЗА 1: Создать НОВЫЕ сервисы (не ломая существующие)

#### 1.1. Создать `diary/services/diary_display_service.py`

**Что вынести из `diary.py`:**
- ✅ Rating keyboard construction (~15 строк)
- ✅ Star display calculation (~10 строк)
- ✅ Analysis result keyboard assembly (~40 строк)
- ✅ Entry pagination logic (~60 строк)
- ✅ Full day analysis display formatting (~90 строк)

**Новые методы:**
```python
class DiaryDisplayService:
    """Сервис для отображения записей дневника."""
    
    async def build_rating_keyboard(self, analysis_id: int, language: str) -> InlineKeyboardMarkup:
        """Создает клавиатуру с рейтингом для анализа."""
        
    async def format_mood_score_display(self, score: int, language: str) -> str:
        """Форматирует оценку настроения для отображения (звезды)."""
        
    async def build_analysis_result_keyboard(
        self, entry: DiaryEntry, analysis: PsychoAnalysis, language: str
    ) -> InlineKeyboardMarkup:
        """Создает клавиатуру для результата анализа."""
        
    async def get_entry_with_pagination(
        self, user: User, entry_id: int, direction: str
    ) -> dict:
        """Получает запись с информацией о пагинации."""
        
    async def format_daily_analysis_display(
        self, combined_entry: CombinedDiaryEntry, daily_analysis: DailyAnalysis, language: str
    ) -> str:
        """Форматирует полный анализ дня для отображения."""
```

**Задачи:**
- [ ] 1.1.1. Создать `diary/services/diary_display_service.py`
- [ ] 1.1.2. Перенести rating keyboard construction
- [ ] 1.1.3. Перенести star display calculation
- [ ] 1.1.4. Перенести pagination logic
- [ ] 1.1.5. Перенести analysis display formatting
- [ ] 1.1.6. Обновить handlers для использования сервиса
- [ ] 1.1.7. Написать тесты

**Приоритет:** 🔴 HIGH  
**Сложность:** Средняя  
**Риск:** Низкий (только вынос, без изменения логики)

---

#### 1.2. Создать `diary/services/feedback_service.py`

**Что вынести из `feedback.py`:**
- ✅ ВСЕ Feedback ORM запросы
- ✅ Photo handling logic
- ✅ Pagination logic
- ✅ Admin reply logic

**Новые методы:**
```python
class FeedbackService:
    """Сервис для работы с обратной связью."""
    
    async def create_feedback(
        self, user: User, message: str, is_voice: bool = False, 
        photo_file_id: str = None
    ) -> Feedback:
        """Создает обращение в поддержку."""
        
    async def get_unprocessed_feedbacks(self, limit: int = 20) -> List[Feedback]:
        """Получает необработанные обращения."""
        
    async def get_feedback_with_pagination(
        self, page: int, page_size: int = 1
    ) -> dict:
        """Получает обращения с пагинацией."""
        
    async def reply_to_feedback(self, feedback_id: int, admin_response: str) -> Feedback:
        """Отвечает на обращение."""
        
    async def process_feedback_photo(self, photo_file_id: str) -> str:
        """Обрабатывает фото из обращения (скачивает, валидирует)."""
```

**Задачи:**
- [ ] 1.2.1. Создать `diary/services/feedback_service.py`
- [ ] 1.2.2. Перенести Feedback ORM запросы
- [ ] 1.2.3. Перенести photo handling
- [ ] 1.2.4. Перенести pagination
- [ ] 1.2.5. Перенести admin reply logic
- [ ] 1.2.6. Обновить handlers
- [ ] 1.2.7. Написать тесты

**Приоритет:** 🔴 HIGH  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 1.3. Создать `core/services/admin_service.py`

**Что вынести из `admin.py` (broadcast_handlers.py):**
- ✅ `get_admin_stats` (85 строк!)
- ✅ `process_broadcast` logic
- ✅ `is_admin` check (убрать дублирование!)

**Новые методы:**
```python
class AdminService:
    """Сервис для административных операций."""
    
    def is_admin(self, telegram_id: int) -> bool:
        """Проверяет, является ли пользователь админом."""
        
    async def get_admin_stats(self) -> dict:
        """Получает полную статистику системы."""
        
    async def send_broadcast(
        self, message: str, media: dict = None, parse_mode: str = 'HTML'
    ) -> dict:
        """Отправляет массовую рассылку."""
```

**Задачи:**
- [ ] 1.3.1. Создать `core/services/admin_service.py`
- [ ] 1.3.2. Перенести `get_admin_stats`
- [ ] 1.3.3. Перенести `send_broadcast`
- [ ] 1.3.4. Убрать дублирование `is_admin` / `is_developer`
- [ ] 1.3.5. Обновить handlers
- [ ] 1.3.6. Написать тесты

**Приоритет:** 🔴 HIGH  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 1.4. Создать `diary/services/task_display_service.py`

**Что вынести из `tasks.py`:**
- ✅ `_run_analysis_and_notify_user` (126 строк!)
- ✅ `view_detailed_task_analysis` direct ORM
- ✅ `_format_task_history_detail` (34 строки)
- ✅ `show_task_history_main` list merging

**Новые методы:**
```python
class TaskDisplayService:
    """Сервис для отображения задач."""
    
    async def format_task_analysis_notification(
        self, user: User, task: TherapyTask, analysis: TaskCompletionAnalysis
    ) -> str:
        """Форматирует уведомление о результате анализа задания."""
        
    async def get_task_analysis_detail(
        self, user: User, task_id: int
    ) -> dict:
        """Получает детальный анализ задания."""
        
    async def format_task_history_detail(
        self, user: User, page: int, page_size: int = 5
    ) -> dict:
        """Форматирует историю заданий для отображения."""
        
    async def get_user_task_history(
        self, user: User
    ) -> List[dict]:
        """Получает полную историю заданий (completed + skipped)."""
```

**Задачи:**
- [ ] 1.4.1. Создать `diary/services/task_display_service.py`
- [ ] 1.4.2. Перенести `_run_analysis_and_notify_user`
- [ ] 1.4.3. Перенести `view_detailed_task_analysis`
- [ ] 1.4.4. Перенести `_format_task_history_detail`
- [ ] 1.4.5. Перенести `show_task_history_main`
- [ ] 1.4.6. Обновить handlers
- [ ] 1.4.7. Написать тесты

**Приоритет:** 🔴 HIGH  
**Сложность:** Средняя  
**Риск:** Низкий

---

#### 1.5. Создать `core/services/calendar_service.py`

**Что вынести из `calendar.py`:**
- ✅ Date arithmetic (prev/next month)
- ✅ Direct user model access
- ✅ **FIX BUG:** missing `user.save()` в `return_to_month`

**Новые методы:**
```python
class CalendarService:
    """Сервис для работы с календарем."""
    
    async def get_user_for_calendar(self, telegram_id: int) -> User:
        """Получает пользователя для календаря."""
        
    def calculate_adjacent_month(
        self, year: int, month: int, direction: str
    ) -> tuple:
        """Вычисляет предыдущий/следующий месяц."""
        
    async def update_user_calendar_position(
        self, user: User, year: int, month: int
    ) -> User:
        """Обновляет позицию календаря пользователя."""
        
    async def get_user_local_date(self, user: User) -> date:
        """Получает локальную дату пользователя."""
```

**Задачи:**
- [ ] 1.5.1. Создать `core/services/calendar_service.py`
- [ ] 1.5.2. Перенести date arithmetic
- [ ] 1.5.3. Перенести user model access
- [ ] 1.5.4. **FIX BUG:** добавить `user.save()` в `return_to_month`
- [ ] 1.5.5. Обновить handlers
- [ ] 1.5.6. Написать тесты

**Приоритет:** 🟠 MEDIUM  
**Сложность:** Низкая  
**Риск:** Низкий (+ FIX bug)

---

#### 1.6. Дополнить `diary/services/user_profile_service.py`

**Что вынести из `profile.py`:**
- ✅ `_filter_remove_items` (utility)
- ✅ `_format_list_for_display` (utility)
- ✅ `_validate_email` (validation)
- ✅ `_validate_date_of_birth` (validation)
- ✅ Balance info formatting

**Добавить методы:**
```python
# В существующий UserService или UserDisplayService

async def filter_removable_items(self, items: list) -> list:
    """Фильтрует элементы с меткой 'remove'."""
    
async def format_list_field_for_display(
    self, items: list, max_items: int = 10
) -> str:
    """Форматирует список для отображения."""
    
async def validate_and_update_profile_field(
    self, user: User, field_name: str, value: str
) -> dict:
    """Валидирует и обновляет поле профиля."""
```

**Задачи:**
- [ ] 1.6.1. Дополнить существующий `user_profile_service.py`
- [ ] 1.6.2. Перенести utility functions
- [ ] 1.6.3. Перенести validation
- [ ] 1.6.4. Обновить handlers
- [ ] 1.6.5. Написать тесты

**Приоритет:** 🟡 MEDIUM  
**Сложность:** Низкая  
**Риск:** Низкий

---

### ФАЗА 2: Рефакторинг существующих сервисов

#### 2.1. Унифицировать `is_admin` / `is_developer`

**Проблема:** Дублируется в 3 местах:
- `bot/handlers/feedback.py` (`is_developer`)
- `bot/handlers/database_handlers.py` (`is_developer`)
- `bot/handlers/admin.py` (`is_admin`)

**Решение:**
```python
# core/services/admin_service.py
class AdminService:
    def is_admin(self, telegram_id: int) -> bool:
        """Единая проверка прав администратора."""
        return str(telegram_id) == settings.DEVELOPER_CHAT_ID
```

**Задачи:**
- [ ] 2.1.1. Создать единый метод в `admin_service.py`
- [ ] 2.1.2. Обновить все imports в handlers
- [ ] 2.1.3. Удалить дубликаты
- [ ] 2.1.4. Написать тесты

---

#### 2.2. Унифицировать работу с БД

**Проблема:** Везде разные паттерны:
- `User.objects.aget(telegram_id=...)`
- `await User.objects.aget(...)`
- `@sync_to_async` обертки

**Решение:**
Создать базовый класс для сервисов:
```python
# core/services/base_service.py
class BaseService:
    """Базовый класс для всех сервисов."""
    
    @staticmethod
    async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
        """Единый метод получения пользователя."""
        try:
            return await User.objects.aget(telegram_id=telegram_id)
        except User.DoesNotExist:
            return None
```

**Задачи:**
- [ ] 2.2.1. Создать `core/services/base_service.py`
- [ ] 2.2.2. Добавить общие DB методы
- [ ] 2.2.3. Обновить все сервисы для наследования
- [ ] 2.2.4. Написать тесты

---

### ФАЗА 3: Подготовить сервисы для API

#### 3.1. Создать универсальные сервисы

Все созданные сервисы должны работать и для бота, и для API:

```
core/services/           # Универсальные сервисы
├── admin_service.py     # ← для бота + API admin
├── calendar_service.py  # ← для бота + API
├── base_service.py      # ← общие DB методы

diary/services/          # Сервисы дневника
├── diary_display_service.py  # ← для бота + API
├── task_display_service.py   # ← для бота + API
├── feedback_service.py       # ← для бота + API admin
└── user_profile_service.py   # ← для бота + API
```

**API будет использовать те же сервисы:**
```python
# api/views/diary_views.py
from diary.services.diary_display_service import DiaryDisplayService

class DiaryEntryViewSet(viewsets.ModelViewSet):
    async def list(self, request):
        entries = await diary_service.get_user_entries(request.user)
        return Response(entries)
```

---

## 📊 Метрики успеха

### До рефакторинга:
- ❌ `diary.py`: 1340 строк
- ❌ `tasks.py`: 816 строк
- ❌ `feedback.py`: 700 строк (0 в сервисах)
- ❌ `admin.py`: 310 строк (0 в сервисах)
- ❌ `database_handlers.py`: 290 строк (0 в сервисах)

### После рефакторинга:
- ✅ `diary.py`: <400 строк (handlers только routing)
- ✅ `tasks.py`: <300 строк
- ✅ `feedback.py`: <150 строк
- ✅ `admin.py`: <100 строк
- ✅ Новые сервисы: ~800 строк (тестируемые, переиспользуемые)

---

## ⚠️ Правила безопасного рефакторинга

1. **НЕ менять логику** - только переносить код
2. **Создать сервис → Написать тесты → Обновить handler → Удалить старый код**
3. **Каждый шаг - отдельный коммит**
4. **После каждого шага - запускать все тесты**
5. **Если тесты падают - откатывать и чинить**

---

## 🎯 Рекомендуемый порядок выполнения

### Неделя 1: Критические сервисы
1. ✅ `diary_display_service.py` (самый большой файл)
2. ✅ `task_display_service.py` (126 строк бизнес-логики)

### Неделя 2: Новые сервисы
3. ✅ `feedback_service.py` (0 сервисов сейчас)
4. ✅ `admin_service.py` (85 строк stats)

### Неделя 3: Завершение
5. ✅ `calendar_service.py` (+ fix bug)
6. ✅ Дополнить `user_profile_service.py`
7. ✅ Унифицировать `is_admin` / `is_developer`
8. ✅ Создать `base_service.py`

---

## 📝 История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-04-05 | 1.0 | Первоначальная версия плана |

---

## ✅ Статус выполнения

### ЗАВЕРШЕНО ✅

#### 1. diary_display_service.py ✅
- **Файл:** `diary/services/diary_display_service.py` (463 строки)
- **Тесты:** `tests/test_diary_display_service.py` (27 тестов)
- **Обновлено:** `bot/handlers/diary.py` (1340 → 1151 строк, -189 строк)
- **Что вынесено:**
  - build_rating_keyboard
  - build_add_comment_button
  - submit_rating
  - remove_rating_buttons_from_keyboard
  - format_mood_stars
  - get_entry_with_pagination
  - format_entry_for_display
  - format_full_day_analysis
  - build_entry_result_keyboard
- **Обновленные handlers:** rate_analysis, entry_prev, entry_next, view_full_day_analysis, _show_entry_page, _process_analysis_result, process_any_entry

#### 2. admin_service.py ✅
- **Файл:** `core/services/admin_service.py` (212 строк)
- **Тесты:** `tests/test_admin_service.py` (17 тестов)
- **Обновлено:** `bot/handlers/admin.py` (310 → 221 строк, -89 строк)
- **Что вынесено:**
  - is_admin
  - get_users_for_broadcast
  - send_broadcast_message
  - get_admin_stats (85 строк!)
- **Обновленные handlers:** broadcast_handler, process_broadcast, cmd_admin_stats

#### 3. Timezone fix (creator_timezone) ✅ — ИЗ OPTIMIZATION_PLAN.md
- **Миграции:** 0093 (schema) + 0094 (data, батчинг по 1000, +dependency на users/0006)
- **Модель:** `DiaryEntry.creator_timezone` — поле добавлено и заполнено
- **Свойства:** `entry_date`, `aentry_date`, `localized_created_at`, `alocalized_created_at` — все используют `creator_timezone`
- **Сервисы:** `diary_service.create_text_entry`, `diary_utils.attempt_restore_streak` — устанавливают TZ
- **CombinedDiaryEntry:** `localized_date_at()` — берёт TZ из первой DiaryEntry за день
- **Тесты:** `test_diary_models.py` (строки 524-715, 9 тестов — все проходят ✅)
- **Приоритет:** 🔥 КРИТИЧЕСКИЙ — ПОЛНОСТЬЮ ЗАВЕРШЕНО (включая исправление миграции 0094)

### В ОЖИДАНИИ ⏳

#### 3. feedback_service.py
- **Файл:** `bot/handlers/feedback.py` (700 строк)
- **Статус:** Не начато
- **Приоритет:** CRITICAL

#### 4. task_display_service.py
- **Файл:** `bot/handlers/tasks.py` (816 строк)
- **Статус:** Не начато
- **Приоритет:** CRITICAL

#### 5. calendar_service.py
- **Файл:** `bot/handlers/calendar.py` (200 строк)
- **Статус:** Не начато
- **Приоритет:** HIGH (+ FIX bug)

#### 6. user_profile_service.py дополнения
- **Файл:** `bot/handlers/profile.py` (687 строк)
- **Статус:** Не начато
- **Приоритет:** MEDIUM

---

## 📊 Итоговые метрики (на 2026-04-09)

### До рефакторинга:
- ❌ `diary.py`: 1340 строк
- ❌ `admin.py`: 310 строк
- ❌ Сервисы display/admin: 0
- ❌ Тесты для display/admin: 0

### После рефакторинга (сегодня):
- ✅ `diary.py`: 1151 строк (-189 строк)
- ✅ `admin.py`: 221 строка (-89 строк)
- ✅ `diary_display_service.py`: 463 строки
- ✅ `admin_service.py`: 212 строк
- ✅ Timezone fix: migrations 0093+0094, модель + сервисы + ~20 тестов
- ✅ Тесты: 74+ (57 diary + 17 admin + ~20 timezone)
- ✅ **Общая экономия из handlers:** -278 строк
- ✅ **Новых сервисов:** 675 строк (тестируемые, переиспользуемые)

### Следующие шаги:
1. feedback_service.py (700 строк → ~150 строк + 300 строк сервиса)
2. task_display_service.py (816 строк → ~300 строк + 300 строк сервиса)
3. calendar_service.py (200 строк + FIX bug)
