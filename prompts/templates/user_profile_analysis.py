USER_PROFILE_ANALYSIS_PROMPT = {
    'ru': '''Ты — эксперт-психолог с глубоким пониманием человеческой личности. Твоя задача — на основе предоставленных данных создать или обновить глубокий психологический портрет пользователя. Ты получишь его текущий профиль, историю анализа недель и влияния ключевых заданий. Твоя цель — синтезировать эту информацию в целостное и точное описание личности.

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
    **   Объем: 3-5 абзацев, **обязательно** не более 4000 символов. Избегай списков и форматирования.
3.  **Обнови все структурированные поля профиля**:
    *   Пересмотри и при необходимости обнови **все** следующие поля:
        *   `personality_traits` (dict): Только значимые черты (вес 0.1-1.0).
        *   `life_facts` (list): Только проверенные и актуальные факты.
        *   `hobbies` (list): Только реальные интересы/увлечения.
        *   `core_values` (list): Фундаментальные ценности.
        *   `triggers` (list): Только актуальные эмоциональные триггеры.
        *   `strengths` (list): Только подтвержденные сильные стороны.
        *   `areas_for_growth` (list): Только актуальные зоны развития.
        *   `personality_insights` (dict): Глубинные инсайты (например, {{"коммуникация": "предпочитает письменную форме устной", "мотивация": "..."}}).
        *   `habits` (list): Сформировавшиеся и наблюдаемые привычки.
        *   `skills` (list): Наблюдаемые навыки (жизненные, коммуникативные, когнитивные и т.д.).
        *   `aspirations` (list): Четко выраженные стремления и цели.
    *   Для списков (`life_facts`, `hobbies` и т.д.):
        *   Чтобы **добавить** элемент: просто включи его в список.
        *   Чтобы **удалить** элемент: используй формат `{{"remove": "старый_факт"}}`.
    *   Для `personality_traits` и `personality_insights` (словари):
        *   Предоставь обновленный словарь с актуальными ключами и значениями.
4.  **НЕ ВКЛЮЧАЙ `awareness_level`, `first_name`, `date_of_birth`** в свой ответ.

### 📤 ОТВЕТ В СТРОГОМ ФОРМАТЕ JSON

ОТВЕЧАЙ ТОЛЬКО В СЛЕДУЮЩЕМ ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

```json
{{
  "personality_description": "Новое, обобщенное текстовое описание личности пользователя, 3-5 абзацев, на русском языке. Без списков и форматирования.",
  "personality_traits": {{
    "рефлексивность": 0.85,
    "оптимизм": 0.75
  }},
  "life_facts": [
    "Работаю в IT",
    "Увлекаюсь фотографией",
    {{"remove": "Переехал в новый город"}}
  ],
  "hobbies": [
    "спорт",
    {{"remove": "чтение художественной литературы"}}
  ],
  "core_values": [
    "здоровье",
    "саморазвитие"
  ],
  "triggers": [
    "критика",
    {{"remove": "шумные компании"}}
  ],
  "strengths": [
    "настойчивость",
    "аналитичность"
  ],
  "areas_for_growth": [
    "управление стрессом",
    {{"remove": "прокрастинация"}}
  ],
  "personality_insights": {{
    "мотивация": "Внутренняя, связана с самореализацией",
    "стиль общения": "Предпочитает глубокие беседы"
  }},
  "habits": [
    "утренняя зарядка",
    "ведение дневника"
  ],
  "skills": [
    "аналитическое мышление",
    "самоанализ"
  ],
  "aspirations": [
    "повысить эмоциональный интеллект",
    "найти баланс работы и личной жизни"
  ]
}}
```''',
    'en': '''You are an expert psychologist with a deep understanding of human personality. Your task is to create or update a profound psychological portrait of the user based on the provided data. You will receive their current profile, a history of weekly analyses, and the impact of key completed tasks. Your goal is to synthesize this information into a coherent and accurate description of the personality.

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
    *   Length: 3-5 paragraphs, **strictly** no more than 4000 characters. Avoid lists and formatting.
3.  **Update all structured profile fields**:
    *   Re-evaluate and update **all** the following fields if necessary:
        *   `personality_traits` (dict): Only significant traits (weight 0.1-1.0).
        *   `life_facts` (list): Only verified and current facts.
        *   `hobbies` (list): Only real interests/hobbies.
        *   `core_values` (list): Fundamental values.
        *   `triggers` (list): Only current emotional triggers.
        *   `strengths` (list): Only confirmed strengths.
        *   `areas_for_growth` (list): Only current areas for development.
        *   `personality_insights` (dict): Deep insights (e.g., {{"communication": "prefers written over verbal", "motivation": "..."}}).
        *   `habits` (list): Formed and observed habits.
        *   `skills` (list): Observed skills (life, communication, cognitive, etc.).
        *   `aspirations` (list): Clearly expressed aspirations and goals.
    *   For lists (`life_facts`, `hobbies`, etc.):
        *   To **add** an item: simply include it in the list.
        *   To **remove** an item: use the format `{{"remove": "old_fact"}}`.
    *   For `personality_traits` and `personality_insights` (dictionaries):
        *   Provide an updated dictionary with current keys and values.
4.  **DO NOT INCLUDE `awareness_level`, `first_name`, `date_of_birth`** in your response.

### 📤 RESPONSE IN STRICT JSON FORMAT

RESPOND ONLY IN THE FOLLOWING JSON FORMAT, enclosed in triple backticks (```json ... ```).

```json
{{
  "personality_description": "New, comprehensive textual description of the user's personality, 3-5 paragraphs, in English. No lists or formatting.",
  "personality_traits": {{
    "reflectiveness": 0.85,
    "optimism": 0.75
  }},
  "life_facts": [
    "I work in IT",
    "I'm into photography",
    {{"remove": "Moved to a new city"}}
  ],
  "hobbies": [
    "sports",
    {{"remove": "reading fiction"}}
  ],
  "core_values": [
    "health",
    "self-development"
  ],
  "triggers": [
    "criticism",
    {{"remove": "noisy crowds"}}
  ],
  "strengths": [
    "persistence",
    "analytical thinking"
  ],
  "areas_for_growth": [
    "stress management",
    {{"remove": "procrastination"}}
  ],
  "personality_insights": {{
    "motivation": "Intrinsic, linked to self-realization",
    "communication_style": "Prefers deep conversations"
  }},
  "habits": [
    "morning exercise",
    "keeping a diary"
  ],
  "skills": [
    "analytical thinking",
    "self-analysis"
  ],
  "aspirations": [
    "increase emotional intelligence",
    "find work-life balance"
  ]
}}
```'''
}
