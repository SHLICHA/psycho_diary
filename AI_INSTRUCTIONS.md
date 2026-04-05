# 📖 Инструкции для AI-ассистента (Psycho Diary Project)

> **Дата создания:** 2026-04-05  
> **Версия:** 1.0  
> **Назначение:** Правила и инструкции для работы с проектом Psycho Diary

---

## 🔴 КРИТИЧЕСКИЕ ПРАВИЛА (всегда соблюдать!)

### 1. Работа с живым проектом
- ✅ **Проект уже запущен** - в БД есть реальные пользователи и данные
- ✅ **Миграции проводить ОСТОРОЖНО** - нельзя ломать существующие данные
- ✅ **Перед миграциями** - всегда делать backup
- ✅ **Тестировать миграции** - сначала на staging/local
- ❌ **НЕЛЬЗЯ** удалять поля/таблицы без data migration
- ❌ **НЕЛЬЗЯ** менять типы полей без миграции данных

### 2. Бот должен продолжать работать
- ✅ API - это РАСШИРЕНИЕ, не замена боту
- ✅ Любые изменения не должны ломать функциональность бота
- ✅ Приоритет: стабильность бота > новые фичи
- ✅ Тестировать бота после каждого изменения

### 3. Код должен быть безопасным и оптимальным
- ✅ Самое узкое место - **AI анализ**
- ✅ Оптимизировать использование AI (токены, контекст, время)
- ✅ Следить за безопасностью данных (шифрование, валидация)

### 4. Общение и процесс работы
- ✅ **Общаться только на РУССКОМ языке**
- ✅ **Не делать больших изменений без согласования**
- ✅ **Сначала обсуждать → потом делать**
- ✅ **Если не согласен** - говорить прямо
- ✅ **Если непонятно** - спрашивать, не придумывать

---

## 📋 ИНСТРУКЦИИ ПО КОНКРЕТНЫМ ЗАДАЧАМ

### Миграции базы данных

**Правила:**
```bash
# 1. Всегда проверять существующие данные
python manage.py dbshell
# Выполнить SELECT для проверки данных

# 2. Создать миграцию
python manage.py makemigrations

# 3. Проверить миграцию ПЕРЕД применением
python manage.py showmigrations
python manage.py sqlmigrate <app> <migration_number>

# 4. Применить миграцию (ОСТОРОЖНО!)
python manage.py migrate

# 5. Проверить результат
python manage.py dbshell
# Выполнить SELECT для проверки
```

**Data Migration:**
```python
# Если нужно изменить существующие данные:
# 1. Создать пустую миграцию:
python manage.py makemigrations --empty <app_name>

# 2. Добавить RunPython с функцией миграции
def migrate_data(apps, schema_editor):
    Model = apps.get_model('app', 'Model')
    for obj in Model.objects.all():
        # Изменить данные
        obj.save()

class Migration(migrations.Migration):
    dependencies = [...]
    operations = [
        migrations.RunPython(migrate_data, migrations.RunPython.noop),
    ]
```

**Безопасность:**
- ✅ Добавление нового поля с `default` или `null=True` - безопасно
- ✅ Добавление индекса - безопасно (но может быть долгим)
- ⚠️ Удаление поля - требует data migration
- ⚠️ Изменение типа поля - требует data migration
- ❌ Удаление таблицы - НИКОГДА без подтверждения

---

### Работа с AI (DeepSeek API)

**Правила оптимизации:**
1. **Минимизировать контекст** - передавать только необходимое
2. **Лимитировать max_tokens** - не более нужного
3. **Кэшировать ответы** - если возможно
4. **Логировать использование** - токены, стоимость, ошибки

**Мониторинг:**
```python
# Всегда логировать:
logger.info(f"[AI Usage] Action: {action}, Tokens: {tokens}, Cost: ${cost}")
```

**Fallback:**
```python
# Если AI падает:
# 1. Retry с уменьшенным контекстом
# 2. Если снова падает → использовать стандартный ответ
# 3. Логировать ошибку
```

---

### Работа с часовыми поясами

**Правила:**
1. **Всегда учитывать TZ пользователя**
2. **Сохранять TZ создателя в записи** (поле `creator_timezone`)
3. **НЕ использовать динамический TZ** из текущего профиля пользователя для старых записей
4. **Конвертировать в UTC** для хранения в БД
5. **Конвертировать в локальный TZ** для отображения

**Пример:**
```python
# Создание записи:
entry.creator_timezone = user.timezone  # Сохраняем TZ!
entry.created_at = timezone.now()  # UTC

# Отображение:
user_tz = pytz.timezone(entry.creator_timezone)
local_time = entry.created_at.astimezone(user_tz)
```

---

### Работа с серий дней (streaks)

