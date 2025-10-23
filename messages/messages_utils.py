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
        'btn_end_chat': '''⏹️ Завершить чат''',

        # === Уведомления ===
        'reminder_entry': '📝 Не забудь сделать запись в дневник сегодня!',
        'reminder_task': '🎯 У тебя есть невыполненное задание!',
        'morning_greeting': '🌅 Доброе утро! Готов вести дневник сегодня?',
        'morning_motivation_recharge_preamble': '''\n\n------------\n💰 <b>Хочешь автоматический анализ дня?</b>\n\n''',
        'morning_motivation_recharge_text': '''Пополните баланс или оформите подписку, чтобы получать автоматический полный анализ дня. Это поможет объединить данные из разных записей и обновить ваш психологический профиль для более точного понимания себя.''',
        'morning_motivation_enable_auto_analysis_preamble': '''\n\n------------\n🔄 <b>Включите автоматический анализ?</b>\n\n''',
        'morning_motivation_enable_auto_analysis_text': '''У вас есть подписка или токены, но автоматический анализ дня отключен. Включите его, чтобы получать персонализированные инсайты и отслеживать свой прогресс.''',
        'btn_morning_motivation_recharge': '💰 Пополнить баланс или оформить подписку',
        'btn_morning_motivation_enable_auto_analysis': '⚙️ Включить автоанализ',        
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
• Персональные рекомендации
• Автоматический анализ
• Неограниченный чат
• Приоритетная поддержка

💳 Подписка стоит 199₽/месяц''',
'auto_analysis_enabled_on_subscription': '''🔄 <b>Автоматический анализ дня включён!</b> Теперь вы будете получать ежедневные персонализированные инсайты и обновления вашего психологического профиля.''',
        'payment_successful': '✅ Платёж успешно обработан!',
        'thank_you_for_support': 'Спасибо за поддержку!',
        'payment_failed': '❌ Платёж не прошёл.',
        'payment_timeout': '⌛ Время ожидания оплаты истекло. Если вы оплатили, перезапустите бота: /start',
'data_not_found': '''❌ Данные не найдены''',
'no_comment': '''Нет комментария''',
'no_recommendation': '''Нет рекомендации''',
'session_expired': '''⏰ Время сессии истекло (1 час). Сессия автоматически завершена.''',
'photo_too_large': '''⚠️ Фото слишком большое. Максимальный размер - 20 МБ''',
'morning_motivation_default': 'Доброе утро, {first_name}! Пусть этот день будет наполнен радостью и вдохновением.',
'insufficient_tokens': '❌ Недостаточно токенов для выполнения этой операции. Пожалуйста, пополните баланс или оформите подписку.',
'insufficient_tokens_in_chat_hint': '(Если вы находитесь в чате, просто продолжите общение. Отправьте своё сообщение ещё раз.)',
'insufficient_tokens_for_auto_analysis_and_disabled': '❌ Недостаточно токенов для автоматического анализа дня. Анализ не выполнен. Автоматический анализ отключен. Пожалуйста, пополните баланс или оформите подписку.',
        'therapy_chat_welcome_premium': '''💬 <b>Вход в психологический чат</b> 🧠

Привет! Я здесь, чтобы выслушать и поддержать. Поделитесь, что вас беспокоит, радует или тревожит — не бойтесь быть собой. 

<b>Важно знать:</b>
• <i>Ваша переписка с ИИ <u>не сохраняется</u> после завершения сеанса.</i>
• <i>Я знаю основную информацию о вас из вашего <u>профиля</u>.</i>

Наши с вами мысли и чувства — важная часть пути к пониманию себя. Готов(а) погрузиться в размышления? Напишите первое сообщение! 💭''',
        'therapy_chat_welcome_paid': '''💬 <b>Вход в психологический чат</b> 🧠

Привет! Я здесь, чтобы выслушать и поддержать. Поделитесь, что вас беспокоит, радует или тревожит — не бойтесь быть собой. 

<b>Важно знать:</b>
• <i>Ваша переписка с ИИ <u>не сохраняется</u> после завершения сеанса.</i>
• <i>Я знаю основную информацию о вас из вашего <u>профиля</u>.</i>
• <i>Каждое ваше сообщение стоит <b>1 токен</b>.</i>

