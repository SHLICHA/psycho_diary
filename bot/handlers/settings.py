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
from asgiref.sync import sync_to_async

from messages import get_message
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_single_button_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard,
    get_city_timezone_confirmation_keyboard,
    get_multiple_city_timezones_keyboard,
    get_task_settings_keyboard,
    )
from bot.utils.state_manager import state_manager
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.message_utils import safe_edit_message_text
from bot.decorators.analytics_decorator import log_user_activity
from diary.services.settings_service import (
    update_user_language,
    toggle_user_notifications,
    toggle_user_auto_analysis,
    get_task_limit_info,
    update_task_limit,
    update_user_timezone,
    get_timezone_info,
    process_city_timezone_lookup,
    confirm_timezone_by_city
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "settings")
@log_user_activity('settings')
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Изменение языка'})
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Установка языка'})
async def set_language(callback: CallbackQuery, user, state: FSMContext, language: str):
    """Установка языка"""
    try:
        new_language = callback.data.split(":")[1]
        result = await update_user_language(user, new_language)
        if not result['success']:
            logger.warning(f"Не удалось установить язык {new_language}: {result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Переключение уведомлений'})
async def toggle_notifications(callback: CallbackQuery, user, language: str):
    """Переключение уведомлений"""
    try:
        result = await toggle_user_notifications(user)
        if not result['success']:
            logger.error(f"Ошибка при переключении уведомлений: {result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        toggle_msg = get_message(result['status_message_key'], language=language)
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Переключение автоанализа'})
async def toggle_auto_analysis(callback: CallbackQuery, user, language: str):
    """Переключение автоанализа"""
    try:
        result = await toggle_user_auto_analysis(user)
        if not result['success']:
            logger.error(f"Ошибка при переключении автоанализа: {result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        status_key = result['status_message_key']
        toggle_msg = get_message('settings_auto_analysis', language=language).format(
            status=get_message(status_key, language=language)
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
        info_result = await get_task_limit_info(user)
        if not info_result['success']:
            logger.error(f"Ошибка при получении информации о лимите заданий: {info_result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=info_result['current_limit']
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Изменение лимита заданий'})
async def increase_tasks_limit(callback: CallbackQuery, user, language: str):
    """Увеличение лимита заданий"""
    try:
        result = await update_task_limit(user, increment=1)
        if not result['success']:
            if result.get('error') == 'limit_exceeded':
                alert_message = get_message(
                    'awareness_level_insufficient_for_tasks_current',
                    language=language,
                    current_level=result['current_level'],
                    current_max_tasks=result['current_max_tasks']
                )
                await callback.answer(alert_message, show_alert=True)
                info_result = await get_task_limit_info(user)
                if info_result['success']:
                    task_settings_msg = get_message('task_settings_menu', language=language).format(
                        max_tasks=info_result['current_limit']
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
            else:
                logger.error(f"Ошибка при увеличении лимита заданий: {result.get('error')}")
                await callback.answer(get_message('error_generic', language=language))
            return
        action = result['action']
        if action == 'increased':
            success_msg = get_message('tasks_limit_increased', language=language).format(
                new_limit=result['new_limit']
            )
        elif action == 'max_reached':
            success_msg = get_message('tasks_limit_max_reached', language=language)
        else:
            success_msg = get_message('tasks_limit_increased', language=language).format(
                new_limit=result['new_limit']
            )
        await callback.answer(success_msg)
        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=result['new_limit']
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
        result = await update_task_limit(user, increment=-1)

        if not result['success']:
            logger.error(f"Ошибка при уменьшении лимита заданий: {result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        action = result['action']
        if action == 'decreased':
            success_msg = get_message('tasks_limit_decreased', language=language).format(
                new_limit=result['new_limit']
            )
        elif action == 'min_reached':
            success_msg = get_message('tasks_limit_min_reached', language=language)
        else:
            success_msg = get_message('tasks_limit_decreased', language=language).format(
                new_limit=result['new_limit']
            )
        await callback.answer(success_msg)
        task_settings_msg = get_message('task_settings_menu', language=language).format(
            max_tasks=result['new_limit']
        )
        await callback.message.edit_text(
            task_settings_msg,
            reply_markup=get_task_settings_keyboard(user, language)
        )
    except Exception as e:
        logger.error(f"Ошибка при уменьшении лимита заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data == "start_timezone_setup_after_first_entry")
@log_user_activity('settings_changed', metadata_extra={'context': 'Начало изменения часового пояса'})
async def start_timezone_setup_after_first_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Начинает процесс смены часового пояса после первой записи.
    Устанавливает флаг в state_data.
    """
    try:
        await state_manager.update_state_data(state, origin='first_entry')
        info_result = await get_timezone_info(user)
        if not info_result['success']:
            logger.error(f"Ошибка при получении информации о часовом поясе: {info_result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        current_timezone = info_result['current_timezone']
        timezone_msg = get_message('ask_timezone_selection', language, current_timezone=current_timezone)
        reply_markup = get_timezone_selection_method_keyboard(language, current_timezone)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале смены часового пояса после первой записи: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_change_timezone")
@log_user_activity('settings_changed', metadata_extra={'context': 'Начало изменения часового пояса'})
async def change_timezone(callback: CallbackQuery, user, language: str):
    """Начало изменения часового пояса"""
    try:
        info_result = await get_timezone_info(user)
        if not info_result['success']:
            logger.error(f"Ошибка при получении информации о часовом поясе: {info_result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return

        current_timezone = info_result['current_timezone']
        timezone_msg = get_message('ask_timezone_selection', language, current_timezone=current_timezone)
        reply_markup = get_timezone_selection_method_keyboard(language, current_timezone)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе вариантов выбора часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "timezone_enter_city")
@log_user_activity('settings_changed', metadata_extra={'context': 'Изменение часового пояса. Ввод города'})
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Обработка ввода города'})
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
        lookup_result = await process_city_timezone_lookup(city_name, language)
        if not lookup_result['success']:
            error_msg = lookup_result.get('error', get_message('timezone_error', language))
            await message.answer(f"❌ {error_msg}")
            city_msg = get_message(key='please_enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
        if lookup_result['source'] == 'cache' or lookup_result['source'] == 'api_single':
            timezone_data = lookup_result['timezone_data']
            confirmation_msg = get_message(
                key='timezone_found',
                language=language,
                city_name=timezone_data['city'],
                country=timezone_data['country'],
                timezone=timezone_data['timezone']
            )
            reply_markup = get_city_timezone_confirmation_keyboard(language, timezone_data)
            await message.answer(
                confirmation_msg,
                reply_markup=reply_markup
            )
            await state_manager.set_state(state, SettingsStates.waiting_for_timezone_confirmation, timezone_data=timezone_data)
            return
        elif lookup_result['source'] == 'api_multiple':
            options = lookup_result['multiple_options']
            selection_msg = get_message(key='multiple_cities_found', language=language)
            reply_markup = get_multiple_city_timezones_keyboard(language, options)
            await message.answer(
                selection_msg,
                reply_markup=reply_markup
            )
            return
        else:
            logger.error(f"Непредусмотренный источник в lookup_result: {lookup_result}")
            await message.answer(get_message(key='selection_failed', language=language))
            city_msg = get_message(key='enter_city', language=language)
            await message.answer(city_msg, reply_markup=get_single_button_keyboard(language, 'settings', 'btn_back'))
            return
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода города: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.callback_query(F.data.startswith("select_timezone:"))
@log_user_activity('settings_changed', metadata_extra={'context': 'Выбор часового пояса (после онбординга)'})
async def select_timezone_from_options_modified(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Модифицированная версия select_timezone_from_options без проверки origin для завершения онбординга."""
    try:
        timezone_str = callback.data.split(":", 1)[1]
        result = await update_user_timezone(user, timezone_str)
        if not result['success']:
            await safe_answer_callback(callback, get_message('wrong_timezone', language=language), show_alert=True)
            return
        success_msg = get_message('timezone_changed', language, timezone=timezone_str)
        from diary.services.main_menu_service import build_main_menu_data
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language, user)

        await safe_edit_message_text(message=callback.message, text=main_menu_msg, reply_markup=main_menu_keyboard)
        await state_manager.clear_state(state) # Очищаем состояние
        await safe_answer_callback(callback, success_msg)
        return
        # --- /НОВОЕ ---

    except Exception as e:
        logger.error(f"[Settings] Ошибка при выборе часового пояса из опций: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_timezone:"))
@log_user_activity('settings_changed', metadata_extra={'context': 'Подтверждение часового пояса (после онбординга)'})
async def confirm_timezone_by_city_modified(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Модифицированная версия confirm_timezone_by_city без проверки origin для завершения онбординга."""
    try:
        data_state = await state_manager.get_state_data(state)
        timezone_data = data_state.get('timezone_data')
        if not timezone_data:
            await safe_answer_callback(callback, get_message('data_not_found', language=language), show_alert=True)
            return
        result = await confirm_timezone_by_city(user, timezone_data)
        if not result['success']:
            logger.error(f"[Settings] Ошибка при подтверждении часового пояса: {result.get('error')}")
            await safe_answer_callback(callback, get_message('error_generic', language=language), show_alert=True)
            return
        success_msg = get_message('timezone_changed', language, timezone=result['new_timezone'])
        from diary.services.main_menu_service import build_main_menu_data
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language, user)

        await safe_edit_message_text(message=callback.message, text=main_menu_msg, reply_markup=main_menu_keyboard)
        await state_manager.clear_state(state) # Очищаем состояние
        await safe_answer_callback(callback, success_msg)
        return
        # --- /НОВОЕ ---

    except Exception as e:
        logger.error(f"[Settings] Ошибка при подтверждении часового пояса: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data == "timezone_select_from_list")
@log_user_activity('settings_changed', metadata_extra={'context': 'Выбор часового пояса из списка'})
async def select_timezone_from_list(callback: CallbackQuery, user, language: str):
    """Выбор часового пояса из списка"""
    try:
        info_result = await get_timezone_info(user)
        if not info_result['success']:
            logger.error(f"Ошибка при получении информации о часовом поясе: {info_result.get('error')}")
            await callback.answer(get_message('error_generic', language=language))
            return
        current_timezone = info_result['current_timezone']
        timezone_msg = get_message('select_timezone_title', language, current_timezone=current_timezone)
        reply_markup = get_common_timezones_keyboard(language, current_timezone)
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе списка часовых поясов: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_timezone:"))
@log_user_activity('settings_changed', metadata_extra={'context': 'Установка часового пояса (после онбординга)'})
async def set_timezone_modified(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Модифицированная версия set_timezone без проверки origin для завершения онбординга."""
    try:
        new_timezone_str = callback.data.split(":", 1)[1]
        result = await update_user_timezone(user, new_timezone_str)
        if not result['success']:
            logger.error(f"Неизвестный часовой пояс: {new_timezone_str}")
            error_msg = get_message('error_unknown_timezone', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            return

        success_msg = get_message('timezone_changed', language, timezone=result['new_timezone'])
        from diary.services.main_menu_service import build_main_menu_data
        menu_data = await build_main_menu_data(user, language)
        main_menu_msg = menu_data['message_text']
        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language, user)

        await safe_edit_message_text(message=callback.message, text=main_menu_msg, reply_markup=main_menu_keyboard)
        await state_manager.clear_state(state) # Очищаем состояние
        await safe_answer_callback(callback, success_msg)
        return
    except Exception as e:
        logger.error(f"Ошибка при установке часового пояса: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data == "onboarding_start_timezone_setup")
@log_user_activity('settings_changed', metadata_extra={'context': 'Начало изменения часового пояса (онбординг)'})
async def onboarding_start_timezone_setup(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Хендлер для начала установки часового пояса, вызываемый из онбординга.
    Устанавливает origin в state_data и вызывает основной хендлер.
    """
    try:
        # Устанавливаем origin в state_data через state_manager
        await state_manager.update_state_data(state, origin='onboarding_timezone_setup')
        logger.debug(f"[Settings] Установлен origin='onboarding_timezone_setup' в state для пользователя {user.telegram_id} через onboarding_start_timezone_setup.")

        # Вызываем основной хендлер для установки часового пояса
        # ИСПОЛЬЗУЕМ ТЕКСТ ИЗ onboarding_timezone_info
        from messages import get_message
        timezone_info_msg = get_message('onboarding_timezone_info', language)
        # ИСПОЛЬЗУЕМ КЛАВИАТУРУ БЕЗ КНОПКИ НАЗАД
        from bot.keyboards import get_timezone_selection_method_keyboard # Импортируем клавиатуру
        # ПРЕДПОЛОЖИМ, что функция get_timezone_selection_method_keyboard принимает show_back_button
        reply_markup = get_timezone_selection_method_keyboard(language, current_timezone=user.timezone, show_back_button=False) # <-- Добавляем show_back_button=False
        # РЕДАКТИРУЕМ СООБЩЕНИЕ callback.message
        await safe_edit_message_text(message=callback.message, text=timezone_info_msg, reply_markup=reply_markup)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[Settings] Ошибка при начале установки часового пояса из онбординга для {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))
