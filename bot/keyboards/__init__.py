"""
Инициализация клавиатур
"""

# Импортируем все клавиатуры для удобного использования

# Основные клавиатуры
from .main_menu import (
    get_main_menu_keyboard,
    get_back_keyboard,
)

# Клавиатуры календаря
from .calendar_keyboard import (
    get_smart_calendar_keyboard,
    get_month_calendar_with_navigation,
    get_year_selection_keyboard,
    get_month_selection_keyboard,
    get_entry_view_keyboard,
    get_calendar_back_keyboard,
    get_back_to_edit_day_keyboard,
    get_confirmation_keyboard,
    format_entry_text_for_editing,
    get_delete_confirmation_keyboard,
    get_delete_entry_confirmation_keyboard,
    get_entry_page_keyboard
)

# Универсальные клавиатуры
from .common_keyboards import (
    get_cancel_keyboard,
)

# Клавиатуры настроек
from .settings_keyboard import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_premium_keyboard,
    get_common_timezones_keyboard,
    get_timezone_selection_method_keyboard,
    get_multiple_city_timezones_keyboard,
    get_city_timezone_confirmation_keyboard,
    get_analysis_time_selection_keyboard,
    get_edit_profile_keyboard,
    get_account_deletion_confirmation_keyboard,
    get_account_deletion_menu_keyboard
)

# Клавиатуры помощи
from .help_keyboard import (
    get_help_keyboard,
    get_help_section_keyboard
)

# Клавиатуры заданий
from .tasks_keyboard import (
    get_task_detail_keyboard,
    get_task_completion_keyboard,
    get_task_pagination_keyboard,
    get_confirm_delete_task_keyboard,
    get_task_history_main_keyboard,
    get_task_history_list_keyboard,
    get_task_history_detail_keyboard,
    get_task_main_menu_keyboard
)

__all__ = [
    # Основные клавиатуры
    'get_main_menu_keyboard',
    
    # Клавиатуры календаря
    'get_smart_calendar_keyboard',
    'get_month_calendar_with_navigation',
    'get_year_selection_keyboard',
    'get_month_selection_keyboard',
    'get_entry_view_keyboard',
    'get_basic_calendar_keyboard',
    'get_calendar_back_keyboard',
    'get_confirm_delete_entry_keyboard',
    'get_back_to_edit_day_keyboard',
    'format_entry_text_for_editing',
    'get_entry_pagination_keyboard',
    'get_entry_page_keyboard',
    
    # Универсальные клавиатуры
    'get_back_keyboard',
    'get_cancel_keyboard',
    'get_confirm_cancel_keyboard',
    'get_common_main_menu_keyboard',
    'get_edit_profile_keyboard',
    
    # Клавиатуры настроек
    'get_settings_keyboard',
    'get_language_selection_keyboard',
    'get_premium_keyboard',
    'get_common_timezones_keyboard',
    'get_timezone_selection_method_keyboard',
    'get_multiple_city_timezones_keyboard',
    'get_city_timezone_confirmation_keyboard',
    'get_analysis_time_selection_keyboard',
    'get_account_deletion_confirmation_keyboard',
    'get_account_deletion_menu_keyboard',
    
    # Клавиатуры помощи
    'get_help_keyboard',
    'get_help_section_keyboard',
    
    # Клавиатуры заданий
    'get_confirm_delete_task_keyboard',
    'get_task_detail_keyboard',
    'get_task_actions_keyboard',
    'get_task_completion_keyboard',
    'get_task_pagination_keyboard',
    'get_task_history_main_keyboard',
    'get_task_history_list_keyboard',
    'get_task_history_detail_keyboard',
    'get_task_main_menu_keyboard'
]