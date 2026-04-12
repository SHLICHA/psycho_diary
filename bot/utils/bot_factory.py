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
    logger.info("=" * 60)
    logger.info("BOT_FACTORY: Создание бота для Celery задачи")
    logger.info("=" * 60)
    
    token = config('TELEGRAM_BOT_TOKEN')
    if not token:
        error_msg = "TELEGRAM_BOT_TOKEN не найден в настройках"
        logger.error(f"✗ {error_msg}")
        raise ValueError(error_msg)
    
    logger.info(f"✓ Bot token найден (длина: {len(token)})")
    
    proxy_url = config('TELEGRAM_PROXY_URL', default=None)
    
    if proxy_url:
        # Маскируем пароль для логов
        if '@' in proxy_url:
            masked_url = f"{proxy_url.split('@')[0].split('://')[0]}://***:***@{proxy_url.split('@')[1]}"
        else:
            masked_url = proxy_url
        
        logger.info(f"✓ Найден прокси: {masked_url}")
        try:
            session = AiohttpSession(proxy=proxy_url)
            logger.info(f"✓ Сессия с прокси создана")
        except Exception as e:
            logger.error(f"✗ ОШИБКА при создании сессии с прокси: {e}", exc_info=True)
            raise
    else:
        logger.warning("⚠ Прокси НЕ используется!")
        session = AiohttpSession()
    
    try:
        bot_instance = Bot(
            token=token,
            session=session,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✓ Bot экземпляр создан успешно")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"✗ ОШИБКА при создании Bot: {e}", exc_info=True)
        raise
    
    return bot_instance
