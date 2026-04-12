"""
Вспомогательный модуль для создания бота в Celery задачах.
Предоставляет функцию для создания бота с поддержкой прокси.
"""
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from decouple import config

logger = logging.getLogger(__name__)


async def create_bot_for_task() -> Bot:
    """
    Создает экземпляр бота для использования в Celery задачах.
    Поддерживает прокси, если указан TELEGRAM_PROXY_URL в .env
    
    Returns:
        Bot: Экземпляр бота с настроенной сессией
    """
    token = config('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден в настройках")
    
    proxy_url = config('TELEGRAM_PROXY_URL', default=None)
    
    if proxy_url:
        logger.info(f"Создание бота для задачи с прокси: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
    else:
        logger.debug("Создание бота для задачи без прокси")
        session = AiohttpSession()
    
    bot_instance = Bot(
        token=token,
        session=session,
        parse_mode=ParseMode.HTML
    )
    
    return bot_instance
