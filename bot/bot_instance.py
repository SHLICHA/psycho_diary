from aiogram import Bot
from aiogram.enums import ParseMode
from decouple import config

# Создаем экземпляр бота при импорте модуля
bot = Bot(
    token=config('TELEGRAM_BOT_TOKEN'),
    parse_mode=ParseMode.HTML
)