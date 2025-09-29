from aiogram.fsm.state import State, StatesGroup

class FeedbackStates(StatesGroup):
    waiting_message = State()  # Ожидание текста/голоса
    waiting_photo = State()   # Ожидание фото (опционально)