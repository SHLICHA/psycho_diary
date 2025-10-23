"""Промты для взаимодействия с API DeepSeek."""

import logging

from . import (
    INCREMENTAL_DAY_ANALYSIS_PROMPT,
    TIMEZONE_DETECTION_PROMPT,
    PUNCTUATION_PROMPT,
    CLARIFICATION_ANALYSIS_PROMPT,
    TASK_EFFECT_ANALYSIS_PROMPT,
    FULL_DAY_ANALYSIS_PROMPT,
    INCREMENTAL_DAY_ANALYSIS_FIRST_ENTRY_PROMPT,
    WEEKLY_ANALYSIS_PROMPT,
    USER_PROFILE_ANALYSIS_PROMPT,
    NEXT_ENTRY_PROMPT_GENERATION,
    COMMENT_ANALYSIS_PROMPT,
    MORNING_MOTIVATION_PROMPT,
    REMINDER_MESSAGE_PROMPT,
    THERAPY_CHAT_PROMPT,
    PROFILE_CHANGE_ANALYSIS_PROMPT
)

logger = logging.getLogger(__name__)

PROMPTS = {
    'ru': {},
    'en': {}
}

PROMPTS['ru']['incremental_day_analysis_first_entry'] = INCREMENTAL_DAY_ANALYSIS_FIRST_ENTRY_PROMPT['ru']
PROMPTS['en']['incremental_day_analysis_first_entry'] = INCREMENTAL_DAY_ANALYSIS_FIRST_ENTRY_PROMPT['en']
PROMPTS['ru']['profile_change_analysis'] = PROFILE_CHANGE_ANALYSIS_PROMPT['ru']
PROMPTS['en']['profile_change_analysis'] = PROFILE_CHANGE_ANALYSIS_PROMPT['en']
PROMPTS['ru']['therapy_chat'] = THERAPY_CHAT_PROMPT['ru']
PROMPTS['en']['therapy_chat'] = THERAPY_CHAT_PROMPT['en']
PROMPTS['ru']['reminder_message'] = REMINDER_MESSAGE_PROMPT['ru']
PROMPTS['en']['reminder_message'] = REMINDER_MESSAGE_PROMPT['en']
PROMPTS['ru']['morning_motivation'] = MORNING_MOTIVATION_PROMPT['ru']
PROMPTS['en']['morning_motivation'] = MORNING_MOTIVATION_PROMPT['en']
PROMPTS['ru']['comment_analysis'] = COMMENT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['comment_analysis'] = COMMENT_ANALYSIS_PROMPT['en']
PROMPTS['ru']['next_entry_prompt_generation'] = NEXT_ENTRY_PROMPT_GENERATION['ru']
PROMPTS['en']['next_entry_prompt_generation'] = NEXT_ENTRY_PROMPT_GENERATION['en']
PROMPTS['ru']['user_profile_analysis'] = USER_PROFILE_ANALYSIS_PROMPT['ru']
PROMPTS['en']['user_profile_analysis'] = USER_PROFILE_ANALYSIS_PROMPT['en']
PROMPTS['ru']['weekly_analysis'] = WEEKLY_ANALYSIS_PROMPT['ru']
PROMPTS['en']['weekly_analysis'] = WEEKLY_ANALYSIS_PROMPT['en']
PROMPTS['ru']['timezone_detection'] = TIMEZONE_DETECTION_PROMPT['ru']
PROMPTS['en']['timezone_detection'] = TIMEZONE_DETECTION_PROMPT['en']
PROMPTS['ru']['full_day_analysis'] = FULL_DAY_ANALYSIS_PROMPT['ru']
PROMPTS['en']['full_day_analysis'] = FULL_DAY_ANALYSIS_PROMPT['en']
PROMPTS['ru']['clarification_analysis'] = CLARIFICATION_ANALYSIS_PROMPT['ru']
PROMPTS['en']['clarification_analysis'] = CLARIFICATION_ANALYSIS_PROMPT['en']
PROMPTS['ru']['punctuation'] = PUNCTUATION_PROMPT['ru']
PROMPTS['en']['punctuation'] = PUNCTUATION_PROMPT['en']
PROMPTS['ru']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['ru']
PROMPTS['en']['incremental_day_analysis'] = INCREMENTAL_DAY_ANALYSIS_PROMPT['en']
PROMPTS['ru']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['ru']
PROMPTS['en']['task_effect_analysis'] = TASK_EFFECT_ANALYSIS_PROMPT['en']

def get_prompt(key: str, language: str = 'ru', **kwargs) -> str:
    #logger.debug(f"=== GET_PROMPT ===")
    #logger.debug(f"Ключ: {key}")
    #logger.debug(f"Язык: {language}")
    if language not in PROMPTS:
        logger.warning(f"Неподдерживаемый язык: {language}, используем 'ru'")
        language = 'ru'

    messages = PROMPTS.get(language, PROMPTS['ru'])

    if key not in messages:
        logger.error(f"Ключ промпта '{key}' не найден для языка {language}")
        return f"[ОШИБКА: Промпт '{key}' не найден]"

    prompt_template = messages[key]

    try:
        if kwargs:
            user_profile = kwargs.get('user_profile', {})
            safe_user_profile = {
                'first_name': user_profile.get('first_name') or user_profile.get('username') or f'Пользователь {user_profile.get("telegram_id", "ID")}'

            }
            safe_user_profile.update({k: v for k, v in user_profile.items() if k != 'first_name'})
            kwargs['user_profile'] = safe_user_profile
            return prompt_template.format(**kwargs)
            
        else:
            return prompt_template
    except KeyError as e:
        logger.error(f"Ошибка форматирования промпта '{key}': отсутствует параметр {e}")
        safe_template = prompt_template.replace("{user_profile['first_name']}", "Пользователь")
        try:
            return safe_template.format(**{k: v or 'N/A' for k, v in kwargs.items()})
        except:
            return safe_template
    except Exception as e:
        logger.error(f"Ошибка форматирования промпта '{key}': {e}", exc_info=True)
        return prompt_template
