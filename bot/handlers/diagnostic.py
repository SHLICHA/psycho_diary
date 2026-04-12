"""
Диагностический хэндлер для проверки работы бота.
Отвечает на команду /test_ping простым сообщением.
"""
import logging
from aiogram import Router
from aiogram.filters import Command

router = Router(name='Diagnostic_router')
logger = logging.getLogger(__name__)


@router.message(Command('test_ping'))
async def test_ping_handler(message):
    """
    Простой хэндлер для диагностики.
    Если бот отвечает на эту команду - значит:
    1. Polling работает
    2. Бот получает сообщения от Telegram
    3. Связь с Telegram есть
    """
    logger.info(f"🏓 Получена команда /test_ping от пользователя {message.from_user.id}")
    
    response = (
        "🏓 <b>PONG!</b>\n\n"
        "✅ Бот работает!\n"
        "✅ Polling активен\n"
        "✅ Бот получает сообщения\n"
        "✅ Прокси работает (если настроен)\n\n"
        "Если вы это видите - всё отлично! 🎉"
    )
    
    await message.answer(response)
    logger.info(f"✓ Отправлен ответ на /test_ping пользователю {message.from_user.id}")
