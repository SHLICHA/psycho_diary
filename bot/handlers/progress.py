"""
Handlers для прогресса
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards import get_back_keyboard
from messages import get_message

router = Router()

@router.callback_query(F.data == "progress")
async def show_progress(callback: CallbackQuery, user, language: str):
    """Показ прогресса"""
    progress_msg = get_message(
        'progress_title',
        language,
        awareness_level=user.awareness_level,
        entries_count=0,
        tasks_completed=0,
        streak_days=0
    )
    await callback.message.edit_text(
        progress_msg,
        reply_markup=get_back_keyboard(language)
    )
    await callback.answer()