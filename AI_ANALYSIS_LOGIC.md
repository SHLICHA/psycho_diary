# AI Analysis Logic (actual)

> Дата обновления: 2026-04-19
> Ветка: version2.0
> Цель: единый актуальный справочник по всем AI-промптам с фокусом на:
> 1. Данные на входе
> 2. Данные на выходе
> 3. Краткое описание

---

## Общая схема

- Все шаблоны регистрируются в prompts/get_prompt.py.
- Фактический вызов LLM идет через bot/services/deepseek_api.py (send_prompt_and_parse).
- Ответы ожидаются в JSON (кроме punctuation), затем сохраняются/применяются сервисами.
- Основной актуальный вектор персонализации:
  - compressed_psych_profile_json
  - personal_fields_json (changed-format) для ряда анализов

---

## 1) incremental_day_analysis (premium)

Краткое описание:
- Инкрементальный анализ новой записи в течение дня для premium-пользователя.
- Выполняет валидацию записи, оценивает настроение, обновляет ai_state, может запросить уточнения и предложить задачу.

Данные на входе:
- all_entries_combined
- new_entry_text
- new_entry_creation_time_local
- ai_state_data
- first_name
- awareness_level
- entries_count
- user_personality_traits
- user_life_facts
- user_hobbies
- user_core_values
- user_triggers
- user_strengths
- user_areas_for_growth

Примечание по объему персональных полей:
- Для `user_personality_traits`, `user_triggers`, `user_strengths` используется top-20 (по приоритету: non-stale, weight desc, frequency desc).

Данные на выходе:
- is_valid
- validation_comment
- formatted_message
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data
- needs_clarification
- clarification_questions
- suggested_task

---

## 2) incremental_day_analysis_first_entry

Краткое описание:
- Специальный анализ первой записи новичка (онбординг).
- Без уточнений и без назначения задания.

Данные на входе:
- new_entry_text
- new_entry_creation_time_local
- first_name
- user_profile

Данные на выходе:
- is_valid
- validation_comment
- formatted_message
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data
- needs_clarification (ожидается false)
- clarification_questions (ожидается [])
- suggested_task (ожидается {})

---

## 3) incremental_day_analysis_lite (free, v1)

Краткое описание:
- Короткий инкрементальный анализ для free-пользователя.
- Без блока уточнений/задач в ответе контракта.

Данные на входе:
- all_entries_combined
- new_entry_text
- ai_state_data
- compressed_psych_profile_json

Данные на выходе:
- is_valid
- validation_comment
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data

---

## 4) incremental_day_analysis_lite_v2

Краткое описание:
- LITE v2 инкрементальный анализ с упором на экономию токенов.
- Использует compressed профиль + day context summary.

Данные на входе:
- user_plan
- first_name
- awareness_level
- entries_count
- compressed_psych_profile_json
- day_context_summary_json
- user_personality_traits (changed-format, weight/frequency)
- user_triggers (changed-format, weight/frequency)
- user_strengths (changed-format, weight/frequency)

Примечание по объему персональных полей:
- Для `user_personality_traits`, `user_triggers`, `user_strengths` используется top-10 (по приоритету: non-stale, weight desc, frequency desc).
- new_entry_text
- new_entry_creation_time_local
- ai_state_data

Данные на выходе:
- is_valid
- validation_comment
- formatted_message
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data (ожидается JSON-объект)
- needs_clarification
- clarification_questions
- suggested_task

---

## 5) clarification_analysis

Краткое описание:
- Дозавершение анализа записи после ответов на уточняющие вопросы.
- Обновляет тональность, mood_score и контекст дня.

Данные на входе:
- original_text
- clarification_questions
- clarification_answers
- ai_state_data
- compressed_psych_profile_json
- personal_fields_json

Данные на выходе:
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data
- suggested_task

---

## 6) comment_analysis

