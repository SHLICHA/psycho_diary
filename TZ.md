📋 ТЕХНИЧЕСКОЕ ЗАДАНИЕ: Психоаналитический дневник в Telegram
🎯 Цель проекта
Создание Telegram-бота для ведения дневника с автоматическим психоэмоциональным анализом записей. Бот должен становиться "умнее" с каждым днем, узнавая пользователя и давая более точные рекомендации. Система включает терапевтические задания для активного участия пользователя в процессе саморазвития.

🛠️ Технологии
Backend: Django 4.x + Django ORM
Bot Framework: aiogram 3.x
База данных: PostgreSQL
API: Yandex SpeechKit, DeepSeek (в перспективе)
Логирование: colorlog
Языки: Русский, Английский
Асинхронность: asyncio (без Celery)
Конфигурация: python-decouple или django-environ
Тестирование: pytest, factory-boy
Линтер: flake8, black
Типизация: mypy
👥 Целевая аудитория
Люди, ведущие саморазвитие, работающие с психологом или самостоятельно занимающиеся психоанализом.

📋 Функциональные требования
1. Регистрация и профиль
Автоматическая регистрация при первом /start
Определение языка через language_code Telegram
Возможность смены языка в настройках
Хранение: имя, язык, дата последней записи, уровень осознанности
GDPR-совместимое удаление данных
2. Создание записей
Поддержка:
Текстовых сообщений
Голосовых сообщений (до 2 минут)
Обработка голоса:
Распознавание речи (Yandex SpeechKit)
Коррекция текста (пунктуация, абзацы через DeepSeek)
Сохранение с датой и временем
Валидация длины и содержания
Ограничение частоты отправки (rate limiting)
3. Психоаналитический анализ
Этапы:
Первичная обработка
Распознавание/коррекция текста
Определение языка записи
Фильтрация стоп-слов и мата
Извлечение ключевых элементов
Эмоции (радость, тревога, гнев, апатия и т.д.)
События дня
Мысли пользователя
Триггеры
Повторяющиеся темы
Сравнение с прошлым опытом
Анализ последних 10 ключевых моментов пользователя
Определение новых/повторяющихся тем
Расчет эмоционального тренда
Оценка дня
Шкала 1-10
Комментарий психолога
Рекомендации
Уточняющие вопросы
Если запись неясна — 1-2 вопроса сразу
Добавление ответов к той же записи
FSM для управления диалогом
Обновление психологического портрета
Новые инсайты
Изменение веса существующих тем
Пересчет уровня осознанности
4. Архив записей
Просмотр по календарю (год → месяц → день)
Показ: текст записи, оценка, анализ
Возможность удаления записей
Поиск по ключевым словам
Экспорт отдельных записей
5. Терапевтические задания
Назначение:
После анализа дневниковой записи
На основе психологического профиля
Не каждая запись получает задание
Выполнение:
Пользователь описывает выполнение задания
Добавляет ощущения/эмоции при выполнении
Все сохраняется как отдельная запись
Анализ выполнения:
Бот анализирует ответ на задание
Дает обратную связь
Учитывает в психологическом профиле пользователя
Пример взаимодействия:

Запись → Анализ → Задание
Выполнение + Ощущения → Анализ бота
Обновление профиля → Лучшие рекомендации

Запись → Анализ → Задание
Выполнение + Ощущения → Анализ бота
Обновление профиля → Лучшие рекомендации
6. Отслеживание прогресса
Бесплатно:
Хранение данных
Базовый анализ
Выполнение заданий
Платно (подписка):
Еженедельные отчеты
Ежемесячные отчеты
Графики эмоций
Персональные рекомендации
Экспорт данных
🧠 Интеллектуальная составляющая
1. Модель пользователя
Учет предыдущих записей
Построение психологического портрета
Адаптация анализа под личность
Взвешенные эмоциональные паттерны
2. Вес инсайтов
Увеличение веса при повторении
Уменьшение при отсутствии упоминания (в перспективе)
Экспоненциальное затухание веса
3. Уровень осознанности
Рассчитывается по:

Частоте саморефлексии
Глубине анализа
Разнообразию тем
Снижению повторяющихся негативных триггеров
Качеству выполнения заданий
4. Глубина записи
Определяется по:

