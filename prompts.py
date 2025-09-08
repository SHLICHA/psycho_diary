"""Промты для взаимодействия с API DeepSeek."""

import logging
import json

logger = logging.getLogger(__name__)

PROMPTS = {
    'ru': {},
    'en': {}
}

TASK_EFFECT_ANALYSIS_PROMPT = {
    'ru': '''Проанализируй влияние выполнения терапевтического задания на эмоциональное состояние пользователя за день.
Ответь в формате JSON, строго придерживаясь структуры, заключенной в тройные обратные кавычки с указанием json (```json ... ```).

Контекст:
Профиль пользователя:
{user_profile}

Текст всех записей пользователя за день:
{day_text}

Средняя оценка настроения до выполнения задания: {avg_mood_before}/10

Ключевые моменты дня до выполнения задания:
{key_points_before}

Выполненное задание:
Название: {task_title}
Описание: {task_description}

Ответ пользователя на задание:
Выполнение: {completion_text}
Ощущения: {feelings_text}

Проанализируй, как выполнение задания повлияло на эмоциональное состояние, описанное в записях дня.
Сравни содержание записей, выполнение и ощущения.
Сформулируй краткий вывод об эффекте.
Оцени, на сколько баллов (целое число) это могло повлиять на среднюю оценку дня (может быть отрицательным).
Если влияние неочевидно или нейтрально, укажи это и поставь значение 0.

Пример структуры ответа:
```json
{{
  "effect_description": "Выполнение задания коррелирует с упоминанием позитивных событий и улучшением настроения.",
  "mood_impact_score": 2
}}
{{
  "effect_description": "строка, краткое описание эффекта (1-2 предложения)",
  "mood_impact_score": целое число (оценка влияния на настроение дня, может быть отрицательным)
}}
```''',

    'en': '''Analyze the impact of completing a therapeutic task on the user's emotional state for the day.
Respond in JSON format, strictly adhering to the structure enclosed in triple backticks (```json ... ```).

Context:
User Profile:
{user_profile}

Text of all user's entries for the day:
{day_text}

Average mood score before completing the task: {avg_mood_before}/10

Key points of the day before completing the task:
{key_points_before}

Completed Task:
Title: {task_title}
Description: {task_description}

User's response to the task:
Completion: {completion_text}
Feelings: {feelings_text}

Analyze how completing the task influenced the emotional state described in the day's entries.
Compare the content of the entries, the completion, and the feelings.
Formulate a brief conclusion about the effect.
Estimate by how many points (integer) this could have affected the average daily score (can be negative).
If the impact is unclear or neutral, state so and put a value of 0.

Example response structure:
```json
{{
  "effect_description": "Completing the task correlates with mentioning positive events and improved mood.",
  "mood_impact_score": 2
}}
{{
  "effect_description": "string, a brief description of the effect (1-2 sentences)",
  "mood_impact_score": integer (estimated impact on the day's mood score, can be negative)
}}
```'''
}

