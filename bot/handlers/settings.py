"""Settings handlers (transport-only)."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from messages import get_message
from bot.states.settings_states import SettingsStates
from bot.states.onboarding_states import OnboardingStates
from bot.keyboards import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_single_button_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard,
    )
from bot.utils.state_manager import state_manager
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.message_utils import safe_edit_message_text
from bot.decorators.analytics_decorator import log_user_activity
from diary.services.settings_service import (
    update_user_language,
    toggle_user_notifications,
    toggle_user_auto_analysis,
    update_user_timezone,
    get_timezone_info,
    process_city_timezone_lookup,
    confirm_timezone_by_city,
    build_task_settings_view,
    build_task_limit_update_view,
    build_city_timezone_lookup_view,
    set_timezone_and_resolve_next_step,
)

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
        view = await build_task_settings_view(user, language)
        if not view.get('success'):
            await callback.answer(view.get('text') or get_message('error_generic', language=language))
            return
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе настроек заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_increase_tasks_limit")
@log_user_activity('settings_changed', metadata_extra={'context': 'Изменение лимита заданий'})
async def increase_tasks_limit(callback: CallbackQuery, user, language: str):
    """Увеличение лимита заданий"""
    try:
        view = await build_task_limit_update_view(user, language, increment=1)
        await callback.answer(view.get('alert_text') or '', show_alert=bool(view.get('show_alert')))
        if view.get('refresh_screen') and view.get('text') and view.get('reply_markup'):
            try:
                await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    logger.debug(
                        f"Сообщение настроек задач не изменилось для user {user.telegram_id}"
                    )
                else:
                    logger.error(f"TelegramBadRequest при редактировании настроек задач: {e}")
    except Exception as e:
        logger.error(f"Ошибка при увеличении лимита заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_decrease_tasks_limit")
async def decrease_tasks_limit(callback: CallbackQuery, user, language: str):
    """Уменьшение лимита заданий"""
    try:
        view = await build_task_limit_update_view(user, language, increment=-1)
        if not view.get('success') and view.get('mode') == 'error':
            await callback.answer(view.get('alert_text') or get_message('error_generic', language=language))
            return
        await callback.answer(view.get('alert_text') or '')
        if view.get('refresh_screen') and view.get('text') and view.get('reply_markup'):
            await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
    except Exception as e:
        logger.error(f"Ошибка при уменьшении лимита заданий: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_change_timezone")
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
        city_name = (message.text or '').strip()
        if not city_name or city_name.lower() in {'назад', 'back', '/start', '/menu'}:
            pre_view = build_city_timezone_lookup_view(
                {'success': False}, language, city_name=city_name
            )
            if pre_view.get('mode') == 'cancel':
                await state_manager.clear_state(state)
                await message.answer(
                    pre_view['text'],
                    reply_markup=get_settings_keyboard(user, language),
                )
                return
            await message.answer(pre_view.get('text') or get_message('please_enter_city', language))
            return

        status_msg = await message.answer(get_message('searching_timezone', language))
        lookup_result = await process_city_timezone_lookup(city_name, language)
        try:
            await status_msg.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение 'Поиск...' для {user.telegram_id}: {e}")

        view = build_city_timezone_lookup_view(lookup_result, language, city_name=city_name)
        if view.get('mode') == 'confirm_single':
            await message.answer(view['text'], reply_markup=view['reply_markup'])
            await state_manager.set_state(
                state,
                SettingsStates.waiting_for_timezone_confirmation,
                **(view.get('fsm_payload') or {}),
            )
            return
        if view.get('mode') == 'select_multiple':
            await message.answer(view['text'], reply_markup=view['reply_markup'])
            return
        if view.get('mode') == 'lookup_failed':
            await message.answer(view['text'])
            await message.answer(
                view.get('retry_text') or get_message('please_enter_city', language),
                reply_markup=view.get('reply_markup'),
            )
            return

        await message.answer(view.get('text') or get_message('selection_failed', language))
        if view.get('retry_text'):
            await message.answer(view['retry_text'], reply_markup=view.get('reply_markup'))
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода города: {e}", exc_info=True)
        try:
            if 'status_msg' in locals():
                await status_msg.delete()
        except Exception as cleanup_error:
            logger.debug(
                f"Не удалось удалить сообщение 'Обработка...' при исключении "
                f"для {user.telegram_id}: {cleanup_error}"
            )
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.callback_query(F.data.startswith("select_timezone:"))
@log_user_activity('settings_changed', metadata_extra={'context': 'Выбор часового пояса (после онбординга)'})
async def select_timezone_from_options_modified(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Выбор TZ из списка вариантов → главное меню."""
    try:
        timezone_str = callback.data.split(":", 1)[1]
        result = await update_user_timezone(user, timezone_str)
        if not result['success']:
            await safe_answer_callback(callback, get_message('wrong_timezone', language=language), show_alert=True)
            return
        success_msg = get_message('timezone_changed', language, timezone=timezone_str)
        from diary.services.main_menu_service import build_main_menu_data
        menu_data = await build_main_menu_data(user=user, language=language)
        main_menu_msg = menu_data['message_text']
        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language, user)

        await safe_edit_message_text(message=callback.message, text=main_menu_msg, reply_markup=main_menu_keyboard)
        await state_manager.clear_state(state)
        await safe_answer_callback(callback, success_msg)
        return
    except Exception as e:
        logger.error(f"[settings.select_timezone] failed user_id={user.id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language=language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_timezone:"))