Длине текста
Количеству уникальных
тем
Наличию саморефлексии
Эмоциональной насыщенности
📊 Метрики отслеживания
Для каждой записи:
Оценка дня (1-10)
Ключевые моменты
Эмоции
Триггеры
Глубина анализа
Время написания
Для каждой задачи:
Качество выполнения
Частота выполнения
Эмоциональный отклик
Прогресс через задания
Время на выполнение
Для пользователя:
Средняя оценка за период
Частота записей
Динамика эмоций
Новые инсайты
Уровень осознанности
Статистика по заданиям
Периоды активности
🗺️ Структура проекта


psycho_diary/
├── bot/                    # Aiogram часть
│   ├── handlers/           # Обработчики команд
│   │   ├── __init__.py
│   │   ├── start.py
│   │   ├── diary.py
│   │   ├── tasks.py
│   │   └── settings.py
│   ├── middlewares/        # Регистрация, язык
│   │   ├── __init__.py
│   │   ├── user_middleware.py
│   │   ├── language_middleware.py
│   │   ├── rate_limit_middleware.py
│   │   └── analytics_middleware.py
│   ├── keyboards/          # Клавиатуры
│   │   ├── __init__.py
│   │   ├── main_menu.py
│   │   └── inline_calendar.py
│   ├── states/             # FSM состояния
│   │   ├── __init__.py
│   │   └── diary_states.py
│   └── utils/              # Вспомогательные функции
│       ├── __init__.py
│       ├── message_utils.py
│       ├── callback_utils.py
│       └── error_handler.py
├── diary/                  # Основное приложение
│   ├── models.py           # Модели данных
│   ├── services/           # Логика анализа
│   │   ├── __init__.py
│   │   ├── analysis_service.py
│   │   ├── task_service.py
│   │   ├── insight_service.py
│   │   ├── metrics_service.py
│   │   └── rollback_service.py
│   ├── managers/           # Кастомные менеджеры
│   │   └── diary_manager.py
│   └── views.py            # В будущем для API
├── users/                  # Модель пользователя
│   ├── models.py
│   └── managers.py
├── core/                   # Настройки, логи
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── logging_config.py
│   ├── exceptions.py
│   ├── constants.py
│   └── health_check.py
├── utils/                  # Общие утилиты
│   ├── __init__.py
│   ├── text_processing.py
│   └── validators.py
├── messages.py             # Тексты сообщений
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md


📦 Модели данных
1. User (расширение AbstractUser)

- telegram_id (BigIntegerField, unique)
- language (CharField, choices=LANGUAGES, default='ru')
- last_entry (DateTimeField, null=True, blank=True)
- awareness_level (PositiveIntegerField, default=1)  # 1-10
- created_at (DateTimeField, auto_now_add=True)
- updated_at (DateTimeField, auto_now=True)
- is_premium (BooleanField, default=False)
- deleted_at (DateTimeField, null=True, blank=True)  # Soft delete

2. DiaryEntry
- user (ForeignKey)
- text (TextField)
- created_at (DateTimeField, auto_now_add=True)
- language (CharField, choices=LANGUAGES)
- word_count (PositiveIntegerField)
- is_processed (BooleanField, default=False)
- processing_error (TextField, blank=True)

3. VoiceToText
- entry (OneToOneField)
- original_duration (PositiveIntegerField)  # секунды
- processed_text (TextField)
- processing_time (FloatField)  # время обработки
- api_response (JSONField)  # для дебага

4. KeyPoint
- entry (ForeignKey, related_name='key_points')
- text (TextField)
- type (CharField, choices=KEYPOINT_TYPES)  # emotion/event/thought/trigger
- confidence (FloatField, default=1.0)  # уверенность анализа

5. PsychoAnalysis
- entry (OneToOneField, related_name='analysis')
- mood_score (PositiveIntegerField)  # 1-10
- comment (TextField)
- recommendation (TextField)
- processing_time (FloatField)
- insights_extracted (PositiveIntegerField)

6. UserInsight
- user (ForeignKey, related_name='insights')
- text (TextField)
- weight (PositiveIntegerField, default=1)
- last_mentioned (DateTimeField)
- category (CharField, choices=INSIGHT_CATEGORIES)
- first_mentioned (DateTimeField, auto_now_add=True)

7. TherapyProgress
- user (ForeignKey)
- date (DateField)
- avg_mood (FloatField)
- insights_count (PositiveIntegerField)
- trigger_count (PositiveIntegerField)
- depth_score (PositiveIntegerField)
- tasks_completed (PositiveIntegerField)
- consistency_score (FloatField)  # регулярность записей