Краткое описание:
- Переанализ записи с учетом комментария пользователя к уже существующему разбору.
- Учитывает предыдущий AI-анализ и, при наличии, блок уточнений.

Данные на входе:
- original_text
- previous_comment
- previous_recommendation
- previous_analysis
- user_comment
- compressed_psych_profile_json
- personal_fields_json
- clarification_questions
- clarification_answers

Данные на выходе:
- mood_score
- comment
- recommendation
- analysis
- updated_ai_state_data
- suggested_task

---

## 7) full_day_analysis (premium)

Краткое описание:
- Полный суточный анализ aggregated дня.
- Может возвращать user_profile_updates и awareness_level_adjustment.

Данные на входе:
- compressed_psych_profile_json
- all_entries_combined_text
- entry_analyses
- daily_mood_scores
- completed_tasks

Данные на выходе:
- daily_analysis:
  - mood_trend
  - key_themes
  - emotional_patterns
  - insights
  - recommendations
  - overall_analysis_text
- user_profile_updates
- awareness_level_adjustment

---

## 8) full_day_analysis_lite (free, v1)

Краткое описание:
- Сокращенный суточный анализ для free.
- Меньше глубины, но совместимый JSON-каркас для downstream обработки.

Данные на входе:
- compressed_psych_profile_json
- all_entries_combined_text
- entry_analyses
- daily_mood_scores

Данные на выходе:
- daily_analysis (укороченный вариант)
- user_profile_updates (ограниченно)
- awareness_level_adjustment

---

## 9) full_day_analysis_lite_v2

Краткое описание:
- LITE v2 суточный анализ с compressed контекстом вместо полного набора данных.
- Ориентирован на экономию токенов.

Данные на входе:
- compressed_psych_profile_json
- day_context_summary_json
- compressed_entries_summary
- daily_mood_scores

Данные на выходе:
- daily_analysis:
  - mood_trend
  - key_themes
  - emotional_patterns
  - insights
  - recommendations
  - overall_analysis_text
- user_profile_updates
- awareness_level_adjustment

---

## 10) weekly_analysis

Краткое описание:
- Глубокий недельный анализ динамики и паттернов.
- Не должен возвращать user_profile_updates (по инструкции шаблона).

Данные на входе:
- compressed_psych_profile_json (premium: full compressed, free: lite compressed)
- week_statistics
- daily_analyses
- previous_weekly_analysis

Данные на выходе:
- summary_text
- progress_insights
- awareness_level_adjustment (опционально)
- statistics
- comparison_with_previous

---

## 11) user_profile_analysis

Краткое описание:
- Глубокое обновление психологического профиля пользователя на основе weekly-history.
- На вход получает полное текущее текстовое описание профиля и пишет новое полное описание, опираясь на старую версию и новые данные.
- Генерирует как текстовый профиль, так и структурированные поля, плюс compressed профиль.

Данные на входе:
- personality_description (полное текущее текстовое описание профиля)
- compressed_psych_profile_json
- personal_fields_json
- recent_weekly_analyses

Данные на выходе:
- personality_description (новое полное текстовое описание профиля)
- personality_traits
- life_facts
- hobbies
- core_values
- triggers
- strengths
- areas_for_growth
- personality_insights
- habits
- skills
- aspirations
- compressed_psych_profile

---

## 12) profile_change_analysis

Краткое описание:
- Анализ изменений профиля относительно исторических слепков.
- Обязательно опирается на полное текущее текстовое описание личности и сопоставляет его с полными текстовыми описаниями в исторических слепках.
- Краткий executive summary изменений и стабильных черт.

Данные на входе:
- current_personality_description (полное текущее текстовое описание личности)
- current_compressed_psych_profile_json
- current_personal_fields_json
- historical_snapshots_json
- num_snapshots

Данные на выходе:
- summary
- key_changes
- stable_traits

---

## 13) task_effect_analysis

Краткое описание:
- Анализ эффекта выполнения терапевтического задания между днем назначения и днем выполнения.
- Дополнительно валидирует адекватность отчета о выполнении.

