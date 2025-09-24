# /home/shlicha/psycho_diary/bot/handlers/profile.py
"""
Handlers для работы с профилем
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from messages import get_message, get_button_text
from bot.keyboards import get_back_keyboard, get_profile_keyboard
from users.models import UserProfileHistory

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "user_profile")
async def show_user_profile(callback: CallbackQuery, user, language: str):
    """Показ основного профиля пользователя."""
    try:
        has_psychological_data = bool(
            (user.personality_traits and isinstance(user.personality_traits, dict) and user.personality_traits) or
            (user.life_facts and isinstance(user.life_facts, list) and user.life_facts) or
            user.personality_description
        )
        profile_msg = get_message(
            key='profile_title',
            language=user.language,
            user_telegram_id=user.telegram_id,
            username=user.username if user.username else '',
            first_name=user.first_name if user.first_name else '',
            last_name=user.last_name if user.last_name else '',
            notifications_status='✅' if user.notifications_enabled else '❌',
            auto_analysis_status='✅' if user.auto_analysis_enabled else '❌',
            premium_status='✅' if user.is_premium else '❌',
            awareness_level=user.awareness_level,
            registration_date=user.created_at.strftime('%d.%m.%Y') if user.created_at else '',
            last_entry=user.last_entry.strftime('%d.%m.%Y %H:%M') if user.last_entry else ''
        )
        try:
            @sync_to_async
            def _get_last_profile_history_sync():
                return UserProfileHistory.objects.filter(user=user).order_by('-created_at').first()
            last_profile_history = await _get_last_profile_history_sync()
            if last_profile_history:
                profile_msg += get_message(
                    key='last_analysis',
                    language=user.user.language,
                    last_analysis_date=last_profile_history.created_at.strftime('%d.%m.%Y %H:%M') if last_profile_history else ''
                    )
        except Exception as e:
            logger.debug(f"Не удалось получить дату последнего анализа профиля: {e}")
        await callback.message.edit_text(
            profile_msg,
            reply_markup=get_profile_keyboard(language, show_psychology_button=has_psychological_data)
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
        psychology_msg = get_message(
            key='psychological_portrait',
            language=user.language
        )
        if user.personality_description:
            desc = user.personality_description.strip()
            if len(desc) > MAX_DESC_LENGTH:
                desc = desc[:MAX_DESC_LENGTH] + get_message(key='description_shortened', language=user.language)
            psychology_msg += desc
        else:
            psychology_msg += get_message(key='portrait_not_ready', language=user.language)
        if len(psychology_msg) > MAX_TOTAL_LENGTH:
             psychology_msg = psychology_msg[:MAX_TOTAL_LENGTH] + get_message(key='message_truncated', language=user.language)
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
