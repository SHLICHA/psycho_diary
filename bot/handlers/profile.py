# /home/shlicha/psycho_diary/bot/handlers/profile.py
"""
Handlers для работы с профилем
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from messages import get_message, get_button_text
from bot.keyboards import get_single_button_keyboard, get_profile_keyboard
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
        profile_detail_buttons = []
        if user.core_values:
            profile_detail_buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_view_values', language),
                    callback_data="view_profile_field:core_values"
                )
            ])
        if user.triggers:
            profile_detail_buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_view_triggers', language),
                    callback_data="view_profile_field:triggers"
                )
            ])
        if user.strengths:
            profile_detail_buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_view_strengths', language),
                    callback_data="view_profile_field:strengths"
                )
            ])
        if user.areas_for_growth:
            profile_detail_buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_view_growth', language),
                    callback_data="view_profile_field:areas_for_growth"
                )
            ])
        if user.personality_insights:
            profile_detail_buttons.append([
                InlineKeyboardButton(
                    text=get_button_text('btn_view_insights', language),
                    callback_data="view_profile_field:personality_insights"
                )
            ])
        # Кнопка "Назад" к общему профилю
        profile_detail_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="user_profile"
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=profile_detail_buttons)
        await callback.message.edit_text(
            psychology_msg,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе психологического профиля: {e}", exc_info=True)
        error_msg = get_message('error_generic', language=language)
        await callback.message.edit_text(error_msg, reply_markup=get_single_button_keyboard(language, 'user_profile', 'btn_back'))
        await callback.answer(error_msg, show_alert=True)

@router.callback_query(F.data.startswith("view_profile_field:"))
async def show_profile_field(callback: CallbackQuery, user, language: str):
    """Показывает конкретное поле психологического профиля."""
    try:
        field_key = callback.data.split(":")[1]
        valid_profile_fields = {
            'personality_traits', 'life_facts', 'hobbies', 'core_values',
            'triggers', 'strengths', 'areas_for_growth', 'personality_insights',
            'habits', 'skills', 'aspirations', 'personality_description'
        }
        if field_key not in valid_profile_fields:
            logger.warning(f"Получен запрос на отображение недопустимого поля профиля: {field_key}")
            error_msg = get_message('field_not_found', language)
            await callback.answer(error_msg, show_alert=True)
            return
        field_value = getattr(user, field_key, None)
        field_emojis = {
            'core_values': '🎯',
            'triggers': '⚠️',
            'strengths': '💪',
            'areas_for_growth': '🌱',
            'personality_insights': '💡',
            'personality_description': '📝',
            'personality_traits': '🧠',
            'life_facts': '📋',
            'hobbies': '🎨',
            'habits': '🔄',
            'skills': '🛠️',
            'aspirations': '🌟',
        }
        emoji = field_emojis.get(field_key, '📋')
        field_display_name = f"{emoji} {get_message(f'field_name_{field_key}', language)}"

        if field_value is None:
            error_msg = get_message('field_not_found', language)
            await callback.answer(error_msg, show_alert=True)
            return

        field_text = ""
        if isinstance(field_value, list):
            if field_value:
                formatted_items = []
                item_emoji = "\n🔸"
                for item in field_value:
                    if isinstance(item, dict):
                        item_text = item.get('text') or item.get('name') or item.get('theme') or item.get('emotion') or item.get('category') or str(item)
                        item_text = item_text or item.get('insight') or item.get('pattern') or item_text
                        if 'text' in item and 'category' in item:
                             insight_text = item['text']
                             insight_category = item['category']
                             formatted_items.append(f"{item_emoji} {insight_text} (Категория: {insight_category})")
                        elif 'emotion' in item and 'context' in item:
                             emotion_text = item['emotion']
                             emotion_context = item['context']
                             formatted_items.append(f"{item_emoji} {emotion_text} (Контекст: {emotion_context})")
                        else:
                             formatted_items.append(f"{item_emoji} {item_text}")
                    else:
                        formatted_items.append(f"{item_emoji} {item}")
                field_text = f"<b>{field_display_name}</b>" + " ".join(formatted_items)
            else:
                field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_list', language)
        elif isinstance(field_value, dict):
            if field_value:
                dict_items = [f"  <b>{k}</b>: {v}" for k, v in field_value.items()]
                field_text = f"<b>{field_display_name}</b>" + " ".join(dict_items)
            else:
                field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_dict', language)
        elif isinstance(field_value, str):
            if field_value.strip():
                field_text = f"<b>{field_display_name}</b>{field_value.strip()}"
            else:
                field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_string', language)
        else:
            field_text = f"<b>{field_display_name}</b>{field_value}"
        back_to_psychology_button = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_back_to_psychology', language),
                    callback_data="view_psychology_profile"
                )
            ]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=back_to_psychology_button)
        await callback.message.edit_text(
            field_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга callback_data в show_profile_field: {callback.data} - {e}")
        await callback.answer(get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при показе поля профиля {callback.data}: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language), show_alert=True)

