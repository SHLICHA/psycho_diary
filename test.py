from diary.tasks.morning_motivations import _send_motivation_to_user
from users.models import User
from datetime import date, timedelta
from aiogram import Bot
from decouple import config

# Получи тестового пользователя
user = User.objects.get(telegram_id=399096554) # Замените на реальный ID

# Создай бота (аналогично задаче)
bot_token = config('TELEGRAM_BOT_TOKEN')
bot_instance = Bot(token=bot_token)

# Вчерашняя дата
yesterday = date.today() - timedelta(days=1)

# Вызов внутренней функции
import asyncio
asyncio.run(_send_motivation_to_user(user, bot_instance, yesterday))