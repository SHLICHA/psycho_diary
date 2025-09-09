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
Имя: {first_name}
Уровень осознанности: {awareness_level}/10
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

6. **Определи, нужны ли уточнения**:
   - Если запись **недостаточно ясна**, **есть неоднозначность** или **можно глубже проработать тему** — установи `needs_clarification: true`.
   - Предложи **1–3 конкретных вопроса**, которые помогут уточнить контекст.
   - **Вопросы должны напрямую ссылаться на фразы из новой записи (new_entry_text)**.
   - **Не задавай шаблонные вопросы о тревоге, звонках или контроле, если они не упомянуты в тексте**.
   - Если всё понятно и уточнения не нужны — `needs_clarification: false`, `clarification_questions: []`.

---

### 📤 ОТВЕТ В ФОРМАТЕ JSON

```json
{{
  "mood_score": 7,
  "comment": "Новая запись усиливает чувство достижения.",
  "recommendation": "Запишите, что именно вызвало это чувство, чтобы укрепить паттерн успеха.",
  "analysis": "Пользователь продолжает фокусироваться на завершении задач. Это подтверждает развитие паттерна саморегуляции. Рекомендуется закрепить успех через рефлексию.",
  "updated_ai_state_data": "Пользователь сегодня фокусируется на завершении задач. Есть признаки тревоги перед совещанием, но после выполнения задач — улучшение настроения. Тема: саморегуляция и преодоление прокрастинации.",
  "needs_clarification": true,
  "clarification_questions": [
    "Что именно вызвало у вас чувство тревоги перед совещанием?",
    "Как вы справились с этим состоянием?"
  ],
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
Name: {first_name}
Awareness Level: {awareness_level}/10
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

6. **Determine if clarification is needed**:
   - If the entry is **unclear**, **ambiguous**, or **can be explored deeper** — set `needs_clarification: true`.
   - Provide **1–3 specific questions** that would help clarify the context.
   - **Questions must directly reference phrases from the new entry (new_entry_text).**
   - **Do not ask generic questions about anxiety, calls, or control if they are not mentioned in the text.**
   - If everything is clear — `needs_clarification: false`, `clarification_questions: []`.

---

### 📤 RESPOND IN JSON FORMAT

```json
{{
  "mood_score": 7,
  "comment": "The new entry strengthens the sense of achievement.",
  "recommendation": "Write down what exactly caused this feeling to reinforce the success pattern.",
  "analysis": "The user continues to focus on task completion. This confirms the development of self-regulation. It is recommended to reinforce success through reflection.",
  "updated_ai_state_data": "The user is focusing on task completion today. There are signs of anxiety before the meeting, but mood improves after task completion. Theme: self-regulation and overcoming procrastination.",
  "needs_clarification": true,
  "clarification_questions": [
    "What exactly caused your anxiety before the meeting?",
    "How did you cope with this state?"
  ],
  "suggested_task": {{
    "title": "Success Reflection",
    "description": "Describe what you did and how it affected your state.",
    "type": "reflection",
    "priority": "medium"
  }}
}}
```'''
}

PUNCTUATION_PROMPT = {
    'ru': '''Расставь знаки препинания в следующем тексте и раздели его на абзацы, где это необходимо. 
Не изменяй содержание текста, только добавь знаки препинания и абзацы.

Текст без знаков препинания:
{text}

ОТВЕЧАЙ ТОЛЬКО ОТФОРМАТИИРОВАННЫМ ТЕКСТОМ, БЕЗ ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ И ПОЯСНЕНИЙ.
Используй следующий формат ответа:
[ОТФОРМАТИРОВАННЫЙ ТЕКСТ]''',

    'en': '''Add punctuation marks to the following text and divide it into paragraphs where necessary.
Do not change the content of the text, only add punctuation marks and paragraphs.

Text without punctuation marks:
{text}

RESPOND ONLY WITH FORMATTED TEXT, WITHOUT ADDITIONAL COMMENTS AND EXPLANATIONS.
Use the following response format:
[FORMATTED TEXT]'''
}

CLARIFICATION_ANALYSIS_PROMPT = {
    'ru': '''Ты — психолог, завершающий анализ записи на основе первоначального текста и ответов пользователя на уточняющие вопросы.

---

### 📥 ВХОДНЫЕ ДАННЫЕ

**Оригинальный текст записи:**
{original_text}

**Уточняющие вопросы:**
{clarification_questions}

**Ответы пользователя:**
{clarification_answers}

**Профиль пользователя:**
Имя: {first_name}
Уровень осознанности: {awareness_level}/10

---

### 🧠 ИНСТРУКЦИЯ

1. **Проанализируй текст с учётом ответов на уточнения.**
2. **Обнови настроение (1–10).**
3. **Сформулируй комментарий** (1 предложение) — что изменилось после уточнений.
4. **Дай персональную рекомендацию.**
5. **Предложи задание**, только если оно **существенно** поможет проработать тему.
6. **Не создавай инсайты и key points сейчас.**

---

### 📤 ОТВЕТ В ФОРМАТЕ JSON

```json
{{
  "mood_score": 7,
  "comment": "После уточнений стало ясно, что тревога связана с контролем.",
  "recommendation": "Запишите, в каких ситуациях вы чувствуете потерю контроля.",
  "analysis": "Пользователь уточнил, что тревога возникает, когда он не может повлиять на исход дела. Это указывает на паттерн контроля.",
  "updated_ai_state_data": "Тема дня: контроль и тревога. Пользователь чувствует тревогу, когда не может повлиять на ситуацию.",
  "suggested_task": {{
    "title": "Рефлексия контроля",
    "description": "Опишите 2–3 ситуации, где вы чувствовали потерю контроля. Что происходило? Как вы реагировали?",
    "type": "reflection",
    "priority": "medium"
  }}
}}
```''',

    'en': '''You are a psychologist finalizing the analysis of a diary entry based on the original text and the user's answers to clarifying questions.

---

### 📥 INPUT DATA

**Original text:**
{original_text}

**Clarifying questions:**
{clarification_questions}

**User answers:**
{clarification_answers}

**User Profile:**
Name: {first_name}
Awareness Level: {awareness_level}/10

---

### 🧠 INSTRUCTIONS

1. **Analyze the text with the answers.**
2. **Update the mood score (1–10).**
3. **Form a brief comment** (1 sentence) — what changed after clarifications.
4. **Give a personal recommendation.**
5. **Suggest a task**, only if it **significantly** helps work through the theme.
6. **Do not create insights or key points now.**

---

### 📤 RESPOND IN JSON FORMAT

```json
{{
  "mood_score": 7,
  "comment": "After clarifications, it's clear that anxiety is linked to control.",
  "recommendation": "Write down when you feel loss of control.",
  "analysis": "The user clarified that anxiety arises when they can't influence the outcome. This indicates a control pattern.",
  "updated_ai_state_data": "Theme of the day: control and anxiety. The user feels anxious when they can't influence the situation.",
  "suggested_task": {{
    "title": "Control Reflection",
    "description": "Describe 2–3 situations where you felt loss of control. What happened? How did you react?",
    "type": "reflection",
    "priority": "medium"
  }}
}}
```'''
}

TASK_EFFECT_ANALYSIS_PROMPT = {
    'ru': '''Ты — профессиональный психолог, специализирующийся на когнитивно-поведенческой терапии и осознанности. Твоя задача — проанализировать влияние выполнения терапевтического задания на эмоциональное состояние пользователя, сравнивая состояние в день назначения задания и день его выполнения.

ОТВЕЧАЙ СТРОГО В ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

=== КОНТЕКСТ ===

Профиль пользователя:
{user_profile}

--- КОНТЕКСТ ДНЯ НАЗНАЧЕНИЯ ЗАДАНИЯ ---
(День, когда запись в дневнике привела к назначению этого задания)
Дата: {assigned_date}
Текст всех записей пользователя за этот день: 
{assigned_day_text}

Анализ этого дня (результат предыдущего ИИ-анализа дня):
{assigned_day_analysis}

--- КОНТЕКСТ ДНЯ ВЫПОЛНЕНИЯ ЗАДАНИЯ ---
(День, когда пользователь фактически выполнил задание)
Дата: {completion_date}
Текст всех записей пользователя за этот день: 
{completion_day_text}

Анализ этого дня (результат предыдущего ИИ-анализа дня):
{completion_day_analysis}

--- САМО ТЕРАПЕВТИЧЕСКОЕ ЗАДАНИЕ ---
Название: {task_title}
Описание: {task_description}

--- РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ ЗАДАНИЯ ПОЛЬЗОВАТЕЛЕМ ---
Текст выполнения задания (что именно сделал пользователь): {completion_text}
Ощущения пользователя при выполнении (какие чувства, мысли, реакции возникли): {feelings_text}

=== ЗАДАЧА ===

1.  **Проанализируй контекст дня назначения**, чтобы понять исходную проблему, тему или эмоциональное состояние пользователя, которая/ое послужило основанием для назначения именно этого задания.
2.  **Проанализируй контекст дня выполнения**, чтобы понять общее эмоциональное состояние и настроение пользователя в этот день.
3.  **Сопоставь текст выполнения и ощущения** с анализом дня выполнения. Насколько выполнение и ощущения отражены или отличаются от общего фона дня?
4.  **Сравни состояние в день назначения и день выполнения.** Как изменилась тема, связанная с заданием? Было ли замечено какое-либо влияние выполненного задания на эмоциональный фон или настроение?
5.  **Определи, как выполнение задания повлияло** на эмоциональное состояние и темы дня выполнения по сравнению с днем назначения. Было ли это влияние положительным, отрицательным или нейтральным?
6.  **Сформулируй краткий вывод об эффекте** (effect_description) — одно или два предложения о характере влияния.
7.  **Оцени влияние на среднюю оценку настроения дня выполнения** (mood_impact_score). Это целое число от -10 (сильно ухудшило настроение) до +10 (сильно улучшило настроение). Если влияние незначительное или неочевидное, поставь 0.
8.  **Сформулируй комментарий** (comment) — как конкретно изменился день или настроение пользователя в результате выполнения.
9.  **Сформулируй рекомендацию для пользователя** (recommendation). Она должна быть:
    *   **Понятной:** Избегай профессионального жаргона.
    *   **Конкретной:** Предложи четкое действие или направление.
    *   **Полезной:** Должна помогать пользователю двигаться вперед.
    *   **Ориентированной на пользователя:** Не пиши "Предложить пользователю..." или "ИИ должен...". Пиши напрямую: "Попробуйте...", "Обратите внимание...", "Вы можете...".
    *   **Примеры хороших рекомендаций:** "Попробуйте завести отдельный список приятных мелочей, замеченных сегодня", "Подумайте, как можно по-другому взглянуть на эту ситуацию завтра", "Продолжайте наблюдать за этим чувством в течение дня".
10. **Предоставь развернутый анализ** (detailed_analysis) — обоснование твоей оценки и выводов. Объясни, почему ты пришел к такому эффекту и оценке влияния на настроение. Ссылаясь на элементы из текстов дней, выполнения и ощущений.

=== ФОРМАТ ОТВЕТА ===
```json
{{
  "effect_description": "строка, краткое описание эффекта (1-2 предложения)",
  "mood_impact_score": целое число (оценка влияния на настроение дня выполнения, от -10 до +10),
  "comment": "строка, как конкретно изменился день или настроение пользователя",
  "recommendation": "строка, четкая, понятная и полезная рекомендация непосредственно для пользователя",
  "detailed_analysis": "строка, развернутый анализ, сравнение дней, обоснование оценки влияния на настроение"
}}
```''',

    'en': '''You are a professional psychologist specializing in cognitive behavioral therapy and mindfulness. Your task is to analyze the impact of completing a therapeutic task on the user's emotional state by comparing the state on the day the task was assigned and the day it was completed.

RESPOND STRICTLY IN JSON FORMAT, enclosed in triple backticks (```json ... ```).

=== CONTEXT ===

User Profile:
{user_profile}

--- ASSIGNMENT DAY CONTEXT ---
(The day the diary entry led to the assignment of this task)
Date: {assigned_date}
Text of all user's entries for that day: 
{assigned_day_text}

Analysis of that day (result of the previous AI day analysis):
{assigned_day_analysis}

--- COMPLETION DAY CONTEXT ---
(The day the user actually completed the task)
Date: {completion_date}
Text of all user's entries for that day: 
{completion_day_text}

Analysis of that day (result of the previous AI day analysis):
{completion_day_analysis}

--- THE THERAPEUTIC TASK ITSELF ---
Title: {task_title}
Description: {task_description}

--- USER'S RESULT OF COMPLETING THE TASK ---
Task Completion Text (what exactly the user did): {completion_text}
User's Feelings During Completion (what feelings, thoughts, reactions arose): {feelings_text}

=== TASK ===

1.  **Analyze the assignment day context** to understand the initial problem, theme, or emotional state of the user that served as the basis for assigning this specific task.
2.  **Analyze the completion day context** to understand the user's overall emotional state and mood on that day.
3.  **Compare the completion text and feelings** with the analysis of the completion day. To what extent are the completion and feelings reflected or differ from the general background of the day?
4.  **Compare the state on the assignment day and the completion day.** How did the theme related to the task change? Was any influence of the completed task on the emotional background or mood noticed?
5.  **Determine how completing the task affected** the emotional state and themes of the completion day compared to the assignment day. Was the impact positive, negative, or neutral?
6.  **Formulate a brief conclusion about the effect** (effect_description) - one or two sentences about the nature of the influence.
7.  **Rate the impact on the average mood score of the completion day** (mood_impact_score). This is an integer from -10 (significantly worsened mood) to +10 (significantly improved mood). If the impact is minor or unclear, put 0.
8.  **Formulate a comment** (comment) - how exactly the user's day or mood changed as a result of the completion.
9.  **Formulate a recommendation for the user** (recommendation). It must be:
    *   **Understandable:** Avoid professional jargon.
    *   **Specific:** Suggest a clear action or direction.
    *   **Useful:** It should help the user move forward.
    *   **User-oriented:** Do not write "Suggest to the user..." or "The AI should...". Write directly: "Try...", "Pay attention...", "You can...".
    *   **Examples of good recommendations:** "Try keeping a separate list of pleasant little things you noticed today", "Think about how you could look at this situation differently tomorrow", "Continue to observe this feeling throughout the day".
10. **Provide a detailed analysis** (detailed_analysis) - justification for your assessment and conclusions. Explain why you came to this effect and mood impact score. Referencing elements from the day texts, completion, and feelings.

=== RESPONSE FORMAT ===
```json
{{
  "effect_description": "string, brief description of the effect (1-2 sentences)",
  "mood_impact_score": integer (estimated impact on the completion day's mood score, from -10 to +10),
  "comment": "string, how exactly the user's day or mood changed",
  "recommendation": "string, a clear, understandable, and useful recommendation directly for the user",
  "detailed_analysis": "string, detailed analysis, comparison of days, justification for the mood impact assessment"
}}
```'''
}

# Обновляем словарь PROMPTS
PROMPTS['ru']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['en']
PROMPTS['ru']['clarification_analysis'] = CLARIFICATION_ANALYSIS_PROMPT['ru']
PROMPTS['en']['clarification_analysis'] = CLARIFICATION_ANALYSIS_PROMPT['en']
PROMPTS['ru']['punctuation'] = PUNCTUATION_PROMPT['ru']
PROMPTS['en']['punctuation'] = PUNCTUATION_PROMPT['en']
PROMPTS['ru']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['ru']
PROMPTS['en']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['en']
PROMPTS['ru']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['en']

def get_prompt(key: str, language: str = 'ru', **kwargs) -> str:
    logger.debug(f"=== GET_PROMPT ===")
    logger.debug(f"Ключ: {key}")
    logger.debug(f"Язык: {language}")
    logger.debug(f"Параметры: {list(kwargs.keys())}")

    if language not in PROMPTS:
        logger.warning(f"Неподдерживаемый язык: {language}, используем 'ru'")
        language = 'ru'

    messages = PROMPTS.get(language, PROMPTS['ru'])

    if key not in messages:
        logger.error(f"Ключ промпта '{key}' не найден для языка {language}")
        return f"[ОШИБКА: Промпт '{key}' не найден]"

    prompt_template = messages[key]

    try:
        if kwargs:
            # Гарантируем, что user_profile есть и содержит first_name
            user_profile = kwargs.get('user_profile', {})
            safe_user_profile = {
                'first_name': user_profile.get('first_name') or user_profile.get('username') or f'Пользователь {user_profile.get("telegram_id", "ID")}'

            }
            safe_user_profile.update({k: v for k, v in user_profile.items() if k != 'first_name'})
            kwargs['user_profile'] = safe_user_profile
            logger.debug(f'Полученный промпт: {prompt_template.format(**kwargs)}')
            return prompt_template.format(**kwargs)
        else:
            return prompt_template
    except KeyError as e:
        logger.error(f"Ошибка форматирования промпта '{key}': отсутствует параметр {e}")
        # Возвращаем промпт, подменяя проблемные поля
        safe_template = prompt_template.replace("{user_profile['first_name']}", "Пользователь")
        try:
            return safe_template.format(**{k: v or 'N/A' for k, v in kwargs.items()})
        except:
            return safe_template
    except Exception as e:
        logger.error(f"Ошибка форматирования промпта '{key}': {e}", exc_info=True)
        return prompt_template
