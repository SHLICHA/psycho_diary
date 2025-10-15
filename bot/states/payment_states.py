from aiogram.fsm.state import State, StatesGroup

class PaymentStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_tokens_email = State()