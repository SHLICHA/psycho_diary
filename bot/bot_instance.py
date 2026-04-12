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
        # Маскируем пароль для логов
        if '@' in proxy_url:
            auth_part = proxy_url.split('@')[0].split('://')[1]
            protocol = proxy_url.split('://')[0]
            rest = proxy_url.split('@')[1]
            masked_url = f"{protocol}://***:***@{rest}"
            logger.info(f"Найден прокси: {masked_url}")
        else:
            logger.info(f"Найден прокси без авторизации: {proxy_url}")
    else:
        logger.warning("TELEGRAM_PROXY_URL НЕ НАЙДЕН! Бот будет работать без прокси.")
    return proxy_url


def create_bot_session():
    """
    Создает сессию с прокси (если указан) или без него.
    """
    proxy_url = get_proxy_url()
    
    logger.info("=" * 60)
    logger.info("СОЗДАНИЕ СЕССИИ БОТА")
    logger.info("=" * 60)
    
    if proxy_url:
        logger.info(f"✓ Прокси URL: {proxy_url}")
        try:
            session = AiohttpSession(proxy=proxy_url)
            logger.info(f"✓ Сессия с прокси создана успешно")
        except Exception as e:
            logger.error(f"✗ ОШИБКА при создании сессии с прокси: {e}", exc_info=True)
            raise
    else:
        logger.warning("⚠ Прокси НЕ используется!")
        try:
            session = AiohttpSession()
            logger.info(f"✓ Сессия без прокси создана")
        except Exception as e:
            logger.error(f"✗ ОШИБКА при создании сессии: {e}", exc_info=True)
            raise
    
    logger.info("=" * 60)
    return session


def create_bot():
    """
    Создает экземпляр бота с настройками прокси.
    """
    logger.info("=" * 60)
    logger.info("ИНИЦИАЛИЗАЦИЯ БОТА")
    logger.info("=" * 60)
    
    token = config('TELEGRAM_BOT_TOKEN')
    if not token:
        error_msg = "TELEGRAM_BOT_TOKEN не найден в настройках"
        logger.error(f"✗ {error_msg}")
        raise ValueError(error_msg)
    
    logger.info(f"✓ Bot token найден (длина: {len(token)})")
    
    session = create_bot_session()
    
    try:
        bot_instance = Bot(
            token=token,
            session=session,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✓ Bot экземпляр создан успешно")
        logger.info("=" * 60)
        return bot_instance
    except Exception as e:
        logger.error(f"✗ ОШИБКА при создании Bot: {e}", exc_info=True)
        raise


# Создаем экземпляр бота при импорте
bot = create_bot()
