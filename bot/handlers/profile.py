# /home/shlicha/psycho_diary/bot/handlers/profile.py
"""
Handlers для работы с профилем
"""

import re
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone

from messages import get_message, get_button_text
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_profile_keyboard,
    get_single_button_keyboard,
    get_edit_profile_keyboard,
    get_account_deletion_confirmation_keyboard,
    get_account_deletion_menu_keyboard,
    get_main_menu_keyboard
    )
from bot.utils.state_manager import state_manager
from diary.models import *
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
            token_balance = user.token_balance,
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
                             formatted_items.append(f"{item_emoji} {insight_text} ({get_message('category', language)}: {insight_category})")
                        elif 'emotion' in item and 'context' in item:
                             emotion_text = item['emotion']
                             emotion_context = item['context']
                             formatted_items.append(f"{item_emoji} {emotion_text} ({get_message('context', language)}: {emotion_context})")
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

@router.callback_query(F.data == "edit_profile")
async def show_edit_profile_menu(callback: CallbackQuery, user, language: str):
    """Показ меню редактирования профиля"""
    try:
        profile_data = {
            'first_name': user.first_name or get_message('not_specified', language),
            'email': user.email or get_message('not_specified', language),
            'date_of_birth': user.date_of_birth.strftime('%d.%m.%Y') if user.date_of_birth else get_message('not_specified', language),
            'hobbies': ', '.join([str(h) for h in user.hobbies if isinstance(h, (str, int, float))]) if isinstance(user.hobbies, list) else get_message('not_specified', language),
            'life_facts': ', '.join([str(f) for f in user.life_facts if isinstance(f, (str, int, float))]) if isinstance(user.life_facts, list) else get_message('not_specified', language)
        }
        profile_msg = get_message('profile_menu', language, **profile_data)
        reply_markup = get_edit_profile_keyboard(language)
        await callback.message.edit_text(
            profile_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню редактирования профиля: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "edit_profile_name")
async def edit_profile_name(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование имени"""
    try:
        await state_manager.set_state(state, SettingsStates.waiting_for_name_input)
        ask_msg = get_message('ask_new_name', language)
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            ask_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе нового имени: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "edit_profile_email")
async def edit_profile_email(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование email"""
    try:
        await state_manager.set_state(state, SettingsStates.waiting_for_email_input)
        ask_msg = get_message('ask_new_email', language)
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            ask_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе нового email: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "edit_profile_dob")
async def edit_profile_dob(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование даты рождения"""
    try:
        await state_manager.set_state(state, SettingsStates.waiting_for_date_of_birth_input)
        ask_msg = get_message('ask_new_dob', language)
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            ask_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе новой даты рождения: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "edit_profile_hobbies")
async def edit_profile_hobbies(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование увлечений"""
    try:
        current_hobbies = ', '.join(user.hobbies) if user.hobbies else ''
        await state_manager.set_state(state, SettingsStates.waiting_for_hobbies_input)
        ask_msg = get_message('ask_new_hobbies', language)
        if current_hobbies:
            ask_msg += get_message(
                key='current_hobbies',
                language=language,
                current_hobbies=current_hobbies)
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            ask_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе новых увлечений: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "edit_profile_life_facts")
async def edit_profile_life_facts(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование фактов о жизни"""
    try:
        current_facts = ', '.join(user.life_facts) if user.life_facts else ''
        await state_manager.set_state(state, SettingsStates.waiting_for_life_facts_input)
        ask_msg = get_message('ask_new_life_facts', language)
        if current_facts:
            ask_msg += get_message(
                key='current_facts',
                language=language,
                current_facts=current_facts
            )
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            ask_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе новых фактов о жизни: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.message(SettingsStates.waiting_for_name_input)
async def process_name_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода нового имени"""
    try:
        new_name = message.text.strip()
        if new_name.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return
        if not new_name:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            return
        user.first_name = new_name
        await user.asave(update_fields=['first_name'])
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода нового имени: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)

