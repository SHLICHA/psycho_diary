USER_PROFILE_ANALYSIS_PROMPT = {
    'ru': '''Ты — эксперт-психолог с глубоким пониманием человеческой личности. Твоя задача — на основе предоставленных данных создать или обновить глубокий психологический портрет пользователя. Ты получишь его текущий профиль, историю анализа недель и влияния ключевых заданий. Твоя цель — синтезировать эту информацию в целостное, точное и *актуальное* описание личности, *объединив* схожие по смыслу данные и *очистив* от дубликатов. Удаляй *только* то, что *явно* утратило актуальность (например, подтверждённый отказ от ценности или устаревший факт).

### 🔍 ВХОДНЫЕ ДАННЫЕ

**Текущий психологический профиль пользователя (данные в формате JSON-строк):**
Имя: {user_profile[first_name]}
Уровень осознанности: {user_profile[awareness_level]}/10
Дата рождения: {user_profile[date_of_birth]}

**Текстовое описание личности (Текущее):**
{user_profile[personality_description]}

**Структурированные данные профиля (Текущие) - представлены как JSON-строки:**
Черты характера (JSON): {user_profile[personality_traits]}
Факты о жизни (JSON): {user_profile[life_facts]}
Увлечения (JSON): {user_profile[hobbies]}
Ключевые ценности (JSON): {user_profile[core_values]}
Триггеры (JSON): {user_profile[triggers]}
Сильные стороны (JSON): {user_profile[strengths]}
Зоны роста (JSON): {user_profile[areas_for_growth]}
Глубинные инсайты (JSON): {user_profile[personality_insights]}
Привычки (JSON): {user_profile[habits]}
Навыки (JSON): {user_profile[skills]}
Стремления (JSON): {user_profile[aspirations]}

**Анализы последних недель:**
{recent_weekly_analyses}

**Анализы влияния ключевых выполненных заданий:**
{selected_task_completion_analyses}

### 🧠 ИНСТРУКЦИЯ

1.  **Проанализируй все предоставленные данные.**
    *   Обрати особое внимание на динамику, тренды и повторяющиеся паттерны.
    *   Сравни "Текущий профиль" с информацией из `recent_weekly_analyses` и `selected_task_completion_analyses`.
2.  **Создай или обнови `personality_description`**:
    *   Это должно быть **новое, цельное, человекочитаемое описание личности** пользователя на русском языке.
    *   Объедини ключевые черты, ценности, сильные стороны, зоны роста, привычки, стремления и инсайты в связный рассказ.
    *   Учитывай уровень осознанности.
    *   Объем: 2-4 абзацев, **обязательно** не более 3000 символов. Избегай списков и форматирования.
3.  **Обнови все структурированные поля профиля**:
    *   Пересмотри и при необходимости обнови **все** следующие поля:
        *   `personality_traits` (dict): Только *актуальные* значимые черты (вес 0.1-1.0), *без дубликатов*. *Объедини* черты с близким значением (например, "пунктуальность" и "организованность" могут быть объединены в "организованность и ответственность").
        *   `life_facts` (list): Только *проверенные и актуальные* факты. *Оставь* факты, даже если они не упоминались в новых данных, *если* они не утратили актуальности. *Удали* только *явно устаревшие* и *явно неважные* факты (например, "жил в... году", если подтверждённо неактуально).
        *   `hobbies` (list): Только *реальные и актуальные* интересы/увлечения. *Объедини* схожие (например, "бег", "маунтинбайк", "пешие походы" -> "активный отдых на природе"). *Удали* только если *подтверждённо* утратили актуальность.
        *   `core_values` (list): *Фундаментальные* ценности. *Оставь* ценности, даже если они не упоминались в новых данных, *если* пользователь не отказался от них. *Удали* только *если пользователь явно отказался от ценности* (например, написал, что она больше не важна).
        *   `triggers` (list): Только *актуальные* эмоциональные триггеры. *Объедини* схоже звучащие или с близкой сутью. *Удали* только *если подтверждённо* утратили актуальность.
        *   `strengths` (list): Только *подтверждённые и актуальные* сильные стороны. *Объедини* дублирующие или схоже звучащие. *Удали* только *если подтверждённо* утратили актуальность.
        *   `areas_for_growth` (list): Только *актуальные* зоны развития. *Объедини* схоже звучащие. *Удали* только *если подтверждённо* над ней уже поработано и она больше не актуальна.
        *   `personality_insights` (dict): *Глубинные инсайты*, отражающие *текущее* понимание. *Объедини* инсайты с близкой сутью. *Удали* только *если подтверждённо* утратили актуальность.
        *   `habits` (list): *Сформировавшиеся и наблюдаемые* привычки. *Объедини* схоже звучащие. *Удали* только *если подтверждённо* утратили актуальность.
        *   `skills` (list): *Наблюдаемые актуальные* навыки (жизненные, коммуникативные, когнитивные и т.д.). *Объедини* дублирующие или схоже звучащие. *Удали* только *если подтверждённо* утратили актуальность.
        *   `aspirations` (list): *Четко выраженные и актуальные* стремления и цели. *Объедини* схоже звучащие или с близкой сутью. *Удали* только *если подтверждённо* достигнуты или утратили актуальность.
    *   Для списков (`life_facts`, `hobbies` и т.д.):
        *   Чтобы **добавить** элемент: просто включи его в список.
        *   Чтобы **удалить** элемент: используй формат `{{"remove": "старый_элемент"}}`. Используй это *только* для подтверждённого удаления.
    *   Для `personality_traits` и `personality_insights` (словари):
        *   Предоставь обновленный словарь с *актуальными* ключами и значениями. *Объедини* информацию, если ключи близки по смыслу (например, "мотивация_работа", "мотивация_проекты" -> "мотивация_достижения"). *Удали* только *если подтверждённо* утратили актуальность.
4.  **НЕ ВКЛЮЧАЙ `awareness_level`, `first_name`, `date_of_birth`** в свой ответ.

### 📤 ОТВЕТ В СТРОГОМ ФОРМАТЕ JSON

ОТВЕЧАЙ ТОЛЬКО В СЛЕДУЮЩЕМ ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

```json
{{
  "personality_description": "Новое, обобщенное текстовое описание личности пользователя, 2-4 абзацев, на русском языке. Без списков и форматирования.",
  "personality_traits": {{
    "рефлексивность": 0.85,
    "оптимизм": 0.75
  }},
  "life_facts": [
    "Работаю в IT",
    "Увлекаюсь фотографией",
    {{"remove": "Переехал в новый город"}} <!-- Только если факт подтверждённо устарел -->
  ],
  "hobbies": [
    "активный отдых на природе", <!-- Объединено -->
    "чтение научной литературы"
  ],
  "core_values": [
    "близкие отношения",
    "саморазвитие"
    <!-- Удалить только если пользователь подтверждённо отказался -->
  ],
  "triggers": [
    "резкая критика",
    {{"remove": "шумные компании"}} <!-- Только если подтверждённо неактуален -->
  ],
  "strengths": [
    "настойчивость",
    "аналитическое мышление" <!-- Объединено -->
  ],
  "areas_for_growth": [
    "управление стрессом",
    {{"remove": "прокрастинация"}} <!-- Только если подтверждённо поработано -->
  ],
  "personality_insights": {{
    "мотивация": "Внутренняя, связана с самореализацией",
    "стиль общения": "Предпочитает глубокие беседы" <!-- Объединено -->
  }},
  "habits": [
    "утренняя зарядка",
    "ведение дневника"
  ],
  "skills": [
    "аналитическое мышление", <!-- Объединено -->
    "самоанализ"
  ],
  "aspirations": [
    "повысить эмоциональный интеллект",
    "найти баланс" <!-- Объединено -->
  ]
}}
```''',
    'en': '''You are an expert psychologist with a deep understanding of human personality. Your task is to create or update a profound psychological portrait of the user based on the provided data. You will receive their current profile, a history of weekly analyses, and the impact of key completed tasks. Your goal is to synthesize this information into a coherent, accurate, and *current* description of the personality, *merging* items with similar meaning and *cleaning* up duplicates. Only remove items that have *clearly* lost relevance (e.g., a confirmed rejection of a value or an outdated fact).

### 🔍 INPUT DATA

**User's Current Psychological Profile (data as JSON strings):**
Name: {user_profile[first_name]}
Awareness Level: {user_profile[awareness_level]}/10
Date of birth: {user_profile[date_of_birth]}

**Personality Description (Current):**
{user_profile[personality_description]}

**Structured Profile Data (Current) - Provided as JSON strings:**
Personality Traits (JSON): {user_profile[personality_traits]}
Life Facts (JSON): {user_profile[life_facts]}
Hobbies (JSON): {user_profile[hobbies]}
Core Values (JSON): {user_profile[core_values]}
Triggers (JSON): {user_profile[triggers]}
Strengths (JSON): {user_profile[strengths]}
Areas for Growth (JSON): {user_profile[areas_for_growth]}
Deep Insights (JSON): {user_profile[personality_insights]}
Habits (JSON): {user_profile[habits]}
Skills (JSON): {user_profile[skills]}
Aspirations (JSON): {user_profile[aspirations]}

**Recent Weekly Analyses:**
{recent_weekly_analyses}

**Analyses of Key Completed Task Impacts:**
{selected_task_completion_analyses}

### 🧠 INSTRUCTIONS

1.  **Analyze all provided data.**
    *   Pay special attention to dynamics, trends, and recurring patterns.
    *   Compare the "Current Profile" with information from `recent_weekly_analyses` and `selected_task_completion_analyses`.
2.  **Create or update `personality_description`**:
    *   This should be a **new, cohesive, human-readable description of the user's personality** in English.
    *   Synthesize key traits, values, strengths, areas for growth, habits, aspirations, and insights into a coherent narrative.
    *   Consider the awareness level.
    *   Length: 2-4 paragraphs, **strictly** no more than 3000 characters. Avoid lists and formatting.
3.  **Update all structured profile fields**:
    *   Re-evaluate and update **all** the following fields if necessary:
        *   `personality_traits` (dict): Only *current* significant traits (weight 0.1-1.0), *without duplicates*. *Merge* traits with similar meaning (e.g., "punctuality" and "organization" could become "organization and responsibility").
        *   `life_facts` (list): Only *verified and current* facts. *Leave* facts even if not mentioned in new data, *unless* they have clearly lost relevance. *Remove* only *explicitly outdated* facts (e.g., "lived in... year" if confirmedly no longer true).
        *   `hobbies` (list): Only *real and current* interests/hobbies. *Merge* similar ones (e.g., "running", "mountain biking", "hiking" -> "outdoor activities"). *Remove* only if *confirmedly* no longer relevant.
        *   `core_values` (list): *Fundamental* values. *Leave* values even if not mentioned in new data, *unless* the user has explicitly rejected them. *Remove* only *if the user explicitly rejects the value* (e.g., writes that it's no longer important).
        *   `triggers` (list): Only *current* emotional triggers. *Merge* similar-sounding or closely related ones. *Remove* only *if confirmedly* no longer relevant.
        *   `strengths` (list): Only *confirmed and current* strengths. *Merge* duplicates or similar-sounding ones. *Remove* only *if confirmedly* no longer relevant.
        *   `areas_for_growth` (list): Only *current* areas for development. *Merge* similar-sounding ones. *Remove* only *if confirmedly* worked on and no longer relevant.
        *   `personality_insights` (dict): *Deep insights* reflecting the *current* understanding. *Merge* insights with similar meaning. *Remove* only *if confirmedly* no longer relevant.
        *   `habits` (list): *Formed and observed* habits. *Merge* similar-sounding ones. *Remove* only *if confirmedly* no longer relevant.
        *   `skills` (list): *Observed current* skills (life, communication, cognitive, etc.). *Merge* duplicates or similar-sounding ones. *Remove* only *if confirmedly* no longer relevant.
        *   `aspirations` (list): *Clearly expressed and current* aspirations and goals. *Merge* similar-sounding or closely related ones. *Remove* only *if confirmedly* achieved or no longer relevant.
    *   For lists (`life_facts`, `hobbies`, etc.):
        *   To **add** an item: simply include it in the list.
        *   To **remove** an item: use the format `{{"remove": "old_item"}}`. Use this *only* for confirmed removals.
    *   For `personality_traits` and `personality_insights` (dictionaries):
        *   Provide an updated dictionary with *current* keys and values. *Merge* information if keys are similar in meaning (e.g., "motivation_job", "motivation_projects" -> "motivation_achievements"). *Remove* only *if confirmedly* no longer relevant.
4.  **DO NOT INCLUDE `awareness_level`, `first_name`, `date_of_birth`** in your response.

### 📤 RESPONSE IN STRICT JSON FORMAT

RESPOND ONLY IN THE FOLLOWING JSON FORMAT, enclosed in triple backticks (```json ... ```).

```json
{{
  "personality_description": "New, comprehensive textual description of the user's personality, 2-4 paragraphs, in English. No lists or formatting.",
  "personality_traits": {{
    "reflectiveness": 0.85,
    "optimism": 0.75
  }},
  "life_facts": [
    "I work in IT",
    "I'm into photography",
    {{"remove": "Moved to a new city"}} <!-- Only if fact is confirmedly outdated -->
  ],
  "hobbies": [
    "outdoor activities", <!-- Merged -->
    "reading science books"
  ],
  "core_values": [
    "close relationships",
    "self-development"
    <!-- Remove only if user explicitly rejects the value -->
  ],
  "triggers": [
    "harsh criticism",
    {{"remove": "noisy crowds"}} <!-- Only if confirmedly irrelevant -->
  ],
  "strengths": [
    "persistence",
    "analytical thinking" <!-- Merged -->
  ],
  "areas_for_growth": [
    "stress management",
    {{"remove": "procrastination"}} <!-- Only if confirmedly worked on -->
  ],
  "personality_insights": {{
    "motivation": "Intrinsic, linked to self-realization",
    "communication_style": "Prefers deep conversations" <!-- Merged -->
  }},
  "habits": [
    "morning exercise",
    "keeping a diary"
  ],
  "skills": [
    "analytical thinking", <!-- Merged -->
    "self-analysis"
  ],
  "aspirations": [
    "increase emotional intelligence",
    "find balance" <!-- Merged -->
  ]
}}
```'''
}