# Настройка прокси для Телеграм бота - Краткая инструкция

## 🚀 Быстрый старт

### 1. Создайте файл .env

```bash
cp .env.example .env
```

### 2. Настройте прокси в .env

Откройте `.env` и добавьте:

```env
# SOCKS5 прокси (рекомендуется)
TELEGRAM_PROXY_URL=socks5://username:password@proxy.example.com:1080

# или HTTP прокси
TELEGRAM_PROXY_URL=http://username:password@proxy.example.com:8080
```

**Если прокси не нужен**, закомментируйте строку:
```env
# TELEGRAM_PROXY_URL=
```

### 3. Протестируйте подключение

```bash
# Установите зависимости (если еще не установлены)
pip install -r requirements.txt

# Запустите тест
python test_proxy_connection.py
```

Если видите ✅ **ТЕСТ ПРОЙДЕН** - всё работает!

### 4. Запустите бота

**Для Docker:**
```bash
docker-compose down
docker-compose up -d
```

**Без Docker:**
```bash
python manage.py runbot
```

## 📋 Формат PROXY_URL

```
протокол://[логин:пароль@]хост:порт
```

### Примеры:

```env
# SOCKS5 с паролем
TELEGRAM_PROXY_URL=socks5://myuser:mypass@1.2.3.4:1080

# SOCKS5 без пароля
TELEGRAM_PROXY_URL=socks5://1.2.3.4:1080

# HTTP прокси
TELEGRAM_PROXY_URL=http://proxy.company.com:8080
```

## 🔍 Troubleshooting

### Бот не работает?

1. **Проверьте прокси:**
   ```bash
   curl --proxy socks5://user:pass@host:port https://api.telegram.org
   ```

2. **Проверьте логи:**
   ```bash
   docker-compose logs telegram_bot | tail -50
   ```

3. **Попробуйте без прокси:**
   Закомментируйте `TELEGRAM_PROXY_URL` в `.env` и перезапустите

### Где взять прокси?

- ✅ **Платные SOCKS5 прокси** (рекомендуется)
- ✅ **Собственный VPS** с 3proxy
- ⚠️ **Бесплатные прокси** (нестабильно)

Подробнее в [PROXY_SETUP.md](PROXY_SETUP.md)

## 📁 Измененные файлы

- `bot/bot_instance.py` - добавлена поддержка прокси
- `bot/utils/bot_factory.py` - новая фабрика для создания бота
- `diary/tasks/*.py` - обновлены все задачи
- `docker-compose.yml` - добавлена переменная прокси
- `requirements.txt` - добавлена `aiohttp-socks`
- `.env.example` - пример с документацией
- `test_proxy_connection.py` - тест подключения
- `PROXY_SETUP.md` - полная документация

## 💡 Как это работает

Все запросы бота к Telegram API теперь идут через указанный прокси. Это работает для:
- Получения сообщений от пользователей
- Отправки ответов
- Всех Celery задач (напоминания, мотивации, анализ)

Настройка применяется централизованно через `TELEGRAM_PROXY_URL` в `.env`.
