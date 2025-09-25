"""
Менеджер состояний FSM
"""

import logging
from typing import Optional, Any
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)

class StateManager:
    """Менеджер для работы с состояниями FSM"""
    
    @staticmethod
    async def set_state(context: FSMContext, state: State, **data):
        """Установка состояния с данными"""
        try:
            await context.set_state(state)
            if data:
                await context.update_data(**data)
        except Exception as e:
            logger.error(f"Error setting state {state.state}: {e}")
    
    @staticmethod
    async def get_state_data(context: FSMContext) -> dict:
        """Получение данных состояния"""
        try:
            data = await context.get_data()
            return data
        except Exception as e:
            logger.error(f"Error getting state data: {e}")
            return {}
    
    @staticmethod
    async def update_state_data(context: FSMContext, **data):
        """Обновление данных состояния"""
        try:
            await context.update_data(**data)
        except Exception as e:
            logger.error(f"Error updating state data: {e}")
    
    @staticmethod
    async def clear_state(context: FSMContext):
        """Очистка состояния"""
        try:
            await context.clear()
        except Exception as e:
            logger.error(f"Error clearing state: {e}")
    
    @staticmethod
    async def get_current_state(context: FSMContext) -> Optional[State]:
        """Получение текущего состояния"""
        try:
            state = await context.get_state()
            return state
        except Exception as e:
            logger.error(f"Error getting current state: {e}")
            return None
    
    @staticmethod
    async def is_in_state(context: FSMContext, state_group: StatesGroup) -> bool:
        """Проверка, находится ли пользователь в определенной группе состояний"""
        try:
            current_state = await context.get_state()
            if current_state is None:
                return False
            state_prefix = f"{state_group.__class__.__module__}.{state_group.__class__.__name__}"
            return current_state.startswith(state_prefix)
        except Exception as e:
            logger.error(f"Error checking state group: {e}")
            return False

state_manager = StateManager()