"""
Многоязычные сообщения для бота
Расширенная система с поддержкой всех сценариев
"""

import logging

from . import ALL_MESSAGES

logger = logging.getLogger(__name__)

# Основные сообщения
MESSAGES = {
    'ru': {
        'mood_1': 'ужасно 😰',
        'mood_2': 'очень плохо 😟',
        'mood_3': 'плохо 😞',
        'mood_4': 'немного плохо 😕',
        'mood_5': 'нормально 😐',
        'mood_6': 'немного хорошо 🙂',
        'mood_7': 'хорошо 😊',
        'mood_8': 'очень хорошо 😄',
        'mood_9': 'отлично 😁',
        'mood_10': 'прекрасно 🤩',
        'edit_entries_header': '📝 Редактирование записей за {date}',
        'ask_entry_edit_with_text': '📝 <b>Отредактируйте свою запись:</b>\n\n<i>Текущий текст:</i>\n<code>{old_text}</code>\n\n<i>Отправьте новый текст записи:</i>',
        'entry_updated_success': '✅ <b>Запись обновлена!</b>\n\nДля получения нового анализа нажмите "Подтвердить" в меню редактирования дня.',
        'confirm_delete_entry_yes': '✅ Да, удалить',
        'confirm_delete_entry_no': '❌ Нет, отмена',
        'entry_deleted_success': '🗑 Запись удалена.',
        'day_analysis_confirmed': '🔄 Анализ запущен. Результат будет доступен в архиве.',
        'back_without_analysis_warning': 'Новый анализ дня произведен не будет. Вы всегда можете вернуться и подтвердить изменения.',
        'btn_confirm_changes': '✅ Подтвердить',
        'btn_reanalyze_entry': '🔁 Пересчитать анализ дня',
        'analysis_already_done': 'Анализ уже выполнен.',
        'analysis_recalculated': 'Анализ пересчитан!',
        'btn_delete_all_entries': '🗑 Удалить весь день',
        'btn_back_to_day': '🔙 Назад к дню',
        'btn_back_to_day_without_analysis': '🔙 Назад без анализа',
        'btn_back_to_edit_day': '🔙 Назад к редактированию',
        'btn_skip': '''⏭ Пропустить''',
        'btn_main_menu': '🔙 В главное меню',
        'btn_recharge_tokens': '💰 Пополнить баланс',

        # === Уведомления ===
        'reminder_entry': '📝 Не забудь сделать запись в дневник сегодня!',
        'reminder_task': '🎯 У тебя есть невыполненное задание!',
        'morning_greeting': '🌅 Доброе утро! Готов вести дневник сегодня?',
        'evening_greeting': '🌇 Добрый вечер! Как прошёл твой день?',
        # === Специальные сообщения ===
        'insight_discovered': '💡 <b>Новый инсайт!</b>\n\nЯ заметил, что у тебя часто встречается тема "{insight}". Это может быть важно для понимания твоих паттернов.',
        'pattern_detected': '🔄 <b>Обнаружен паттерн!</b>\n\nЯ вижу повторяющуюся тему в твоих записях: "{pattern}". Давай подумаем, что с этим можно сделать.',
        'improvement_detected': '📈 <b>Прогресс!</b>\n\nЯ заметил улучшение в твоём настроении! Продолжай в том же духе.',
        # === Премиум функции ===
        'premium_required': '👑 Эта функция доступна только премиум пользователям.',
        'premium_benefits': '''👑 <b>Премиум подписка</b>

✨ <b>Что входит:</b>
• Еженедельные отчеты
• Графики эмоций
• Персональные рекомендации
• Расширенная статистика
• Приоритетная поддержка

💳 Подписка стоит 299₽/месяц''',

'data_not_found': '''❌ Данные не найдены''',
'no_comment': '''Нет комментария''',
'no_recommendation': '''Нет рекомендации''',
'session_expired': '''⏰ Время сессии истекло (1 час). Сессия автоматически завершена.''',
'photo_too_large': '''⚠️ Фото слишком большое. Максимальный размер - 20 МБ''',
'morning_motivation_default': 'Доброе утро, {first_name}! Пусть этот день будет наполнен радостью и вдохновением.',
'insufficient_tokens': '❌ Недостаточно токенов для выполнения этой операции. Пожалуйста, пополните баланс.',
'insufficient_tokens_for_auto_analysis_and_disabled': '❌ Недостаточно токенов для автоматического анализа дня. Анализ не выполнен. Автоматический анализ отключен. Пожалуйста, пополните баланс или оформите подписку.',
    },
    'en': {
        # === Mood scores ===
        'mood_1': 'terrible 😰',
        'mood_2': 'very bad 😟',
        'mood_3': 'bad 😞',
        'mood_4': 'a bit bad 😕',
        'mood_5': 'normal 😐',
        'mood_6': 'a bit good 🙂',
        'mood_7': 'good 😊',
        'mood_8': 'very good 😄',
        'mood_9': 'excellent 😁',
        'mood_10': 'wonderful 🤩',
        
        # === Confirmations ===
        'edit_entries_header': '📝 Editing entries for {date}',
        'ask_entry_edit_with_text': '📝 <b>Edit your entry:</b>\n\n<i>Current text:</i>\n<code>{old_text}</code>\n\n<i>Send the new entry text:</i>',
        'entry_updated_success': '✅ <b>Entry updated!</b>\n\nTo get a new analysis, click "Confirm" in the day editing menu.',
        'confirm_delete_entry_prompt': '❓ Are you sure you want to delete this entry?',
        'confirm_delete_entry_yes': 'Yes, delete',
        'confirm_delete_entry_no': 'No, cancel',
        'entry_deleted_success': '🗑 Entry deleted.',
        'day_analysis_confirmed': '🔄 Analysis started. The result will be available in the archive.',
        'back_without_analysis_warning': 'A new analysis of the day will not be performed. You can always come back and confirm the changes.',
        'btn_confirm_changes': '✅ Confirm',
        'btn_reanalyze_entry': '🔁 Recalculate analysis',
        'analysis_already_done': 'Analysis already done.',
        'analysis_recalculated': 'Analysis recalculated!',
        'btn_delete_all_entries': '🗑 Delete entire day',
        'btn_back_to_day': '🔙 Back to day',
        'btn_back_to_day_without_analysis': '🔙 Back without analysis',
        'btn_back_to_edit_day': '🔙 Back to editing',
        'btn_skip': '''⏭ Skip''',
        'btn_main_menu': '🔙 Main menu',
        'btn_recharge_tokens': '💰 Recharge Balance',
        
        # === Notifications ===
        'reminder_entry': '📝 Don\'t forget to make an entry in your diary today!',
        'reminder_task': '🎯 You have an incomplete task!',
        'morning_greeting': '🌅 Good morning! Ready to keep a diary today?',
        'evening_greeting': '🌇 Good evening! How was your day?',
        
        # === Special messages ===
        'insight_discovered': '💡 <b>New insight!</b>\n\nI noticed that you often mention "{insight}". This might be important for understanding your patterns.',
        'pattern_detected': '🔄 <b>Pattern detected!</b>\n\nI see a recurring theme in your entries: "{pattern}". Let\'s think about what can be done about it.',
        'improvement_detected': '📈 <b>Improvement!</b>\n\nI noticed an improvement in your mood! Keep it up.',
        
        # === Premium features ===
        'premium_required': '👑 This feature is available only to premium users.',
        'premium_benefits': '''👑 <b>Premium subscription</b>

✨ <b>What's included:</b>
• Weekly reports
• Mood charts
• Personal recommendations
• Extended statistics
• Priority support

💳 Subscription costs $4.99/month''',

'data_not_found': '''❌ Data not found''',
'no_comment': '''No comment''',
'no_recommendation': '''No recommendation''',
'session_expired': '''⏰ Session time expired (1 hour). Session automatically completed''',
'photo_too_large': '''⚠️ Photo is too large. Maximum size - 20 MB''',
'insufficient_tokens': '❌ Insufficient tokens to perform this operation. Please top up your balance.',
'insufficient_tokens_for_auto_analysis': '❌ Insufficient tokens for automatic daily analysis. Analysis not performed. Please top up your balance or subscribe.',
'insufficient_tokens_for_auto_analysis_and_disabled': '❌ Insufficient tokens for automatic daily analysis. Analysis not performed. Automatic analysis has been disabled. Please top up your balance or subscribe.',
     
    }
}

MESSAGES['ru'].update(ALL_MESSAGES['ru'])
MESSAGES['en'].update(ALL_MESSAGES['en'])

def get_message(key: str, language: str = 'ru', **kwargs) -> str:
    """
    Получение сообщения по ключу и языку с подстановкой параметров
    """
    #logger.debug("=== GET_MESSAGE ===")
    #logger.debug(f"Ключ: {key}")
    #logger.debug(f"Язык: {language}")
    #logger.debug(f"Параметры: {kwargs}")
    if language not in MESSAGES:
        logger.warning(f"Неподдерживаемый язык: {language}, используем ru")
        language = 'ru'
    messages = MESSAGES.get(language, MESSAGES['ru'])
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

def get_button_text(key: str, language: str = 'ru') -> str:
    """
    Получение текста кнопки по ключу и языку
    """
    return get_message(key, language)

def get_mood_text(score: int, language: str = 'ru') -> str:
    """
    Получение текстового описания оценки настроения
    """
    key = f'mood_{score}'
    return get_message(key, language)

def get_status_text(status: bool, language: str = 'ru') -> str:
    """
    Получение текста статуса (вкл/выкл)
    """
    if status:
        return get_message('status_enabled', language=language)
    else:
        return get_message('status_disabled', language=language)