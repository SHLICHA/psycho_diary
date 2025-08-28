# prompts.py
"""Промты для взаимодействия с API DeepSeek."""

import logging

logger = logging.getLogger(__name__)

PROMPTS = {
    'ru': {},
    'en': {}
}


CLARIFICATION_ANALYSIS_PROMPT = {
    'ru': {
        'final_with_clarifications': '''Ты профессиональный психолог. Ниже приведена запись пользователя, на которую были заданы уточняющие вопросы, и ответы пользователя на них.

Оригинальная запись пользователя:
"{original_text}"

Ответы пользователя на уточнения:
"{clarification_answers}"

Пожалуйста, предоставь финальный психологический анализ этой записи, учитывая как оригинальный текст, так и ответы на уточнения. Ответ должен быть в стандартном формате JSON:
- "mood_score": оценка настроения от 1 до 10
- "comment": краткий комментарий (1 предложение)
- "recommendation": персональная рекомендация (1-2 предложения)
- "analysis": подробный финальный анализ (3-4 предложения)
- "suggested_task": объект (не обязательный пункт, только если необходимо, описание задания)
   - "title": название задания
   - "description": описание задания
   - "type": тип задания (из списка: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": приоритет (строка: low, medium, high, critical)
- "key_points": массив объектов (ключевые моменты)
   - "text": текст ключевого момента
   - "type": тип (emotion, event, thought, trigger, other)
   - "confidence": уверенность (float от 0.0 до 1.0)
- "user_insights": массив объектов (новые инсайты)
   - "text": текст инсайта
   - "category": категория из списка: emotion, behavior, thought, trigger, pattern, belief, other
   - "weight": вес (int, от 1 до 10)

Пример ответа:
{{
  "mood_score": 8,
  "comment": "Благодаря уточнениям, стало ясно, что вы мотивированы и поддерживаете себя.",
  "recommendation": "Продолжайте использовать внутренний диалог для самоподдержки.",
  "analysis": "Оригинальная запись содержала элементы самоодобрения. В ответах на уточнения вы подтвердили, что обращаетесь к себе. Это свидетельствует о развитом навыке самосострадания. Такой подход помогает эффективно справляться со стрессом и повышает устойчивость. Рекомендуется поощрять это позитивное поведение.",
  "suggested_task": {{
    "title": "Ежедневная благодарность себе",
    "description": "Каждый вечер записывайте одно достижение или качество, за которое вы благодарны себе.",
    "type": "mindfulness",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "самоодобрение",
      "type": "thought",
      "confidence": 0.95
    }},
    {{
      "text": "мотивация",
      "type": "emotion",
      "confidence": 0.9
    }}
  ],
  "user_insights": [
    {{
      "text": "Самосострадание - эффективный механизм эмоциональной регуляции",
      "category": "personal",
      "weight": 2
    }}
  ]
}}''',
    },
    'en': {
        'final_with_clarifications': '''You are a professional psychologist. Below is a user's entry, clarification questions that were asked, and the user's answers to those questions.

Original user entry:
"{original_text}"

User's answers to clarifications:
"{clarification_answers}"

Please provide a final psychological analysis of this entry, taking into account both the original text and the clarification answers. The response must be in standard JSON format:
- "mood_score": mood score from 1 to 10
- "comment": brief comment (1 sentence)
- "recommendation": personal recommendation (1-2 sentences)
- "analysis": detailed final analysis (3-4 sentences)
- "suggested_task": object (optional, only if necessary, task description)
   - "title": task title
   - "description": task description
   - "type": task type (from the list: daily, reflection, cognitive, creative, behavioral, mindfulness)
   - "priority": priority (string: low, medium, high, critical)
- "key_points": array of objects (key points)
   - "text": text of the key point
   - "type": type (emotion, event, thought, trigger, other)
   - "confidence": confidence (float from 0.0 to 1.0)
- "user_insights": array of objects (new insights)
   - "text": text of the insight
   - "category": category from the list: emotion, behavior, thought, trigger, pattern, belief, other
   - "weight": weight (int, from 1 to 10)

Example response:
{{
  "mood_score": 8,
  "comment": "Thanks to the clarifications, it became clear that you are motivated and self-supporting.",
  "recommendation": "Continue to use inner dialogue for self-support.",
  "analysis": "The original entry contained elements of self-approval. Your answers to the clarifications confirmed that you were addressing yourself. This indicates a developed skill of self-compassion. This approach helps to cope with stress effectively and increases resilience. It is recommended to encourage this positive behavior.",
  "suggested_task": {{
    "title": "Daily Gratitude to Yourself",
    "description": "Every evening, write down one achievement or quality you are grateful for in yourself.",
    "type": "mindfulness",
    "priority": "medium"
  }},
  "key_points": [
    {{
      "text": "self-approval",
      "type": "thought",
      "confidence": 0.95
    }},
    {{
      "text": "motivation",
      "type": "emotion",
      "confidence": 0.9
    }}
  ],
  "user_insights": [
    {{
      "text": "Self-compassion is an effective mechanism of emotional regulation",
      "category": "personal",
      "weight": 2
    }}
  ]
}}''',
    }
}
# Промпт с уточнящими вопросами
PROMPTS['ru'].update(CLARIFICATION_ANALYSIS_PROMPT['ru'])
PROMPTS['en'].update(CLARIFICATION_ANALYSIS_PROMPT['en'])

# === ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ПРОМПТОВ (уже должна быть в файле) ===
# Убедитесь, что у вас есть функция get_prompt, как в предыдущем ответе
def get_prompt(key: str, language: str = 'ru', **kwargs) -> str:
    """
    Получение сообщения по ключу и языку с подстановкой параметров
    """
    logger.info("=== GET_MESSAGE ===")
    logger.info(f"Ключ: {key}")
    logger.info(f"Язык: {language}")
    logger.info(f"Параметры: {kwargs}")
    if language not in PROMPTS:
        logger.warning(f"Неподдерживаемый язык: {language}, используем ru")
        language = 'ru'
    messages = PROMPTS.get(language, PROMPTS['ru'])
    if key not in messages:
        logger.error(f"Ключ '{key}' не найден для языка {language}")
        return f"[ОШИБКА: Сообщение '{key}' не найдено]"
    message = messages.get(key, f'[Отсутствует сообщение: {key}]')    
    try:
        if kwargs:
            result = message.format(**kwargs)
            return result
        else:
            return message
    except KeyError as e:
        logger.error(f"Ошибка форматирования сообщения '{key}': отсутствует параметр {e}")
        return message
    except Exception as e:
        logger.error(f"Ошибка форматирования сообщения '{key}': {e}")
        return message
