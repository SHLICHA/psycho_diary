"""
Handlers для работы с настройками
"""

import re
import pytz
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from messages import get_message
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_language_selection_keyboard,
    get_premium_keyboard,
    get_back_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard
    )
from bot.utils.state_manager import state_manager

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery, user, language: str):
    """Показ настроек"""
    try:
        settings_msg = get_message('settings_menu', language=language)
        await callback.message.edit_text(
            settings_msg,
            reply_markup=get_settings_keyboard(user, language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе настроек: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_change_language")
async def change_language(callback: CallbackQuery, state: FSMContext, language: str):
    """Изменение языка"""
    try:
        await state_manager.set_state(state, SettingsStates.waiting_for_language_choice)
        language_msg = get_message('settings_menu', language=language)
        await callback.message.edit_text(
            language_msg,
            reply_markup=get_language_selection_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе выбора языка: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_language:"))
async def set_language(callback: CallbackQuery, user, state: FSMContext, language: str):
    """Установка языка"""
    try:
        new_language = callback.data.split(":")[1]
        supported_languages = ['ru', 'en']
        if new_language not in supported_languages:
            logger.warning(f"Неподдерживаемый язык: {new_language}")
            await callback.answer(get_message('error_generic', language=language))
            return
        user.language = new_language
        await user.asave(update_fields=['language'])
        await state_manager.clear_state(state)
        success_msg = get_message('language_changed', language=new_language)
        if callback.message.text != success_msg:
            await callback.message.edit_text(
                success_msg,
                reply_markup=get_settings_keyboard(user, new_language)
            )
        else:
            try:
                await callback.message.edit_reply_markup(
                    reply_markup=get_settings_keyboard(user, new_language)
                )
            except Exception as e:
                logger.warning(f"Не удалось обновить клавиатуру: {e}")
                await callback.message.edit_text(
                    success_msg,
                    reply_markup=get_settings_keyboard(user, new_language)
                )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при установке языка: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_toggle_notifications")
async def toggle_notifications(callback: CallbackQuery, user, language: str):
    """Переключение уведомлений"""
    try:
        current_state = user.notifications_enabled
        new_state = not current_state
        user.notifications_enabled = new_state
        await user.asave(update_fields=['notifications_enabled'])
        if new_state:
            toggle_msg = get_message('notifications_enabled', language=language)
        else:
            toggle_msg = get_message('notifications_disabled', language=language)
        await callback.answer(toggle_msg)
        new_keyboard = get_settings_keyboard(user, language)
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        except Exception as e:
            logger.warning(f"Не удалось обновить клавиатуру напрямую: {e}")
            settings_msg = get_message('settings_menu', language=language)
            await callback.message.edit_text(
                settings_msg,
                reply_markup=new_keyboard
            )
    except Exception as e:
        logger.error(f"Ошибка при переключении уведомлений: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_toggle_auto_analysis")
async def toggle_auto_analysis(callback: CallbackQuery, user, language: str):
    """Переключение автоанализа"""
    try:
        current_state = user.auto_analysis_enabled
        new_state = not current_state
        user.auto_analysis_enabled = new_state
        await user.asave(update_fields=['auto_analysis_enabled'])
        if new_state:
            toggle_msg = get_message('settings_auto_analysis', language=language).format(
                status=get_message('status_enabled', language=language)
            )
        else:
            toggle_msg = get_message('settings_auto_analysis', language=language).format(
                status=get_message('status_disabled', language=language)
            )
        await callback.answer(toggle_msg)
        new_keyboard = get_settings_keyboard(user, language)
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        except Exception as e:
            logger.warning(f"Не удалось обновить клавиатуру напрямую: {e}")
            settings_msg = get_message('settings_menu', language=language)
            await callback.message.edit_text(
                settings_msg,
                reply_markup=new_keyboard
            )     
    except Exception as e:
        logger.error(f"Ошибка при переключении автоанализа: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_premium")
async def show_premium(callback: CallbackQuery, user, language: str):
    """Показ премиум функций"""
    try:
        if user.is_premium:
            premium_msg = get_message('settings_premium', language=language).format(
                status=get_message('status_enabled', language=language)
            )
        else:
            premium_msg = get_message('premium_benefits', language=language)
        await callback.message.edit_text(
            premium_msg,
            reply_markup=get_premium_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе премиум функций: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "premium_subscribe")
async def premium_subscribe(callback: CallbackQuery, user, language: str):
    """Подписка на премиум"""
    try:
        subscribe_msg = "💳 Для подписки на премиум функции свяжитесь с администратором"
        await callback.message.edit_text(
            subscribe_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при подписке на премиум: {e}")
        await callback.answer(get_message('error_generic', language=language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data == "settings_change_timezone")
async def change_timezone(callback: CallbackQuery, user, language: str):
    """Начало изменения часового пояса"""
    try:
        timezone_msg = get_message('ask_timezone_selection', language, current_timezone=user.timezone)
        reply_markup = get_timezone_selection_method_keyboard(language, user.timezone)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе вариантов выбора часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "timezone_select_from_list")
async def select_timezone_from_list(callback: CallbackQuery, user, language: str):
    """Выбор часового пояса из списка"""
    try:
        timezone_msg = get_message('select_timezone_title', language, current_timezone=user.timezone)
        reply_markup = get_common_timezones_keyboard(language, user.timezone)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
        logger.info("Показан список популярных часовых поясов")
    except Exception as e:
        logger.error(f"Ошибка при показе списка часовых поясов: {e}")
        await callback.answer(get_message('error_generic', language=language))

# TODO Реализовать ввод местополения и определения часового пояса
@router.callback_query(F.data == "timezone_enter_manually")
async def enter_timezone_manually(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Ввод часового пояса вручную"""
    try:
        timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
        reply_markup = get_back_keyboard(language)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await state_manager.set_state(state, SettingsStates.waiting_for_timezone_input)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе ручного введения часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_timezone:"))
async def set_timezone(callback: CallbackQuery, user, language: str):
    """Установка выбранного часового пояса"""
    try:
        new_timezone_str = callback.data.split(":", 1)[1]
        try:
            tz_obj = pytz.timezone(new_timezone_str)
            canonical_tz_name = str(tz_obj)
            user.timezone = canonical_tz_name
            await user.asave(update_fields=['timezone'])
            success_msg = get_message('timezone_changed', language, timezone=canonical_tz_name)
            settings_msg = get_message('settings_menu', language=language)
            reply_markup = get_settings_keyboard(user, language)
            await callback.message.edit_text(
                settings_msg,
                reply_markup=reply_markup
            )
            await callback.answer(success_msg)
        except pytz.UnknownTimeZoneError:
            logger.error(f"Неизвестный часовой пояс: {new_timezone_str}")
            error_msg = get_message('error_unknown_timezone', language)
            await callback.answer(error_msg, show_alert=True)
            return      
    except Exception as e:
        logger.error(f"Ошибка при установке часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.message(SettingsStates.waiting_for_timezone_input)
async def process_timezone_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ручного ввода часового пояса"""
    try:
        input_text = message.text.strip()
        if input_text.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            settings_msg = get_message('settings_menu', language=language)
            await message.answer(
                settings_msg,
                reply_markup=get_settings_keyboard(user, language)
            )
            return
        if not re.match(r"^[a-zA-Z]+/[a-zA-Z_]+$", input_text):
            logger.warning(f"Неверный формат часового пояса: {input_text}")
            error_msg = get_message('error_invalid_timezone', language)
            await message.answer(error_msg)
            timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
            await message.answer(timezone_msg, reply_markup=get_back_keyboard(language))
            return
        try:
            tz_obj = pytz.timezone(input_text)
            canonical_tz_name = str(tz_obj)
            user.timezone = canonical_tz_name
            await user.asave(update_fields=['timezone'])
            await state_manager.clear_state(state)
            success_msg = get_message('timezone_changed', language, timezone=canonical_tz_name)
            await message.answer(success_msg)
            settings_msg = get_message('settings_menu', language=language)
            await message.answer(
                settings_msg,
                reply_markup=get_settings_keyboard(user, language)
            )      
        except pytz.UnknownTimeZoneError:
            logger.error(f"Неизвестный введенный часовой пояс: {input_text}")
            error_msg = get_message('error_unknown_timezone', language)
            await message.answer(error_msg)
            timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
            await message.answer(timezone_msg, reply_markup=get_back_keyboard(language))
            return
    except Exception as e:
        logger.error(f"Ошибка при обработке ручного ввода часового пояса: {e}")
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)
