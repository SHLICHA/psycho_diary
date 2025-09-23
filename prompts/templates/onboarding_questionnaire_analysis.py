ONBOARDING_QUESTIONNAIRE_ANALYSIS_PROMPT = {
    'ru': '''Ты - профессиональный психолог, специализирующийся на создании психологических профилей. Твоя задача - проанализировать ответы нового пользователя на анкету для формирования его начального психологического портрета.

---

### 📥 ВХОДНЫЕ ДАННЫЕ: Ответы на анкету

1. Как бы вы хотели, чтобы бот к вам обращался?
   Ответ: {q1_answer}

2. С какой целью вы решили вести дневник?
   Ответ: {q2_answer}

3. Какие 3 слова лучше всего описывают ваш характер?
   Ответ: {q3_answer}

4. Что для вас наиболее важно в жизни?
   Ответ: {q4_answer}

5. Чем вы любите заниматься в свободное время?
   Ответ: {q5_answer}

6. Есть ли что-то, что часто сильно влияет на ваше настроение (в положительную или отрицательную сторону)?
   Ответ: {q6_answer}

7. Что вы больше всего надеетесь получить от этого бота?
   Ответ: {q7_answer}

---

### 🧠 ИНСТРУКЦИЯ

Проанализируй каждый ответ и извлеки из него релевантную информацию для формирования психологического профиля пользователя. Твоя цель - заполнить следующие категории:

1.  **`personality_traits`**: Черты характера (словарь, где ключ - черта, значение - вес 0.5-1.0).
2.  **`core_values`**: Ключевые ценности (список строк).
3.  **`hobbies`**: Увлечения/хобби (список строк).
4.  **`triggers`**: Триггеры настроения (список строк).
5.  **`life_facts`**: Факты о жизни и цели (список строк).
6.  **`strengths`**: Сильные стороны (список строк, если можно выделить из ответов).
7.  **`areas_for_growth`**: Зоны роста (список строк, если можно выделить из ответов).
8.  **`first_name`**: Имя пользователя (если указано в первом вопросе и подходит).

**Правила:**
- Используй только информацию, явно указанную в ответах.
- Не выдумывай. Если информация неясна или отсутствует, пропусти категорию или оставь пустой список/словарь.
- Для `personality_traits` присваивай вес от 0.5 (умеренная уверенность) до 1.0 (высокая уверенность).
- Избегай дубликатов внутри каждой категории.
- Ответ должен быть в строгом JSON-формате.

---

### 📤 ОТВЕТ В СТРОГОМ ФОРМАТЕ JSON

ОТВЕЧАЙ ТОЛЬКО В СЛЕДУЮЩЕМ ФОРМАТЕ JSON, заключенном в тройные обратные кавычки (```json ... ```).

```json
{{
  "user_profile_updates": {{
    "personality_traits": {{
      "интроверт": 0.8,
      "рефлексивный": 0.9
    }},
    "core_values": [
      "саморазвитие",
      "честность"
    ],
    "hobbies": [
      "чтение",
      "программирование"
    ],
    "triggers": [
      "шумные места",
      "нехватка сна"
    ],
    "life_facts": [
      "хочу лучше понимать свои эмоции",
      "работаю в IT"
    ],
    "strengths": [
      "аналитическое мышление"
    ],
    "areas_for_growth": [
      "управление стрессом"
    ]
  }}
}}
```''',

    'en': '''You are a professional psychologist specializing in creating psychological profiles. Your task is to analyze a new user's answers to a questionnaire to form their initial psychological portrait.

---

### 📥 INPUT DATA: Questionnaire Answers

1. What would you like the bot to call you?
   Answer: {q1_answer}

2. What is your purpose for keeping a diary?
   Answer: {q2_answer}

3. What 3 words best describe your personality?
   Answer: {q3_answer}

4. What is most important to you in life?
   Answer: {q4_answer}

5. What do you like to do in your free time?
   Answer: {q5_answer}

6. Is there something that often strongly affects your mood (positively or negatively)?
   Answer: {q6_answer}

7. What do you most hope to get out of this bot?
   Answer: {q7_answer}

---

### 🧠 INSTRUCTIONS

Analyze each answer and extract relevant information to form the user's psychological profile. Your goal is to populate the following categories:

1.  **`personality_traits`**: Personality traits (a dictionary where the key is the trait and the value is a weight from 0.5-1.0).
2.  **`core_values`**: Core values (a list of strings).
3.  **`hobbies`**: Hobbies/Interests (a list of strings).
4.  **`triggers`**: Mood triggers (a list of strings).
5.  **`life_facts`**: Life facts and goals (a list of strings).
6.  **`strengths`**: Strengths (a list of strings, if they can be identified from the answers).
7.  **`areas_for_growth`**: Areas for growth (a list of strings, if they can be identified from the answers).
8.  **`first_name`**: User's first name (if provided in the first question and suitable).

**Rules:**
- Use only the information explicitly stated in the answers.
- Do not make things up. If the information is unclear or missing, skip the category or leave an empty list/dictionary.
- For `personality_traits`, assign a weight from 0.5 (moderate confidence) to 1.0 (high confidence).
- Avoid duplicates within each category.
- The response must be in strict JSON format.

---

### 📤 RESPOND IN STRICT JSON FORMAT

RESPOND ONLY IN THE FOLLOWING JSON FORMAT, enclosed in triple backticks (```json ... ```).

```json
{{
  "user_profile_updates": {{
    "personality_traits": {{
      "introvert": 0.8,
      "reflective": 0.9
    }},
    "core_values": [
      "self-development",
      "honesty"
    ],
    "hobbies": [
      "reading",
      "programming"
    ],
    "triggers": [
      "noisy places",
      "lack of sleep"
    ],
    "life_facts": [
      "want to understand my emotions better",
      "work in IT"
    ],
    "strengths": [
      "analytical thinking"
    ],
    "areas_for_growth": [
      "stress management"
    ]
  }}
}}
```'''
}