8. TherapyTask
- user (ForeignKey, related_name='tasks')
- title (CharField)
- description (TextField)
- assigned_at (DateTimeField, auto_now_add=True)
- completed_at (DateTimeField, null=True, blank=True)
- status (CharField, choices=TASK_STATUS)
- type (CharField, choices=TASK_TYPES)
- priority (PositiveIntegerField, default=1)

9. TaskCompletion
- task (OneToOneField, related_name='completion')
- completion_text (TextField)
- feelings_text (TextField)
- created_at (DateTimeField, auto_now_add=True)
- time_spent (PositiveIntegerField)  # минуты

10. TaskAnalysis
- completion (OneToOneField, related_name='analysis')
- bot_response (TextField)
- insights_updated (BooleanField, default=False)
- quality_score (PositiveIntegerField)  # 1-10
- feedback_given (BooleanField, default=False)

11. UserActivity
- user (ForeignKey)
- activity_type (CharField, choices=ACTIVITY_TYPES)
- timestamp (DateTimeField, auto_now_add=True)
- metadata (JSONField, blank=True)  # дополнительные данные

🌍 Многоязычность
messages.py
MESSAGES = {
    'ru': {
        'welcome': 'Привет! Это твой дневник...',
        'ask_entry': 'Расскажи, как прошёл твой день...',
        'processing': 'Обрабатываю запись...',
        'task_assigned': '🎯 Новое задание: {title}\n{description}',
        'task_completed': '✅ Отлично! Теперь опиши свои ощущения при выполнении:',
        'rate_limit': 'Пожалуйста, подожди немного перед следующей записью.',
        'error_processing': 'Произошла ошибка при обработке. Попробуйте позже.',
        'entry_saved': '✅ Запись сохранена и проанализирована!\nОценка: {score}/10',
        'rate_limit_exceeded': 'Вы превысили лимит сообщений. Пожалуйста, подождите немного.',
        'error_generic': 'Произошла ошибка. Попробуйте позже.',
    },
    'en': {
        'welcome': 'Hi! This is your diary...',
        'ask_entry': 'Tell me how your day went...',
        'processing': 'Processing your entry...',
        'task_assigned': '🎯 New task: {title}\n{description}',
        'task_completed': '✅ Great! Now describe your feelings during completion:',
        'rate_limit': 'Please wait a moment before your next entry.',
        'error_processing': 'An error occurred during processing. Please try again later.',
        'entry_saved': '✅ Entry saved and analyzed!\nScore: {score}/10',
        'rate_limit_exceeded': 'You have exceeded the message limit. Please wait a moment.',
        'error_generic': 'An error occurred. Please try again later.',
    }
}

⚙️ Константы (core/constants.py)
# Лимиты
VOICE_MESSAGE_MAX_DURATION = 120  # секунд
TEXT_MESSAGE_MAX_LENGTH = 5000
MESSAGES_PER_MINUTE_LIMIT = 5

# Веса и коэффициенты
INSIGHT_WEIGHT_INCREMENT = 1
INSIGHT_WEIGHT_DECREMENT = 0.1
AWARENESS_LEVEL_MAX = 10

# Типы ключевых моментов
KEYPOINT_TYPES = [
    ('emotion', 'Эмоция'),
    ('event', 'Событие'),
    ('thought', 'Мысль'),
    ('trigger', 'Триггер'),
]

# Статусы задач
TASK_STATUS = [
    ('pending', 'Ожидает'),
    ('completed', 'Выполнена'),
    ('skipped', 'Пропущена'),
]

# Типы задач
TASK_TYPES = [
    ('daily', 'Ежедневная'),
    ('reflection', 'Рефлексивная'),
    ('cognitive', 'Когнитивная'),
    ('creative', 'Творческая'),
]

# Языки
LANGUAGES = [
    ('ru', 'Русский'),
    ('en', 'English'),
]

🎛️ Команды управления
python manage.py runbot          # Запуск бота
python manage.py analyze_entry <entry_id>   # Анализ конкретной записи
python manage.py generate_weekly_report <user_id>   # Еженедельный отчет
python manage.py export_user_data <user_id>   # Экспорт данных пользователя
python manage.py cleanup_old_data   # Очистка старых временных данных
python manage.py calculate_insights   # Пересчет всех инсайтов
python manage.py health_check   # Проверка состояния системы

