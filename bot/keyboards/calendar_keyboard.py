"""
Клавиатура календаря для архива записей
"""

import logging

from typing import List
from datetime import datetime, date
from calendar import monthrange
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.diary_service import diary_service
from core.constants import MONTH_NAMES_RU, MONTH_NAMES_EN, MONTH_NAMES_SHORT_RU, MONTH_NAMES_SHORT_EN
from diary.models import DiaryEntry, CombinedDiaryEntry
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
        # Используем новую функцию
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
            # === НОВАЯ ЛОГИКА ОТМЕТКИ ДНЯ ===
            avg_mood_score = days_data[day]
            if avg_mood_score is not None and avg_mood_score > 0:
                # Определяем эмодзи на основе настроения (1-10)
                # Можно сделать более градационную шкалу
                if avg_mood_score >= 8:
                    mood_emoji = "😄" # Отлично
                elif avg_mood_score >= 6:
                    mood_emoji = "😊" # Хорошо
                elif avg_mood_score >= 4:
                    mood_emoji = "😐" # Нормально
                elif avg_mood_score >= 2:
                    mood_emoji = "😞" # Плохо
                else: # 1 или близко к 1
                    mood_emoji = "😢" # Ужасно
                day_text = f"{mood_emoji}{day}"
            else:
                # Если CombinedDiaryEntry есть, но средняя оценка 0 или None 
                # (возможно, день еще не проанализирован ИИ)
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
                # Выделяем текущий год
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
                # Выделяем текущий месяц
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

# TODO Пересмотреть. Пагинация? Подтвердить не в сегодняшнем дне
def get_day_entries_edit_keyboard(entries: List[DiaryEntry], target_date: date, language: str, is_day_analyzed: bool) -> InlineKeyboardMarkup:
    """
    Клавиатура для редактирования записей за день.

    Args:
        entries: Список записей DiaryEntry.
        target_date: Дата, для которой отображаются записи.
        language: Язык интерфейса.
        is_day_analyzed: Флаг, проанализирован ли день (для отображения кнопки "Подтвердить").

    Returns:
        InlineKeyboardMarkup: Клавиатура.
    """
    buttons = []
    year = target_date.year
    month = target_date.month
    day = target_date.day
    # Заголовок с датой
    date_str = target_date.strftime("%d.%m.%Y")
    header_text = get_message('edit_entries_header', language).format(date=date_str)
    buttons.append([
        InlineKeyboardButton(text=header_text, callback_data="edit_empty_header")
    ])
    for i, entry in enumerate(entries, 1):
        entry_preview = entry.text[:50] + "..." if len(entry.text) > 50 else entry.text
        entry_button_text = f"{i}. {entry_preview}"
        buttons.append([
            InlineKeyboardButton(
                text=entry_button_text,
                callback_data=f"edit_specific_entry:{entry.id}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_edit_entry', language),
                callback_data=f"edit_specific_entry:{entry.id}"
            ),
            InlineKeyboardButton(
                text=get_button_text('btn_delete_entry', language),
                callback_data=f"request_delete_specific_entry:{entry.id}"
            )
        ])
    bottom_row = []
    if not is_day_analyzed:
        bottom_row.append(
            InlineKeyboardButton(
                text=get_button_text('btn_confirm_changes', language),
                callback_data=f"confirm_day_analysis:{target_date.isoformat()}"
            )
        )
    back_text_key = 'btn_back_to_day_without_analysis' if not is_day_analyzed else 'btn_back_to_day'
    bottom_row.append(
        InlineKeyboardButton(
            text=get_button_text(back_text_key, language),
            callback_data=f"calendar_select_day:{year}:{month}:{day}"
        )
    )
    buttons.append(bottom_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirmation_keyboard(
    language: str,
    confirm_text_key: str,      # Ключ для текста кнопки "Подтвердить" из messages.py
    cancel_text_key: str,       # Ключ для текста кнопки "Отменить" из messages.py
    confirm_callback_data: str, # Callback data для кнопки "Подтвердить"
    cancel_callback_data: str,  # Callback data для кнопки "Отменить"
    # Опционально: можно добавить параметры для кастомизации внешнего вида
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
                text=get_button_text(confirm_text_key, language), # Используем get_button_text как в других клавиатурах
                callback_data=confirm_callback_data
            ),
            InlineKeyboardButton(
                text=get_button_text(cancel_text_key, language), # Используем get_button_text как в других клавиатурах
                callback_data=cancel_callback_data
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_delete_confirmation_keyboard(language: str, entry_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления записи (алиас)."""
    return get_confirmation_keyboard(
        language=language,
        confirm_text_key='btn_confirm_delete', # Убедись, что такой ключ есть в messages.py
        cancel_text_key='btn_cancel_delete',   # Убедись, что такой ключ есть в messages.py
        confirm_callback_data=f"confirm_delete_entry:{entry_id}",
        cancel_callback_data="cancel_delete_entry"
    )

def get_delete_entry_confirmation_keyboard(entry_id: int, target_date, language: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления конкретной записи (алиас)."""
    iso_date_str = target_date.isoformat() if not isinstance(target_date, str) else target_date
    return get_confirmation_keyboard(
        language=language,
        confirm_text_key='btn_confirm_delete_entry', # Убедись, что такой ключ есть
        cancel_text_key='btn_cancel',                # Используем общий ключ
        confirm_callback_data=f"confirm_delete_specific_entry:{entry_id}:{iso_date_str}",
        cancel_callback_data=f"cancel_delete_specific_entry:{entry_id}:{iso_date_str}"
    )

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
    Асинхронное получение дней месяца, в которые есть записи,
    и средней оценки настроения за эти дни.
    
    Returns:
        dict: Словарь, где ключ - день месяца (int), 
              значение - средняя оценка настроения (float) или None, если CombinedDiaryEntry отсутствует.
    """
    logger.debug(f"Получение дней с записями и настроением для {year}-{month} пользователя {user.telegram_id}")
    days_data = {}
    try:
        # Используем select_related для оптимизации запроса к CombinedDiaryEntry
        async for combined_entry in CombinedDiaryEntry.objects.filter(
            user=user,
            date__year=year,
            date__month=month
        ).select_related('user'): # select_related может помочь, если будут дополнительные поля из user
            day = combined_entry.date.day
            # Проверяем, есть ли записи (entry_count > 0) - это надежнее, чем просто существование CombinedDiaryEntry
            if combined_entry.entry_count > 0:
                # Сохраняем среднюю оценку. Если 0.0, все равно сохраняем, чтобы отличать от отсутствия данных.
                days_data[day] = combined_entry.average_mood_score 
            # Если entry_count == 0, CombinedDiaryEntry может быть артефактом или остатком от удаления,
            # и мы его игнорируем.
            
        logger.debug(f"Получены данные для дней: {list(days_data.keys())}")
        return days_data
    except Exception as e:
        logger.error(f"Ошибка при асинхронном получении дней с записями и настроением: {e}")
        # Возвращаем пустой словарь в случае ошибки
        return {}