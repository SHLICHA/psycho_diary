TASKS_MESSAGES_RU = {
    'ru': {  
        'task_assigned': '''\n🎯 <b>Новое задание!</b>

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
        'btn_try_again': '''🔄 Попробовать снова''',
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

        'task_history_detail': '''📝 <b>Задание: {title}</b>
🕒 <b>Назначено:</b> {assigned_at}
{completed_at}
📊 <b>Статус:</b> {status}

<b>Описание:</b>
{description}

<b>Выполнение:</b>
{completion_text}

<b>Ощущения:</b>
{feelings_text}''',
        
        'completion_not_found': 'Выполнение не найдено',
        'feelings_not_found': 'Ощущения не найдены',
        'completion_text_missing': 'Текст выполнения отсутствует',
        'feelings_text_missing': 'Описание ощущений отсутствует',
        'completion_load_error': 'Ошибка при загрузке выполнения',
        'feelings_load_error': 'Ошибка при загрузке ощущений',
        'error_loading_task_details': 'Ошибка при загрузке деталей задания',
        'task_completed_at': '''✅ <b>Завершено:</b> {completed_at}''',
        'no_effect_description': '''Нет описания эффекта''',
        'task_summary': '{task_count} незавершенных задач.', # или '1 незавершенная задача', '2 незавершенные задачи', и т.д. - но для простоты используем общий вариант
        'task_summary_single': '1 незавершенная задача.',
        'task_summary_few': '{task_count} незавершенные задачи.',
        'task_summary_many': '{task_count} незавершенных задач.',
        'task_summary_zero': '',
        'task_completion_invalid': '''❌ <b>Задание не засчитано</b>

Причина: {validation_comment}

Пожалуйста, выполните задание более подробно и содержательно.''',

    'settings_tasks_limit': 'Лимит заданий: {limit}',
    'task_settings_menu': 'Настройки заданий\n\nМаксимум заданий в день: {max_tasks}',
    'tasks_limit_increased': 'Лимит заданий увеличен до {new_limit}',
    'tasks_limit_decreased': 'Лимит заданий уменьшен до {new_limit}',
    'tasks_limit_max_reached': 'Достигнут максимальный лимит заданий',
    'tasks_limit_min_reached': 'Достигнут минимальный лимит заданий',

    'task_completion_invalid_formatted': '''<b>⚠️ Нужно немного доработать</b>\n\n{validation_comment}\n\n<i>Попробуй описать выполнение задания более подробно - что именно ты делал, какие мысли и чувства возникали.</i>''',
    'task_effect_analysis_result_formatted': '''<b>🎯 Результат выполнения задания</b>\n\n💫 <b>Эффект:</b> {effect_description}\n\n😊 <b>Влияние на настроение:</b> {mood_impact}\n\n💭 <b>Комментарий:</b> {comment}\n\n🌟 <b>Рекомендация:</b> {recommendation}\n\n<i>Ты отлично справился с заданием! Продолжай в том же духе! 💪</i>''',
    'task_analysis_error_formatted': '''<b>❌ Произошла ошибка</b>\n\nК сожалению, не удалось проанализировать выполнение задания.\nПопробуй выполнить задание еще раз или вернись к нему позже.''',}
}