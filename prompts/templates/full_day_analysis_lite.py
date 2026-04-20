"""
LITE версия промпта для полного анализа дня.

Использует сжатый профиль вместо полного для экономии токенов.
Ориентирован на ключевую информацию без детального контекста.
"""

FULL_DAY_ANALYSIS_LITE_PROMPT = {
    'ru': '''Ты — психолог, анализирующий дневниковые записи пользователя. Твоя задача — провести анализ дня на основе сжатого психологического профиля и ключевых данных за день.

---

### 📥 ВХОДНЫЕ ДАННЫЕ

**Сжатый психологический профиль (основное):**
{compressed_psych_profile_json}
*Это ключевые паттерны, главные триггеры, сильные стороны и зоны роста в кратком формате.*

**Записи за день:**
{all_entries_combined_text}

**Анализы записей:**
{entry_analyses}

**Оценки настроения:**
{daily_mood_scores}

---

### 🧠 ИНСТРУКЦИЯ (КРАТКАЯ)

1. Определи `mood_trend` дня (улучшение/ухудшение/стабильность/нестабильность)
2. Выяви 3-5 ключевых тем дня с значимостью
3. Определи доминирующие эмоции и их контекст
4. Сформулируй 2-3 главных инсайта
5. Дай 1-2 персонализированные рекомендации
6. Напиши краткий анализ дня (2-3 предложения)
7. Предложи обновления профиля если есть новые значимые данные

---

### 📤 ОТВЕТ В JSON

```json
{{
  "daily_analysis": {{
    "mood_trend": "stable",
    "key_themes": [
      {{"theme": "работа", "mentions": 3, "significance": 0.8}}
    ],
    "emotional_patterns": [
      {{"emotion": "тревога", "frequency": 2, "context": "перед встречами"}}
    ],
    "insights": [
      {{"text": "Пользователь лучше справляется с планированием", "category": "behavior", "significance": 0.9}}
    ],
    "recommendations": ["Выделите 10 минут утром для планирования"],
    "overall_analysis_text": "День прошел стабильно. Пользователь показал хорошую продуктивность в рабочих задачах."
  }},
  "user_profile_updates": {{
    "triggers": [],
    "strengths": [],
    "areas_for_growth": []
  }},
  "awareness_level_adjustment": {{
    "new_level": null,
    "reasoning": ""
  }}
}}
```

Формат ключей строго обязателен. Отвечай только JSON.''',
    
    'en': '''You are a psychologist analyzing user's diary entries. Analyze the day based on compressed profile and key data.

---

### 📥 INPUT DATA

**Compressed psychological profile:**
{compressed_psych_profile_json}

**Day entries:**
{all_entries_combined_text}

**Entry analyses:**
{entry_analyses}

**Mood scores:**
{daily_mood_scores}

---

### 🧠 INSTRUCTIONS

1. Determine mood_trend (improvement/decline/stable/unstable)
2. Identify 3-5 key themes with significance
3. Determine dominant emotions and context
4. Formulate 2-3 key insights
5. Give 1-2 personalized recommendations
6. Write brief day analysis (2-3 sentences)
7. Suggest profile updates if new significant data

---

### 📤 JSON RESPONSE

```json
{{
  "daily_analysis": {{
    "mood_trend": "stable",
    "key_themes": [{{"theme": "work", "mentions": 3, "significance": 0.8}}],
    "emotional_patterns": [{{"emotion": "anxiety", "frequency": 2, "context": "before meetings"}}],
    "insights": [{{"text": "User performs better with planning", "category": "behavior", "significance": 0.9}}],
    "recommendations": ["Spend 10 minutes on morning planning"],
    "overall_analysis_text": "Day was stable. Good productivity in work tasks."
  }},
  "user_profile_updates": {{
    "triggers": [],
    "strengths": [],
    "areas_for_growth": []
  }},
  "awareness_level_adjustment": {{
    "new_level": null,
    "reasoning": ""
  }}
}}
```

Strict key format required. Answer only JSON.'''
}