**Логика подсчета:**
- Серия = количество дней ПОДРЯД с записями
- Если сегодня НЕТ записи → показывать серию ДО сегодня + предупреждение
- Не показывать "0" если были записи вчера, позавчера и т.д.

**Формат сообщения:**
```
✅ Есть запись сегодня:
"🔥 Серия: 5 дней подряд!"

❌ Нет записи сегодня:
"🔥 Серия: 5 дней. Но она оборвется, если не сделать запись сегодня!"
```

---

### Работа с Celery задачами

**Правила:**
1. **Всегда обрабатывать ошибки** - задача не должна падать молча
2. **Логировать начало и конец** выполнения
3. **Использовать retry** для временных ошибок
4. **Не блокировать очередь** - разбивать большие задачи

**Пример:**
```python
@shared_task(bind=True, max_retries=3)
def my_task(self, user_id):
    try:
        logger.info(f"[Task] Начало для пользователя {user_id}")
        # ... логика ...
        logger.info(f"[Task] Успех для пользователя {user_id}")
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"[Task] Ошибка: {e}", exc_info=True)
        try:
            self.retry(countdown=60 * 5)  # Retry через 5 минут
        except self.MaxRetriesExceededError:
            logger.error(f"[Task] Максимум retries превышен")
            return {'status': 'failed', 'error': str(e)}
```

---

### Работа с сообщениями (i18n)

**Правила:**
1. **ВСЕ сообщения** в `messages/` директории
2. **НЕ хардкодить текст** в коде
3. **Использовать `get_message()`** для получения сообщений
4. **Добавлять новые сообщения** в оба языка (ru + en)

**Пример:**
```python
# messages/ru/ru_main.py:
'my_new_message': 'Привет, {name}!'

# messages/en/en_main.py:
'my_new_message': 'Hello, {name}!'

# Использование:
text = get_message('my_new_message', language, name=user.name)
```

---

### Работа с шифрованием

**Правила:**
1. **Использовать EncryptedField** для чувствительных данных
2. **НЕ хранить plaintext** чувствительные данные
3. **При миграции** encrypted полей - быть особенно осторожным

**Encrypted поля:**
- `EncryptedCharField`
- `EncryptedTextField`
- `EncryptedJSONField`
- `EncryptedEmailField`

---

## 🏗️ АРХИТЕКТУРА ПРОЕКТА

### Структура
```
psycho_diary/
├── bot/              # Telegram бот (aiogram)
│   ├── handlers/     # Обработчики сообщений
│   ├── services/     # Сервисы бота
│   ├── keyboards/    # Клавиатуры
│   ├── middlewares/  # Middleware
│   ├── states/       # FSM states
│   └── utils/        # Утилиты
├── diary/            # Модуль дневника
│   ├── services/     # Сервисы дневника
│   ├── tasks/        # Celery задачи
│   └── models.py     # Модели
├── users/            # Модуль пользователей
│   └── models.py     # Модели
├── api/              # REST API (в разработке)
│   ├── views.py      # ViewSet'ы
│   ├── serializers.py  # Сериализаторы
│   └── urls.py       # Роуты
├── core/             # Основные настройки
│   ├── settings.py   # Django settings
│   ├── celery.py     # Celery config
│   └── tasks.py      # Celery tasks imports
├── messages/         # i18n сообщения
│   ├── ru/           # Русские сообщения
│   └── en/           # Английские сообщения
└── prompts/          # AI промпты
    └── templates/    # Шаблоны промптов
```

### Технологии
- **Backend:** Django 4.2.7
- **Bot:** aiogram 3.1.1
- **Database:** PostgreSQL 15
- **Cache/Broker:** Redis 7
- **Task Queue:** Celery 5.5.3
- **AI:** DeepSeek API
- **Speech:** Yandex SpeechKit
- **Payments:** YooKassa
- **API:** Django REST Framework + SimpleJWT

---

## 🚀 ИНСТРУКЦИИ ПО РАЗВЕРТЫВАНИЮ

### Запуск бота (production)
```bash
# Docker
docker-compose up -d --build

# Миграции (ОСТОРОЖНО!)
docker-compose exec web python manage.py migrate

# Статика
docker-compose exec web python manage.py collectstatic --no-input

# Логи
docker-compose logs -f
docker-compose logs -f celery_worker
docker-compose logs -f web
```

### Запуск тестов
```bash
# Все тесты
python -m pytest tests/ -v

# Конкретный тест
python -m pytest tests/test_messages.py -v

# С покрытием
python -m pytest --cov=. --cov-report=html
```

### Celery задачи
```bash
# Запуск worker
celery -A core worker --loglevel=info

# Запуск beat (периодические задачи)
celery -A core beat --loglevel=info

# Мониторинг
celery -A core flower
```

