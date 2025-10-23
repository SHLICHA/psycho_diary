"""
Handlers для работы с календарем
"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import date

from bot.decorators.analytics_decorator import log_user_activity
from bot.utils.calendar_utils import update_calendar_display
from bot.keyboards import (
    get_month_calendar_with_navigation,
    get_smart_calendar_keyboard,
    get_year_selection_keyboard,
    get_month_selection_keyboard
    )
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from messages import get_message
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "archive")
@log_user_activity('archive_viewed', metadata_extra={'context': 'Открытие календаря'})
async def show_archive(callback: CallbackQuery, state: FSMContext, language: str):
    """Показ архива записей с умным календарем"""
    try:
        await state_manager.clear_state(state)
        user = await User.objects.aget(telegram_id=callback.from_user.id)
        archive_msg = get_message('archive_menu', language)
        await safe_edit_message_text(
            message=callback.message,
            text=archive_msg,
            reply_markup=await get_smart_calendar_keyboard(user, language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при показе архива: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_prev_month:"))
async def prev_month(callback: CallbackQuery, user, language: str):
    """Переход к предыдущему месяцу"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        prev_month_num = month - 1
        prev_year = year
        if prev_month_num < 1:
            prev_month_num = 12
            prev_year = year - 1  
        target_date = date(prev_year, prev_month_num, 1)
        success = await update_calendar_display(
            message=callback.message,
            user=user,
            target_date=target_date,
            language=language
        )
        if success:
            await safe_answer_callback(callback, "")
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Ошибка при переходе к предыдущему месяцу: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_next_month:"))
async def next_month(callback: CallbackQuery, user, language: str):
    """Переход к следующему месяцу"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        next_month_num = month + 1
        next_year = year
        if next_month_num > 12:
            next_month_num = 1
            next_year = year + 1
        target_date = date(next_year, next_month_num, 1)
        success = await update_calendar_display(
            message=callback.message,
            user=user,
            target_date=target_date,
            language=language
        )
        if success:
            await safe_answer_callback(callback, "")
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Ошибка при переходе к следующему месяцу: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_open_year_selector:"))
async def open_year_selector(callback: CallbackQuery, language: str):
    """Открытие селектора года"""  
    try:
        year = int(callback.data.split(":")[1])
        year_msg = get_message('archive_select_year', language)
        await safe_edit_message_text(
            message=callback.message,
            text=year_msg,
            reply_markup=get_year_selection_keyboard(year, language)
        )
        await safe_answer_callback(callback, "") 
    except Exception as e:
        logger.error(f"Ошибка при открытии селектора года: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_year:"))
async def select_year(callback: CallbackQuery, user, language: str):
    """Выбор года - показываем календарь выбранного года"""
    try:
        year = int(callback.data.split(":")[1])
        user_local_date = user.get_local_datetime().date()
        current_day = user_local_date.day if user_local_date.year == year and user_local_date.month == 1 else 1
        calendar_msg = get_message('archive_menu', language)
        await callback.message.edit_text(
            calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, year, 1, current_day, language)
        )
        await callback.answer()  
    except Exception as e:
        logger.error(f"Ошибка при выборе года: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_quick_month:"))
async def quick_month_navigation(callback: CallbackQuery, user, language: str):
    """Быстрая навигация по месяцам - открывает селектор месяцев"""
    try:
        parts = callback.data.split(":")
        if len(parts) < 3:
             raise ValueError("Некорректный формат callback_data для calendar_quick_month")
        year = int(parts[1])
        month = int(parts[2])
        month_msg = get_message('archive_select_month', language).format(year=year)
        await safe_edit_message_text(
            message=callback.message,
            text=month_msg,
            reply_markup=get_month_selection_keyboard(year, month, language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при быстрой навигации по месяцам: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_open_month_selector:"))
async def open_month_selector(callback: CallbackQuery, user, language: str):
    """Открытие селектора месяцев"""
    try:
        parts = callback.data.split(":")
        if len(parts) < 3:
             raise ValueError("Некорректный формат callback_data для calendar_open_month_selector")
        year = int(parts[1])
        current_month = int(parts[2])
        month_msg = get_message('archive_select_month', language).format(year=year)
        await safe_edit_message_text(
            message=callback.message,
            text=month_msg,
            reply_markup=get_month_selection_keyboard(year, current_month, language)
        )
        await safe_answer_callback(callback, "") 
    except Exception as e:
        logger.error(f"Ошибка при открытии селектора месяцев: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_specific_month:"))
async def select_specific_month(callback: CallbackQuery, user, language: str):
    """Выбор конкретного месяца"""
    try:
        parts = callback.data.split(":")
        if len(parts) < 3:
             raise ValueError("Некорректный формат callback_data для calendar_select_specific_month")
        year = int(parts[1])
        month = int(parts[2])
        target_date = date(year, month, 1)
        success = await update_calendar_display(
            message=callback.message,
            user=user,
            target_date=target_date,
            language=language
        )
        if success:
            await safe_answer_callback(callback, "")
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Ошибка при выборе конкретного месяца: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_return_to_month:"))
async def return_to_month(callback: CallbackQuery, user, language: str):
    """Возврат к конкретному месяцу календаря"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        user.current_calendar_year = year
        user.current_calendar_month = month
        target_date = date(year, month, 1)
        success = await update_calendar_display(
            message=callback.message,
            user=user,
            target_date=target_date,
            language=language
        )
        if success:
            await safe_answer_callback(callback, "")
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))
    except Exception as e:
        logger.error(f"Ошибка при возврате к календарю: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "calendar_empty")
async def handle_empty_calendar_button(callback: CallbackQuery):
    """Обработка пустых кнопок в календаре"""
    await safe_answer_callback(callback, "")