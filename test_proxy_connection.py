#!/usr/bin/env python
"""
Тестовый скрипт для проверки подключения бота через прокси.
Запускать: python test_proxy_connection.py
"""
import os
import sys
import asyncio
from pathlib import Path

# Добавляем проект в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

# Загружаем .env
from dotenv import load_dotenv
load_dotenv()

from decouple import config
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode


async def test_proxy():
    """Тестируем подключение через прокси."""
    print("=" * 60)
    print("ТЕСТ ПОДКЛЮЧЕНИЯ БОТА ЧЕРЕЗ ПРОКСИ")
    print("=" * 60)
    
    # Получаем настройки
    bot_token = config('TELEGRAM_BOT_TOKEN', default=None)
    proxy_url = config('TELEGRAM_PROXY_URL', default=None)
    
    print(f"\n📋 Конфигурация:")
    print(f"   BOT_TOKEN: {'✅ Найден' if bot_token else '❌ Не найден'}")
    print(f"   PROXY_URL: {'✅ ' + proxy_url if proxy_url else '❌ Не настроен (будет использоваться прямое подключение)'}")
    
    if not bot_token:
        print("\n❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден в .env файле!")
        return False
    
    # Создаем сессию
    print(f"\n🔧 Создание сессии...")
    try:
        if proxy_url:
            session = AiohttpSession(proxy=proxy_url)
            print(f"   ✅ Сессия создана с прокси: {proxy_url}")
        else:
            session = AiohttpSession()
            print(f"   ✅ Сессия создана без прокси (прямое подключение)")
    except Exception as e:
        print(f"   ❌ ОШИБКА при создании сессии: {e}")
        return False
    
    # Создаем бота
    print(f"\n🤖 Создание бота...")
    try:
        bot = Bot(
            token=bot_token,
            session=session,
            parse_mode=ParseMode.HTML
        )
        print(f"   ✅ Бот создан успешно")
    except Exception as e:
        print(f"   ❌ ОШИБКА при создании бота: {e}")
        await session.close()
        return False
    
    # Тестируем подключение
    print(f"\n🌐 Тестирование подключения к Telegram API...")
    try:
        me = await bot.get_me()
        print(f"   ✅ Подключение успешно!")
        print(f"\n👤 Информация о боте:")
        print(f"   Имя: {me.first_name}")
        print(f"   Username: @{me.username}")
        print(f"   ID: {me.id}")
        success = True
    except Exception as e:
        print(f"   ❌ ОШИБКА подключения: {e}")
        print(f"\n💡 Возможные причины:")
        if proxy_url:
            print(f"   - Неверный URL прокси: {proxy_url}")
            print(f"   - Прокси-сервер недоступен")
            print(f"   - Неверные учетные данные прокси")
            print(f"   - Брандмауэр блокирует соединение")
        else:
            print(f"   - Telegram заблокирован в вашей сети")
            print(f"   - Настройте прокси в .env файле (TELEGRAM_PROXY_URL)")
        success = False
    finally:
        await session.close()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ТЕСТ ПРОЙДЕН! Бот может подключиться к Telegram.")
        if not proxy_url:
            print("⚠️  Но прокси не настроен. Если Telegram заблокирован, настройте прокси!")
    else:
        print("❌ ТЕСТ НЕ ПРОЙДЕН! Проверьте настройки и попробуйте снова.")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    try:
        result = asyncio.run(test_proxy())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Тест прерван пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        sys.exit(1)
