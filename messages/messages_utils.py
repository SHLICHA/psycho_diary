"""
Многоязычные сообщения для бота
Расширенная система с поддержкой всех сценариев
"""

import logging

from . import HELP_MESSAGES

logger = logging.getLogger(__name__)

# Основные сообщения
MESSAGES = {
    'ru': {
        'welcome': '''🧠 <b>Привет! Это твой психологический дневник.</b>

Здесь ты можешь вести записи о своих днях, а я помогу тебе понять свои эмоции и мысли.

Я буду твоим цифровым психологом, который запомнит твои особенности и станет лучше понимать тебя с каждым днем.

Начнем?''',
        
        'welcome_back': '👋 С возвращением, {username}! Рад снова видеть тебя.',
        
        # === Создание записей ===
        'ask_entry': '📝 <b>Расскажи, как прошёл твой день...</b>',
        'ask_voice_entry': '🎙 <b>Отправь голосовое сообщение о своём дне...</b>',
        'processing': '⏳ <i>Обрабатываю твою запись...</i>',
        'entry_saved': '''✅ <b>Запись сохранена и проанализирована!</b>

📊 <b>Оценка дня:</b> {score}/10 - {mood}
💭 <b>Комментарий:</b> {comment}
🎯 <b>Рекомендация:</b> {recommendation}''',
        
        # === Сообщения об ошибках ===
        'error_processing': '❌ Произошла ошибка при обработке. Попробуйте позже.',
        'rate_limit': '🕐 Пожалуйста, подожди немного перед следующей записью.',
        'rate_limit_exceeded': '⚠️ Вы превысили лимит сообщений. Пожалуйста, подождите немного.',
        'error_generic': '❌ Произошла ошибка. Попробуйте позже.',
        'invalid_input': '🤔 Не понял твое сообщение. Пожалуйста, отправь текст или голосовое сообщение.',
        'invalid_input_type': "Пожалуйста, отправьте текстовое сообщение или голосовое сообщение.",
        'text_too_short': "Текст слишком короткий. Пожалуйста, напишите немного больше.",
        'text_too_long': "Текст слишком длинный. Пожалуйста, сократите его.",
        'voice_too_short': "Голосовое сообщение слишком короткое. Пожалуйста, запишите более длинное сообщение.",
        'voice_too_long': "Голосовое сообщение слишком длинное. Пожалуйста, запишите более короткое сообщение.",
        'validation_error_text': "Ошибка при проверке текста. Попробуйте еще раз.",
        'validation_error_voice': "Ошибка при проверке голосового сообщения. Попробуйте еще раз.",
        'validation_error_message': "Ошибка при проверке сообщения. Попробуйте еще раз.",
        'entry_delete_cancelled': "Удаление отменено.",
        'confirm_delete_entire_day_prompt': "❓ Вы уверены, что хотите удалить ВСЕ записи за {date}?",
        'btn_confirm_delete': '✅ Да, удалить',
        'btn_cancel_delete': '❌ Нет, отмена',
        'btn_confirm_delete_entry': '✅ Да, удалить запись',
        'btn_confirm_delete_day': "✅ Да, удалить день",
        'day_deleted_success': "🗑 День успешно удален.",
        'confirm_delete_entry_prompt': "❓ Вы уверены, что хотите удалить эту запись?",

        
        # === Меню и навигация ===
        'main_menu': '''🧠 <b>Твой психологический дневник</b>

Выбери действие:''',
        
        'settings_menu': '''⚙️ <b>Настройки</b>

Здесь ты можешь настроить работу дневника под себя:''',
        
        'archive_menu': '📅 <b>Архив записей</b>',
        'tasks_menu': '🎯 <b>Мои задания</b>',
        'progress_menu': '📊 <b>Мой прогресс</b>',
        
        # === Кнопки меню ===
        'btn_new_entry': '📝 Новая запись',
        'btn_archive': '📅 Архив',
        'btn_tasks': '🎯 Задания',
        'btn_progress': '📊 Прогресс',
        'btn_settings': '⚙️ Настройки',
        'btn_help': '❓ Помощь',
        'btn_back': '🔙 Назад',
        'btn_cancel': '❌ Отмена',
        
        # === Кнопки для записей ===
        'btn_text_entry': '✍️ Текстовая запись',
        'btn_voice_entry': '🎙 Голосовая запись',
        'btn_view_entry': '👁 Просмотреть',
        'btn_delete_entry': '🗑 Удалить',
        'btn_analyze_again': '🔄 Перевыполнить анализ',
        'btn_edit_entry': '✏️ Редактировать',
        'btn_view_history': '👁 Просмотреть историю',
        # === Кнопки для просмотра инсайтов и ключевых моментов ===
        'btn_view_insights': '💡 Инсайты',
        'btn_view_key_points': '📌 Ключ. моменты',
        # === Заголовки для просмотра инсайтов и ключевых моментов ===
        'header_insights': '💡 Инсайты за {date}',
        'header_key_points': '📌 Ключевые моменты за {date}',
        # === Сообщения, если данных нет ===
        'no_insights_for_day': '📭 Нет инсайтов за {date}.',
        'no_key_points_for_day': '📭 Нет ключевых моментов за {date}.',
        # === Сообщения об ошибках ===
        'error_loading_insights': '❌ Ошибка при загрузке инсайтов.',
        'error_loading_key_points': '❌ Ошибка при загрузке ключевых моментов.',
        'full_day_analysis_header': '🔬 Полный анализ дня {date}',
        'no_full_analysis_yet': '🔬 Полный анализ дня еще не выполнен. Нажмите "Пересчитать анализ дня".', 
        
        # === Настройки ===
        'settings_language': '🌍 Язык: {language}',
        'settings_notifications': '🔔 Уведомления: {status}',
        'settings_auto_analysis': '📈 Автоанализ: {status}',
        'settings_premium': '👑 Премиум: {status}',
        
        'btn_enter_city': '🏙 Ввести город',
        'language_changed': '✅ Язык успешно изменен на {language}',
        'notifications_enabled': '✅ Уведомления включены',
        'notifications_disabled': '✅ Уведомления отключены',

        'settings_timezone': '🌍 Часовой пояс: {timezone}',
        'timezone_changed': '✅ Часовой пояс успешно изменен на {timezone}',
        'timezone_not_changed': '❌ Не удалось изменить часовой пояс. Попробуйте еще раз.',
        'timezone_reminder': '''🌍 <b>Не забудьте установить свой часовой пояс!</b>

Вы все еще используете часовой пояс по умолчанию (UTC). 
Для более точной работы бота рекомендуем установить ваш местный часовой пояс в настройках.''',

        'settings_analysis_time': '⏰ Время анализа: {time}',
        'ask_analysis_time': '⏰ <b>Выберите время автоматического анализа</b>\nТекущее время: {current_time}\n\nАнализ будет запускаться каждый день в выбранное время по вашему часовому поясу.',
        'analysis_time_changed': '✅ Время автоматического анализа установлено на {time}',
        'profile_menu': '''👤 <b>Ваш профиль</b>
📝 <b>Имя:</b> {first_name}
📧 <b>Email:</b> {email}
🎂 <b>Дата рождения:</b> {date_of_birth}
🎯 <b>Увлечения:</b> {hobbies}
📌 <b>Факты о жизни:</b> {life_facts}

Выберите, что хотите изменить:''',
        'btn_edit_profile': '👤 Редактировать профиль',
        'btn_edit_name': '📝 Изменить имя',
        'btn_edit_email': '📧 Изменить email',
        'btn_edit_dob': '🎂 Изменить дату рождения',
        'btn_edit_hobbies': '🎯 Изменить увлечения',
        'btn_edit_life_facts': '📌 Изменить факты о жизни',
        'ask_new_name': '📝 <b>Введите ваше новое имя:</b>',
        'ask_new_email': '📧 <b>Введите ваш новый email:</b>',
        'ask_new_dob': '🎂 <b>Введите вашу новую дату рождения (ДД.ММ.ГГГГ):</b>',
        'ask_new_hobbies': '🎯 <b>Введите ваши увлечения через запятую:</b>',
        'ask_new_life_facts': '📌 <b>Введите факты о вашей жизни через запятую:</b>',
        'profile_updated': '✅ Профиль успешно обновлен!',
        'invalid_email_format': '❌ Неверный формат email. Попробуйте еще раз.',
        'invalid_date_format': '❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ.',
        'invalid_date_future': '❌ Дата рождения не может быть в будущем.',
        'delete_account': '🗑 Удалить аккаунт',
        'account_deletion_menu': '''🗑 <b>Удаление аккаунта</b>

Вы собираетесь удалить свой аккаунт и все связанные с ним данные.

⚠️ <b>Важно:</b>
• Это действие невозможно отменить.
• Все ваши записи, задания и персональные данные будут удалены.
• {balance_info}

Выберите действие:''',

        'account_balance_info_positive': 'На вашем балансе <b>{balance} ₽</b>. При удалении аккаунта эти средства будут утеряны.',
        'account_balance_info_zero': 'Ваш баланс пуст.',
        'account_balance_info_negative': 'У вас отрицательный баланс ({balance} ₽).',

        'btn_delete_account_and_funds': '🗑 Удалить аккаунт и средства',
        'btn_contact_support_for_refund': '📞 Связаться с поддержкой',
        'btn_cancel_deletion': '❌ Отмена',

        'confirm_account_deletion': '''❓ <b>Подтверждение удаления аккаунта</b>

Вы уверены, что хотите удалить свой аккаунт?
Это действие невозможно отменить.

После удаления:
• Все ваши данные будут удалены.
• Доступ к аккаунту будет утерян.
• {balance_warning}

Введите "УДАЛИТЬ МОЙ АККАУНТ" для подтверждения:''',

        'balance_warning_positive': 'Вы потеряете <b>{balance} ₽</b> на балансе.',
        'balance_warning_zero_or_negative': 'Все данные будут удалены.',

        'account_deletion_cancelled': '✅ Удаление аккаунта отменено.',
        'account_deletion_confirmed': '''✅ <b>Аккаунт удален</b>

Ваш аккаунт и все связанные с ним данные были успешно удалены.
Спасибо за использование нашего сервиса.''',
        'account_deletion_error': '❌ Произошла ошибка при удалении аккаунта. Пожалуйста, попробуйте позже или свяжитесь с поддержкой.',

        
        # === Сообщения для выбора часового пояса ===
        'ask_timezone_selection': '🌍 <b>Выберите свой часовой пояс</b>\n\nТекущий пояс: {current_timezone}\n\nВы можете выбрать из списка популярных поясов или ввести свой.',
        'btn_select_common_timezones': '📋 Выбрать из списка',
        'btn_enter_custom_timezone': '✍️ Ввести вручную',
        'btn_detect_timezone': '🧭 Определить автоматически', # Если будет реализовано позже
        
        # === Сообщения для списка часовых поясов ===
        'select_timezone_title': '🌍 <b>Выберите свой часовой пояс</b>\n\nТекущий пояс: {current_timezone}',
        'btn_timezone_utc': 'UTC',
        'btn_timezone_moscow': 'Europe/Moscow (MSK)',
        'btn_timezone_yekaterinburg': 'Asia/Yekaterinburg',
        'btn_timezone_omsk': 'Asia/Omsk',
        'btn_timezone_krasnoyarsk': 'Asia/Krasnoyarsk',
        'btn_timezone_irkutsk': 'Asia/Irkutsk',
        'btn_timezone_yakutsk': 'Asia/Yakutsk',
        'btn_timezone_vladivostok': 'Asia/Vladivostok',
        'btn_timezone_magadan': 'Asia/Magadan',
        # Можно добавить и другие популярные мировые пояса
        'btn_timezone_new_york': 'America/New_York (EST/EDT)',
        'btn_timezone_london': 'Europe/London (GMT/BST)',
        'btn_timezone_berlin': 'Europe/Berlin (CET/CEST)',
        'btn_timezone_tokyo': 'Asia/Tokyo (JST)',
        
        # === Сообщения для ручного ввода ===
        'ask_enter_custom_timezone': '✍️ <b>Введите свой часовой пояс</b>\n\nВведите идентификатор часового пояса (например, `Europe/Moscow`, `America/New_York`).\n\nТекущий пояс: {current_timezone}',
        'error_invalid_timezone': '❌ Неверный формат часового пояса. Пожалуйста, используйте формат `Region/City` (например, `Europe/Moscow`).',
        'error_unknown_timezone': '❌ Указанный часовой пояс не найден. Пожалуйста, проверьте введённое значение.',
        'ask_entry_edit': '📝 <b>Отредактируйте свою запись:</b>\n\n<i>Текущий текст:</i>\n{old_text}',
        'entry_updated': '✅ <b>Запись обновлена!</b>\n\n📊 <b>Оценка дня:</b> {score}/10 - {mood}\n💭 <b>Комментарий:</b> {comment}\n🎯 <b>Рекомендация:</b> {recommendation}',
        
        # === Статусы ===
        'status_enabled': 'ВКЛ',
        'status_disabled': 'ВЫКЛ',
        'status_active': 'Активен',
        'status_inactive': 'Неактивен',
        
        # === Архив ===
        'archive_empty': '📭 У тебя пока нет записей в дневнике.',
        'archive_select_year': '📅 Выбери год:',
        'archive_select_month': '📅 Выбери месяц {year}:',
        'archive_select_day': '📅 Выбери день {month}.{year}:',
        'clarification_needed': '❓ Для более точного анализа мне нужны уточнения:\n\n',
        'archive_entry': '''📅 <b>Запись от {date}</b>
        

📝 <b>Текст:</b>
{text}

📊 <b>Оценка:</b> {score}/10 - {mood}
💭 <b>Анализ:</b> {analysis}''',
        
        # === Задания ===
        'task_assigned': '''🎯 <b>Новое задание!</b>

<b>{title}</b>

{description}''',
        
        'task_completed_success': '''🎉 <b>Прекрасно!</b>

Твой ответ сохранен. Я учту это в дальнейшем анализе.

{feedback}''',
    'task_effect_analysis_result': '''🔍 <b>Анализ влияния задания</b>

{effect_description}

📊 <b>Предполагаемое влияние на настроение дня:</b> {mood_impact} балл(ов)
💭 <b>Комментарий:</b> {comment}
🎯 <b>Рекомендация:</b> {recommendation}''',

        'task_effect_analysis_started': '🔍 <i>Анализ влияния задания на ваш день запущен. Результат будет отправлен отдельно.</i>',
        'task_no_active': '📭 У тебя нет активных заданий.',
        'task_skipped': '⏭ Задание пропущено.',
        'task_deleted': '🗑 Задание удалено.',
        
        # === Кнопки заданий ===
        'btn_complete_task': '✅ Выполнить',
        'btn_skip_task': '⏭ Пропустить задание',
        'btn_delete_task': '🗑 Удалить задание',
        'btn_view_task': '👁 Посмотреть',
        'btn_cancel_task': '❌ Отменить задание',
        'task_cancelled_confirmation': '✅ Задание <b>{title}</b> было успешно отменено (удалено).',
        'task_cancelled_simple_message': '📢 Задание "<b>{title}</b>" было отменено.',
        'task_not_found_for_cancellation': '⚠️ Задание не найдено или уже было удалено.',
        'task_history_empty': '📭 История заданий пуста.',
        'error_loading_task_details': '❌ Ошибка при загрузке деталей задания.',
        'task_restored': '✅ Задание восстановлено и снова доступно!',
        'task_not_found_or_not_skipped': '❌ Задание не найдено или не является пропущенным.',
        'btn_restore_task': '🔄 Восстановить задание',

        'btn_detailed_analysis': '🔬 Детальный анализ',
        'detailed_task_analysis_header': 'Детальный анализ задания "{task_title}"',
        'task_analysis_not_found': 'Детальный анализ для этого выполнения задания пока недоступен.',
        'task_analysis_no_details': 'Детальный анализ для задания "{task_title}" не содержит информации.',
        'task_completion_not_found': 'Информация о выполнении задания не найдена.',
        'task_analysis_error': 'Ошибка при получении анализа задания.',      
        # === Прогресс ===
        'progress_title': '''📊 <b>Твой прогресс</b>

📈 <b>Уровень осознанности:</b> {awareness_level}/10
📝 <b>Всего записей:</b> {entries_count}
🎯 <b>Выполнено заданий:</b> {tasks_completed}
📅 <b>Дней подряд:</b> {streak_days}''',
        
        'progress_detailed': '''📊 <b>Подробная статистика</b>

📉 <b>Динамика настроения:</b>
{mood_chart}

🔥 <b>Частые темы:</b>
{frequent_themes}

💡 <b>Новые инсайты:</b>
{new_insights}''',
        
        # === Помощь ===
        'help_text': '''❓ <b>Помощь по дневнику</b>

📝 <b>Как вести записи:</b>
• Отправь текстовое или голосовое сообщение
• Опиши свой день честно и подробно
• Бот проанализирует твою запись

🎯 <b>Задания:</b>
• Выполняй персональные задания
• Отмечай выполнение в боте
• Получай персональную обратную связь

📊 <b>Прогресс:</b>
• Отслеживай свой рост
• Анализируй динамику
• Развивай осознанность

⚙️ <b>Настройки:</b>
• Выбери удобный язык
• Настрой уведомления
• Управляй приватностью

Нужна дополнительная помощь? Обратись к своему психологу!''',
        
        # === Оценки настроения ===
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
        
        # === Подтверждения ===
        'edit_entries_header': '📝 Редактирование записей за {date}',
        'ask_entry_edit_with_text': '📝 <b>Отредактируйте свою запись:</b>\n\n<i>Текущий текст:</i>\n<code>{old_text}</code>\n\n<i>Отправьте новый текст записи:</i>',
        'entry_updated_success': '✅ <b>Запись обновлена!</b>\n\nДля получения нового анализа нажмите "Подтвердить" в меню редактирования дня.',
        'confirm_delete_entry_yes': 'Да, удалить',
        'confirm_delete_entry_no': 'Нет, отмена',
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
        'confirm_skip_task': '❓ Ты уверен, что хочешь пропустить это задание?',
        'confirm_delete_task': '❓ Ты уверен, что хочешь удалить это задание?',
        
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

        'onboarding_welcome': '👋 Добро пожаловать в бот для ведения психологического дневника!',
        'onboarding_instruction': (
            '📝 Этот бот поможет вам вести цифровой дневник и получать по нему автоматический психологический анализ от ИИ.\n\n'
            'Основные шаги:\n'
            '1️⃣ <b>Запись:</b> Делайте записи текстом или голосом.\n'
            '2️⃣ <b>Анализ:</b> ИИ сразу анализирует вашу запись (настроение, инсайты).\n'
            '3️⃣ <b>Задания:</b> На основе анализа ИИ может предложить персональные терапевтические задания.\n'
            '4️⃣ <b>Рост:</b> Регулярное использование поможет лучше понимать себя и повышать психологическую осознанность.\n\n'
            '⚙️ Вы можете настроить бот под себя: изменить язык, установить часовой пояс, включить/выключить автоматический анализ и многое другое в разделе "Настройки".'
        ),
        'onboarding_agreement': (
            '⚠️ <b>Важно:</b>\n\n'
            'Этот бот <b>не является</b> заменой консультации с профессиональным психологом или психотерапевтом.\n\n'
            'Информация, которую вы предоставляете, анализируется ИИ. Результаты носят рекомендательный характер.\n\n'
            'Если у вас есть серьезные психологические трудности, мы настоятельно рекомендуем обратиться за помощью к квалифицированному специалисту.\n\n'
            'Вы можете в любой момент удалить все свои данные в настройках.'
        ),
        'onboarding_required': (
            '🔒 Для продолжения работы с ботом необходимо ознакомиться и согласиться с условиями использования.\n\n'
            'Пожалуйста, нажмите кнопку ниже, чтобы начать.'
        ),
        'access_denied': '🚫 Доступ ограничен. Пожалуйста, сначала ознакомьтесь и согласитесь с условиями использования.', # Для safe_answer_callback
        'onboarding_thank_you': '✅ Спасибо за согласие! Теперь вы можете пользоваться всем функционалом бота.',
        'onboarding_disagreed': (
            '❌ Вы не согласились с условиями использования.\n\n'
            'К сожалению, без согласия основной функционал бота недоступен.\n'
            'Если вы передумаете, просто отправьте команду /start, чтобы попробовать снова.'
        ),
        # === Кнопки онбординга (Новые кнопки) ===
        'btn_start_onboarding': '🚀 Начать',
        'btn_next': '➡️ Далее',
        'btn_agree': '✅ Я согласен',
        'btn_disagree': '❌ Отказаться',
        # === Сообщения анкетирования ===
        'btn_fill_questionnaire': '📋 Заполнить анкету',
        'onboarding_question_1': 'Как бы вы хотели, чтобы бот к вам обращался?',
        'onboarding_question_2': 'С какой целью вы решили вести дневник?',
        'onboarding_question_3': 'Какие 3 слова лучше всего описывают ваш характер?',
        'onboarding_question_4': 'Что для вас наиболее важно в жизни?',
        'onboarding_question_5': 'Чем вы любите заниматься в свободное время?',
        'onboarding_question_6': 'Есть ли что-то, что часто сильно влияет на ваше настроение (в положительную или отрицательную сторону)?',
        'onboarding_question_7': 'Что вы больше всего надеетесь получить от этого бота?',
        'onboarding_thank_you_for_profile': 'Спасибо за ответы! Эта информация поможет боту лучше понимать вас.',
        'onboarding_skip_questionnaire': 'Вы можете заполнить анкету позже в настройках.',
        'questionnaire_reminder': '📋 Вы еще не заполнили анкету! Это поможет боту лучше понимать вас и давать более персонализированные рекомендации. Нажмите кнопку ниже, чтобы начать.',

        # === Кнопки анкетирования ===
        'btn_skip_questionnaire': 'Пропустить анкету',
        'btn_submit_answers': 'Отправить ответы',
        
       # === Анализ недели === 
'weekly_analysis_title': '''📈 <b>Анализ недели</b>
Неделя: {week_start_date} - {week_end_date}
Уровень осознанности: {awareness_level}/10
''',
'weekly_analysis_summary': '''🧠 <b>Резюме недели:</b>
{summary_text}
''',
'weekly_analysis_progress': '''📊 <b>Прогресс:</b>
Тренд настроения: {mood_trend_display}
{progress_notes}
''',
'weekly_analysis_stats': '''📈 <b>Статистика:</b>
• Записей: {total_entries}
• Дней подряд (на неделе): {streak_days_current}
• Среднее настроение: {avg_mood_score}
• Заданий назначено: {tasks_assigned}
• Заданий выполнено: {tasks_completed}
''',
'weekly_analysis_no_data': '📭 Нет данных для отображения за эту неделю.',
'weekly_analysis_not_found': 'Анализ за эту неделю еще не выполнен.',
'weekly_analysis_comparison': '''⚖️ <b>Сравнение с предыдущей неделей:</b>
{progress_comment}
''',
'weekly_analysis_comparison_mood': 'Настроение: {mood_comparison}',
'weekly_analysis_comparison_consistency': 'Регулярность: {consistency_comparison}',

# Новые кнопки
'btn_weekly_details': '🔬 Анализ недели',
'btn_next_week': '⏭ След. неделя',
'btn_prev_week': '⏮ Пред. неделя',
'btn_weekly_progress': '📊 Прогресс по неделям', # Кнопка в основном меню "Прогресс"

'btn_user_profile': '👤 Профиль',
'btn_view_psychology_profile': '🧠 Психологический портрет',
'error_generic': '❗ Произошла ошибка. Пожалуйста, попробуйте позже.',
    },
    'en': {
        # ===Greetings and main messages ===
        'welcome': '''🧠 <b>Hi! This is your psychological diary.</b>

Here you can keep records of your days, and I will help you understand your emotions and thoughts.

I will be your digital psychologist who will remember your features and understand you better each day.

Let's start?''',
        
        'welcome_back': '👋 Welcome back, {username}! Good to see you again.',
        
        # === Creating entries ===
        'ask_entry': '📝 <b>Tell me how your day went...</b>',
        'ask_voice_entry': '🎙 <b>Send a voice message about your day...</b>',
        'processing': '⏳ <i>Processing your entry...</i>',
        'entry_saved': '''✅ <b>Entry saved and analyzed!</b>

📊 <b>Day score:</b> {score}/10 - {mood}
💭 <b>Comment:</b> {comment}
🎯 <b>Recommendation:</b> {recommendation}''',
        
        # === Error messages ===
        'error_processing': '❌ An error occurred during processing. Please try again later.',
        'rate_limit': '🕐 Please wait a moment before your next entry.',
        'rate_limit_exceeded': '⚠️ You have exceeded the message limit. Please wait a moment.',
        'error_generic': '❌ An error occurred. Please try again later.',
        'invalid_input': '🤔 I didn\'t understand your message. Please send text or voice message.',
        'invalid_input_type': "Please send a text message or a voice message.",
        'text_too_short': "The text is too short. Please write a bit more.",
        'text_too_long': "The text is too long. Please shorten it.",
        'voice_too_short': "The voice message is too short. Please record a longer message.",
        'voice_too_long': "The voice message is too long. Please record a shorter message.",
        'validation_error_text': "Error validating text. Please try again.",
        'validation_error_voice': "Error validating voice message. Please try again.",
        'validation_error_message': "Error validating message. Please try again.",
        'confirm_delete_entire_day_prompt': "❓ Are you sure you want to delete ALL entries for {date}?",
        'btn_confirm_delete': '✅ Yes, delete',
        'btn_cancel_delete': '❌ No, cancel',
        'btn_confirm_delete_entry': '✅ Yes, delete entry',
        'btn_confirm_delete_day': "✅ Yes, delete the day",
        'day_deleted_success': "🗑 Day successfully deleted.",
    
        # Для обработки удаления
        'entry_delete_cancelled': "Deletion cancelled.",
        
        # === Menu and navigation ===
        'main_menu': '''🧠 <b>Your psychological diary</b>

Choose an action:''',
        
        'settings_menu': '''⚙️ <b>Settings</b>

Here you can customize the diary for yourself:''',
        
        'archive_menu': '📅 <b>Entry archive</b>',
        'tasks_menu': '🎯 <b>My tasks</b>',
        'progress_menu': '📊 <b>My progress</b>',
        
        # === Menu buttons ===
        'btn_new_entry': '📝 New entry',
        'btn_archive': '📅 Archive',
        'btn_tasks': '🎯 Tasks',
        'btn_progress': '📊 Progress',
        'btn_settings': '⚙️ Settings',
        'btn_help': '❓ Help',
        'btn_back': '🔙 Back',
        'btn_cancel': '❌ Cancel',
        
        # === Entry buttons ===
        'btn_text_entry': '✍️ Text entry',
        'btn_voice_entry': '🎙 Voice entry',
        'btn_view_entry': '👁 View',
        'btn_delete_entry': '🗑 Delete',
        'btn_analyze_again': '🔄 Re-analyze',
        'btn_edit_entry': '✏️ Edit',
        'btn_view_history': '👁 View history',
        # === Buttons for viewing insights and key points ===
        'btn_view_insights': '💡 Insights',
        'btn_view_key_points': '📌 Key Points',
        # === Headers for viewing insights and key points ===
        'header_insights': '💡 Insights for {date}',
        'header_key_points': '📌 Key Points for {date}',
        # === Messages if no data ===
        'no_insights_for_day': '📭 No insights for {date}.',
        'no_key_points_for_day': '📭 No key points for {date}.',
        # === Error messages ===
        'error_loading_insights': '❌ Error loading insights.',
        'error_loading_key_points': '❌ Error loading key points.',
        'full_day_analysis_header': '🔬 Full Day Analysis for {date}',
        'no_full_analysis_yet': '🔬 Full day analysis has not been performed yet. Click "Recalculate day analysis".',
        
        # === Settings ===
        'settings_language': '🌍 Language: {language}',
        'settings_notifications': '🔔 Notifications: {status}',
        'settings_auto_analysis': '📈 Auto-analysis: {status}',
        'settings_premium': '👑 Premium: {status}',
        
        'language_changed': '✅ Language successfully changed to {language}',
        'notifications_enabled': '✅ Notifications enabled',
        'notifications_disabled': '✅ Notifications disabled',

        'btn_enter_city': '🏙 Enter city',
        'settings_timezone': '🌍 Timezone: {timezone}',
        'timezone_changed': '✅ Timezone successfully changed to {timezone}',
        'timezone_not_changed': '❌ Failed to change timezone. Please try again.',
        'timezone_reminder': '''🌍 <b>Don't forget to set your timezone!</b>

You are still using the default timezone (UTC). 
For more accurate bot operation, we recommend setting your local timezone in the settings.''',

        'settings_analysis_time': '⏰ Analysis time: {time}',
        'ask_analysis_time': '⏰ <b>Select automatic analysis time</b>\nCurrent time: {current_time}\n\nAnalysis will run daily at the selected time according to your timezone.',
        'analysis_time_changed': '✅ Automatic analysis time set to {time}',
        'profile_menu': '''👤 <b>Your Profile</b>
📝 <b>Name:</b> {first_name}
📧 <b>Email:</b> {email}
🎂 <b>Date of Birth:</b> {date_of_birth}
🎯 <b>Hobbies:</b> {hobbies}
📌 <b>Life Facts:</b> {life_facts}

Choose what you want to change:''',
        'btn_edit_profile': '👤 Edit Profile',
        'btn_edit_name': '📝 Edit Name',
        'btn_edit_email': '📧 Edit Email',
        'btn_edit_dob': '🎂 Edit Date of Birth',
        'btn_edit_hobbies': '🎯 Edit Hobbies',
        'btn_edit_life_facts': '📌 Edit Life Facts',
        'ask_new_name': '📝 <b>Enter your new name:</b>',
        'ask_new_email': '📧 <b>Enter your new email:</b>',
        'ask_new_dob': '🎂 <b>Enter your new date of birth (DD.MM.YYYY):</b>',
        'ask_new_hobbies': '🎯 <b>Enter your hobbies separated by commas:</b>',
        'ask_new_life_facts': '📌 <b>Enter facts about your life separated by commas:</b>',
        'profile_updated': '✅ Profile updated successfully!',
        'invalid_email_format': '❌ Invalid email format. Please try again.',
        'invalid_date_format': '❌ Invalid date format. Use DD.MM.YYYY.',
        'invalid_date_future': '❌ Date of birth cannot be in the future.',
        'delete_account': '🗑 Delete account',
        'account_deletion_menu': '''🗑 <b>Account Deletion</b>

You are about to delete your account and all associated data.

⚠️ <b>Important:</b>
• This action cannot be undone.
• All your entries, tasks, and personal data will be deleted.
• {balance_info}

Choose an action:''',

        'account_balance_info_positive': 'Your balance is <b>{balance} RUB</b>. These funds will be lost if you delete your account.',
        'account_balance_info_zero': 'Your balance is zero.',
        'account_balance_info_negative': 'You have a negative balance of {balance} RUB.',

        'btn_delete_account_and_funds': '🗑 Delete Account and Funds',
        'btn_contact_support_for_refund': '📞 Contact Support',
        'btn_cancel_deletion': '❌ Cancel',

        'confirm_account_deletion': '''❓ <b>Confirm Account Deletion</b>

Are you sure you want to delete your account?
This action cannot be undone.

After deletion:
• All your data will be deleted.
• Access to the account will be lost.
• {balance_warning}

Type "DELETE MY ACCOUNT" to confirm:''',

        'balance_warning_positive': 'You will lose <b>{balance} RUB</b> from your balance.',
        'balance_warning_zero_or_negative': 'All data will be deleted.',

        'account_deletion_cancelled': '✅ Account deletion cancelled.',
        'account_deletion_confirmed': '''✅ <b>Account Deleted</b>

Your account and all associated data have been successfully deleted.
Thank you for using our service.''',
        'account_deletion_error': '❌ An error occurred while deleting the account. Please try again later or contact support.',
        
        # === Messages for timezone selection ===
        'ask_timezone_selection': '🌍 <b>Select your timezone</b>\n\nCurrent timezone: {current_timezone}\n\nYou can choose from a list of popular timezones or enter your own.',
        'btn_select_common_timezones': '📋 Select from list',
        'btn_enter_custom_timezone': '✍️ Enter manually',
        'btn_detect_timezone': '🧭 Detect automatically', # If implemented later
        
        # === Messages for timezone list ===
        'select_timezone_title': '🌍 <b>Select your timezone</b>\n\nCurrent timezone: {current_timezone}',
        'btn_timezone_utc': 'UTC',
        'btn_timezone_moscow': 'Europe/Moscow (MSK)',
        'btn_timezone_yekaterinburg': 'Asia/Yekaterinburg',
        'btn_timezone_omsk': 'Asia/Omsk',
        'btn_timezone_krasnoyarsk': 'Asia/Krasnoyarsk',
        'btn_timezone_irkutsk': 'Asia/Irkutsk',
        'btn_timezone_yakutsk': 'Asia/Yakutsk',
        'btn_timezone_vladivostok': 'Asia/Vladivostok',
        'btn_timezone_magadan': 'Asia/Magadan',
        # Add other popular world timezones
        'btn_timezone_new_york': 'America/New_York (EST/EDT)',
        'btn_timezone_london': 'Europe/London (GMT/BST)',
        'btn_timezone_berlin': 'Europe/Berlin (CET/CEST)',
        'btn_timezone_tokyo': 'Asia/Tokyo (JST)',
        
        # === Messages for manual entry ===
        'ask_enter_custom_timezone': '✍️ <b>Enter your timezone</b>\n\nEnter the timezone identifier (e.g., `Europe/Moscow`, `America/New_York`).\n\nCurrent timezone: {current_timezone}',
        'error_invalid_timezone': '❌ Invalid timezone format. Please use the `Region/City` format (e.g., `Europe/Moscow`).',
        'error_unknown_timezone': '❌ The specified timezone was not found. Please check the entered value.',  
        'ask_entry_edit': '📝 <b>Edit your entry:</b>\n\n<i>Current text:</i>\n{old_text}', 
        'entry_updated': '✅ <b>Entry updated!</b>\n\n📊 <b>Day score:</b> {score}/10 - {mood}\n💭 <b>Comment:</b> {comment}\n🎯 <b>Recommendation:</b> {recommendation}',     
        # === Statuses ===
        'status_enabled': 'ON',
        'status_disabled': 'OFF',
        'status_active': 'Active',
        'status_inactive': 'Inactive',
        
        # === Archive ===
        'archive_empty': '📭 You don\'t have any diary entries yet.',
        'archive_select_year': '📅 Select year:',
        'archive_select_month': '📅 Select month {year}:',
        'archive_select_day': '📅 Select day {month}.{year}:',
        'clarification_needed': '❓ I need clarifications for a more accurate analysis:\n\n',
        'archive_entry': '''📅 <b>Entry from {date}</b>
        

📝 <b>Text:</b>
{text}

📊 <b>Score:</b> {score}/10 - {mood}
💭 <b>Analysis:</b> {analysis}''',
        
        # === Tasks ===
        'task_assigned': '''🎯 <b>New task!</b>

<b>{title}</b>

{description}''',
        
        'task_completed_success': '''🎉 <b>Perfect!</b>

Your response is saved. I will consider this in future analysis.

{feedback}''',
    'task_effect_analysis_result': '''🔍 <b>Task Impact Analysis</b>

{effect_description}

📊 <b>Estimated impact on daily mood:</b> {mood_impact} point(s)
💭 <b>Comment:</b> {comment}
🎯 <b>Recommendation:</b> {recommendation}''',

        'task_effect_analysis_started': '🔍 <i>The analysis of the task\'s impact on your day has started. The result will be sent separately.</i>',
        'task_no_active': '📭 You have no active tasks.',
        'task_skipped': '⏭ Task skipped.',
        'task_deleted': '🗑 Task deleted.',
        
        # === Task buttons ===
        'btn_complete_task': '✅ Complete',
        'btn_skip_task': '⏭ Skip task',
        'btn_delete_task': '🗑 Delete task',
        'btn_view_task': '👁 View',
        'btn_cancel_task': '❌ Cancel Task',
        'task_cancelled_confirmation': '✅ The task "<b>{title}</b>" has been successfully canceled (deleted).',
        'task_cancelled_simple_message': '📢 The task "<b>{title}</b>" has been canceled.',
        'task_not_found_for_cancellation': '⚠️ Task not found or has already been deleted.',
        'task_history_empty': '📭 Task history is empty.',
        'error_loading_task_details': '❌ Error loading task details.',
        'task_restored': '✅ Task restored and available again!',
        'task_not_found_or_not_skipped': '❌ Task not found or is not skipped.',
        'btn_restore_task': '🔄 Restore Task',

        'btn_detailed_analysis': '🔬 Detailed Analysis',
        'detailed_task_analysis_header': 'Detailed Analysis for Task "{task_title}"',
        'task_analysis_not_found': 'Detailed analysis for this task completion is not available yet.',
        'task_analysis_no_details': 'Detailed analysis for task "{task_title}" contains no information.',
        'task_completion_not_found': 'Task completion information not found.',
        'task_analysis_error': 'Error retrieving task analysis.',
        # === Progress ===
        'progress_title': '''📊 <b>Your progress</b>

📈 <b>Awareness level:</b> {awareness_level}/10
📝 <b>Total entries:</b> {entries_count}
🎯 <b>Tasks completed:</b> {tasks_completed}
📅 <b>Day streak:</b> {streak_days}''',
        
        'progress_detailed': '''📊 <b>Detailed statistics</b>

📉 <b>Mood dynamics:</b>
{mood_chart}

🔥 <b>Frequent themes:</b>
{frequent_themes}

💡 <b>New insights:</b>
{new_insights}''',
        
        # === Help ===
        'help_text': '''❓ <b>Diary help</b>

📝 <b>How to keep entries:</b>
• Send text or voice message
• Describe your day honestly and in detail
• Bot will analyze your entry

🎯 <b>Tasks:</b>
• Complete personal tasks
• Mark completion in bot
• Get personal feedback

📊 <b>Progress:</b>
• Track your growth
• Analyze dynamics
• Develop awareness

⚙️ <b>Settings:</b>
• Choose convenient language
• Set up notifications
• Manage privacy

Need more help? Contact your psychologist!''',
        
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
        'confirm_skip_task': '❓ Are you sure you want to skip this task?',
        'confirm_delete_task': '❓ Are you sure you want to delete this task?',
        
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

        'onboarding_welcome': '👋 Welcome to the psychological diary bot!',
        'onboarding_instruction': (
            '📝 This bot helps you keep a digital diary and get automatic psychological analysis from AI.\n\n'
            'Main steps:\n'
            '1️⃣ <b>Entry:</b> Make entries by text or voice.\n'
            '2️⃣ <b>Analysis:</b> AI instantly analyzes your entry (mood, insights).\n'
            '3️⃣ <b>Tasks:</b> Based on the analysis, AI can offer personalized therapeutic tasks.\n'
            '4️⃣ <b>Growth:</b> Regular use will help you understand yourself better and increase psychological mindfulness.\n\n'
            '⚙️ You can customize the bot: change the language, set the timezone, enable/disable automatic analysis, and much more in the "Settings" section.'
        ),
        'onboarding_agreement': (
            '⚠️ <b>Important:</b>\n\n'
            'This bot is <b>not a substitute</b> for a consultation with a professional psychologist or psychotherapist.\n\n'
            'The information you provide is analyzed by AI. The results are for informational purposes only.\n\n'
            'If you have serious psychological difficulties, we strongly recommend that you seek help from a qualified specialist.\n\n'
            'You can delete all your data at any time in the settings.'
        ),
        'onboarding_required': (
            '🔒 To continue using the bot, you must read and agree to the terms of use.\n\n'
            'Please click the button below to begin.'
        ),
        'access_denied': '🚫 Access is restricted. Please read and agree to the terms of use first.', # For safe_answer_callback
        'onboarding_thank_you': '✅ Thank you for your agreement! You can now use all the bot\'s features.',
        'onboarding_disagreed': (
            '❌ You did not agree to the terms of use.\n\n'
            'Unfortunately, without agreement, the main functionality of the bot is unavailable.\n'
            'If you change your mind, just send the /start command to try again.'
        ),
        # === Onboarding Buttons (New Buttons) ===
        'btn_start_onboarding': '🚀 Start',
        'btn_next': '➡️ Next',
        'btn_agree': '✅ I Agree',
        'btn_disagree': '❌ Disagree',
        # === Questionnaire Messages ===
        'btn_fill_questionnaire': '📋 Fill Questionnaire',
        'onboarding_question_1': 'What would you like the bot to call you?',
        'onboarding_question_2': 'What is your purpose for keeping a diary?',
        'onboarding_question_3': 'What 3 words best describe your personality?',
        'onboarding_question_4': 'What is most important to you in life?',
        'onboarding_question_5': 'What do you like to do in your free time?',
        'onboarding_question_6': 'Is there something that often strongly affects your mood (positively or negatively)?',
        'onboarding_question_7': 'What do you most hope to get out of this bot?',
        'onboarding_thank_you_for_profile': 'Thank you for your answers! This information will help the bot understand you better.',
        'onboarding_skip_questionnaire': 'You can fill out the questionnaire later in the settings.',
        'questionnaire_reminder': '📋 You haven\'t filled out the questionnaire yet! This will help the bot understand you better and provide more personalized recommendations. Click the button below to start.',
       
        # === Questionnaire Buttons ===
        'btn_skip_questionnaire': 'Skip Questionnaire',
        'btn_submit_answers': 'Submit Answers',

'weekly_analysis_title': '''📈 <b>Weekly Analysis</b>
Week: {week_start_date} - {week_end_date}
Awareness Level: {awareness_level}/10
''',
'weekly_analysis_summary': '''🧠 <b>Week Summary:</b>
{summary_text}
''',
'weekly_analysis_progress': '''📊 <b>Progress:</b>
Mood Trend: {mood_trend_display}
{progress_notes}
''',
'weekly_analysis_stats': '''📈 <b>Statistics:</b>
• Entries: {total_entries}
• Streak Days (this week): {streak_days_current}
• Avg. Mood Score: {avg_mood_score}
• Tasks Assigned: {tasks_assigned}
• Tasks Completed: {tasks_completed}
''',
'weekly_analysis_no_data': '📭 No data to display for this week.',
'weekly_analysis_not_found': 'Analysis for this week has not been performed yet.',
'weekly_analysis_comparison': '''⚖️ <b>Comparison with Previous Week:</b>
{progress_comment}
''',
'weekly_analysis_comparison_mood': 'Mood: {mood_comparison}',
'weekly_analysis_comparison_consistency': 'Consistency: {consistency_comparison}',

# Новые кнопки
'btn_weekly_details': '🔬 Weekly Analysis',
'btn_next_week': '⏭ Next Week',
'btn_prev_week': '⏮ Prev. Week',
'btn_weekly_progress': '📊 Weekly Progress', # Кнопка в основном меню "Прогресс"

'btn_user_profile': '👤 Profile',
'btn_view_psychology_profile': '🧠 Psychological Portrait',
'error_generic': '❗ An error occurred. Please try again later.',
    }
}

