"""
Состояния для работы с дневником
"""

from aiogram.fsm.state import State, StatesGroup

class DiaryStates(StatesGroup):
    """Состояния для создания записей в дневнике"""
    
    # Ожидание записи (текстовой или голосовой)
    waiting_for_text_entry = State()
    waiting_for_voice_entry = State()
    
    # Уточняющие вопросы (если нужно)
    asking_clarifying_questions = State()
    waiting_for_clarification = State()
    
    # Просмотр архива
    browsing_archive = State()
    viewing_entry = State()
    
    # Удаление записи
    confirming_entry_deletion = State()
    
    # Перевыполнение анализа
    reanalyzing_entry = State()

    # Обработка отредактированной записи
    waiting_for_entry_edit = State()

    # Ожидание комментария
    waiting_for_user_comment = State()

    processing_entry = State()

    def __str__(self):
        return f"DiaryStates.{self.__class__.__name__}"