@log_user_activity('settings_changed', metadata_extra={'context': 'Подтверждение часового пояса (после онбординга)'})
async def confirm_timezone_by_city_modified(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Подтверждение TZ по городу → главное меню."""
    try:
        data_state = await state_manager.get_state_data(state)
        timezone_data = data_state.get('timezone_data')
        if not timezone_data:
            await safe_answer_callback(callback, get_message('data_not_found', language=language), show_alert=True)
            return
        result = await confirm_timezone_by_city(user, timezone_data)
        if not result['success']:
            logger.error(
                f"[settings.confirm_timezone] service failed user_id={user.id}: "
                f"{result.get('error')}"
            )
            await safe_answer_callback(callback, get_message('error_generic', language=language), show_alert=True)
            return
        success_msg = get_message('timezone_changed', language, timezone=result['new_timezone'])
        from diary.services.main_menu_service import build_main_menu_data
        menu_data = await build_main_menu_data(user=user, language=language)
        main_menu_msg = menu_data['message_text']
        from bot.keyboards import get_main_menu_keyboard
        main_menu_keyboard = await get_main_menu_keyboard(language, user)

        await safe_edit_message_text(message=callback.message, text=main_menu_msg, reply_markup=main_menu_keyboard)
        await state_manager.clear_state(state)
        await safe_answer_callback(callback, success_msg)
        return
    except Exception as e:
        logger.error(f"[settings.confirm_timezone] failed user_id={user.id}: {e}")
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
@log_user_activity('settings_changed', metadata_extra={'context': 'Установка часового пояса (после онбординга или в онбординге)'})
async def set_timezone(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Transport: set_timezone_and_resolve_next_step → send/FSM."""
    try:
        new_timezone_str = callback.data.split(":", 1)[1]
        current_fsm_state = await state_manager.get_current_state(state)
        is_onboarding_tz_step = (
            current_fsm_state == OnboardingStates.waiting_for_timezone_confirmation
        )
        view = await set_timezone_and_resolve_next_step(
            user=user,
            new_timezone_str=new_timezone_str,
            language=language,
            is_onboarding=is_onboarding_tz_step,
        )
        if not view.get('success'):
            await safe_answer_callback(
                callback,
                view.get('alert_text') or get_message('error_generic', language),
                show_alert=bool(view.get('show_alert', True)),
            )
            return

        await safe_edit_message_text(
            message=callback.message,
            text=view['text'],
            reply_markup=view.get('reply_markup'),
        )
        if view.get('next') == 'onboarding_first_entry':
            await state_manager.set_state(state, OnboardingStates.waiting_for_first_entry)
        elif view.get('clear_state'):
            await state_manager.clear_state(state)
        await safe_answer_callback(callback, view.get('alert_text') or "")
    except Exception as e:
        logger.error(f"[settings.set_timezone] failed user_id={user.id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