@router.message(SettingsStates.waiting_for_email_input)
async def process_email_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода нового email"""
    try:
        new_email = message.text.strip()
        if new_email.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return
        if not new_email:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            return
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, new_email):
            error_msg = get_message('invalid_email_format', language)
            await message.answer(error_msg)
            return
        user.email = new_email
        await user.asave(update_fields=['email'])
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода нового email: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)

@router.message(SettingsStates.waiting_for_date_of_birth_input)
async def process_dob_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новой даты рождения"""
    try:
        dob_text = message.text.strip()
        if dob_text.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return
        if not dob_text:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            return
        try:
            new_dob = datetime.strptime(dob_text, '%d.%m.%Y').date()
            if new_dob > datetime.now().date():
                error_msg = get_message('invalid_date_future', language)
                await message.answer(error_msg)
                return
        except ValueError:
            error_msg = get_message('invalid_date_format', language)
            await message.answer(error_msg)
            return
        user.date_of_birth = new_dob
        await user.asave(update_fields=['date_of_birth'])
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода новой даты рождения: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)

@router.message(SettingsStates.waiting_for_hobbies_input)
async def process_hobbies_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новых увлечений"""
    try:
        hobbies_text = message.text.strip()
        if hobbies_text.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return
        if hobbies_text:
            new_hobbies = [hobby.strip() for hobby in hobbies_text.split(',') if hobby.strip()]
        else:
            new_hobbies = []
        user.hobbies = new_hobbies
        await user.asave(update_fields=['hobbies'])
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода новых увлечений: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)

@router.message(SettingsStates.waiting_for_life_facts_input)
async def process_life_facts_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новых фактов о жизни"""
    try:
        facts_text = message.text.strip()
        if facts_text.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return
        if facts_text:
            new_facts = [fact.strip() for fact in facts_text.split(',') if fact.strip()]
        else:
            new_facts = []
        user.life_facts = new_facts
        await user.asave(update_fields=['life_facts'])
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода новых фактов о жизни: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)

async def show_edit_profile_menu_callback(message_or_callback, user, language: str):
    """Показ меню редактирования профиля (callback)"""
    try:
        profile_data = {
            'first_name': user.first_name or get_message('not_specified', language),
            'email': user.email or get_message('not_specified', language),
            'date_of_birth': user.date_of_birth.strftime('%d.%m.%Y') if user.date_of_birth else get_message('not_specified', language),
            'hobbies': ', '.join(user.hobbies) if user.hobbies else get_message('not_specified', language),
            'life_facts': ', '.join(user.life_facts) if user.life_facts else get_message('not_specified', language)
        }
        profile_msg = get_message('profile_menu', language, **profile_data)
        reply_markup = get_edit_profile_keyboard(language)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(
                profile_msg,
                reply_markup=reply_markup
            )
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text(
                profile_msg,
                reply_markup=reply_markup
            )
            await message_or_callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню редактирования профиля: {e}")
        error_msg = get_message('error_generic', language)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(error_msg)
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer(error_msg)

