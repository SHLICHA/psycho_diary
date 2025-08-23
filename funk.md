📁 bot/handlers/diary.py
[handlers][new_entry] - Создание новой записи (предложение ввести текст/голос)
[handlers][process_text_entry] - Обработка текстовой записи
[handlers][process_voice_entry] - Обработка голосовой записи
[handlers][handle_invalid_entry_type] - Обработка недопустимого типа сообщения
[handlers][cancel_entry] - Отмена создания записи
[handlers][show_archive] - Показ архива записей с умным календарем
[handlers][prev_month] - Переход к предыдущему месяцу календаря
[handlers][next_month] - Переход к следующему месяцу календаря
[handlers][open_year_selector] - Открытие селектора года
[handlers][select_year] - Выбор года (показ календаря года)
[handlers][open_month_selector] - Открытие селектора месяцев
[handlers][select_specific_month] - Выбор конкретного месяца
[handlers][return_to_month] - Возврат к конкретному месяцу календаря
[handlers][select_day] - Выбор дня в календаре (показ записей)
[handlers][delete_selected_entry] - Удаление выбранной записи
[handlers][handle_empty_calendar_button] - Обработка пустых кнопок календаря
[handlers][back_to_calendar] - Возврат к календарю после просмотра записи
[handlers][view_entry_history] - Просмотр истории записей за день
[handlers][view_specific_entry] - Просмотр конкретной записи из истории
[handlers][edit_entry] - Редактирование записи за день
[handlers][edit_specific_entry] - Редактирование конкретной записи
[handlers][process_entry_edit] - Обработка отредактированной записи
[handlers][delete_entry] - Удаление записи за день
[handlers][delete_specific_entry] - Удаление конкретной записи
[handlers][confirm_delete_entry] - Подтверждение удаления записи
[handlers][cancel_delete_entry] - Отмена удаления записи

📁 bot/keyboards/calendar_keyboards.py
[keyboards][get_smart_calendar_keyboard] - Получение умного календаря с фокусом на текущий месяц
[keyboards][get_month_calendar_with_navigation] - Получение календаря месяца с навигацией
[keyboards][get_year_selection_keyboard] - Клавиатура выбора года
[keyboards][get_month_selection_keyboard] - Клавиатура выбора месяца
[keyboards][get_basic_calendar_keyboard] - Базовый календарь на случай ошибок
[keyboards][get_entry_view_keyboard] - Клавиатура для просмотра записи с кнопкой возврата к календарю
[keyboards][get_specific_entry_view_keyboard] - Клавиатура просмотра конкретной записи
[keyboards][get_entry_history_keyboard] - Клавиатура истории записей за день
[keyboards][get_confirm_delete_keyboard] - Клавиатура подтверждения удаления записи
[keyboards][get_back_to_calendar_keyboard] - Клавиатура возврата к календарю

📁 bot/services/diary_service.py
[services][diary_service] - Сервис для работы с записями дневника
[services][create_text_entry] - Создание текстовой записи
[services][create_voice_entry] - Создание голосовой записи
[services][get_user_entries_for_date] - Получение записей пользователя за дату
[services][get_combined_entry_text] - Получение объединенного текста записей
[services][delete_entry] - Удаление записи
[services][get_days_with_entries] - Получение дней с записями

📁 bot/handlers/tasks.py
[handlers][show_tasks] - Показ текущих заданий с пагинацией
[handlers][paginate_tasks] - Пагинация между заданиями
[handlers][view_specific_task] - Просмотр конкретного задания
[handlers][start_task_completion] - Начало выполнения задания
[handlers][process_task_completion] - Обработка выполнения задания
[handlers][process_feelings_description] - Обработка описания ощущений
[handlers][skip_task] - Пропуск задания
[handlers][delete_task] - Удаление задания
[handlers][confirm_delete_task] - Подтверждение удаления задания
[handlers][cancel_delete_task] - Отмена удаления задания
[handlers][view_task_history] - Просмотр истории заданий
[handlers][view_completed_task] - Просмотр выполненного задания

📁 bot/keyboards/tasks_keyboard.py
[keyboards][get_tasks_main_keyboard] - Главная клавиатура заданий
[keyboards][get_task_pagination_keyboard] - Клавиатура действий с заданием с пагинацией
[keyboards][get_task_detail_keyboard] - Клавиатура просмотра деталей задания
[keyboards][get_task_completion_keyboard] - Клавиатура выполнения задания
[keyboards][get_confirm_delete_task_keyboard] - Клавиатура подтверждения удаления задания
[keyboards][get_task_analysis_keyboard] - Клавиатура анализа выполнения задания
[keyboards][get_task_history_keyboard] - Клавиатура истории заданий