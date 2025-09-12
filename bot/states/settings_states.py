"""
Состояния для работы с настройками
"""

from aiogram.fsm.state import State, StatesGroup

class SettingsStates(StatesGroup):
    """Состояния для работы с настройками"""
    
    # Основные настройки
    in_settings_menu = State()
    
    # Изменение языка
    changing_language = State()
    waiting_for_language_choice = State()
    
    # Изменение уведомлений
    changing_notifications = State()
    
    # Изменение автоанализа
    changing_auto_analysis = State()
    
    # Премиум настройки
    in_premium_menu = State()
    processing_premium_subscription = State()
    
    # Изменение часового пояса
    waiting_for_timezone_input = State()
    waiting_for_city_input = State()  # Новое состояние
    waiting_for_timezone_confirmation = State()

    # Подтверждение изменений
    confirming_settings_change = State()

        # Редактирование профиля
    editing_profile = State()
    waiting_for_name_input = State()
    waiting_for_email_input = State()
    waiting_for_date_of_birth_input = State()
    waiting_for_hobbies_input = State()
    waiting_for_life_facts_input = State()

    # Удаление аккаунта
    in_account_deletion_menu = State()
    waiting_for_deletion_confirmation = State()
    waiting_for_deletion_confirmation_text = State()  # Новое состояние
    account_deletion_confirmed = State()

    def __str__(self):
        return f"SettingsStates.{self.__class__.__name__}"