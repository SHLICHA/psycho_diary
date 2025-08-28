"""
Handlers для работы с профилем
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from messages import get_message
from bot.keyboards import get_back_keyboard

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "user_profile")
async def show_user_profile(callback: CallbackQuery, user, language: str):
    """Показ профиля пользователя"""
    try:
        profile_msg = f"""👤 <b>Ваш профиль</b>

🆔 <b>ID:</b> {user.telegram_id}
📝 <b>Имя пользователя:</b> @{user.username if user.username else 'Не указан'}
👤 <b>Имя:</b> {user.first_name if user.first_name else 'Не указано'}
👥 <b>Фамилия:</b> {user.last_name if user.last_name else 'Не указана'}
🌍 <b>Язык:</b> {'Русский' if user.language == 'ru' else 'English'}
🔔 <b>Уведомления:</b> {'Включены' if user.notifications_enabled else 'Выключены'}
📈 <b>Автоанализ:</b> {'Включен' if user.auto_analysis_enabled else 'Выключен'}
👑 <b>Премиум:</b> {'Да' if user.is_premium else 'Нет'}
📊 <b>Уровень осознанности:</b> {user.awareness_level}/10
📅 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Не указана'}
📝 <b>Последняя запись:</b> {user.last_entry.strftime('%d.%m.%Y %H:%M') if user.last_entry else 'Нет записей'}
"""
        await callback.message.edit_text(
            profile_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}")
        await callback.answer(get_message('error_generic', language=language))