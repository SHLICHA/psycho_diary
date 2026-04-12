"""
Модуль для создания экземпляра бота с поддержкой прокси.
"""
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from decouple import config

logger = logging.getLogger(__name__)


def get_proxy_url():
    """
    Получает URL прокси из настроек.
    Поддерживаемые форматы:
    - HTTP прокси: http://user:password@host:port
    - SOCKS5 прокси: socks5://user:password@host:port
    - SOCKS4 прокси: socks4://user:password@host:port
    
    Примеры:
    - http://proxy.example.com:8080
    - socks5://user:pass@1.2.3.4:1080
    """
    proxy_url = config('TELEGRAM_PROXY_URL', default=None)
    if proxy_url:
        logger.info(f"Найден прокси: {proxy_url}")
    return proxy_url


def create_bot_session():
    """
    Создает сессию с прокси (если указан) или без него.
    """
    proxy_url = get_proxy_url()
    
    if proxy_url:
        logger.info(f"Создание сессии с прокси: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
    else:
        logger.info("Создание сессии без прокси")
        session = AiohttpSession()
    
    return session


def create_bot():
    """
    Создает экземпляр бота с настройками прокси.
    """
    token = config('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден в настройках")
    
    session = create_bot_session()
    
    bot_instance = Bot(
        token=token,
        session=session,
        parse_mode=ParseMode.HTML
    )
    
    logger.info("Bot экземпляр создан успешно")
    return bot_instance


# Создаем экземпляр бота при импорте
bot = create_bot()