MESSAGES['ru'].update({
    # === Сообщения для заданий ===
    'ask_task_completion_with_context': '''Выполняется задание: <b>{title}</b>\n\n{description}\n\nПожалуйста, опишите, как ты выполнял это задание

- Что именно ты сделал?
- Какие шаги предпринял?
- Что было сложным или легким?''',
    
    'ask_feelings_description': '''💭 <b>Опиши свои ощущения при выполнении задания</b>

Расскажи, что ты чувствовал во время выполнения:
- Какие эмоции испытывал?
- Что тебе понравилось?
- Что было трудным?''',
    
    'task_completed_success': '''🎉 <b>Прекрасно! Задание выполнено!</b>

Твой ответ сохранен и проанализирован.

📊 <b>Оценка выполнения:</b> {score}/10 - {mood}
💭 <b>Комментарий:</b> {comment}
🎯 <b>Рекомендация:</b> {recommendation}''',
    
    'task_processing': '⏳ <i>Анализирую вашу запись и влияние выполненного задания...</i>',
    'task_completion_saved': '✅ <b>Выполнение задания сохранено!</b>',
    'task_completion_analysis': '🧠 <b>Анализ выполнения задания</b>\n\n{analysis}',
    'task_completion_recommendation': '🎯 <b>Рекомендация:</b> {recommendation}',
    
    # === Сообщения для ошибок заданий ===
    'task_not_found': '❌ Задание не найдено или не принадлежит вам.',
    'task_already_completed': '✅ Задание уже выполнено.',
    'task_already_skipped': '⏭ Задание уже пропущено.',
    'task_deleted': '🗑 Задание удалено.',
    'task_skipped': '⏭ Задание пропущено.',
    'task_delete_cancelled': '❌ Удаление задания отменено.',
    'task_skip_cancelled': '❌ Пропуск задания отменено.',
    
    # === Сообщения подтверждения ===
    'confirm_delete_task': '❓ Ты уверен, что хочешь удалить это задание?',
    'confirm_skip_task': '❓ Ты уверен, что хочешь пропустить это задание?',
    'confirm_complete_task': '❓ Ты уверен, что хочешь отметить это задание как выполненное?',
    
    # === Кнопки заданий ===
    'btn_complete_task': '✅ Выполнить',
    'btn_view_task': '👁 Посмотреть',
    'btn_task_history': '📜 История заданий',
    'btn_active_tasks': '🎯 Активные задания',
    
    # === Статусы заданий ===
    'task_status_pending': 'Ожидает',
    'task_status_in_progress': 'В процессе',
    'task_status_completed': 'Выполнена',
    'task_status_skipped': 'Пропущена',
    'task_status_expired': 'Просрочена',
    
    # === Типы заданий ===
    'task_type_daily': 'Ежедневная',
    'task_type_reflection': 'Рефлексивная',
    'task_type_cognitive': 'Когнитивная',
    'task_type_creative': 'Творческая',
    'task_type_behavioral': 'Поведенческая',
    'task_type_mindfulness': 'Осознанность',
})

