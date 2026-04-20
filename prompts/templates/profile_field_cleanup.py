PROFILE_FIELD_CLEANUP_PROMPT = {
    'ru': '''Ты — AI-модуль очистки одного поля психологического профиля.

Твоя задача: обработать ТОЛЬКО одно поле профиля и вернуть очищенный список без потери уникальных смыслов.

### ВХОД

**Имя поля:**
{field_name}

**Элементы поля (JSON):**
{field_items_json}

Каждый элемент содержит: `value`, `weight`, `frequency`, `is_stale`.

### ПРАВИЛА

1. Не вводи искусственные лимиты на количество элементов.
2. Сохраняй все семантически уникальные элементы.
3. Удаляй шум/мусор/дубликаты и ВСЕ близкие повторы по смыслу.
4. Считай элементами с одним смыслом любые формулировки, где различаются только:
  - регистр, пунктуация, порядок слов;
  - степень общности/частности (например, "конфликты с мамой" и "конфликты с родителями");
  - синонимичные обороты (например, "боюсь критики" и "тяжело переношу критику").
5. Для каждого смыслового кластера оставляй ТОЛЬКО 1 элемент с самым точным и нейтральным `value`.
6. Если сомневаешься между "оставить оба" и "объединить" — выбирай объединение.
7. Не дроби один смысл на несколько похожих пунктов и не перефразируй один и тот же смысл в разных элементах.
8. Для объединённого элемента используй:
  - `weight`: максимум среди объединённых;
  - `frequency`: максимум среди объединённых;
  - `is_stale`: `true` только если все объединённые были stale.
9. Поля `weight`, `frequency`, `is_stale` должны быть корректными:
   - `weight` от 0.0 до 1.0
   - `frequency` целое >= 1
   - `is_stale` boolean
10. Не добавляй новые факты, которых нет во входе.
11. Перед ответом сделай self-check: в `cleaned_items` не должно быть двух элементов с одинаковым смыслом.
12. Ответ только JSON, без пояснений.

### ФОРМАТ ОТВЕТА

```json
{{
  "cleaned_items": [
    {{"value": "...", "weight": 0.7, "frequency": 3, "is_stale": false}}
  ]
}}
```
''',
    'en': '''You are an AI module that cleans a single psychological profile field.

Your task: process ONLY one profile field and return a cleaned list without losing unique meaning.

### INPUT

**Field name:**
{field_name}

**Field items (JSON):**
{field_items_json}

Each item contains: `value`, `weight`, `frequency`, `is_stale`.

### RULES

1. Do not apply artificial count limits.
2. Keep all semantically unique items.
3. Remove noise/junk/duplicates and ALL close semantic repeats.
4. Treat items as the same meaning when they differ only by:
  - casing, punctuation, or word order;
  - broader vs narrower wording (for example, "conflicts with mother" vs "conflicts with parents");
  - synonymous phrasing (for example, "afraid of criticism" vs "criticism is hard for me").
5. Keep ONLY 1 item per semantic cluster with the most precise and neutral `value`.
6. If uncertain between "keep both" and "merge", choose merge.
7. Do not split one meaning into multiple near-duplicate phrasings.
8. For a merged item use:
  - `weight`: max among merged items;
  - `frequency`: max among merged items;
  - `is_stale`: `true` only if all merged items were stale.
9. Keep `weight`, `frequency`, `is_stale` valid:
   - `weight` in 0.0..1.0
   - `frequency` integer >= 1
   - `is_stale` boolean
10. Do not invent new facts not present in the input.
11. Before returning, self-check that `cleaned_items` contains no two items with the same meaning.
12. Return JSON only, no commentary.

### RESPONSE FORMAT

```json
{{
  "cleaned_items": [
    {{"value": "...", "weight": 0.7, "frequency": 3, "is_stale": false}}
  ]
}}
```
'''
}