Наши с вами мысли и чувства — важная часть пути к пониманию себя. Готов(а) погрузиться в размышления? Напишите первое сообщение! 💭''',
        'btn_therapy_chat': '💬 Пообщаться',  
        'btn_remove': '''🗑️ Убрать''',

        'btn_purchase_tokens': '💎 Купить токены',
        'btn_purchase_subscription': '👑 Купить подписку',
        'btn_manage_subscription': '💰 Управление подпиской',
        'btn_renew_subscription': '🔄 Продлить подписку (300₽)',
        'btn_enter_email_for_receipt': '📧 Ввести email для чека',
        'ask_email_for_receipt': '''📧 <b>Введите ваш email для чека</b>\n\nТребуется для соблюдения ФЗ-54 «О применении ККТ». На этот email будет отправлен чек об оплате.''',
        'email_invalid_format': '❌ Неверный формат email. Пожалуйста, введите реальный email для получения чека.',
        'payment_email_saved': '✅ Email сохранён. Продолжаем оформление платежа...',
        'category': '''Категория''',
        'context': '''Контекст''',
        'not_specified': '''Не указано''',
        'broadcast_select_type': '📢 Выберите тип рассылки:',
        'broadcast_important_btn': '🔴 Важная (всем)',
        'broadcast_regular_btn': '🔵 Информационная',
        'broadcast_cancel_btn': '❌ Отмена',
        'broadcast_type_selected_important': '🔴 Важная, всем пользователям',
        'broadcast_type_selected_regular': '🔵 Информационная, только подписавшимся',
        'broadcast_enter_message': '📢 Введите сообщение для рассылки {broadcast_type}:',
        'broadcast_cancelled': '❌ Рассылка отменена',
        'broadcast_success': '✅ Рассылка завершена\nТип: {broadcast_type}\nДоставлено: {success}\nНе удалось: {failed}',
        'broadcast_error': '❌ Ошибка при рассылке',
        'broadcast_failed_cancel': 'Не удалось отменить рассылку',
        'broadcast_prefix': 'Сообщение от администратора',
'btn_morning_motivation_renew_subscription': '🔄 Продлить подписку',
'btn_morning_motivation_manage_subscription': '💰 Управление подпиской',
'btn_next': '➡️ Далее',
'morning_motivation_premium_expiry_preamble': '''\n\n------------\n⏰ <b>Подписка скоро заканчивается!</b>\n\n''',
'premium_expires_in_3_days': 'Ваша подписка PRO закончится через <b>3 дня</b>. Не забудьте продлить, чтобы не потерять доступ к премиум-функциям.',
'premium_expires_in_2_days': 'Ваша подписка PRO закончится через <b>2 дня</b>. Продлите её, чтобы продолжить пользоваться всеми возможностями.',
'premium_expires_in_1_days': 'Ваша подписка PRO <b>заканчивается завтра</b>! Продлите её прямо сейчас.',
'reply_feedback_prompt': (
    '✍️ Ответ на обращение #{feedback_id} от {username} ({created_at}):\n\n'
    'Сообщение:\n{message_text}\n\n'
    'Введите ваш ответ:'
),
'btn_cancel_reply': '❌ Отменить',
'error_feedback_reply_start': '❌ Ошибка при обработке обращения',
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
        'btn_end_chat': '''⏹️ End Chat''',
        
        # === Notifications ===
        'reminder_entry': '📝 Don\'t forget to make an entry in your diary today!',
        'reminder_task': '🎯 You have an incomplete task!',
        'morning_greeting': '🌅 Good morning! Ready to keep a diary today?',
        'morning_motivation_recharge_preamble': '''\n\n------------\n💰 <b>Want automatic day analysis?</b>\n\n''',
        'morning_motivation_recharge_text': '''Recharge your balance or subscribe to get automatic full day analysis. This will help combine data from different entries and update your psychological profile for a better understanding of yourself.''',
        'morning_motivation_enable_auto_analysis_preamble': '''\n\n------------\n🔄 <b>Enable automatic analysis?</b>\n\n''',
        'morning_motivation_enable_auto_analysis_text': '''You have a subscription or tokens, but automatic daily analysis is disabled. Enable it to receive personalized insights and track your progress.''',
        'btn_morning_motivation_recharge': '💰 Recharge Balance or Subscribe',
        'btn_morning_motivation_enable_auto_analysis': '⚙️ Enable Auto Analysis',
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
'auto_analysis_enabled_on_subscription': '''🔄 <b>Automatic daily analysis enabled!</b> You will now receive daily personalized insights and updates to your psychological profile.''',
        'payment_successful': '✅ Payment processed successfully!',
        'thank_you_for_support': 'Thank you for your support!',
        'payment_failed': '❌ Payment failed.',
        'payment_timeout': '⌛ Payment timeout. If you have paid, please restart the bot: /start',
'data_not_found': '''❌ Data not found''',
'no_comment': '''No comment''',
'no_recommendation': '''No recommendation''',
'session_expired': '''⏰ Session time expired (1 hour). Session automatically completed''',
'photo_too_large': '''⚠️ Photo is too large. Maximum size - 20 MB''',
'insufficient_tokens': '❌ Insufficient tokens to perform this operation. Please top up your balance.',
'insufficient_tokens_in_chat_hint': '(If you are in the chat, just continue the conversation. Send your message again.)',
'insufficient_tokens_for_auto_analysis': '❌ Insufficient tokens for automatic daily analysis. Analysis not performed. Please top up your balance or subscribe.',
'insufficient_tokens_for_auto_analysis_and_disabled': '❌ Insufficient tokens for automatic daily analysis. Analysis not performed. Automatic analysis has been disabled. Please top up your balance or subscribe.',
        'therapy_chat_welcome_premium': '''💬 <b>Entering the Therapy Chat</b> 🧠

