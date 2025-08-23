"""
Утилиты для работы с состояниями FSM
"""

import logging
from typing import Optional, Dict, Any
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)

async def set_user_state(
    context: FSMContext, 
    state: State, 
    user_id: int,
    **data
) -> bool:
    """
    Установка состояния для пользователя
    
    Args:
        context: Контекст FSM
        state: Состояние для установки
        user_id: ID пользователя
        **data: Дополнительные данные
        
    Returns:
        bool: Успешность операции
    """
    try:
        await context.set_state(state)
        if data:
            await context.update_data(**data)
        
        logger.info(f"Set state {state.state} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting state for user {user_id}: {e}")
        return False

async def get_user_state_data(context: FSMContext, user_id: int) -> Dict[str, Any]:
    """
    Получение данных состояния пользователя
    
    Args:
        context: Контекст FSM
        user_id: ID пользователя
        
    Returns:
        Dict[str, Any]: Данные состояния
    """
    try:
        data = await context.get_data()
        logger.debug(f"Retrieved state data for user {user_id}: {data}")
        return data
    except Exception as e:
        logger.error(f"Error getting state data for user {user_id}: {e}")
        return {}

async def update_user_state_data(
    context: FSMContext, 
    user_id: int,
    **data
) -> bool:
    """
    Обновление данных состояния пользователя
    
    Args:
        context: Контекст FSM
        user_id: ID пользователя
        **data: Данные для обновления
        
    Returns:
        bool: Успешность операции
    """
    try:
        await context.update_data(**data)
        logger.debug(f"Updated state data for user {user_id} with: {data}")
        return True
    except Exception as e:
        logger.error(f"Error updating state data for user {user_id}: {e}")
        return False

async def clear_user_state(context: FSMContext, user_id: int) -> bool:
    """
    Очистка состояния пользователя
    
    Args:
        context: Контекст FSM
        user_id: ID пользователя
        
    Returns:
        bool: Успешность операции
    """
    try:
        await context.clear()
        logger.info(f"Cleared state for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error clearing state for user {user_id}: {e}")
        return False

async def is_user_in_state_group(
    context: FSMContext, 
    user_id: int,
    state_group: StatesGroup
) -> bool:
    """
    Проверка, находится ли пользователь в определенной группе состояний
    
    Args:
        context: Контекст FSM
        user_id: ID пользователя
        state_group: Группа состояний
        
    Returns:
        bool: Находится ли пользователь в группе состояний
    """
    try:
        current_state = await context.get_state()
        if current_state is None:
            return False
        
        # Проверяем, принадлежит ли состояние к группе
        state_group_name = f"{state_group.__class__.__module__}.{state_group.__class__.__qualname__}"
        return current_state.startswith(state_group_name)
    except Exception as e:
        logger.error(f"Error checking state group for user {user_id}: {e}")
        return False

def get_state_name(state: State) -> str:
    """
    Получение имени состояния
    
    Args:
        state: Состояние
        
    Returns:
        str: Имя состояния
    """
    return state.state if state else "None"