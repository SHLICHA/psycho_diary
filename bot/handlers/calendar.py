"""
Handlers для работы с календарем
"""

import asyncio
import logging
import pytz


from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, date, timedelta

from messages import get_message, get_button_text
from diary.models import CombinedDiaryEntry, DiaryEntry, PsychoAnalysis, TherapyTask, KeyPoint, UserInsight
from diary.services import analysis_service, daily_state_service
from bot.states.diary_states import DiaryStates
from bot.services.task_service import task_service
from bot.keyboards import (
    get_cancel_keyboard,
    get_month_calendar_with_navigation,
    get_calendar_back_keyboard,
    get_cancel_keyboard,
    get_day_entries_edit_keyboard, 
    get_confirm_delete_entry_keyboard, 
    get_back_to_edit_day_keyboard,
    format_entry_text_for_editing,
    get_entry_view_keyboard,
    get_smart_calendar_keyboard,
    get_year_selection_keyboard,
    get_month_selection_keyboard
    )
from bot.keyboards.main_menu import get_back_keyboard, get_main_menu_keyboard
from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
from bot.utils.state_manager import state_manager
from bot.utils.time_utils import convert_utc_to_user_timezone
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from core.constants import TEXT_MESSAGE_MAX_LENGTH, TASK_TYPES
from bot.services.diary_service import diary_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from bot.services.diary_service import (
    create_text_entry, 
    create_voice_entry, 
    get_user_entries_for_date,
    get_combined_entry_text,
    delete_entry
)
from core.constants import TEXT_MESSAGE_MAX_LENGTH, VOICE_MESSAGE_MAX_DURATION
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "archive")
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
        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year = year - 1  
        today = datetime.now()
        current_day = today.day if today.month == prev_month and today.year == prev_year else 1
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[prev_month] if 1 <= prev_month <= 12 else ""
        
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=prev_year
        )
        if callback.message.text != calendar_msg:
            await safe_edit_message_text(
                message=callback.message,
                text=calendar_msg,
                reply_markup=await get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
            )
        else:
            try:
                await callback.message.edit_reply_markup(
                    reply_markup=get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
                )
            except Exception as keyboard_error:
                logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                await safe_edit_message_text(
                    message=callback.message,
                    text=calendar_msg,
                    reply_markup=get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
                )
        
        await safe_answer_callback(callback, "")
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
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1
        today = datetime.now()
        current_day = today.day if today.month == next_month and today.year == next_year else 1
        
        calendar_msg = get_message('archive_menu', language)
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, next_year, next_month, current_day, language)
        )
        await safe_answer_callback(callback, "")
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
        today = datetime.now()
        current_day = today.day if today.year == year and today.month == 1 else 1
        calendar_msg = get_message('archive_menu', language)
        await callback.message.edit_text(
            calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, year, 1, current_day, language)
        )
        await callback.answer()  
    except Exception as e:
        logger.error(f"Ошибка при выборе года: {e}")
        await callback.answer(get_message('error_generic', language))
# Неактивный хендлер
@router.callback_query(F.data.startswith("calendar_quick_month:"))
async def quick_month_navigation(callback: CallbackQuery, user, language: str):
    """Быстрая навигация по месяцам"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        logger.info(f"Быстрый переход к месяцу: {month}.{year}")      
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при быстрой навигации по месяцам: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))
# Неактивный хендлер
@router.callback_query(F.data.startswith("calendar_open_month_selector:"))
async def open_month_selector(callback: CallbackQuery, language: str):
    """Открытие селектора месяцев"""
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        month_msg = get_message('archive_select_month', language).format(year=year)
        await callback.message.edit_text(
            month_msg,
            reply_markup=get_month_selection_keyboard(year, month, language)
        )
        await callback.answer()
        logger.info("Показан выбор месяцев")  
    except Exception as e:
        logger.error(f"Ошибка при открытии селектора месяцев: {e}")
        await callback.answer(get_message('error_generic', language))
# Неактивный хендлер
@router.callback_query(F.data.startswith("calendar_select_specific_month:"))
async def select_specific_month(callback: CallbackQuery, user, language: str):
    """Выбор конкретного месяца"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        await callback.message.edit_text(
            calendar_msg,
            reply_markup=get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при выборе конкретного месяца: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_return_to_month:"))
async def return_to_month(callback: CallbackQuery, user, language: str):
    """Возврат к конкретному месяцу календаря"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        logger.info(f"Возврат к календарю: {month}.{year}")
        user.current_calendar_year = year
        user.current_calendar_month = month
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        from messages import get_message
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при возврате к календарю: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_day:"))
async def select_day(callback: CallbackQuery, user, language: str):
    """Выбор дня для просмотра записей"""
    try:
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        logger.info(f"Выбран день: {day}.{month}.{year}")
        user.current_calendar_year = year
        user.current_calendar_month = month
        selected_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, selected_date)
        if entries:
            combined_text = await diary_service.get_combined_entry_text(user, selected_date)
            analysis_text = "Анализ не доступен"
            mood_score = 5
            recommendation = "Продолжайте в том же духе"
            mood_text = get_message(f'mood_{mood_score}', language)
            try:
                first_entry = entries[0]
                if hasattr(first_entry, 'analysis'):
                    try:
                        analysis = await PsychoAnalysis.objects.aget(entry=first_entry)
                        analysis_text = analysis.analysis_text or analysis.comment or "Анализ записан"
                        mood_score = analysis.mood_score
                        recommendation = analysis.recommendation or "Продолжайте в том же духе"
                        mood_text = get_message(f'mood_{mood_score}', language)
                    except PsychoAnalysis.DoesNotExist:
                        logger.warning("Анализ для первой записи не найден")
                    except Exception as analysis_error:
                        logger.error(f"Ошибка при получении анализа: {analysis_error}")
            except Exception as e:
                logger.error(f"Общая ошибка при работе с анализом: {e}")
            archive_entry_msg = get_message('archive_entry', language,
                date=selected_date.strftime("%d.%m.%Y"),
                text=combined_text[:1000] + "..." if len(combined_text) > 1000 else combined_text,
                score=mood_score,
                mood=mood_text,
                analysis=analysis_text
            )
            await callback.message.edit_text(archive_entry_msg, 
                reply_markup=get_entry_view_keyboard(language, year, month, day))
            logger.info(f"Показана запись за {day}.{month}.{year}")
        else:
            no_entries_msg = get_message('archive_empty', language)
            await callback.message.edit_text(no_entries_msg, 
                reply_markup=get_calendar_back_keyboard(language, year, month))
            logger.info(f"Нет записей за {day}.{month}.{year}")  
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при выборе дня: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data == "calendar_empty")
async def handle_empty_calendar_button(callback: CallbackQuery):
    """Обработка пустых кнопок в календаре"""
    await safe_answer_callback(callback, "")