Данные на входе:
- compressed_psych_profile_json
- personal_fields_json
- assigned_date
- assigned_day_text
- assigned_day_analysis
- completion_date
- completion_day_text
- completion_day_analysis
- task_title
- task_description
- task_complexity
- completion_text
- feelings_text

Данные на выходе:
- is_valid
- validation_comment
- effect_description
- mood_impact_score
- comment
- recommendation
- tokens_awarded
- detailed_analysis
- formatted_message

---

## 14) therapy_chat

Краткое описание:
- Ответ AI-психолога в интерактивном чате.
- Сервис хранит историю в памяти сессии, не в отдельной AI-модели БД анализа.

Данные на входе:
- compressed_psych_profile_json
- history
- user_message
- user_profile (safe-блок: first_name, awareness_level, is_premium, entries_count)

Данные на выходе:
- is_valid
- response_text

---

## 15) morning_motivation

Краткое описание:
- Генерация утреннего мотивационного сообщения.
- Использует вчерашний анализ и compressed профиль.

Данные на входе:
- compressed_psych_profile_json
- previous_day_analysis
- user_profile (сервис передает дополнительные поля, включая first_name и meta)
- profile_changed
- profile_change_summary

Данные на выходе:
- motivation_message

---

## 16) reminder_message

Краткое описание:
- Персонализированное напоминание сделать запись и завершать задания.

Данные на входе:
- compressed_psych_profile_json
- uncompleted_tasks_count
- current_streak
- longest_streak
- previous_day_analysis
- user_profile

Данные на выходе:
- motivation_message

---

## 17) next_entry_prompt_generation

Краткое описание:
- Генерация короткой подсказки для следующей записи дневника.

Данные на входе:
- first_name
- awareness_level
- days_since_last_entry
- analysis_context

Данные на выходе:
- prompt_text

---

## 18) punctuation

Краткое описание:
- Постобработка текста (обычно после STT): пунктуация + абзацы.
- Единственный prompt, где ожидается не JSON, а чистый текст.

Данные на входе:
- text

Данные на выходе:
- formatted text (строка)

---

## 19) timezone_detection

Краткое описание:
- Определение TZ по названию города.
- Поддержка single result / multiple options / not found.

Данные на входе:
- city_name

Данные на выходе:
- success
- timezone, city, country (single)
- multiple + options[] (multiple matches)
- error (not found)

---

## Что реально сохраняется после AI-вызовов (кратко)

- incremental / clarification / comment:
  - PsychoAnalysis
  - CombinedDiaryEntry.ai_state_data и daily_mood_scores
  - иногда TherapyTask
- full_day_*:
  - DailyAnalysis
  - обновления профиля User (через user_profile_updates)
  - awareness_level (при наличии adjustment)
- weekly_analysis:
  - WeeklyAnalysis (summary/progress/statistics/comparison/api_response)
- user_profile_analysis:
  - UserProfileHistory (снапшот до обновления)
  - User (поля профиля + compressed_psych_profile)
- profile_change_analysis:
  - WeeklyAnalysis.profile_changes_summary
- task_effect_analysis:
  - TaskCompletionAnalysis
  - TokenTransaction (если tokens_awarded > 0)
- morning_motivation / reminder_message / therapy_chat / punctuation / timezone_detection / next_entry_prompt_generation:
  - зависят от сценария, обычно возвращают текст/данные для отправки пользователю
  - next_entry_prompt_generation дополнительно сохраняется в NextEntryPrompt

---

## Важное текущее замечание

- Основные анализы уже приведены к unified-контракту персонализации через compressed_psych_profile_json и personal_fields_json.
- Есть legacy-ветка принудительной обработки уточнений в diary/tasks/reminder_ask_questions.py, где clarification_analysis вызывается со старым user_profile. Это не блокирует выполнение (из-за fallback в get_prompt), но технически не идеально и требует доунификации.