# Добавим в MESSAGES['en']:

MESSAGES['en'].update({
    # === Task messages ===
    'ask_task_completion_with_context': '''Completing task: <b>{title}</b>\n\n{description}\n\nPlease describe how you completed this task

Now describe how you completed this task:
- What exactly did you do?
- What steps did you take?
- What was difficult or easy?''',
    
    'ask_feelings_description': '''💭 <b>Describe your feelings during task completion</b>

Tell me what you felt while completing:
- What emotions did you experience?
- What did you enjoy?
- What was difficult?''',
    
    'task_completed_success': '''🎉 <b>Perfect! Task completed!</b>

Your response is saved and analyzed.

📊 <b>Completion score:</b> {score}/10 - {mood}
💭 <b>Comment:</b> {comment}
🎯 <b>Recommendation:</b> {recommendation}''',
    
    'task_processing': '⏳ <i>Analyzing your entry and the impact of the completed task...</i>',
    'task_completion_saved': '✅ <b>Task completion saved!</b>',
    'task_completion_analysis': '🧠 <b>Task completion analysis</b>\n\n{analysis}',
    'task_completion_recommendation': '🎯 <b>Recommendation:</b> {recommendation}',
    
    # === Task error messages ===
    'task_not_found': '❌ Task not found or does not belong to you.',
    'task_already_completed': '✅ Task already completed.',
    'task_already_skipped': '⏭ Task already skipped.',
    'task_deleted': '🗑 Task deleted.',
    'task_skipped': '⏭ Task skipped.',
    'task_delete_cancelled': '❌ Task deletion cancelled.',
    'task_skip_cancelled': '❌ Task skip cancelled.',
    
    # === Confirmation messages ===
    'confirm_delete_task': '❓ Are you sure you want to delete this task?',
    'confirm_skip_task': '❓ Are you sure you want to skip this task?',
    'confirm_complete_task': '❓ Are you sure you want to mark this task as completed?',
    
    # === Task buttons ===
    'btn_complete_task': '✅ Complete',
    'btn_view_task': '👁 View',
    'btn_task_history': '📜 Task history',
    'btn_active_tasks': '🎯 Active tasks',
    
    # === Task statuses ===
    'task_status_pending': 'Pending',
    'task_status_in_progress': 'In progress',
    'task_status_completed': 'Completed',
    'task_status_skipped': 'Skipped',
    'task_status_expired': 'Expired',
    
    # === Task types ===
    'task_type_daily': 'Daily',
    'task_type_reflection': 'Reflection',
    'task_type_cognitive': 'Cognitive',
    'task_type_creative': 'Creative',
    'task_type_behavioral': 'Behavioral',
    'task_type_mindfulness': 'Mindfulness',
})

# Добавляем сообщения помощи в основной словарь
MESSAGES['ru'].update(HELP_MESSAGES['ru'])
MESSAGES['en'].update(HELP_MESSAGES['en'])



# Функция для получения сообщения по ключу и языку
def get_message(key: str, language: str = 'ru', **kwargs) -> str:
    """
    Получение сообщения по ключу и языку с подстановкой параметров
    """
    logger.info("=== GET_MESSAGE ===")
    logger.info(f"Ключ: {key}")
    logger.info(f"Язык: {language}")
    logger.info(f"Параметры: {kwargs}")
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

# Функция для получения текста кнопки
def get_button_text(key: str, language: str = 'ru') -> str:
    """
    Получение текста кнопки по ключу и языку
    """
    return get_message(key, language)

# Функция для получения оценки настроения
def get_mood_text(score: int, language: str = 'ru') -> str:
    """
    Получение текстового описания оценки настроения
    """
    key = f'mood_{score}'
    return get_message(key, language)

# Функция для получения статуса
def get_status_text(status: bool, language: str = 'ru') -> str:
    """
    Получение текста статуса (вкл/выкл)
    """
    if status:
        return get_message('status_enabled', language=language)
    else:
        return get_message('status_disabled', language=language)