INCREMENTAL_DAY_ANALYSIS_PROMPT = {
    'ru': '''Ты — профессиональный психолог, ведущий инкрементальный анализ дневника пользователя. Твоя задача — **обогатить** состояние дня, а не переписать его с нуля.

---

### 📥 ВХОДНЫЕ ДАННЫЕ

**Все записи за день (в хронологическом порядке):**
{all_entries_combined}

**Новая запись (последняя):**
{new_entry_text}

**Текущее состояние дня (ai_state_data):**
{ai_state_data}

**Профиль пользователя:**
Имя: {user_profile['first_name']}
Уровень осознанности: {user_profile['awareness_level']}/10
Премиум: {'Да' if user_profile['is_premium'] else 'Нет'}
Количество записей: {user_profile['entries_count']}

---

### 🧠 ИНСТРУКЦИЯ

1. **Проанализируй новую запись в контексте дня**:
   - Как она подтверждает, опровергает или дополняет текущие темы?
   - Есть ли новые эмоции, события, мысли, триггеры?
   - Как изменилось настроение? Оцени от 1 до 10.

2. **Обнови состояние дня (ai_state_data)**:
   - Сохрани устойчивые темы.
   - Добавь новые значимые.
   - Удали устаревшие, если они больше не актуальны.
   - Сформулируй краткий, но содержательный контекст дня (3–4 предложения).

3. **Сформируй краткий комментарий** (1 предложение) — как новая запись повлияла на день.

4. **Дай персональную рекомендацию** (1–2 предложения) — что может быть полезно прямо сейчас.

5. **Предложи задание**, только если оно **существенно** поможет проработать тему (не чаще 1 раза в 2–3 дня).

6. **Не создавай инсайты и ключевые моменты сейчас**. Они будут выделены при финальном анализе.

---

### 📤 ОТВЕТ В ФОРМАТЕ JSON

```json
{{
  "mood_score": 7,
  "comment": "Новая запись усиливает чувство достижения.",
  "recommendation": "Запишите, что именно вызвало это чувство, чтобы укрепить паттерн успеха.",
  "analysis": "Пользователь продолжает фокусироваться на завершении задач. Это подтверждает развитие паттерна саморегуляции. Рекомендуется закрепить успех через рефлексию.",
  "updated_ai_state_data": "Пользователь сегодня фокусируется на завершении задач. Есть признаки тревоги перед совещанием, но после выполнения задач — улучшение настроения. Тема: саморегуляция и преодоление прокрастинации.",
  "suggested_task": {{
    "title": "Рефлексия успеха",
    "description": "Опишите, что именно вы сделали, и как это повлияло на ваше состояние.",
    "type": "reflection",
    "priority": "medium"
  }}
}}
```''',

    'en': '''You are a professional psychologist conducting an incremental analysis of the user's diary. Your task is to **enrich the day's state**, not rewrite it from scratch.

---

### 📥 INPUT DATA

**All entries for the day (chronologically):**
{all_entries_combined}

**New entry (latest):**
{new_entry_text}

**Current day state (ai_state_data):**
{ai_state_data}

**User Profile:**
Name: {user_profile['first_name']}
Awareness Level: {user_profile['awareness_level']}/10
Premium: {'Yes' if user_profile['is_premium'] else 'No'}
Entries Count: {user_profile['entries_count']}

---

### 🧠 INSTRUCTIONS

1. **Analyze the new entry in the context of the day**:
   - How does it confirm, contradict, or expand current themes?
   - Are there new emotions, events, thoughts, triggers?
   - How has the mood changed? Rate from 1 to 10.

2. **Update the day's state (ai_state_data)**:
   - Preserve stable themes.
   - Add new significant ones.
   - Remove outdated ones.
   - Formulate a concise, but meaningful day context (3–4 sentences).

3. **Form a brief comment** (1 sentence) — how the new entry affected the day.

4. **Give a personal recommendation** (1–2 sentences) — what would be helpful right now.

5. **Suggest a task** only if it **significantly** helps work through a theme (no more than once every 2–3 days).

6. **Do not create insights or key points now**. They will be extracted during the final analysis.

---

### 📤 RESPOND IN JSON FORMAT

```json
{{
  "mood_score": 7,
  "comment": "The new entry strengthens the sense of achievement.",
  "recommendation": "Write down what exactly caused this feeling to reinforce the success pattern.",
  "analysis": "The user continues to focus on task completion. This confirms the development of self-regulation. It is recommended to reinforce success through reflection.",
  "updated_ai_state_data": "The user is focusing on task completion today. There are signs of anxiety before the meeting, but mood improves after task completion. Theme: self-regulation and overcoming procrastination.",
  "suggested_task": {{
    "title": "Success Reflection",
    "description": "Describe what you did and how it affected your state.",
    "type": "reflection",
    "priority": "medium"
  }}
}}
```'''
}

# Добавляем в PROMPTS
PROMPTS['ru']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['ru']
PROMPTS['en']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['en']

PROMPTS['ru']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['en']

def get_prompt(key: str, language: str = 'ru', **kwargs) -> str:
    """
    Получение промпта по ключу и языку с подстановкой параметров.

    Args:
        key (str): Ключ промпта.
        language (str): Код языка ('ru', 'en'). По умолчанию 'ru'.
        **kwargs: Параметры для форматирования строки промпта.

    Returns:
        str: Отформатированная строка промпта или сообщение об ошибке.
    """
    logger.debug(f"=== GET_PROMPT ===")
    logger.debug(f"Ключ: {key}")
    logger.debug(f"Язык: {language}")
    logger.debug(f"Параметры: {list(kwargs.keys())}") # Логируем только ключи для краткости

    if language not in PROMPTS:
        logger.warning(f"Неподдерживаемый язык: {language}, используем 'ru'")
        language = 'ru'
    
    messages = PROMPTS.get(language, PROMPTS['ru'])
    
    if key not in messages:
        logger.error(f"Ключ промпта '{key}' не найден для языка {language}")
        return f"[ОШИБКА: Промпт '{key}' не найден]"
    
    prompt_template = messages.get(key)
    
    try:
        if kwargs:
            result = prompt_template.format(**kwargs)
            return result
        else:
            return prompt_template
    except KeyError as e:
        logger.error(f"Ошибка форматирования промпта '{key}': отсутствует параметр {e}")
        return prompt_template 
    except Exception as e:
        logger.error(f"Ошибка форматирования промпта '{key}': {e}", exc_info=True)
        return prompt_template
