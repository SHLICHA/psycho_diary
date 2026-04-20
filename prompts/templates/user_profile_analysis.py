USER_PROFILE_ANALYSIS_PROMPT = {
    'ru': '''Ты — эксперт-психолог с глубоким пониманием человеческой личности. Твоя задача — на основе предоставленных данных создать или обновить глубокий психологический портрет пользователя. Ты получишь его текущий профиль и историю анализа недель. Твоя цель — синтезировать эту информацию в целостное, точное и *актуальное* описание личности, *объединив* схожие по смыслу данные и *очистив* от дубликатов. Удаляй *только* то, что *явно* утратило актуальность (например, подтверждённый отказ от ценности или устаревший факт).

### 🔍 ВХОДНЫЕ ДАННЫЕ

**Текущее полное текстовое описание профиля пользователя:**
{personality_description}

**Сжатый психологический профиль (JSON):**
{compressed_psych_profile_json}

**Унифицированные личностные поля (JSON, changed-format):**
{personal_fields_json}

**Анализы последних недель:**
{recent_weekly_analyses}

### 🧠 ИНСТРУКЦИЯ

1.  **Проанализируй все предоставленные данные.**
    *   Обрати особое внимание на динамику, тренды и повторяющиеся паттерны.
    *   Сравни текущие данные профиля с информацией из `recent_weekly_analyses`.
    *   **Важно**: Проанализируй каждый элемент `personal_fields_json`. Если элемент не упоминался в новых данных и ты видишь по контексту, что он утратил актуальность — **обязательно** пометь его на удаление через `{{"remove": "элемент"}}`.
2.  **Создай или обнови `personality_description`**:
  *   Это должно быть **новое, цельное, полное человекочитаемое описание профиля** пользователя на русском языке.
  *   **Обязательно опирайся на текущее текстовое описание профиля**: сохрани подтверждённые устойчивые характеристики, перепиши устаревшие или неточные формулировки и встрои новые данные в уже существующий целостный портрет.
    *   Объедини ключевые черты, ценности, сильные стороны, зоны роста, привычки, стремления и инсайты в связный рассказ.
    *   Учитывай уровень осознанности.
    *   Объем: 2-4 абзацев, **обязательно** не более 3000 символов. Избегай списков и форматирования.
3.  **Обнови все структурированные поля профиля**:
    *   Пересмотри и при необходимости обнови **все** следующие поля:
        *   `personality_traits` (dict): Только *актуальные* значимые черты (вес 0.1-1.0), *без дубликатов*. *Объедини* черты с близким значением (например, "пунктуальность" и "организованность" могут быть объединены в "организованность и ответственность").
        *   `life_facts` (list): Только *проверенные и актуальные* факты. *Оставь* факты, даже если они не упоминались в новых данных, *если* они не утратили актуальности. *Удали* только *явно устаревшие* и *явно неважные* факты (например, "жил в... году", если подтверждённо неактуально).
        *   `hobbies` (list): Только *реальные и актуальные* интересы/увлечения. *Объедини* схожие (например, "бег", "маунтинбайк", "пешие походы" -> "активный отдых на природе"). *Удали* только если *подтверждённо* утратили актуальность.
        *   `core_values` (list): *Фундаментальные* ценности. *Оставь* ценности, даже если они не упоминались в новых данных, *если* пользователь не отказался от них. *Удали* только *если пользователь явно отказался от ценности* (например, написал, что она больше не важна).
        *   `triggers` (list): Только *актуальные* эмоциональные триггеры. *Объедини* схоже звучащие или с близкой сутью. *Удали* только *если подтверждено* утратили актуальность.
        *   `strengths` (list): Только *подтверждённые и актуальные* сильные стороны. *Объедини* дублирующие или схоже звучащие. *Удали* только *если подтверждено* утратили актуальность.
        *   `areas_for_growth` (list): Только *актуальные* зоны развития. *Объедини* схоже звучащие. *Удали* только *если подтверждено* над ней уже поработано и она больше не актуальна.
        *   `personality_insights` (dict): *Глубинные инсайты*, отражающие *текущее* понимание. *Объедини* инсайты с близкой сутью. *Удали* только *если подтверждено* утратили актуальность.
        *   `habits` (list): *Сформировавшиеся и наблюдаемые* привычки. *Объедини* схоже звучащие. *Удали* только *если подтверждено* утратили актуальность.
        *   `skills` (list): *Наблюдаемые актуальные* навыки (жизненные, коммуникативные, когнитивные и т.д.). *Объедини* дублирующие или схоже звучащие. *Удали* только *если подтверждено* утратили актуальность.
        *   `aspirations` (list): *Четко выраженные и актуальные* стремления и цели. *Объедини* схоже звучащие или с близкой сутью. *Удали* только *если подтверждено* достигнуты или утратили актуальность.
    *   Для списков (`life_facts`, `hobbies` и т.д.):
        *   Чтобы **добавить** элемент: просто включи его в список.
        *   Чтобы **удалить** элемент: используй формат `{{"remove": "старый_элемент"}}`. Используй это *только* для подтверждённого удаления. **Без этой пометки элемент останется в профиле навсегда.** Если ты видишь, что элемент устарел — обязательно используй этот формат.
    *   Для `personality_traits` и `personality_insights` (словари):
        *   Предоставь обновленный словарь с *актуальными* ключами и значениями. *Объедини* информацию, если ключи близки по смыслу (например, "мотивация_работа", "мотивация_проекты" -> "мотивация_достижения"). *Удали* только *если подтверждено* утратили актуальность.
4.  **Создай `compressed_psych_profile`** — сжатое представление профиля для использования в кратких анализах (LITE):
    *   `psych_summary` (3-5 предложений): Краткое описание личности — основные черты, ценности, текущее эмоциональное состояние
    *   `core_patterns` (3-5 items): Ключевые поведенческие паттерны, которые ты заметил
    *   `emotional_style` (1 предложение): Как пользователь обычно реагирует на события
    *   `main_triggers` (2-3 items): Главные эмоциональные триггеры
    *   `coping_style` (1 предложение): Как пользователь обычно справляется со стрессом
    *   `current_focus` (1-2 предложения): Что сейчас главное для пользователя

    *Этот профиль будет использоваться в кратких анализах записей вместо полного профиля.*

5.  **НЕ ВКЛЮЧАЙ `awareness_level`, `first_name`, `date_of_birth`** в свой ответ.

### 📤 ОТВЕТ В СТРОГОМ ФОРМАТЕ JSON

ОТВЕЧАЙ ТОЛЬКО В СЛЕДУЮЩЕМ ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

```json
{{
  "personality_description": "Новое полное текстовое описание профиля пользователя, переписанное на основе старого описания и новых данных; 2-4 абзацев, на русском языке. Без списков и форматирования.",
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
    "активный отдых на природе",
    "чтение научной литературы"
  ],
  "core_values": [
    "близкие отношения",
    "саморазвитие"
  ],
  "triggers": [
    "резкая критика",
    {{"remove": "шумные компании"}}
  ],
  "strengths": [
    "настойчивость",
    "аналитическое мышление"
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
    "найти баланс"
  ],
  "compressed_psych_profile": {{
    "psych_summary": "Краткое описание личности (3-5 предложений) — основные черты, ценности и текущее состояние",
    "core_patterns": ["ключевой паттерн 1", "ключевой паттерн 2", "ключевой паттерн 3"],
    "emotional_style": "Описание эмоционального стиля (1 предложение)",
    "main_triggers": ["основной триггер 1", "основной триггер 2"],
    "coping_style": "Описание стиля совладания со стрессом (1 предложение)",
    "current_focus": "Текущий фокус внимания/главная тема (1-2 предложения)"
  }}
}}
```''',
    'en': '''You are an expert psychologist with a deep understanding of human personality. Your task is to create or update a profound psychological portrait of the user based on the provided data. You will receive their current profile and a history of weekly analyses. Your goal is to synthesize this information into a coherent, accurate, and *current* description of the personality, *merging* items with similar meaning and *cleaning* up duplicates. Only remove items that have *clearly* lost relevance (e.g., a confirmed rejection of a value or an outdated fact).

### 🔍 INPUT DATA

**Current full textual profile description:**
{personality_description}

**Compressed psychological profile (JSON):**
{compressed_psych_profile_json}

**Unified personal fields (JSON, changed-format):**
{personal_fields_json}

**Recent Weekly Analyses:**
{recent_weekly_analyses}

### 🧠 INSTRUCTIONS

1.  **Analyze all provided data.**
    *   Pay special attention to dynamics, trends, and recurring patterns.
    *   Compare the current profile data with information from `recent_weekly_analyses`.
    *   **Important**: Review every element in `personal_fields_json`. If an item has not been mentioned in new data and you can see from context that it has lost relevance — **mark it for removal** using `{{"remove": "item"}}`.
2.  **Create or update `personality_description`**:
  *   This should be a **new, cohesive, full human-readable profile description** of the user in English.
  *   **You must explicitly build on the current textual profile description**: keep confirmed stable characteristics, rewrite outdated or imprecise wording, and integrate new signals into the existing portrait instead of replacing it blindly.
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
        *   To **remove** an item: use the format `{{"remove": "old_item"}}`. Use this *only* for confirmed removals. **Without this marker, the item will remain in the profile forever.** If you see that an item is outdated — always use this format.
    *   For `personality_traits` and `personality_insights` (dictionaries):
        *   Provide an updated dictionary with *current* keys and values. *Merge* information if keys are similar in meaning (e.g., "motivation_job", "motivation_projects" -> "motivation_achievements"). *Remove* only *if confirmedly* no longer relevant.
4.  **Create `compressed_psych_profile`** — compact profile representation for use in brief analyses (LITE):
    *   `psych_summary` (3-5 sentences): Brief personality description — main traits, values, current emotional state
    *   `core_patterns` (3-5 items): Key behavioral patterns you've noticed
    *   `emotional_style` (1 sentence): How the user typically responds to events
    *   `main_triggers` (2-3 items): Main emotional triggers
    *   `coping_style` (1 sentence): How the user typically copes with stress
    *   `current_focus` (1-2 sentences): What's currently most important for the user

    *This profile will be used in brief entry analyses instead of the full profile.*

5.  **DO NOT INCLUDE `awareness_level`, `first_name`, `date_of_birth`** in your response.

### 📤 RESPONSE IN STRICT JSON FORMAT

RESPOND ONLY IN THE FOLLOWING JSON FORMAT, enclosed in triple backticks (```json ... ```).

```json
{{
  "personality_description": "New full textual profile description of the user, rewritten from the old description plus new data; 2-4 paragraphs, in English. No lists or formatting.",
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
    "outdoor activities",
    "reading science books"
  ],
  "core_values": [
    "close relationships",
    "self-development"
  ],
  "triggers": [
    "harsh criticism",
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
    "find balance"
  ],
  "compressed_psych_profile": {{
    "psych_summary": "Brief personality description (3-5 sentences) — main traits, values, and current state",
    "core_patterns": ["key pattern 1", "key pattern 2", "key pattern 3"],
    "emotional_style": "Description of emotional style (1 sentence)",
    "main_triggers": ["main trigger 1", "main trigger 2"],
    "coping_style": "Description of coping style (1 sentence)",
    "current_focus": "Current focus of attention/main theme (1-2 sentences)"
  }}
}}
```'''
}
