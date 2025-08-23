"""
Клавиатура календаря для архива записей
"""

import logging

from asgiref.sync import async_to_sync
from datetime import datetime, date
from calendar import monthrange
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.diary_service import diary_service
from messages import get_button_text

logger = logging.getLogger(__name__)

async def get_smart_calendar_keyboard(user, language: str) -> InlineKeyboardMarkup:
    """Получение умного календаря с фокусом на текущий месяц"""
    
    try:
        logger.info("Создание умного календаря")
        
        # Получаем текущую дату
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        current_day = today.day
        
        logger.info(f"Текущая дата: {current_day}.{current_month}.{current_year}")
        
        # Создаем календарь для текущего месяца
        return await get_month_calendar_with_navigation(user, current_year, current_month, current_day, language)
        
    except Exception as e:
        logger.error(f"Ошибка при создании умного календаря: {e}")
        # Возвращаем базовый календарь в случае ошибки
        return get_basic_calendar_keyboard(language)

async def get_month_calendar_with_navigation(user, year: int, month: int, current_day: int, language: str) -> InlineKeyboardMarkup:
    """Получение календаря месяца с навигацией (АСИНХРОННАЯ версия!)"""
    
    buttons = []
    
    # Названия месяцев
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
    
    # Заголовок с навигацией по месяцам
    header_buttons = [
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"calendar_prev_month:{year}:{month}"
        ),
        InlineKeyboardButton(
            text=f"{month_name} {year}",
            callback_data="calendar_empty"  # Не активная кнопка
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"calendar_next_month:{year}:{month}"
        )
    ]
    buttons.append(header_buttons)
    
    # Заголовки дней недели
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekdays_en = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    weekdays = weekdays_ru if language == 'ru' else weekdays_en
    
    weekday_buttons = [
        InlineKeyboardButton(text=day, callback_data="calendar_empty") 
        for day in weekdays
    ]
    buttons.append(weekday_buttons)
    
    # Получаем дни с записями для текущего месяца (АСИНХРОННО!)
    try:
        # ИСПРАВЛЕНО: используем асинхронную версию
        days_with_entries = await get_days_with_entries_async(user, year, month)
        logger.info(f"Получено {len(days_with_entries)} дней с записями (async)")
    except Exception as e:
        logger.error(f"Ошибка при асинхронном получении дней с записями: {e}")
        days_with_entries = set()
    
    # Дни месяца
    first_day_weekday = date(year, month, 1).weekday()  # 0=понедельник
    days_in_month = monthrange(year, month)[1]
    
    day_buttons = []
    # Пустые кнопки для дней предыдущего месяца
    for i in range(first_day_weekday):
        day_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
    
    # Кнопки для дней текущего месяца
    today = datetime.now()
    for day in range(1, days_in_month + 1):
        # Подсвечиваем сегодняшний день
        day_text = str(day)
        if year == today.year and month == today.month and day == today.day:
            day_text = f"🔹{day}🔹"
        elif day in days_with_entries:
            # Отмечаем дни с записями
            day_text = f"📝{day}"
        
        day_buttons.append(
            InlineKeyboardButton(
                text=day_text,
                callback_data=f"calendar_select_day:{year}:{month}:{day}"
            )
        )
        
        # По 7 дней в ряд (дни недели)
        if len(day_buttons) % 7 == 0:
            buttons.append(day_buttons)
            day_buttons = []
    
    # Оставшиеся дни
    if day_buttons:
        # Добавляем пустые кнопки до конца недели
        while len(day_buttons) % 7 != 0:
            day_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
        buttons.append(day_buttons)
    
    # Кнопка выбора года
    year_button = [
        InlineKeyboardButton(
            text=f"📅 Выбрать год: {year}",
            callback_data=f"calendar_open_year_selector:{year}"
        )
    ]
    buttons.append(year_button)
    
    # Кнопка "Назад"
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_days_with_entries_sync(user, year: int, month: int) -> set:
    """Синхронное получение дней месяца, в которые есть записи"""
    try:
        from diary.models import DiaryEntry
        from django.db.models import Q
        
        logger.info(f"Синхронное получение дней с записями для пользователя {user.telegram_id} за {month}.{year}")
        
        # Синхронный запрос к базе данных
        days_with_entries = set()
        
        # Получаем записи пользователя за месяц
        entries = DiaryEntry.objects.filter(
            user=user,
            created_at__year=year,
            created_at__month=month
        ).distinct()
        
        # Извлекаем дни
        for entry in entries:
            day = entry.created_at.day
            days_with_entries.add(day)
        
        logger.info(f"Найдено {len(days_with_entries)} дней с записями в {month}.{year} (sync)")
        return days_with_entries
        
    except Exception as e:
        logger.error(f"Ошибка при синхронном получении дней с записями: {e}")
        return set()

