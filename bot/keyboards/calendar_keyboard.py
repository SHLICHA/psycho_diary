"""
Клавиатура календаря для архива записей
"""

import logging

from asgiref.sync import sync_to_async
from datetime import date
from calendar import monthrange
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.constants import MONTH_NAMES_RU, MONTH_NAMES_EN, MONTH_NAMES_SHORT_RU, MONTH_NAMES_SHORT_EN
from diary.models import CombinedDiaryEntry
from messages import get_button_text, get_message

logger = logging.getLogger(__name__)

async def get_smart_calendar_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Получение умного календаря с фокусом на текущий месяц"""
    try:
        user_local_date = user.get_local_datetime().date()
        current_year = user_local_date.year
        current_month = user_local_date.month
        current_day = user_local_date.day
        return await get_month_calendar_with_navigation(user, current_year, current_month, current_day, language)
    except Exception as e:
        return get_basic_calendar_keyboard(language)

async def get_month_calendar_with_navigation(user, year: int, month: int, current_day: int, language: str) -> InlineKeyboardMarkup:
    """Получение календаря месяца с навигацией"""
    buttons = []
    month_names = MONTH_NAMES_RU if language == 'ru' else MONTH_NAMES_EN
    month_name = month_names[month] if 1 <= month <= 12 else ""
    header_buttons = [
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"calendar_prev_month:{year}:{month}"
        ),
        InlineKeyboardButton(
            text=f"{month_name} {year}",
            callback_data=f"calendar_quick_month:{year}:{month}"
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"calendar_next_month:{year}:{month}"
        )
    ]
    buttons.append(header_buttons)
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekdays_en = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    weekdays = weekdays_ru if language == 'ru' else weekdays_en
    weekday_buttons = [
        InlineKeyboardButton(text=day, callback_data="calendar_empty") 
        for day in weekdays
    ]
    buttons.append(weekday_buttons)
    try:
        days_data = await get_days_with_entries_and_mood_async(user, year, month)
        logger.debug(f"Данные дней для календаря: {days_data}")
    except Exception as e:
        logger.error(f"Ошибка при асинхронном получении дней с настроением: {e}")
        days_data = {}
    user_local_date = user.get_local_datetime().date()
    first_day_weekday = date(year, month, 1).weekday()
    days_in_month = monthrange(year, month)[1]
    day_buttons = []
    for i in range(first_day_weekday):
        day_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
    today = user.get_local_datetime().date()
    for day in range(1, days_in_month + 1):
        day_text = str(day)
        if year == user_local_date.year and month == user_local_date.month and day == user_local_date.day:
            day_text = f"🔹{day}🔹"
        elif day in days_data:
            avg_mood_score = days_data[day]
            if avg_mood_score is not None and avg_mood_score > 0:
                if avg_mood_score >= 8:
                    mood_emoji = "😄"
                elif avg_mood_score >= 6:
                    mood_emoji = "😊"
                elif avg_mood_score >= 4:
                    mood_emoji = "😐"
                elif avg_mood_score >= 2:
                    mood_emoji = "😞"
                else:
                    mood_emoji = "😢"
                day_text = f"{mood_emoji}{day}"
            else:
                day_text = f"📝{day}"
        day_buttons.append(
            InlineKeyboardButton(
                text=day_text,
                callback_data=f"calendar_select_day:{year}:{month}:{day}"
            )
        )
        if len(day_buttons) % 7 == 0:
            buttons.append(day_buttons)
            day_buttons = []
    if day_buttons:
        while len(day_buttons) % 7 != 0:
            day_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
        buttons.append(day_buttons)
    year_button = [
        InlineKeyboardButton(
            text=f"📅 Выбрать год: {year}",
            callback_data=f"calendar_open_year_selector:{year}"
        )
    ]
    buttons.append(year_button)
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_year_selection_keyboard(current_year: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора года"""
    buttons = []
    buttons.append([
        InlineKeyboardButton(
            text="📅 Выбор года",
            callback_data="calendar_empty"
        )
    ])
    start_year = current_year - 4
    end_year = current_year + 4
    for i in range(start_year, end_year + 1, 3):
        year_row = []
        for j in range(3):
            year = i + j
            if year <= end_year:
                year_text = f"🔹{year}🔹" if year == current_year else str(year)
                year_row.append(
                    InlineKeyboardButton(
                        text=year_text,
                        callback_data=f"calendar_select_year:{year}"
                    )
                )
        if year_row:
            buttons.append(year_row)
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="archive"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_month_selection_keyboard(year: int, current_month: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора месяца"""
    buttons = []
    buttons.append([
        InlineKeyboardButton(
            text=f"📅 Выбор месяца {year}",
            callback_data="calendar_empty"
        )
    ])
    month_names_short = MONTH_NAMES_SHORT_RU if language == 'ru' else MONTH_NAMES_SHORT_EN
    for i in range(0, 12, 3):
        month_row = []
        for j in range(3):
            month_index = i + j + 1
            if month_index <= 12:
                month_text = f"🔹{month_names_short[month_index-1]}🔹" if month_index == current_month else month_names_short[month_index-1]
                month_row.append(
                    InlineKeyboardButton(
                        text=month_text,
                        callback_data=f"calendar_select_specific_month:{year}:{month_index}"
                    )
                )
        if month_row:
            buttons.append(month_row)
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_return_to_month:{year}:{current_month}"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# TODO нужена ли функция?
def get_basic_calendar_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Базовый календарь на случай ошибок"""
    buttons = []
    buttons.append([
        InlineKeyboardButton(
            text="📅 Архив записей",
            callback_data="calendar_empty"
        )
    ])
    current_year = user.get_local_datetime().year
    buttons.append([
        InlineKeyboardButton(
            text=str(current_year),
            callback_data=f"calendar_open_year_selector:{current_year}"
        )
    ])
    month_names_short = MONTH_NAMES_SHORT_RU if language == 'ru' else MONTH_NAMES_SHORT_EN
    month_row = []
    for i, month_name in enumerate( month_names_short, 1):
        month_row.append(
            InlineKeyboardButton(
                text=month_name,
                callback_data=f"calendar_open_month_selector:{current_year}:{i}"
            )
        )
        if i % 4 == 0:
            buttons.append(month_row)
            month_row = []
    if month_row:
        buttons.append(month_row)
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_calendar_back_keyboard(language: str, year: int, month: int) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к календарю"""
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data=f"calendar_return_to_month:{year}:{month}"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_entry_view_keyboard(language: str, year: int, month: int, day: int) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра записи с кнопкой возврата к календарю"""
    buttons = []
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_edit_entry', language),
            callback_data=f"edit_entry:{year}:{month}:{day}"
        ),
        InlineKeyboardButton(
            text=get_button_text('btn_delete_entry', language),
            callback_data=f"delete_entry:{year}:{month}:{day}"
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=get_message('btn_view_insights', language),
            callback_data=f"view_day_insights:{year}:{month}:{day}"
        ),
        InlineKeyboardButton(
            text=get_message('btn_view_key_points', language),
            callback_data=f"view_day_keypoints:{year}:{month}:{day}"
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_analyze_again', language),
            callback_data=f"reanalyze_entry:{year}:{month}:{day}"
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_return_to_month:{year}:{month}"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirmation_keyboard(
    language: str,
    confirm_text_key: str,
    cancel_text_key: str,
    confirm_callback_data: str,
    cancel_callback_data: str,
) -> InlineKeyboardMarkup:
    """
    Универсальная клавиатура подтверждения/отмены действия.

    Args:
        language (str): Язык интерфейса.
        confirm_text_key (str): Ключ для локализованного текста кнопки подтверждения.
        cancel_text_key (str): Ключ для локализованного текста кнопки отмены.
        confirm_callback_data (str): Данные callback для кнопки подтверждения.
        cancel_callback_data (str): Данные callback для кнопки отмены.

    Returns:
        InlineKeyboardMarkup: Сгенерированная клавиатура.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text(confirm_text_key, language),
                callback_data=confirm_callback_data
            ),
            InlineKeyboardButton(
                text=get_button_text(cancel_text_key, language),
                callback_data=cancel_callback_data
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_delete_confirmation_keyboard(language: str, entry_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления записи (алиас)."""
    return get_confirmation_keyboard(
        language=language,
        confirm_text_key='btn_confirm_delete',
        cancel_text_key='btn_cancel_delete', 
        confirm_callback_data=f"confirm_delete_entry:{entry_id}",
        cancel_callback_data="cancel_delete_entry"
    )