Hi! I'm here to listen and support. Share what troubles, pleases, or worries you — don't be afraid to be yourself. 

<b>Important to know:</b>
• <i>Your chat history with the AI is <u>not saved</u> after the session ends.</i>
• <i>I know basic information about you from your <u>profile</u>.</i>

Our thoughts and feelings are an important part of the path to understanding ourselves. Ready to dive into reflection? Write your first message! 💭''',
        'therapy_chat_welcome_paid': '''💬 <b>Entering the Therapy Chat</b> 🧠

Hi! I'm here to listen and support. Share what troubles, pleases, or worries you — don't be afraid to be yourself. 

<b>Important to know:</b>
• <i>Your chat history with the AI is <u>not saved</u> after the session ends.</i>
• <i>I know basic information about you from your <u>profile</u>.</i>
• <i>Each of your messages costs <b>1 token</b>.</i>

Our thoughts and feelings are an important part of the path to understanding ourselves. Ready to dive into reflection? Write your first message! 💭''',
        'btn_therapy_chat': '💬 Talk to Psychologist',
        'btn_remove': '''🗑️ Remove''',

        'btn_purchase_tokens': '💎 Buy tokens',
        'btn_purchase_subscription': '👑 Buy subscription',
        'btn_manage_subscription': '💰 Manage subscription',
        'btn_renew_subscription': '🔄 Renew subscription',
        'btn_enter_email_for_receipt': '📧 Enter email for receipt',
        'ask_email_for_receipt': '''📧 <b>Enter your email for receipt</b>\n\nRequired for compliance with Federal Law-54 "On the use of cash register equipment". The receipt will be sent to this email.''',
        'email_invalid_format': '❌ Invalid email format. Please enter a real email to receive the receipt.',
        'payment_email_saved': '✅ Email saved. Continuing with payment processing...',
        'category': '''Category''',
        'context': '''Context''',
        'not_specified': '''Not specified''',
        'broadcast_select_type': '📢 Select broadcast type:',
        'broadcast_important_btn': '🔴 Important (to all)',
        'broadcast_regular_btn': '🔵 Informational',
        'broadcast_cancel_btn': '❌ Cancel',
        'broadcast_type_selected_important': '🔴 Important, to all users',
        'broadcast_type_selected_regular': '🔵 Informational, to subscribers only',
        'broadcast_enter_message': '📢 Enter broadcast message {broadcast_type}:',
        'broadcast_cancelled': '❌ Broadcast cancelled',
        'broadcast_success': '✅ Broadcast completed\nType: {broadcast_type}\nDelivered: {success}\nFailed: {failed}',
        'broadcast_error': '❌ Broadcast error',
        'broadcast_failed_cancel': 'Failed to cancel broadcast',
        'broadcast_prefix': 'Message from admin',
'btn_morning_motivation_renew_subscription': '🔄 Renew Subscription',
'btn_morning_motivation_manage_subscription': '💰 Manage Subscription',
'btn_next': '➡️ Next',
'morning_motivation_premium_expiry_preamble': '''\n\n------------\n⏰ <b>Your subscription is ending soon!</b>\n\n''',
'premium_expires_in_3_days': 'Your PRO subscription will end in <b>3 days</b>. Remember to renew to keep access to premium features.',
'premium_expires_in_2_days': 'Your PRO subscription will end in <b>2 days</b>. Renew it to continue enjoying all features.',
'premium_expires_in_1_days': 'Your PRO subscription <b>ends tomorrow</b>! Renew it now.',
'reply_feedback_prompt': (
    '✍️ Reply to feedback #{feedback_id} from {username} ({created_at}):\n\n'
    'Message:\n{message_text}\n\n'
    'Enter your reply:'
),
'btn_cancel_reply': '❌ Cancel',
'error_feedback_reply_start': '❌ Error processing feedback',
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