🎨 Интерфейс бота (ЧИСТЫЙ ЧАТ)
Принципы взаимодействия:
Минимизация сообщений: использование edit/delete вместо новых сообщений
Inline кнопки: все действия через callback кнопки
Контекстное меню: динамическое обновление интерфейса
Главное меню (редактируемое сообщение):
🧠 Твой психологический дневник

Выбери действие:
[📝 Новая запись] [📅 Архив]
[🎯 Задания] [📊 Прогресс]
[⚙️ Настройки] [❓ Помощь]

Создание записи:
Сообщение: "📝 Напиши, как прошёл твой день..."
После отправки: редактируем на "Обрабатываю..."
После анализа: редактируем на результат с кнопками:

✅ Запись сохранена!
Оценка: 7/10 - Хороший день

[🎯 Получить задание] [📅 К архиву]
[📝 Новая запись] [📊 Прогресс]

Архив (календарь через inline):

📅 Выбери дату:
[<<] [Март 2024] [>>]
[1] [2] [3] ... [31]

Задания:
🎯 Текущее задание:
"Проанализируй ситуацию с 3 точек зрения"

[✅ Выполнить] [⏭ Пропустить] [🗑 Удалить]

После выполнения:
✅ Отлично! Опиши свои ощущения:

(После ответа - редактируем на финальный результат)

Настройки:

⚙️ Настройки:

🌍 Язык: Русский [Сменить]
🔔 Уведомления: Вкл [Выкл]
📈 Автоанализ: Вкл [Выкл]

[🔙 Назад]

🔐 Безопасность и конфиденциальность
Хранение только необходимых данных
Шифрование чувствительных данных
Удаление записей по запросу пользователя (soft/hard delete)
Защита от спама (rate limiting)
Логирование действий пользователей
GDPR-совместимость
Анонимизация данных при экспорте

📈 Платные функции
Подписка (ежемесячно):
Еженедельные отчеты
Ежемесячные отчеты
Графики эмоций
Персональные рекомендации
Экспорт в PDF/JSON
Расширенная статистика по заданиям
Приоритетная поддержка
Расширенные аналитические отчеты

⚡ Асинхронность и задачи
Без Celery:
Все обработки в aiogram handlers
Фоновые задачи через asyncio.create_task()
Планирование через cron
Rate limiting через Redis (в перспективе)

🧪 Тестирование
Unit тесты:
Модели данных
Сервисы анализа
Обработчики сообщений
Интеграционные тесты:
Полный цикл обработки записи
Система заданий
Многоязычность
End-to-end тесты:
Сценарии пользователей
Обработка ошибок

📊 Мониторинг и логирование
Уровни логирования:
DEBUG: для разработки
INFO: события бота
WARNING: не критичные ошибки
ERROR: ошибки обработки
CRITICAL: краши
Метрики мониторинга:
Время обработки сообщений
Частота ошибок
Активность пользователей
Использование API
Аналитика использования:
Частота использования функций
Время взаимодействия
Пути пользователей
Конверсия заданий

🛡️ Обработка ошибок и восстановление
Типы ошибок:
SpeechRecognitionError: Ошибка распознавания речи
AnalysisError: Ошибка анализа текста
DatabaseError: Ошибка базы данных
ExternalAPIError: Ошибка внешних API
Механизмы восстановления:
Автоматический retry при временных ошибках
Создание снапшотов перед критическими операциями
Возможность отката изменений
Уведомления администраторов при критических ошибках

📈 Метрики производительности
Отслеживаемые метрики:
Среднее время обработки голосового сообщения
Среднее время анализа текста
Частота ошибок по типам
Время ответа бота
Использование ресурсов
Система сбора:
Автоматическая запись метрик в Redis
Агрегация данных
Генерация отчетов

🚀 Этапы разработки
Этап 1 (MVP - 4 недели):
Регистрация и профиль
Прием текста/голоса
Базовый анализ
Архив записей
Базовая система заданий
Чистый интерфейс (edit/delete)
Обработка ошибок
Метрики производительности
Аналитика использования
Этап 2 (Расширение - 3 недели):
Интеллектуальный анализ
Уточняющие вопросы (FSM)
Отслеживание прогресса
Расширенная система заданий
Многоязычность
Этап 3 (Премиум - 3 недели):
Платные функции
Графики и отчеты
Расширенная аналитика
Экспорт данных
Мониторинг и оптимизация