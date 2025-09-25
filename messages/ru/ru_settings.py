SETTINGS_MESSAGES_RU = {
    'ru': {  
        'settings_menu': '''⚙️ <b>Настройки</b>

Здесь ты можешь настроить работу дневника под себя:''',      
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

        'enter_city': '''🏙 <b>Введите название вашего города</b>\nНапример: Москва, Санкт-Петербург, Новосибирск''',
        'please_enter_city': '''Пожалуйста, введите название города''',
        'timezone_found': '''🏙 Найден часовой пояс для города <b>{city_name}</b>, <b>{country}</b>:\n\n🕒 <code>{timezone}</code>''',
        'searching_timezone': '''⏳ Ищу часовой пояс для указанного города...''',
        'timezone_error': '''Ошибка при определении часового пояса''',
        'city_not_found': '''Город не найден''',
        'multiple_cities_found': '''🏙 Найдено несколько вариантов. Выберите правильный:''',
        'selection_failed': '''❌ Не удалось получить варианты выбора''',
        'timezone_detection_failed': '''❌ Не удалось определить часовой пояс''',
        'invalid_timezone': '''❌ Определен неверный часовой пояс''',
        'wrong_timezone': '''❌ Неверный часовой пояс''',
        'current_hobbies': '''\n\n<i>Текущие увлечения:</i> <code>{current_hobbies}</code>''',
        'current_facts': '''\n\n<i>Текущие факты:</i> <code>{current_facts}</code>''',
        'delete_account_btn': '''УДАЛИТЬ МОЙ АККАУНТ''',
        'invalid_confirmation_text': '''❌ Неверный текст подтверждения. Пожалуйста, введите точную фразу.''',
        'btn_subscribe': '''💳 Подписаться'''
    }
}