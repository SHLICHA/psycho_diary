import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from decouple import config

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from bot.handlers import all_routers
from bot.utils.state_manager import state_manager
from bot.middlewares.db_middleware import DatabaseConnectionMiddleware
from bot.middlewares.user_middleware import UserMiddleware
from bot.middlewares.language_middleware import LanguageMiddleware
from bot.middlewares.rate_limit_middleware import RateLimitMiddleware
from bot.middlewares.premium_check_middleware import PremiumCheckMiddleware
from bot.bot_instance import bot

async def log_update_middleware(handler, event, data):
    """
    Простой middleware для логирования всех входящих обновлений.
    Поможет диагностировать, получает ли бот сообщения от Telegram.
    """
    logger.info("=" * 60)
    logger.info("ПОЛУЧЕНО ОБНОВЛЕНИЕ ОТ TELEGRAM")
    logger.info(f"Тип события: {type(event).__name__}")
    
    if hasattr(event, 'message') and event.message:
        msg = event.message
        logger.info(f"От пользователя: {msg.from_user.id} (@{msg.from_user.username})")
        logger.info(f"Текст: {msg.text or '(нет текста)'}")
    elif hasattr(event, 'callback_query') and event.callback_query:
        cq = event.callback_query
        logger.info(f"Callback от пользователя: {cq.from_user.id}")
        logger.info(f"Data: {cq.data}")
    
    logger.info("=" * 60)
    return await handler(event, data)

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск психо-дневника...")
    
    # Проверяем, что токен есть
    bot_token = config('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не найден")
        return
    
    logger.info("Bot token найден")

    # Инициализация диспетчера с хранилищем состояний
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    logger.info("Memory storage инициализирован")
    
    # === Регистрация middleware (в правильном порядке) ===
    logger.info("Регистрация middleware...")

    # 0. Log middleware - для логирования всех входящих обновений (ДИАГНОСТИКА)
    dp.update.outer_middleware(log_update_middleware)
    logger.info("LogUpdateMiddleware зарегистрирован (ДИАГНОСТИКА)")

    db_middleware = DatabaseConnectionMiddleware()
    dp.update.middleware(db_middleware)
    logger.info("DatabaseConnectionMiddleware зарегистрирован")

    # 1. UserMiddleware - регистрация пользователей
    user_middleware = UserMiddleware()
    dp.message.middleware(user_middleware)
    dp.callback_query.middleware(user_middleware)
    logger.info("UserMiddleware зарегистрирован")
    
    # 2. LanguageMiddleware - определение языка
    language_middleware = LanguageMiddleware()
    dp.message.middleware(language_middleware)
    dp.callback_query.middleware(language_middleware)
    logger.info("LanguageMiddleware зарегистрирован")
    
    # 3. RateLimitMiddleware - ограничение частоты запросов
    rate_limit_middleware = RateLimitMiddleware()
    dp.message.middleware(rate_limit_middleware)
    logger.info("RateLimitMiddleware зарегистрирован")

    # 5. PremiumCheckMiddleware - проверка подписки
    premium_check_middleware = PremiumCheckMiddleware()
    dp.message.middleware(premium_check_middleware)
    dp.callback_query.middleware(premium_check_middleware)
    logger.info("PremiumCheckMiddleware зарегистрирован")    
    
    logger.info("Все middleware зарегистрированы")
    
    # === Регистрация handlers ===
    logger.info("Регистрация handlers...")
    
    # Регистрируем все роутеры
    for router in all_routers:
        dp.include_router(router)
        logger.info(
            f"Зарегистрирован {getattr(router, 'name', 'unnamed')} "
            f"с {len(router.message.handlers)} message handlers и "
            f"{len(router.callback_query.handlers)} callback handlers"
        )
    
    logger.info("Все handlers зарегистрированы")
    logger.info("Bot инициализирован успешно")

    state_manager.set_bot(bot)
    logger.info("Bot instance передан в state_manager")    
    
    try:
        logger.info("=" * 60)
        logger.info("ЗАПУСК POLLING")
        logger.info("=" * 60)
        logger.info("Если видите это сообщение - бот начал polling")
        logger.info("Следующее сообщение должно быть от aiogram о получении обновлений")
        logger.info("=" * 60)
        # Запуск polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"✗ Bot остановлен с ошибкой: {e}", exc_info=True)
    finally:
        logger.info("Bot shutdown завершен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot остановлен пользователем")
    except Exception as e:
        print(f"Bot остановлен с ошибкой: {e}")