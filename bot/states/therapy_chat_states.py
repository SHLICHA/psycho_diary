"""
Состояния FSM для чата с психологом.
"""

from aiogram.fsm.state import State, StatesGroup

class TherapyChatStates(StatesGroup):
    """
    Группа состояний для чата с психологом.
    """
    in_therapy_chat = State() # Состояние активного чата с психологом