def get_delete_entry_confirmation_keyboard(language: str, entry_id: int, target_date: date) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления записи (алиас)."""
    # Преобразуем дату в строку ISO для передачи в callback_data
    if isinstance(target_date, date):
        target_date_iso = target_date.isoformat() 
    else:
        # На случай, если target_date каким-то образом оказалась строкой или другим типом
        logger.error(f"get_delete_entry_confirmation_keyboard: target_date не является объектом date: {type(target_date)}")
        # Используем сегодняшнюю дату как фолбэк
        target_date_iso = date.today().isoformat() 
    return get_confirmation_keyboard(
        language=language,
        confirm_text_key='btn_confirm_delete', # <-- Правильный ключ для текста кнопки подтверждения
        cancel_text_key='btn_cancel_delete',   # <-- Правильный ключ для текста кнопки отмены
        confirm_callback_data=f"confirm_delete_specific_entry:{entry_id}:{target_date_iso}", # <-- Правильный callback_data
        cancel_callback_data=f"cancel_delete_specific_entry:{entry_id}:{target_date_iso}"     # <-- Правильный callback_data
    )

def get_entry_page_keyboard(
    entry_id: int,
    current_index: int,
    total_entries: int,
    target_date: date, # <-- Новый параметр
    language: str,
    is_day_analyzed: bool 
) -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру для страницы просмотра записи с учетом статуса анализа дня.

    Args:
        entry_id: ID текущей записи.
        current_index: Индекс текущей записи в списке.
        total_entries: Общее количество записей за день.
        target_date: Дата, к которой относится запись.
        language: Язык интерфейса.
        is_day_analyzed: Был ли день проанализирован.

    Returns:
        InlineKeyboardMarkup: Сформированная клавиатура.
    """
    keyboard_buttons = []

    # Кнопки пагинации (если больше одной записи)
    if total_entries > 1:
        pagination_row = [
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"entry_prev:{entry_id}"
            ),
            InlineKeyboardButton(
                text=f"{current_index + 1}/{total_entries}",
                callback_data="entry_empty" # Или другая заглушка
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"entry_next:{entry_id}"
            )
        ]
        keyboard_buttons.append(pagination_row)

    # Кнопки действий с записью
    actions_row_1 = [
        InlineKeyboardButton(
            text=get_button_text('btn_edit_entry', language),
            callback_data=f"entry_edit:{entry_id}"
        ),
        InlineKeyboardButton(
            text=get_button_text('btn_delete_entry', language),
            callback_data=f"entry_delete_confirm:{entry_id}:{target_date.isoformat()}" # <-- Передаем target_date.isoformat()
        )
    ]
    keyboard_buttons.append(actions_row_1)

    # --- КНОПКА АНАЛИЗА ДНЯ ---
    if is_day_analyzed:
        # Если день проанализирован, показываем кнопку "Анализ дня"
        analysis_day_button = InlineKeyboardButton(
            text="🔬 Анализ дня", # Или get_message('btn_view_day_analysis', language) если добавите
            callback_data=f"view_full_day_analysis:{target_date.year}:{target_date.month}:{target_date.day}" # Новый callback
        )
    else:
        # Если день НЕ проанализирован, показываем кнопку "Пересчитать анализ дня"
        analysis_day_button = InlineKeyboardButton(
            text=get_button_text('btn_reanalyze_entry', language),
            callback_data=f"reanalyze_day:{target_date.year}:{target_date.month}:{target_date.day}"
        )
    
    keyboard_buttons.append([analysis_day_button]) # Добавляем кнопку в отдельный ряд

    # Кнопка удаления всего дня
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_delete_all_entries', language),
            callback_data=f"delete_entire_day:{target_date.year}-{target_date.month}-{target_date.day}"
        )
    ])

    # Кнопка "Назад к дню" (календарю)
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back_to_day', language),
            callback_data=f"calendar_return_to_month:{target_date.year}:{target_date.month}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_back_to_edit_day_keyboard(target_date: date, language: str) -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Назад к редактированию дня".

    Args:
        target_date: Дата.
        language: Язык интерфейса.

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    year = target_date.year
    month = target_date.month
    day = target_date.day
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back_to_edit_day', language),
                callback_data=f"view_entry_history:{year}:{month}:{day}"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

