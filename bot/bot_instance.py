"""
Модуль для создания экземпляра бота с поддержкой прокси.
"""
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from decouple import config

logger = logging.getLogger(__name__)


def mask_proxy_url(proxy_url: str) -> str:
    """Маскирует логин/пароль в URL прокси для логов."""
    if not proxy_url or '@' not in proxy_url or '://' not in proxy_url:
        return proxy_url or ''
    protocol, rest = proxy_url.split('://', 1)
    host_part = rest.split('@', 1)[-1]
    return f"{protocol}://***:***@{host_part}"


def get_proxy_url():
    """
    Получает URL прокси из настроек.
    Поддерживаемые форматы:
    - HTTP прокси: http://user:password@host:port
    - SOCKS5 прокси: socks5://user:password@host:port
    - SOCKS4 прокси: socks4://user:password@host:port
    """
    proxy_url = (config('TELEGRAM_PROXY_URL', default='') or '').strip()
    if not proxy_url or proxy_url.lower() in {'none', 'null', 'false', '-'}:
        logger.warning("TELEGRAM_PROXY_URL не задан. Бот будет работать без прокси.")
        return None

    logger.info("Найден прокси: %s", mask_proxy_url(proxy_url))
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
        logger.info("✓ Прокси URL: %s", mask_proxy_url(proxy_url))
        try:
            session = AiohttpSession(proxy=proxy_url)
            logger.info("✓ Сессия с прокси создана успешно")
        except Exception as e:
            logger.error("✗ ОШИБКА при создании сессии с прокси: %s", e, exc_info=True)
            raise
    else:
        logger.warning("⚠ Прокси НЕ используется!")
        try:
            session = AiohttpSession()
            logger.info("✓ Сессия без прокси создана")
        except Exception as e:
            logger.error("✗ ОШИБКА при создании сессии: %s", e, exc_info=True)
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
        logger.error("✗ %s", error_msg)
        raise ValueError(error_msg)

    logger.info("✓ Bot token найден (длина: %s)", len(token))

    session = create_bot_session()

    try:
        bot_instance = Bot(
            token=token,
            session=session,
            parse_mode=ParseMode.HTML
        )
        logger.info("✓ Bot экземпляр создан успешно")
        logger.info("=" * 60)
        return bot_instance
    except Exception as e:
        logger.error("✗ ОШИБКА при создании Bot: %s", e, exc_info=True)
        raise


# Создаем экземпляр бота при импорте
bot = create_bot()