---

## 📊 БАЗА ДАННЫХ

### Важные таблицы
- `users_user` - пользователи
- `diary_entry` - записи дневника
- `diary_combined_entry` - объединенные записи дня
- `diary_psycho_analysis` - анализы записей
- `diary_daily_analysis` - анализы дня
- `diary_weekly_analysis` - недельные анализы
- `diary_therapy_task` - терапевтические задания
- `users_token_transaction` - транзакции токенов
- `users_payment` - платежи

### Критичные поля
- `users_user.telegram_id` - уникальный ID
- `users_user.token_balance` - баланс токенов
- `users_user.is_premium` - премиум статус
- `diary_entry.created_at` - время создания (UTC!)
- `diary_entry.creator_timezone` - TZ создателя

---

## 📝 ЧЕКЛИСТ ПЕРЕД КОММИТОМ

### Перед каждым коммитом:
- [ ] Код работает локально
- [ ] Тесты проходят
- [ ] Нет debug/print операторов
- [ ] Нет хардкода сообщений
- [ ] Миграции проверены (если есть изменения моделей)
- [ ] Оба языка обновлены (ru + en)
- [ ] Логирование добавлено
- [ ] Обработка ошибок есть

### Перед миграцией БД:
- [ ] Backup сделан
- [ ] Миграция протестирована локально
- [ ] Data migration есть (если нужно)
- [ ] Откат возможен (forward + backward)
- [ ] Документация обновлена

---

## 🔍 ПОИСК ПРОБЛЕМ

### Логирование
```bash
# Логи бота
docker-compose logs -f telegram_bot

# Логи Celery
docker-compose logs -f celery_worker

# Логи web
docker-compose logs -f web

# Файл логов
tail -f bot_debug.log
```

### Уровень логирования
```python
# В settings.py:
LOG_LEVEL = 'DEBUG'  # Для отладки
LOG_LEVEL = 'INFO'   # Для production

# В конкретных модулях:
logger = logging.getLogger(__name__)
logger.debug('...')  # Детальная отладка
logger.info('...')   # Информация
logger.warning('...') # Предупреждение
logger.error('...')  # Ошибка
```

---

## 🎯 ПРИОРИТЕТЫ ЗАДАЧ

### P0 - Критичные (делать немедленно)
- ❌ Бот не работает
- ❌ Данные пользователей повреждаются
- ❌ Безопасность скомпрометирована
- ❌ Потеря данных

### P1 - Высокие (делать в первую очередь)
- 🔥 Еженедельный анализ падает
- 🔥 Часовые пояса смещают записи
- 🔥 Поля профиля раздуваются
- 🔥 Высокие затраты на AI

### P2 - Средние (делать после P1)
- Оптимизация кода
- Рефакторинг
- Улучшение UX

### P3 - Низкие (делать когда есть время)
- Новые фичи
- Улучшения документации
- Косметические изменения

---

## 💡 ПОЛЕЗНЫЕ КОМАНДЫ

### Django
```bash
# Shell
python manage.py shell

# Проверить миграции
python manage.py showmigrations

# Создать суперпользователя
python manage.py createsuperuser

# Проверить БД
python manage.py dbshell

# Проверить статику
python manage.py findstatic <file>
```

### Docker
```bash
# Перезапустить сервис
docker-compose restart web

# Войти в контейнер
docker-compose exec web bash

# Очистить volume
docker-compose down -v

# Посмотреть размер БД
docker exec -it <db_container> psql -U <user> -d <db> -c "SELECT pg_size_pretty(pg_database_size('<db>'));"
```

### Git
```bash
# Посмотреть изменения
git status
git diff

# Отменить изменения
git checkout -- <file>

# Создать ветку
git checkout -b feature/<name>

# Вернуться к коммиту
git log --oneline
git checkout <commit>
```

---

## 📞 КОНТАКТЫ И РЕСУРСЫ

### Документация
- Django: https://docs.djangoproject.com/
- aiogram: https://docs.aiogram.dev/
- Celery: https://docs.celeryq.dev/
- PostgreSQL: https://www.postgresql.org/docs/

### API Документация
- DeepSeek: https://platform.deepseek.com/
- Yandex SpeechKit: https://yandex.cloud/ru/docs/speechkit/
- YooKassa: https://yookassa.ru/developers/api

---

## 📜 ИСТОРИЯ ИЗМЕНЕНИЙ

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-04-05 | 1.0 | Первоначальная версия инструкций |

---

> **ВАЖНО:** Этот файл должен обновляться при каждом новом правиле или инструкции!
> 
> **Если добавляешь новое правило** - добавь его в соответствующую секцию или создай новую.