# TODO Разметка для копирования
def format_entry_text_for_editing(entry_text: str) -> str:
    """
    Форматирует текст записи для удобного редактирования (например, в блоке кода).

    Args:
        entry_text: Исходный текст записи.

    Returns:
        str: Отформатированный текст.
    """
    return entry_text

async def get_days_with_entries_and_mood_async(user, year: int, month: int) -> dict:
    """
    Асинхронное получение дней месяца с оценками настроения
    """
    logger.debug(f"Получение дней с записями и настроением для {year}-{month} пользователя {user.telegram_id}")
    days_data = {}
    try:
        # Используем сырой SQL запрос для полного контроля
        @sync_to_async
        def get_mood_data_sync():
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        EXTRACT(DAY FROM date) as day,
                        average_mood_score
                    FROM diary_combined_entry 
                    WHERE user_id = %s 
                    AND EXTRACT(YEAR FROM date) = %s 
                    AND EXTRACT(MONTH FROM date) = %s
                    AND entry_count > 0
                    AND average_mood_score IS NOT NULL
                    ORDER BY date
                """, [user.id, year, month])
                
                return cursor.fetchall()
        
        mood_data = await get_mood_data_sync()
        logger.debug(f"Найдено {len(mood_data)} записей с оценками настроения")
        
        for day, average_mood_score in mood_data:
            day_int = int(day)
            if average_mood_score is not None and average_mood_score > 0:
                days_data[day_int] = float(average_mood_score)
            else:
                days_data[day_int] = None
                
        logger.debug(f"Данные настроения: {days_data}")
        return days_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении оценок настроения: {e}", exc_info=True)
        return {}