@router.callback_query(F.data == "delete_account")
async def show_account_deletion_menu(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Показ меню удаления аккаунта"""
    try:
        balance = 0
        if balance > 0:
            balance_info = get_message('account_balance_info_positive', language, balance=balance)
            balance_warning = get_message('balance_warning_positive', language, balance=balance)
        elif balance == 0:
            balance_info = get_message('account_balance_info_zero', language)
            balance_warning = get_message('balance_warning_zero_or_negative', language)
        else:
            balance_info = get_message('account_balance_info_negative', language, balance=abs(balance))
            balance_warning = get_message('balance_warning_zero_or_negative', language)
        menu_msg = get_message('account_deletion_menu', language, balance_info=balance_info)
        await state_manager.set_state(state, SettingsStates.in_account_deletion_menu)
        await state_manager.update_state_data(state, balance_warning=balance_warning)
        await callback.message.edit_text(
            menu_msg,
            reply_markup=get_account_deletion_menu_keyboard(language, balance_info)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню удаления аккаунта: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "confirm_account_deletion_final")
async def confirm_account_deletion_final(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Финальное подтверждение удаления аккаунта - запрос текста подтверждения"""
    try:
        data = await state_manager.get_state_data(state)
        balance_warning = data.get('balance_warning', '')
        confirm_msg = get_message('confirm_account_deletion', language, balance_warning=balance_warning)
        await state_manager.set_state(state, SettingsStates.waiting_for_deletion_confirmation_text)
        await callback.message.edit_text(
            confirm_msg,
            reply_markup=get_account_deletion_confirmation_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при финальном подтверждении удаления аккаунта: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.message(SettingsStates.waiting_for_deletion_confirmation_text)
async def process_account_deletion_confirmation_text(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода текста подтверждения удаления аккаунта"""
    try:
        confirmation_text = message.text.strip()
        expected_text = get_message('delete_account_btn', language)
        if confirmation_text != expected_text:
            error_msg = get_message('invalid_confirmation_text', language)
            await message.answer(error_msg)
            data = await state_manager.get_state_data(state)
            balance_warning = data.get('balance_warning', '')
            confirm_msg = get_message('confirm_account_deletion', language, balance_warning=balance_warning)
            await message.answer(confirm_msg)
            return
        success = await anonymize_user_account(user)
        if success:
            success_msg = get_message('account_deletion_confirmed', language)
            await message.answer(success_msg)
            await state_manager.clear_state(state)
        else:
            error_msg = get_message('account_deletion_error', language)
            await message.answer(error_msg)
    except Exception as e:
        logger.error(f"Ошибка при обработке текста подтверждения удаления аккаунта: {e}")
        error_msg = get_message('account_deletion_error', language)
        await message.answer(error_msg)

@router.callback_query(F.data == "delete_account_cancel")
async def cancel_account_deletion(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Отмена удаления аккаунта"""
    try:
        cancel_msg = get_message('account_deletion_cancelled', language)
        await callback.message.edit_text(cancel_msg)
        settings_msg = get_message('settings_menu', language=language)
        await callback.message.edit_text(
            settings_msg,
            reply_markup=get_main_menu_keyboard(user, language)
        )
        await state_manager.clear_state(state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления аккаунта: {e}")
        await callback.answer(get_message('error_generic', language=language))

async def anonymize_user_account(user):
    """
    "Обезличивание" аккаунта пользователя:
    - Удаление всех данных из моделей приложения diary
    - Обнуление персональных данных в модели User
    - Установка флагов deleted_at, is_blocked, deletion_status
    - Отключение уведомлений
    """
    try:
        await TaskCompletionAnalysis.objects.filter(
            completion__task__user=user
        ).adelete()
        await TaskCompletion.objects.filter(
            task__user=user
        ).adelete()
        await TherapyTask.objects.filter(user=user).adelete()
        await TherapyProgress.objects.filter(user=user).adelete()
        await DailyAnalysis.objects.filter(
            combined_entry__user=user
        ).adelete()
        await CombinedDiaryEntry.objects.filter(user=user).adelete()
        await PsychoAnalysis.objects.filter(
            entry__user=user
        ).adelete()
        await UserActivity.objects.filter(user=user).adelete()
        await DiaryEntry.objects.filter(user=user).adelete()
        user.first_name = ""
        user.last_name = ""
        user.email = ""
        user.username = f"deleted_user_{user.telegram_id}"
        user.timezone = "UTC"
        user.last_entry = None
        user.awareness_level = 1
        user.is_premium = False
        user.last_activity = None
        user.current_calendar_year = 2025 
        user.current_calendar_month = 1
        user.notifications_enabled = False
        user.auto_analysis_enabled = False
        user.max_ai_tasks_per_day = 1
        user.personality_description = ''
        user.personality_traits = {}
        user.life_facts = []
        user.hobbies = []
        user.core_values = []
        user.triggers = []
        user.strengths = []
        user.areas_for_growth = []
        user.date_of_birth = None
        user.deleted_at = timezone.now()
        user.is_blocked = True 
        user.deletion_status = 'anonymized'
        await user.asave()
        logger.info(f"Аккаунт пользователя {user.telegram_id} успешно обезличен")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обезличивании аккаунта пользователя {user.telegram_id}: {e}", exc_info=True)
        return False