from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    waiting_for_agreement_1 = State()
    waiting_for_agreement_2 = State()
    waiting_for_first_entry = State()
    waiting_for_timezone_confirmation = State()