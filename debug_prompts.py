# /home/shlicha/debug_prompts.py
"""
Скрипт для отладки подсказок
"""

import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from diary.services.smart_prompt_manager import smart_prompt_manager
from users.models import User
from diary.models import NextEntryPrompt
from datetime import date

async def debug_prompts():
    """Проверяем состояние подсказок"""
    user = await User.objects.aget(telegram_id=399096554)
    today = date.today()
    
    print("=== ДЕБАГ ПОДСКАЗОК ===")
    print(f"Пользователь: {user.telegram_id}")
    print(f"Сегодня: {today}")
    
    # Проверяем существующие подсказки
    from asgiref.sync import sync_to_async
    
    @sync_to_async
    def get_prompts():
        return list(NextEntryPrompt.objects.filter(user=user).order_by('-target_date'))
    
    prompts = await get_prompts()
    print(f"\nНайдено подсказок: {len(prompts)}")
    
    for p in prompts:
        print(f"- {p.target_date}: used={p.is_used}, text: {p.prompt_text[:50]}...")
    
    # Проверяем получение подсказки на сегодня
    prompt_text = await smart_prompt_manager.get_prompt_for_user(user, 'ru')
    print(f"\nПодсказка для сегодня: {prompt_text[:100]}...")
    
    # Проверяем логику дат
    print(f"\n=== ПРОВЕРКА ДАТ ===")
    from diary.models import DiaryEntry
    try:
        last_entry = await DiaryEntry.objects.filter(user=user).alatest('created_at')
        entry_date = await last_entry.aentry_date()
        print(f"Последняя запись: {last_entry.id}, дата: {entry_date}")
        print(f"Совпадает с сегодня: {entry_date == today}")
    except Exception as e:
        print(f"Ошибка получения последней записи: {e}")

if __name__ == "__main__":
    asyncio.run(debug_prompts())