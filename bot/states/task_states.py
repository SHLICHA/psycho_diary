"""
Состояния для работы с заданиями
"""

from aiogram.fsm.state import State, StatesGroup

class TaskStates(StatesGroup):
    """Состояния для работы с терапевтическими заданиями"""
    
    # Просмотр заданий
    browsing_tasks = State()
    viewing_task = State()
    
    # Выполнение задания
    completing_task = State()
    waiting_for_task_completion = State()
    
    # Описание ощущений при выполнении
    describing_feelings = State()
    waiting_for_feelings_description = State()
    
    # Подтверждение выполнения
    confirming_task_completion = State()
    
    # Пропуск задания
    skipping_task = State()
    confirming_task_skip = State()
    
    # Удаление задания
    deleting_task = State()
    confirming_task_deletion = State()
    
    # Просмотр результатов анализа выполнения
    viewing_completion_analysis = State()

    def __str__(self):
        return f"TaskStates.{self.__class__.__name__}"