# /home/shlicha/psycho_diary/bot/states/onboarding_states.py
"""
Состояния FSM для процесса онбординга (знакомства) нового пользователя.
"""

from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    # Состояния для текущего онбординга (если есть)
    showing_agreement = State() # <-- Старое состояние, оставим для совместимости
    collecting_profile_data = State() # <-- Старое состояние, анкета, можем оставить или удалить позже

    # Новые состояния для нового онбординга
    show_agreement_for_first_entry = State() # <-- Новое состояние: показ соглашения перед первой записью
    # Состояния для первой записи будут в diary_states.py
    # waiting_for_first_text_entry = State() # <-- Это будет в DiaryStates
    # waiting_for_timezone_setup = State() # <-- Это будет в SettingsStates или DiaryStates