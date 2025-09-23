# /home/shlicha/psycho_diary/bot/handlers/profile.py
"""
Handlers для работы с профилем
"""

import logging
import json
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from messages import get_message, get_button_text
from bot.keyboards import get_back_keyboard
from users.models import UserProfileHistory

router = Router()
logger = logging.getLogger(__name__)

async def _format_json_field_as_text(data, max_items: int = 10) -> str:
    """Форматирует JSON-поле (dict/list) в человекочитаемый текст."""
    if not data:
        return "Нет данных"
    
    if isinstance(data, dict):
        if not data:
            return "Нет данных"
        lines = []
        for i, (key, value) in enumerate(data.items()):
            if i >= max_items:
                lines.append("... (и другие)")
                break
            if isinstance(value, (int, float)):
                lines.append(f"• {key}: {value}")
            else:
                lines.append(f"• {key}: {value}")
        return "\n".join(lines)
    elif isinstance(data, list):
        if not data:
            return "Нет данных"
        lines = []
        for i, item in enumerate(data):
            if i >= max_items:
                lines.append("... (и другие)")
                break
            if isinstance(item, dict):
                if len(item) == 1:
                    k, v = next(iter(item.items()))
                    lines.append(f"• {k}: {v}")
                else:
                    lines.append(f"• {json.dumps(item, ensure_ascii=False)}")
            else:
                lines.append(f"• {item}")
        return "\n".join(lines)
    else:
        return str(data)

def _get_profile_keyboard(language: str, show_psychology_button: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру для экрана профиля."""
    buttons = []
    
    if show_psychology_button:
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_view_psychology_profile', language),
                callback_data="view_psychology_profile"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "user_profile")
async def show_user_profile(callback: CallbackQuery, user, language: str):
    """Показ основного профиля пользователя."""
    try:
        has_psychological_data = bool(
            (user.personality_traits and isinstance(user.personality_traits, dict) and user.personality_traits) or
            (user.life_facts and isinstance(user.life_facts, list) and user.life_facts) or
            user.personality_description
        )
        
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
        try:
            @sync_to_async
            def _get_last_profile_history_sync():
                return UserProfileHistory.objects.filter(user=user).order_by('-created_at').first()
            last_profile_history = await _get_last_profile_history_sync()
            if last_profile_history:
                profile_msg += f"\n🕒 <b>Последний анализ профиля:</b> {last_profile_history.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        except Exception as e:
            logger.debug(f"Не удалось получить дату последнего анализа профиля: {e}")
        await callback.message.edit_text(
            profile_msg,
            reply_markup=_get_profile_keyboard(language, show_psychology_button=has_psychological_data)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data == "view_psychology_profile")
async def show_psychology_profile(callback: CallbackQuery, user, language: str):
    """Показ психологического профиля пользователя (только текстовое описание)."""
    MAX_DESC_LENGTH = 3500
    MAX_TOTAL_LENGTH = 3580
    
    try:
        psychology_msg = "🧠 <b>Ваш психологический портрет</b>\n\n"
        if user.personality_description:
            desc = user.personality_description.strip()
            if len(desc) > MAX_DESC_LENGTH:
                desc = desc[:MAX_DESC_LENGTH] + "\n\n<i>...(описание сокращено)...</i>" 
            psychology_msg += desc
        else:
            psychology_msg += "Еще не сформировано. Продолжайте вести дневник, и ИИ постепенно создаст ваш психологический портрет."
        if len(psychology_msg) > MAX_TOTAL_LENGTH:
             psychology_msg = psychology_msg[:MAX_TOTAL_LENGTH] + "\n\n<i>...(сообщение обрезано)...</i>"
        back_buttons = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_back', language),
                    callback_data="user_profile"
                )
            ]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=back_buttons)
        await callback.message.edit_text(
            psychology_msg,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе психологического профиля: {e}", exc_info=True)
        error_msg = get_message('error_generic', language=language)
        await callback.message.edit_text(error_msg, reply_markup=get_back_keyboard(language))
        await callback.answer(error_msg, show_alert=True)
