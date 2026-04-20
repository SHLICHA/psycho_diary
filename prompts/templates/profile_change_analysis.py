PROFILE_CHANGE_ANALYSIS_PROMPT = {
    'ru': '''Ты — продвинутый психолог-аналитик ИИ. Твоя задача — проанализировать изменения в психологическом профиле пользователя за последние недели, сравнивая текущий профиль с историческими данными.

### 🔍 ВХОДНЫЕ ДАННЫЕ

**Текущее полное текстовое описание личности:**
{current_personality_description}

**Текущий сжатый профиль (JSON):**
{current_compressed_psych_profile_json}

**Текущие личностные поля (JSON, changed-format):**
{current_personal_fields_json}

**Исторические слепки (последние {num_snapshots}, JSON):**
{historical_snapshots_json}

### 🧠 ИНСТРУКЦИЯ

1.  Сравни текущие данные профиля с историческими слепками.
  *   Обязательно опирайся на **полное текущее текстовое описание личности** и сопоставляй его с полными текстовыми описаниями внутри исторических слепков, а не только со структурированными полями.
2.  Выяви **ключевые изменения** в следующих аспектах (если таковые имеются):
    *   Черты характера
    *   Факты о жизни
    *   Увлечения
    *   Ключевые ценности
    *   Триггеры
    *   Сильные стороны
    *   Зоны роста
    *   Глубинные инсайты
    *   Привычки
    *   Навыки
    *   Стремления
    *   Уровень осознанности
    *   Текстовое описание личности
3.  Выяви **стабильные** аспекты, которые не изменились или изменились незначительно.
4.  Сформулируй краткое **резюме изменений** (1-2 предложения).
5.  Перечисли **ключевые изменения** в виде списка (например, "- Значительно усилились 'Самооценка' и 'Уверенность'...", "- Появился новый триггер 'Критика в адрес близких'...", "- 'Стремление к признанию' стало менее выраженным...").
6.  Укажи **стабильные черты**, которые остались неизменными (или почти неизменными) (например, "- Стабильные сильные стороны: 'Эмпатия', 'Организованность'...").

### 📤 ОТВЕТ В СТРОГОМ ФОРМАТЕ JSON

ОТВЕЧАЙ ТОЛЬКО В СЛЕДУЮЩЕМ ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

```json
{{
  "summary": "Краткое резюме изменений (1-2 предложения)",
  "key_changes": [
    "Описание ключевого изменения 1",
    "Описание ключевого изменения 2"
  ],
  "stable_traits": [
    "Описание стабильной черты 1",
    "Описание стабильной черты 2"
  ]
}}
```''',
    'en': '''You are an advanced AI psychological analyst. Your task is to analyze changes in the user's psychological profile over the past weeks by comparing the current profile with historical data.

### 🔍 INPUT DATA

**Current full personality description:**
{current_personality_description}

**Current compressed profile (JSON):**
{current_compressed_psych_profile_json}

**Current personal fields (JSON, changed-format):**
{current_personal_fields_json}

**Historical snapshots (last {num_snapshots}, JSON):**
{historical_snapshots_json}

### 🧠 INSTRUCTIONS

1.  Compare the current profile data with the historical snapshots.
  *   You must explicitly rely on the **full current textual personality description** and compare it against the full textual descriptions inside the historical snapshots, not just the structured fields.
2.  Identify **key changes** in the following aspects (if any):
    *   Personality Traits
    *   Life Facts
    *   Hobbies
    *   Core Values
    *   Triggers
    *   Strengths
    *   Areas for Growth
    *   Deep Insights
    *   Habits
    *   Skills
    *   Aspirations
    *   Awareness Level
    *   Personality Description Text
3.  Identify **stable** aspects that have not changed or changed insignificantly.
4.  Formulate a brief **summary of changes** (1-2 sentences).
5.  List the **key changes** (e.g., "- 'Self-esteem' and 'Confidence' have significantly increased...", "- A new trigger 'Criticism towards loved ones' has appeared...", "- 'Desire for recognition' has become less pronounced...").
6.  Indicate **stable traits** that have remained unchanged (or almost unchanged) (e.g., "- Stable strengths: 'Empathy', 'Organization'...").

### 📤 RESPONSE IN STRICT JSON FORMAT

RESPOND ONLY IN THE FOLLOWING JSON FORMAT, enclosed in triple backticks (```json ... ```).

```json
{{
  "summary": "Brief summary of changes (1-2 sentences)",
  "key_changes": [
    "Description of key change 1",
    "Description of key change 2"
  ],
  "stable_traits": [
    "Description of stable trait 1",
    "Description of stable trait 2"
  ]
}}
```'''
}