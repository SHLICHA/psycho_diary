# /home/shlicha/psycho_diary/bot/states/onboarding_states.py
"""
Состояния FSM для процесса онбординга (знакомства) нового пользователя.
"""

from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    """
    Группа состояний для онбординга.
    """
    # Показываем инструкцию
    showing_instruction = State()
    
    # Показываем соглашение и ждем согласия
    showing_agreement = State() 
    
    # Этап анкетирования
    collecting_profile_data = State()