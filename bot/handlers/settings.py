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
from messages import get_message
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_premium_keyboard,
    get_back_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard,
    get_city_timezone_confirmation_keyboard,
    get_multiple_city_timezones_keyboard,
    get_analysis_time_selection_keyboard,
    get_edit_profile_keyboard,
    get_account_deletion_confirmation_keyboard,
    get_account_deletion_menu_keyboard
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
        subscribe_msg = "💳 Ждет доработки"
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

@router.callback_query(F.data == "timezone_enter_city")
async def enter_city_for_timezone(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Ввод города для определения часового пояса"""
    try:
        city_msg = get_message(key='enter_city', language=language)
        reply_markup = get_back_keyboard(language)
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
            await message.answer(city_msg, reply_markup=get_back_keyboard(language))
            return
        api_result = result['result']
        if not api_result.get('success', False):
            error_msg = api_result.get('error', get_message(key='city_not_found', language=language))
            await message.answer(f"❌ {error_msg}")
            city_msg = get_message(key='please_enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_back_keyboard(language))
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
                await message.answer(city_msg, reply_markup=get_back_keyboard(language))
                return
        timezone_str = api_result.get('timezone')
        city = api_result.get('city', city_name)
        country = api_result.get('country', 'Неизвестно')
        if not timezone_str:
            await message.answer(get_message(key='timezone_detection_failed', language=language))
            city_msg = get_message(key='enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_back_keyboard(language))
            return
        try:
            pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            await message.answer(get_message(key='invalid_timezone', language=language))
            city_msg = get_message(key='enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_back_keyboard(language))
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

@router.callback_query(F.data == "settings_change_analysis_time")
async def change_analysis_time(callback: CallbackQuery, user, language: str):
    """Изменение времени автоанализа"""
    try:
        current_time = user.preferred_analysis_time.strftime('%H:%M') if user.preferred_analysis_time else '02:00'
        time_msg = get_message('ask_analysis_time', language, current_time=current_time)
        reply_markup = get_analysis_time_selection_keyboard(language, current_time)
        await callback.message.edit_text(
            time_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе выбора времени автоанализа: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_analysis_time:"))
async def set_analysis_time(callback: CallbackQuery, user, language: str):
    """Установка времени автоанализа"""
    try:
        time_str = callback.data.split(":", 1)[1]
        try:
            new_time = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            await callback.answer("❌ Неверный формат времени", show_alert=True)
            return
        user.preferred_analysis_time = new_time
        await user.asave(update_fields=['preferred_analysis_time'])
        success_msg = get_message('analysis_time_changed', language, time=time_str)
        settings_msg = get_message('settings_menu', language=language)
        reply_markup = get_settings_keyboard(user, language)
        await callback.message.edit_text(
            settings_msg,
            reply_markup=reply_markup
        )
        await callback.answer(success_msg, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при установке времени автоанализа: {e}")
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data == "edit_profile")
async def show_edit_profile_menu(callback: CallbackQuery, user, language: str):
    """Показ меню редактирования профиля"""
    try:
        profile_data = {
            'first_name': user.first_name or 'Не указано',
            'email': user.email or 'Не указан',
            'date_of_birth': user.date_of_birth.strftime('%d.%m.%Y') if user.date_of_birth else 'Не указана',
            'hobbies': ', '.join(user.hobbies) if user.hobbies else 'Не указаны',
            'life_facts': ', '.join(user.life_facts) if user.life_facts else 'Не указаны'
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
        reply_markup = get_back_keyboard(language)
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
        reply_markup = get_back_keyboard(language)
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
        reply_markup = get_back_keyboard(language)
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
        reply_markup = get_back_keyboard(language)
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
        reply_markup = get_back_keyboard(language)
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
            'first_name': user.first_name or 'Не указано',
            'email': user.email or 'Не указан',
            'date_of_birth': user.date_of_birth.strftime('%d.%m.%Y') if user.date_of_birth else 'Не указана',
            'hobbies': ', '.join(user.hobbies) if user.hobbies else 'Не указаны',
            'life_facts': ', '.join(user.life_facts) if user.life_facts else 'Не указаны'
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
            reply_markup=get_settings_keyboard(user, language)
        )
        await state_manager.clear_state(state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления аккаунта: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "contact_support_for_refund")
async def contact_support_for_refund(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Связаться с поддержкой для возврата средств"""
    try:
        # TODO
        support_msg = "📞 Дработка"
        await callback.message.edit_text(support_msg)
        await state_manager.clear_state(state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при переходе к контакту поддержки: {e}")
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
        user.language = "ru" 
        user.timezone = "UTC"
        user.last_entry = None
        user.awareness_level = 1
        user.is_premium = False
        user.last_activity = None
        user.preferred_analysis_time = "02:00"
        user.current_calendar_year = 2025 
        user.current_calendar_month = 1
        user.notifications_enabled = False
        user.auto_analysis_enabled = False
        user.max_ai_tasks_per_day = 1
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