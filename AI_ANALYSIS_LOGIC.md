# 🧠 Полная логика AI-анализов Psycho Diary

> **Дата:** 2026-04-09
> **Версия:** 1.0
> **Назначение:** Документация всех AI-анализов для передачи специалисту

---

## 📋 Оглавление

1. [Архитектура AI-взаимодействия](#архитектура-ai-взаимодействия)
2. [Анализ #1: Инкрементальный анализ записи](#анализ-1-инкрементальный-анализ-записи)
3. [Анализ #2: Полный анализ дня](#анализ-2-полный-анализ-дня)
4. [Анализ #3: Анализ с уточняющими вопросами](#анализ-3-анализ-с-уточняющими-вопросами)
5. [Анализ #4: Анализ комментария пользователя](#анализ-4-анализ-комментария-пользователя)
6. [Анализ #5: Еженедельный анализ](#анализ-5-еженедельный-анализ)
7. [Анализ #6: Анализ психологического профиля](#анализ-6-анализ-психологического-профиля)
8. [Анализ #7: Анализ изменений профиля](#анализ-7-анализ-изменений-профиля)
9. [Анализ #8: Анализ эффекта задания](#анализ-8-анализ-эффекта-задания)
10. [Анализ #9: Терапевтический чат](#анализ-9-терапевтический-чат)
11. [Анализ #10: Утреннее напоминание](#анализ-10-утреннее-напоминание)
12. [Анализ #11: Напоминание о записи](#анализ-11-напоминание-о-записи)
13. [Анализ #12: Генерация подсказок](#анализ-12-генерация-подсказок)
14. [Вспомогательные AI-вызовы](#вспомогательные-ai-вызовы)
15. [Сводная таблица](#сводная-таблица)

---

## Архитектура AI-взаимодействия

### Модель и API
- **API:** DeepSeek API (`https://api.deepseek.com/v1/chat/completions`)
- **Модель:** `deepseek-chat`
- **Температура:** 0.3 (анализы), 0.1 (утилиты)
- **Max tokens:** 8100 (анализы), 5000 (пунктуация), 1000 (утилиты)
- **Таймаут:** 100 сек (анализы), 80 сек (пунктуация), 30 сек (утилиты)
- **Retry:** до 5 попыток с экспоненциальной задержкой

### Центральный сервис
Все AI-вызовы проходят через `bot/services/deepseek_api.py` → `DeepSeekAPIService.send_prompt_and_parse()`:
1. Отправляет POST-запрос с промптом
2. Парсит JSON из ответа (поддерживает markdown-блоки ```json ... ```)
3. Санитизирует HTML
4. Возвращает `{'success': bool, 'result': dict, 'raw_response': str, 'api_usage': dict}`

---

## Анализ #1: Инкрементальный анализ записи

**Когда срабатывает:** Каждая новая запись пользователя в дневник.
**Файл:** `bot/services/diary_service.py` → `process_new_entry_logic()`
**Промпты:**
- Premium: `incremental_day_analysis`
- Free: `incremental_day_analysis_lite`
- Первая запись новичка: `incremental_day_analysis_first_entry`

### Что отправляем

| Поле | Premium | Free | Первая запись |
|------|---------|------|---------------|
| Все записи за день (текст) | ✅ | ✅ | — |
| Новая запись | ✅ | ✅ | ✅ |
| Текущее состояние дня (ai_state_data) | ✅ | ✅ | — |
| Имя пользователя | ✅ | ✅ | ✅ |
| Уровень осознанности | ✅ | — | — |
| Кол-во записей | ✅ | — | — |
| Черты характера | ✅ | — | — |
| Факты о жизни | ✅ | ✅ | — |
| Увлечения | ✅ | — | — |
| Ценности | ✅ | — | — |
| Триггеры | ✅ | ✅ | — |
| Сильные стороны | ✅ | ✅ | — |
| Зоны роста | ✅ | — | — |
| Привычки, навыки, стремления | ✅ | — | — |
| Время создания записи (локальное) | ✅ | — | ✅ |

### Что получаем

```json
{
  "is_valid": true,
  "validation_comment": "",
  "formatted_message": "",
  "mood_score": 7,
  "comment": "поддерживающий комментарий 1-2 предложения",
  "recommendation": "персональная рекомендение",
  "analysis": "краткий анализ дня",
  "updated_ai_state_data": "обновлённое состояние дня",
  "needs_clarification": false,
  "clarification_questions": ["уточняющий вопрос?"],
  "suggested_task": {
    "title": "Название задания",
    "description": "Описание задания",
    "type": "mindfulness|reflection|etc",
    "priority": "low|medium|high"
  }
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `PsychoAnalysis` | mood_score, comment, recommendation, analysis_text, api_response |
| `CombinedDiaryEntry` | ai_state_data (обновляется), daily_mood_scores (дополняется) |
| `TherapyTask` | создаётся если есть suggested_task и лимит заданий не исчерпан |
| `DiaryEntry` | clarification_questions, clarification_answers (если needs_clarification) |

### Логика валидации

Запись **НЕВАЛИДНА** только если:
- Бессмысленный набор символов ("ыфва ыва", "12345", "......")
- Только эмодзи без текста
- Техническая ошибка ("test", "привет бот", "1", пустое сообщение)
- Нет никакой информации о внутреннем состоянии

Запись **ВАЛИДНА** даже если:
- Короткая ("Опять всё то же", "День прошёл как обычно")
- Негативная ("Ничего не хочу", "Всё плохо")
- Повторяющаяся (может быть важным паттерном)

---

## Анализ #2: Полный анализ дня

**Когда срабатывает:** Автоматически на следующий день (Celery, ежедневно в 00:01 UTC).
**Файл:** `diary/services/full_day_analysis_service.py`
**Промпты:**
- Premium: `full_day_analysis`
- Free: `full_day_analysis_lite`

### Что отправляем

| Поле | Premium | Free |
|------|---------|------|
| Профиль: имя | ✅ | ✅ |
| Профиль: уровень осознанности | ✅ | — |
| Профиль: is_premium | ✅ | — |
| Профиль: черты характера | ✅ | — |
| Профиль: факты о жизни | ✅ | ✅ |
| Профиль: увлечения | ✅ | — |
| Профиль: ценности | ✅ | — |
| Профиль: триггеры | ✅ | ✅ |
| Профиль: сильные стороны | ✅ | ✅ |
| Профиль: зоны роста | ✅ | — |
| Профиль: привычки | ✅ | — |
| Профиль: навыки | ✅ | — |
| Профиль: стремления | ✅ | — |
| Все записи за день (объединённый текст) | ✅ | ✅ |
| Анализы отдельных записей (mood, comment, recommendation, user_comment) | ✅ | ✅ |
| Оценки настроения за день (список) | ✅ | ✅ |
| Выполненные задания за день | ✅ | — |

### Что получаем

**Premium:**
```json
{
  "daily_analysis": {
    "mood_trend": "stable|improving|declining|volatile",
    "key_themes": [{"theme": "работа", "mentions": 3, "significance": 0.8}],
    "emotional_patterns": [{"emotion": "тревога", "frequency": 2, "context": "перед встречами"}],
    "insights": [{"text": "...", "category": "behavior", "significance": 0.9}],
    "recommendations": ["Попробуйте выделить 10 минут утром для планирования"],
    "overall_analysis_text": "связный анализ дня, 3-5 предложений"
  },
  "user_profile_updates": {
    "life_facts": ["новый факт"],
    "strengths": ["..."],
    "personality_traits": {"черта": 0.8},
    "triggers": [{"remove": "старый триггер"}]
  },
  "awareness_level_adjustment": {"new_level": 7, "reasoning": "..."}
}
```

**Free (сокращённый):**
```json
{
  "daily_analysis": {
    "mood_trend": "stable",
    "key_themes": [{"theme": "работа", "significance": 0.8}],
    "insights": [{"text": "...", "category": "behavior", "significance": 0.7}],
    "overall_analysis_text": "очень краткий анализ, 1-2 предложения"
  },
  "user_profile_updates": {"life_facts": [...], "strengths": []},
  "awareness_level_adjustment": {"new_level": 6, "reasoning": "..."}
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `DailyAnalysis` | mood_trend, key_themes, emotional_patterns, insights, recommendations, overall_analysis_text, api_response |
| `CombinedDiaryEntry` | is_analyzed = True |
| `User` | personality_traits, life_facts, hobbies, core_values, triggers, strengths, areas_for_growth (add/remove/merge) |
| `User` | awareness_level (если есть adjustment) |

---

## Анализ #3: Анализ с уточняющими вопросами

**Когда срабатывает:** Когда инкрементальный анализ вернул `needs_clarification: true`. Пользователь отвечает на уточняющие вопросы.
**Файл:** `bot/services/diary_service.py` → `process_clarification_answers_logic()`
**Также:** `diary/tasks/reminder_ask_questions.py` (принудительная обработка по таймеру)
**Промпт:** `clarification_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| Оригинальный текст записи | Исходный текст DiaryEntry |
| Уточняющие вопросы | Список вопросов, заданных ранее |
| Ответы пользователя | Ответы на каждый вопрос |
| Текущее состояние дня (ai_state_data) | Накопленный контекст дня |
| Полный профиль пользователя | Все поля профиля |

### Что получаем

```json
{
  "mood_score": 7,
  "comment": "поддерживающий комментарий с учётом ответов",
  "recommendation": "персонализированная рекомендация",
  "analysis": "детальный анализ",
  "updated_ai_state_data": "обновлённое состояние дня",
  "suggested_task": {"title": "...", "description": "...", "type": "...", "complexity": "low|medium|high"}
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `PsychoAnalysis` | mood_score, comment, recommendation, analysis_text (обновляются) |
| `CombinedDiaryEntry` | ai_state_data (обновляется) |
| `DiaryEntry` | clarification_questions, clarification_answers (сбрасываются), is_processed = True |
| `TherapyTask` | создаётся если есть suggested_task |

---

## Анализ #4: Анализ комментария пользователя

**Когда срабатывает:** Пользователь добавляет комментарий к уже проанализированной записи.
**Файл:** `bot/services/diary_service.py` → `process_user_comment_logic()`
**Промпт:** `comment_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| Оригинальный текст записи | Исходный текст DiaryEntry |
| Предыдущий анализ ИИ | comment, recommendation, analysis_text |
| Комментарий пользователя | Новый комментарий пользователя |
| Полный профиль пользователя | Все поля профиля |
| Уточнения (если были) | Вопросы и ответы |

### Что получаем

```json
{
  "mood_score": 7,
  "comment": "обновлённый комментарий",
  "recommendation": "обновлённая рекомендация",
  "analysis": "обновлённый анализ",
  "updated_ai_state_data": "обновлённое состояние дня",
  "suggested_task": {"title": "...", "description": "...", "type": "..."}
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `PsychoAnalysis` | mood_score, comment, recommendation, analysis_text (обновляются) |
| `CombinedDiaryEntry` | is_analyzed = False (сбрасывается для повторного анализа дня) |

---

## Анализ #5: Еженедельный анализ

**Когда срабатывает:** Каждый понедельник ~03:00 по часовому поясу пользователя (Celery).
**Файл:** `diary/services/weekly_analysis_service.py`
**Промпт:** `weekly_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Профиль пользователя** | Имя, уровень осознанности, дата рождения, черты характера, факты о жизни, увлечения, ценности, триггеры, сильные стороны, зоны роста |
| **Анализы дней недели** | Для каждого дня: date, mood_trend, key_themes, emotional_patterns, insights, overall_analysis_text, average_mood_score |
| **Статистика недели** | total_entries, streak_days_current, avg_mood_score, tasks_assigned, tasks_completed, unique_themes_count, unique_emotions_count, word_count_total |
| **Анализ предыдущей недели** | summary_text (если есть) |

### Что получаем

```json
{
  "summary_text": "краткое резюме недели, 2-3 предложения",
  "progress_insights": {
    "mood_trend": "stable|improving|declining|volatile",
    "key_insights": [{"text": "...", "significance": 0.8}],
    "notable_patterns": [{"pattern": "...", "frequency": 5}],
    "progress_notes": "1-2 предложения"
  },
  "awareness_level_adjustment": {"new_level": 7, "reasoning": "..."},
  "statistics": {...},
  "comparison_with_previous": {
    "previous_week_start": "2026-03-28",
    "mood_comparison": "...",
    "consistency_comparison": "...",
    "progress_comment": "..."
  }
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `WeeklyAnalysis` | summary_text, progress_insights, statistics, comparison_with_previous, api_response |
| `WeeklyAnalysis` | consolidated_user_profile → awareness_level (если есть adjustment) |

---

## Анализ #6: Анализ психологического профиля

**Когда срабатывается:** Сразу после еженедельного анализа (Celery, в цепочке).
**Файл:** `diary/services/user_profile_analysis_service.py`
**Промпт:** `user_profile_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Текущий профиль** | ВСЕ поля: awareness_level, date_of_birth, personality_description, personality_traits, life_facts, hobbies, core_values, triggers, strengths, areas_for_growth, personality_insights, habits, skills, aspirations (сериализованные в JSON-строки) |
| **Еженедельные анализы** | Последние 4 недели: summary_text, progress_insights, statistics, comparison_with_previous |
| **Анализы влияния заданий** | Топ-5 TaskCompletionAnalysis по mood_impact_score: effect_description, mood_impact_score, comment, recommendation, detailed_analysis |

### Что получаем

```json
{
  "personality_description": "цельное описание, 2-4 абзаца, до 3000 символов",
  "personality_traits": {"черта": 0.8, "другая_черта": 0.6},
  "life_facts": ["факт 1", "факт 2"],
  "hobbies": ["хобби 1"],
  "core_values": ["ценность 1"],
  "triggers": ["триггер 1"],
  "strengths": ["сильная сторона 1"],
  "areas_for_growth": ["зона роста 1"],
  "personality_insights": {"ключ": "значение"},
  "habits": ["привычка 1"],
  "skills": ["навык 1"],
  "aspirations": ["стремление 1"]
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `UserProfileHistory` | Снимок ВСЕХ полей профиля ДО обновления (создаётся перед обновлением) |
| `User` | ВСЕ поля профиля обновляются (merge + dedup + remove) |

---

## Анализ #7: Анализ изменений профиля

**Когда срабатывается:** После анализа профиля (Celery, в цепочке).
**Файл:** `diary/services/user_profile_change_analysis_service.py`
**Промпт:** `profile_change_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Текущий профиль** | ВСЕ поля профиля (после обновления) |
| **Исторические профили** | Последние N снимков UserProfileHistory (по умолчанию 3) |

### Что получаем

```json
{
  "summary": "краткое резюме изменений, 1-2 предложения",
  "key_changes": ["описание изменения 1", "описание изменения 2"],
  "stable_traits": ["описание стабильной черты 1"]
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `WeeklyAnalysis` | profile_changes_summary (JSON) |

---

## Анализ #8: Анализ эффекта задания

**Когда срабатывает:** Пользователь описывает выполнение терапевтического задания.
**Файл:** `diary/services/task_management_service.py` → `analyze_task_completion_effect()`
**Промпт:** `task_effect_analysis`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Профиль пользователя** | Имя, уровень осознанности, черты характера, факты о жизни, увлечения, ценности, триггеры, сильные стороны, зоны роста |
| **Контекст дня назначения** | Дата, текст CombinedDiaryEntry, анализ DailyAnalysis |
| **Контекст дня выполнения** | Дата, текст CombinedDiaryEntry, анализ DailyAnalysis |
| **Задание** | title, description, complexity |
| **Результат выполнения** | completion_text, feelings_text |

### Что получаем

```json
{
  "is_valid": true,
  "validation_comment": "",
  "effect_description": "1-2 предложения об эффекте задания",
  "mood_impact_score": 3,
  "comment": "поддерживающий комментарий об изменении состояния",
  "recommendation": "персонализированная рекомендия",
  "tokens_awarded": 2,
  "detailed_analysis": "обоснование оценки",
  "formatted_message": "<b>HTML</b> сообщение с эмодзи"
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `TaskCompletionAnalysis` | effect_description, mood_impact_score, comment, recommendation, detailed_analysis, tokens_awarded, api_response |
| `TokenTransaction` | tokens_awarded → user.token_balance |
| `TaskCompletionAnalysis` | Предыдущие анализы для того же задания → is_obsolete = True |
| `TherapyTask` | Если is_valid=false → status = 'pending', TaskCompletion удаляется |

---

## Анализ #9: Терапевтический чат

**Когда срабатывает:** Каждое сообщение пользователя в чате с ИИ-психологом.
**Файл:** `diary/services/therapy_chat_service.py`
**Промпт:** `therapy_chat`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Профиль пользователя** | first_name, awareness_level, is_premium, entries_count, personality_traits, life_facts, hobbies, core_values, triggers, strengths, areas_for_growth, habits, skills, aspirations |
| **История чата** | Последние 10 пар сообщений (role + content) |
| **Новое сообщение** | Текущее сообщение пользователя |

### Что получаем

```json
{
  "is_valid": true,
  "response_text": "<b>поддерживающий, эмпатичный ответ</b> с эмодзи"
}
```

### Что сохраняем

НЕ сохраняется в БД. Ответ отправляется напрямую пользователю в Telegram.

---

## Анализ #10: Утреннее напоминание

**Когда срабатывает:** Ежедневно (Celery, каждый час, проверяет локальное время пользователя).
**Файл:** `diary/tasks/morning_motivations.py`
**Промпт:** `morning_motivation`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Профиль пользователя** | Все поля |
| **Анализ предыдущего дня** | mood_trend, key_themes, emotional_patterns, insights, recommendations, average_mood_score (из DailyAnalysis + CombinedDiaryEntry) |
| **Изменения профиля** | profile_changes_summary из WeeklyAnalysis (если есть) |

### Что получаем

```json
{
  "motivation_message": "<b>короткое мотивирующее сообщение</b> с эмодзи, 2-5 предложений"
}
```

### Что сохраняем

НЕ сохраняется в БД. Отправляется напрямую пользователю.

---

## Анализ #11: Напоминание о записи

**Когда срабатывает:** Ежедневно в определённое время (Celery, каждый час, проверяет).
**Файл:** `diary/tasks/reminder_tasks.py`
**Промпт:** `reminder_message`

### Что отправляем

| Поле | Описание |
|------|----------|
| **Профиль пользователя** | Все поля |
| **Кол-во незавершённых заданий** | Число |
| **Текущая серия** | Дней подряд |
| **Максимальная серия** | Лучший результат |
| **Анализ вчерашнего дня** | mood_trend, key_themes, emotional_patterns, insights, recommendations |

### Что получаем

```json
{
  "motivation_message": "персонализированное напоминание с эмодзи"
}
```

### Что сохраняем

НЕ сохраняется в БД. Отправляется напрямую пользователю.

---

## Анализ #12: Генерация подсказок

**Когда срабатывает:** Когда у пользователя нет записей за день (Celery, для генерации подсказки).
**Файл:** `diary/services/smart_prompt_manager.py` → `_call_ai_prompt_generation()`
**Промпт:** `next_entry_prompt_generation`

### Что отправляем

| Поле | Описание |
|------|----------|
| Имя пользователя | first_name |
| Уровень осознанности | awareness_level/10 |
| Дней с последней записи | Число |
| Контекст анализа (опц.) | key_themes, mood_trend из DailyAnalysis |

### Что получаем

```json
{
  "prompt_text": "вдохновляющая подсказка, 1-2 предложения с эмодзи"
}
```

### Что сохраняем

| Модель | Поля |
|--------|------|
| `NextEntryPrompt` | prompt_text, target_date, is_used = False |

---

## Вспомогательные AI-вызовы

### Пунктуация

**Когда:** После распознавания голосовой записи (Yandex SpeechKit).
**Файл:** `bot/services/deepseek_api.py` → `punctuate_and_format_text()`
**Промпт:** `punctuation`

**Отправляем:** Сырой текст без знаков препинания.
**Получаем:** Текст с расставленными знаками препинания и абзацами.
**Параметры:** temperature=0.3, max_tokens=5000, retry=2, timeout=80сек

### Определение часового пояса

**Когда:** Пользователь вводит название города в настройках.
**Файл:** `bot/services/deepseek_api.py` → `detect_timezone_by_city()`
**Промпт:** `timezone_detection`

**Отправляем:** Название города.
**Получаем:** `{"success": true, "timezone": "Europe/Moscow", "city": "...", "country": "..."}`
**Параметры:** temperature=0.1, max_tokens=1000, retry=3, timeout=30сек

---

## Сводная таблица

| # | Анализ | Промпт | Триггер | Premium/Free | Контекст (размер) | Сохраняется |
|---|--------|--------|---------|--------------|-------------------|-------------|
| 1 | Инкрементальный анализ записи | `incremental_day_analysis` / `lite` / `first_entry` | Новая запись | ✅ Разные промпты | Средний | PsychoAnalysis, CombinedDiaryEntry, TherapyTask |
| 2 | Полный анализ дня | `full_day_analysis` / `lite` | Celery (следующий день) | ✅ Разные промпты | Большой | DailyAnalysis, User, CombinedDiaryEntry |
| 3 | Анализ с уточнениями | `clarification_analysis` | Ответы на вопросы | ❌ Одинаковый | Средний | PsychoAnalysis, CombinedDiaryEntry |
| 4 | Анализ комментария | `comment_analysis` | Комментарий к записи | ❌ Одинаковый | Средний | PsychoAnalysis, CombinedDiaryEntry |
| 5 | Еженедельный анализ | `weekly_analysis` | Celery (понедельник) | ❌ Одинаковый | **Очень большой** | WeeklyAnalysis |
| 6 | Анализ профиля | `user_profile_analysis` | После weekly analysis | ❌ Одинаковый | **Очень большой** | User, UserProfileHistory |
| 7 | Анализ изменений профиля | `profile_change_analysis` | После анализа профиля | ❌ Одинаковый | Большой | WeeklyAnalysis.profile_changes_summary |
| 8 | Анализ эффекта задания | `task_effect_analysis` | Выполнение задания | ❌ Одинаковый | Большой | TaskCompletionAnalysis, TokenTransaction |
| 9 | Терапевтический чат | `therapy_chat` | Сообщение в чате | ❌ Одинаковый | Средний (10 пар) | ❌ Не сохраняется |
| 10 | Утреннее напоминание | `morning_motivation` | Celery (утро) | ❌ Одинаковый | Средний | ❌ Не сохраняется |
| 11 | Напоминание о записи | `reminder_message` | Celery (напоминание) | ❌ Одинаковый | Средний | ❌ Не сохраняется |
| 12 | Генерация подсказок | `next_entry_prompt_generation` | Нет записей | ❌ Одинаковый | Малый | NextEntryPrompt |
| 13 | Пунктуация | `punctuation` | Голосовая запись | ❌ Одинаковый | Малый (текст) | ❌ Не сохраняется |
| 14 | Определение TZ | `timezone_detection` | Ввод города | ❌ Одинаковый | Минимальный | ❌ Не сохраняется |

---

## Цепочка Celery-анализов (понедельник)

```
schedule_weekly_analyses_task (каждый час)
  └── perform_weekly_analysis_for_user_task (если понедельник 03:00 по TZ пользователя)
       ├── 1. weekly_analysis_service.perform_weekly_analysis()
       │      └── Создаёт WeeklyAnalysis
       │
       ├── 2. user_profile_analysis_service.perform_user_profile_analysis()
       │      ├── Создаёт UserProfileHistory (снимок ДО)
       │      ├── Вызывает AI → обновляет User
       │      └── Обновляет awareness_level из WeeklyAnalysis
       │
       └── 3. perform_profile_change_analysis()
              ├── Сравнивает текущий профиль с историческими
              ├── Вызывает AI → анализ изменений
              └── Сохраняет в WeeklyAnalysis.profile_changes_summary
```

---

## Различия Premium / Free

### Инкрементальный анализ записи

| Аспект | Premium | Free |
|--------|---------|------|
| Профиль | 10+ полей | 3 поля (имя, факты, сильные стороны, триггеры) |
| Комментарий | Развёрнутый, 2+ предложения | Краткий, 1-2 предложения |
| Рекомендация | Персонализированная | Одна короткая |
| Анализ дня | Детальный | Одно предложение |
| Уточняющие вопросы | ✅ | ❌ |
| Задания | ✅ | ❌ |

### Полный анализ дня

| Аспект | Premium | Free |
|--------|---------|------|
| Профиль | ВСЕ поля | 4 поля |
| Выполненные задания | ✅ | ❌ |
| Emotional patterns | ✅ | ❌ |
| Recommendations | ✅ | ❌ |
| overall_analysis_text | 3-5 предложений | 1-2 предложения |
| Подсказка о подписке | ❌ | ✅ (опционально) |

---

## Схема данных: что ИИ знает о пользователе

### Полный профиль (Premium, полный анализ дня, профиль, чат)
```
{
  first_name,
  awareness_level,
  is_premium,
  entries_count,
  date_of_birth,
  personality_description,
  personality_traits: {trait: weight},
  life_facts: [...],
  hobbies: [...],
  core_values: [...],
  triggers: [...],
  strengths: [...],
  areas_for_growth: [...],
  personality_insights: {...},
  habits: [...],
  skills: [...],
  aspirations: [...]
}
```

### Сокращённый профиль (Free, инкрементальный)
```
{
  first_name,
  life_facts: [...],
  strengths: [...],
  triggers: [...]
}
```

---

## Обработка ошибок AI

Все AI-вызовы имеют retry-логику:

| Параметр | Значение |
|----------|----------|
| Макс. попыток | 5 (анализы), 2 (пунктуация), 3 (TZ) |
| Базовая задержка | 1.5 сек (анализы), 1.0 сек (пунктуация) |
| Экспонента | delay = base_delay × (attempt + 1) |
| Таймаут | 100 сек (анализы) |

Если все попытки исчерпаны:
- Возвращается `{'success': False, 'error': 'timeout|request_failed', ...}`
- Для инкрементального анализа: запись остаётся is_processed=False
- Для полного анализа дня: CombinedDiaryEntry остаётся is_analyzed=False
- Celery-задачи имеют max_retries=3 с повтором через 5 минут

---

> **Документ создан:** 2026-04-09
> **Актуален для:** ветки version2.0
