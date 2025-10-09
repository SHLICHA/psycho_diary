from aiogram.fsm.state import State, StatesGroup

class PaymentStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_tokens_email = State()
    waiting_for_custom_tokens_amount = State()
    waiting_for_tokens_amount = State() # Для произвольного ввода