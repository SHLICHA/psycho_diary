"""
Handlers для работы с настройками
"""

import re
import pytz
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone
from aiogram.exceptions import TelegramBadRequest

from messages import get_message
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_premium_keyboard,
    get_single_button_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard,
    get_city_timezone_confirmation_keyboard,
    get_multiple_city_timezones_keyboard,
    get_analysis_time_selection_keyboard,
    get_edit_profile_keyboard,
    get_account_deletion_confirmation_keyboard,
    get_account_deletion_menu_keyboard,
    get_task_settings_keyboard,
    get_main_menu_keyboard
    )
from bot.services import deepseek_api_service
from bot.utils.state_manager import state_manager
from diary.models import *
from users.models import CityTimezone

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

@router.callback_query(F.data == "settings_tasks")
async def show_task_settings(callback: CallbackQuery, user, language: str):
    """Показ настроек заданий"""
    try:
        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=user.max_ai_tasks_per_day
        )
        await callback.message.edit_text(
            task_settings_msg,
            reply_markup=get_task_settings_keyboard(user, language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе настроек заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_increase_tasks_limit")
async def increase_tasks_limit(callback: CallbackQuery, user, language: str):
    """Увеличение лимита заданий"""
    try:
        awareness_level = user.awareness_level
        max_allowed = 5
        if awareness_level < 8:
            max_allowed = 1
        elif awareness_level == 8:
            max_allowed = 2
        elif awareness_level == 9:
            max_allowed = 3
        new_limit_proposed = user.max_ai_tasks_per_day + 1
        if new_limit_proposed > max_allowed:
            alert_message = get_message('awareness_level_insufficient_for_tasks_current', language=language, current_level=awareness_level, current_max_tasks=max_allowed)
            await callback.answer(alert_message, show_alert=True)
            task_settings_msg = get_message('task_settings_menu', language=language).format(
                max_tasks=user.max_ai_tasks_per_day
            )
            try:
                await callback.message.edit_text(
                    task_settings_msg,
                    reply_markup=get_task_settings_keyboard(user, language)
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    logger.debug(f"Сообщение настроек задач не изменилось для user {user.telegram_id}, редактирование проигнорировано.")
                else:
                    logger.error(f"TelegramBadRequest при редактировании сообщения настроек задач: {e}")
            return
        if user.max_ai_tasks_per_day < max_allowed:
            user.max_ai_tasks_per_day += 1
            await user.asave(update_fields=['max_ai_tasks_per_day'])
            success_msg = get_message('tasks_limit_increased', language=language).format(
                new_limit=user.max_ai_tasks_per_day
            )
        else:
            success_msg = get_message('tasks_limit_max_reached', language=language)
        await callback.answer(success_msg)

        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=user.max_ai_tasks_per_day
        )
        await callback.message.edit_text(
            task_settings_msg,
            reply_markup=get_task_settings_keyboard(user, language)
        )
    except Exception as e:
        logger.error(f"Ошибка при увеличении лимита заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_decrease_tasks_limit")
async def decrease_tasks_limit(callback: CallbackQuery, user, language: str):
    """Уменьшение лимита заданий"""
    try:
        if user.max_ai_tasks_per_day > 1:
            user.max_ai_tasks_per_day -= 1
            await user.asave(update_fields=['max_ai_tasks_per_day'])
            success_msg = get_message('tasks_limit_decreased', language=language).format(
                new_limit=user.max_ai_tasks_per_day
            )
        else:
            success_msg = get_message('tasks_limit_min_reached', language=language)
        await callback.answer(success_msg)
        from bot.keyboards import get_task_settings_keyboard
        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=user.max_ai_tasks_per_day
        )
        await callback.message.edit_text(
            task_settings_msg,
            reply_markup=get_task_settings_keyboard(user, language)
        )
    except Exception as e:
        logger.error(f"Ошибка при уменьшении лимита заданий: {e}")
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

@router.callback_query(F.data == "timezone_enter_city")
async def enter_city_for_timezone(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Ввод города для определения часового пояса"""
    try:
        city_msg = get_message(key='enter_city', language=language)
        reply_markup = get_single_button_keyboard(language, 'settings', 'btn_back')
        await callback.message.edit_text(
            city_msg,
            reply_markup=reply_markup
        )
        await state_manager.set_state(state, SettingsStates.waiting_for_city_input)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе ввода города: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.message(SettingsStates.waiting_for_city_input)
async def process_city_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода города для определения часового пояса"""
    try:
        city_name = message.text.strip()
        if city_name.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            settings_msg = get_message('settings_menu', language=language)
            await message.answer(
                settings_msg,
                reply_markup=get_settings_keyboard(user, language)
            )
            return
        if not city_name:
            error_msg = get_message(key='please_enter_city', language=language)
            await message.answer(error_msg)
            return
        try:
            city_tz = await CityTimezone.objects.aget(city_name__iexact=city_name)
            timezone_data = {
                'timezone': city_tz.timezone,
                'city': city_tz.city_name,
                'country': city_tz.country
            }
            confirmation_msg = get_message(
                key='timezone_found',
                language=language,
                city_name=city_tz.city_name,
                country=city_tz.country,
                timezone=city_tz.timezone
            )
            reply_markup = get_city_timezone_confirmation_keyboard(language, timezone_data)
            await message.answer(
                confirmation_msg,
                reply_markup=reply_markup
            )
            await state_manager.set_state(state, SettingsStates.waiting_for_timezone_confirmation, timezone_data=timezone_data)
            return
        except CityTimezone.DoesNotExist:
            pass
        await message.answer(get_message('searching_timezone', language))
        result = await deepseek_api_service.detect_timezone_by_city(city_name, language)
        if not result['success']:
            error_msg = result.get('message', get_message('timezone_error', language))
            await message.answer(f"❌ {error_msg}")
            city_msg = get_message(key='please_enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
        api_result = result['result']
        if not api_result.get('success', False):
            error_msg = api_result.get('error', get_message(key='city_not_found', language=language))
            await message.answer(f"❌ {error_msg}")
            city_msg = get_message(key='please_enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
        if api_result.get('multiple', False):
            options = api_result.get('options', [])
            if options:
                selection_msg = get_message(key='multiple_cities_found', language=language)
                reply_markup = get_multiple_city_timezones_keyboard(language, options)
                await message.answer(
                    selection_msg,
                    reply_markup=reply_markup
                )
                return
            else:
                await message.answer(get_message(key='selection_failed', language=language))
                city_msg = get_message(key='enter_city', language=language)
                await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
                return
        timezone_str = api_result.get('timezone')
        city = api_result.get('city', city_name)
        country = api_result.get('country', 'Неизвестно')
        if not timezone_str:
            await message.answer(get_message(key='timezone_detection_failed', language=language))
            city_msg = get_message(key='enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
        try:
            pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            await message.answer(get_message(key='invalid_timezone', language=language))
            city_msg = get_message(key='enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
        timezone_data = {
            'timezone': timezone_str,
            'city': city,
            'country': country
        }
        confirmation_msg = get_message(
                key='timezone_found',
                language=language,
                city_name=city,
                country=country,
                timezone=timezone_str
            )
        reply_markup = get_city_timezone_confirmation_keyboard(language, timezone_data)
        await message.answer(
            confirmation_msg,
            reply_markup=reply_markup
        )
        await state_manager.set_state(state, SettingsStates.waiting_for_timezone_confirmation, timezone_data=timezone_data)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода города: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.callback_query(F.data.startswith("select_timezone:"))
async def select_timezone_from_options(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Выбор часового пояса из предложенных вариантов"""
    try:
        timezone_str = callback.data.split(":", 1)[1]
        try:
            pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            await callback.answer(get_message('wrong_timezone', language=language), show_alert=True)
            return
        user.timezone = timezone_str
        await user.asave(update_fields=['timezone'])
        try:
            pass
        except Exception as e:
            logger.warning(f"Не удалось сохранить в кэш: {e}")
        success_msg = get_message('timezone_changed', language, timezone=timezone_str)
        settings_msg = get_message('settings_menu', language=language)
        reply_markup = get_settings_keyboard(user, language)
        await callback.message.edit_text(
            settings_msg,
            reply_markup=reply_markup
        )
        await callback.answer(success_msg)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при выборе часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_timezone:"))
async def confirm_timezone_by_city(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Подтверждение часового пояса по городу"""
    try:
        data = await state_manager.get_state_data(state)
        timezone_data = data.get('timezone_data')
        
        if not timezone_data:
            await callback.answer(get_message('data_not_found', language=language), show_alert=True)
            return 
        timezone_str = timezone_data['timezone']
        city = timezone_data.get('city', '')
        country = timezone_data.get('country', '')
        try:
            pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            await callback.answer(get_message('wrong_timezone', language=language), show_alert=True)
            return
        user.timezone = timezone_str
        await user.asave(update_fields=['timezone'])
        try:
            await CityTimezone.objects.acreate(
                city_name=city,
                timezone=timezone_str,
                country=country
            )
        except Exception as e:
            logger.warning(f"Не удалось сохранить в кэш: {e}")
        success_msg = get_message('timezone_changed', language, timezone=timezone_str)
        settings_msg = get_message('settings_menu', language=language)
        reply_markup = get_settings_keyboard(user, language)
        await callback.message.edit_text(
            settings_msg,
            reply_markup=reply_markup
        )
        await callback.answer(success_msg)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при подтверждении часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

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
    except Exception as e:
        logger.error(f"Ошибка при показе списка часовых поясов: {e}")
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
