# /home/shlicha/psycho_diary/bot/states/onboarding_states.py
"""
Состояния FSM для процесса онбординга (знакомства) нового пользователя.
"""

from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    # Состояния для текущего онбординга (если есть)
    showing_agreement = State() # <-- Старое состояние, оставим для совместимости
    collecting_profile_data = State() # <-- Старое состояние, анкета, можем оставить или удалить позже

    # Новые состояния для нового онбординга (пока не используем FSM для основного потока, но могут пригодиться)
    # show_agreement_for_first_entry = State() # <-- Новое состояние: показ соглашения перед первой записью (теперь не нужно)
    showing_info = State() # <-- Состояние для показа инструкции (если будем использовать FSM)
    waiting_for_first_entry = State() # <-- Состояние ожидания первой записи (если будем использовать FSM)