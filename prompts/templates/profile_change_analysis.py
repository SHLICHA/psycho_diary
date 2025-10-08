PROFILE_CHANGE_ANALYSIS_PROMPT = {
    'ru': '''Ты — продвинутый психолог-аналитик ИИ. Твоя задача — проанализировать изменения в психологическом профиле пользователя за последние недели, сравнивая текущий профиль с историческими данными.

### 🔍 ВХОДНЫЕ ДАННЫЕ

**Текущий профиль пользователя (на момент анализа):**
{current_profile}

**Исторические профили (последние {num_snapshots}):**
{historical_profiles}

### 🧠 ИНСТРУКЦИЯ

1.  Сравни текущий профиль с историческими.
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

**Current User Profile (at the time of analysis):**
{current_profile}

**Historical Profiles (last {num_snapshots}):**
{historical_profiles}

### 🧠 INSTRUCTIONS

1.  Compare the current profile with the historical ones.
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