def get_year_selection_keyboard(current_year: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора года"""
    
    buttons = []
    
    # Заголовок
    buttons.append([
        InlineKeyboardButton(
            text="📅 Выбор года",
            callback_data="calendar_empty"
        )
    ])
    
    # Года вокруг текущего
    year_range = 9  # Показываем 9 лет вокруг текущего
    start_year = current_year - 4
    end_year = current_year + 4
    
    # Разбиваем на строки по 3 года
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
    
    # Кнопка "Назад"
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data="archive"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def get_days_with_entries_async(user, year: int, month: int) -> set:
    """Асинхронное получение дней месяца, в которые есть записи"""
    try:
        logger.info(f"Асинхронное получение дней с записями для пользователя {user.telegram_id} за {month}.{year}")
        
        days_with_entries = await diary_service.get_days_with_entries(user, year, month)
        
        logger.info(f"Найдено {len(days_with_entries)} дней с записями (async)")
        return days_with_entries
        
    except Exception as e:
        logger.error(f"Ошибка при асинхронном получении дней с записями: {e}")
        return set()

def get_month_selection_keyboard(year: int, current_month: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора месяца"""
    
    buttons = []
    
    # Заголовок
    buttons.append([
        InlineKeyboardButton(
            text=f"📅 Выбор месяца {year}",
            callback_data="calendar_empty"
        )
    ])
    
    # Месяцы
    month_names_ru = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    month_names_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_names = month_names_ru if language == 'ru' else month_names_en
    
    # Разбиваем на строки по 3 месяца
    for i in range(0, 12, 3):
        month_row = []
        for j in range(3):
            month_index = i + j + 1
            if month_index <= 12:
                # Выделяем текущий месяц
                month_text = f"🔹{month_names[month_index-1]}🔹" if month_index == current_month else month_names[month_index-1]
                month_row.append(
                    InlineKeyboardButton(
                        text=month_text,
                        callback_data=f"calendar_select_specific_month:{year}:{month_index}"
                    )
                )
        if month_row:
            buttons.append(month_row)
    
    # Кнопка "Назад"
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_return_to_month:{year}:{current_month}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_basic_calendar_keyboard(language: str) -> InlineKeyboardMarkup:
    """Базовый календарь на случай ошибок"""
    
    buttons = []
    
    # Заголовок
    buttons.append([
        InlineKeyboardButton(
            text="📅 Архив записей",
            callback_data="calendar_empty"
        )
    ])
    
    # Текущий год
    current_year = datetime.now().year
    buttons.append([
        InlineKeyboardButton(
            text=str(current_year),
            callback_data=f"calendar_open_year_selector:{current_year}"
        )
    ])
    
    # Месяцы
    month_names_ru = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    month_names_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_names = month_names_ru if language == 'ru' else month_names_en
    
    month_row = []
    for i, month_name in enumerate(month_names, 1):
        month_row.append(
            InlineKeyboardButton(
                text=month_name,
                callback_data=f"calendar_open_month_selector:{current_year}:{i}"
            )
        )
        
        if i % 4 == 0:  # 4 месяца в ряд
            buttons.append(month_row)
            month_row = []
    
    if month_row:
        buttons.append(month_row)
    
    # Кнопка "Назад"
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
                callback_data=f"calendar_return_to_month:{year}:{month}"  # Возврат к конкретному месяцу!
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_entry_view_keyboard(language: str, year: int, month: int, day: int) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра записи с кнопкой возврата к календарю"""
    
    buttons = []
    
    # Кнопки управления записью
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
    
    # Кнопка повторного анализа
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_analyze_again', language),
            callback_data=f"reanalyze_entry:{year}:{month}:{day}"
        )
    ])
    
    # Кнопка "Назад" к календарю
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_return_to_month:{year}:{month}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_entry_management_keyboard(language: str, entry_id: int, year: int, month: int, day: int) -> InlineKeyboardMarkup:
    """Клавиатура управления конкретной записью"""
    
    buttons = []
    
    # Кнопки редактирования и удаления на одной строке
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_edit_entry', language),
            callback_data=f"edit_specific_entry:{entry_id}"
        ),
        InlineKeyboardButton(
            text=get_button_text('btn_delete_entry', language),
            callback_data=f"delete_specific_entry:{entry_id}"
        )
    ])
    
    # Кнопка повторного анализа
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_analyze_again', language),
            callback_data=f"reanalyze_specific_entry:{entry_id}"
        )
    ])
    
    # Кнопка "Назад" к просмотру дня
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_select_day:{year}:{month}:{day}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_entry_history_keyboard(language: str, entries: list, year: int, month: int, day: int) -> InlineKeyboardMarkup:
    """Клавиатура истории записей за день"""
    
    buttons = []
    
    # Кнопки для каждой записи
    for i, entry in enumerate(entries, 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"📝 Запись {i} ({entry.created_at.strftime('%H:%M')})",
                callback_data=f"view_specific_entry:{entry.id}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_edit_entry', language),
                callback_data=f"edit_specific_entry:{entry.id}"
            ),
            InlineKeyboardButton(
                text=get_button_text('btn_delete_entry', language),
                callback_data=f"delete_specific_entry:{entry.id}"
            )
        ])
    
    # Кнопка "Назад" к просмотру дня
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_select_day:{year}:{month}:{day}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_specific_entry_view_keyboard(language: str, entry_id: int, year: int, month: int, day: int) -> InlineKeyboardMarkup:
    """Клавиатура просмотра конкретной записи"""
    
    buttons = []
    
    # Кнопки управления конкретной записью
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_edit_entry', language),
            callback_data=f"edit_specific_entry:{entry_id}"
        ),
        InlineKeyboardButton(
            text=get_button_text('btn_delete_entry', language),
            callback_data=f"delete_specific_entry:{entry_id}"
        )
    ])
    
    # Кнопка повторного анализа
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_analyze_again', language),
            callback_data=f"reanalyze_specific_entry:{entry_id}"
        )
    ])
    
    # Кнопка "Назад" к просмотру дня
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text('btn_back', language),
            callback_data=f"calendar_select_day:{year}:{month}:{day}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_delete_keyboard(language: str, entry_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления записи"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=f"confirm_delete_entry:{entry_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет, отмена",
                callback_data="cancel_delete_entry"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_calendar_keyboard(language: str, year: int, month: int) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к календарю"""
    
    buttons = [
        [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data=f"calendar_return_to_month:{year}:{month}"  # Возврат к конкретному месяцу!
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)