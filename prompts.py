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

PROMPTS['ru']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['en']

def get_prompt(key: str, language: str = 'ru', **kwargs) -> str:
    """
    Получение промпта по ключу и языку с подстановкой параметров.

    Args:
        key (str): Ключ промпта.
        language (str): Код языка ('ru', 'en'). По умолчанию 'ru'.
        **kwargs: Параметры для форматирования строки промпта.

    Returns:
        str: Отформатированная строка промпта или сообщение об ошибке.
    """
    logger.debug(f"=== GET_PROMPT ===")
    logger.debug(f"Ключ: {key}")
    logger.debug(f"Язык: {language}")
    logger.debug(f"Параметры: {list(kwargs.keys())}") # Логируем только ключи для краткости

    if language not in PROMPTS:
        logger.warning(f"Неподдерживаемый язык: {language}, используем 'ru'")
        language = 'ru'
    
    messages = PROMPTS.get(language, PROMPTS['ru'])
    
    if key not in messages:
        logger.error(f"Ключ промпта '{key}' не найден для языка {language}")
        return f"[ОШИБКА: Промпт '{key}' не найден]"
    
    prompt_template = messages.get(key)
    
    try:
        if kwargs:
            result = prompt_template.format(**kwargs)
            return result
        else:
            return prompt_template
    except KeyError as e:
        logger.error(f"Ошибка форматирования промпта '{key}': отсутствует параметр {e}")
        return prompt_template 
    except Exception as e:
        logger.error(f"Ошибка форматирования промпта '{key}': {e}", exc_info=True)
        return prompt_template
