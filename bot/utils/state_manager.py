"""
Менеджер состояний FSM с автоматическим таймаутом
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram import Bot
from django.db import DatabaseError

from messages import get_message

logger = logging.getLogger(__name__)

class StateManager:
    """Менеджер для работы с состояниями FSM с автоматическим таймаутом"""
    
    def __init__(self, timeout_seconds: int = 3600):  # 1 час по умолчанию
        self._timeout_seconds = timeout_seconds
        self._state_timers: Dict[str, asyncio.Task] = {}
        self._bot_instance: Optional[Bot] = None
        self._storage_key_to_user_id: Dict[str, int] = {}
        
    def set_bot(self, bot: Bot):
        """Установка экземпляра бота для отправки сообщений"""
        self._bot_instance = bot
    
    async def set_state(self, context: FSMContext, state: State, **data):
        """Установка состояния с автоматическим таймаутом"""
        try:
            # Получаем идентификатор пользователя и ключ хранилища
            user_id = context.key.user_id
            storage_key = self._get_storage_key(context.key)
            
            # Останавливаем предыдущий таймер если есть
            await self._stop_timer(storage_key)
            
            # Устанавливаем состояние и данные
            await context.set_state(state)
            if data:
                await context.update_data(**data)
            
            # Сохраняем связь ключа хранилища с user_id
            self._storage_key_to_user_id[storage_key] = user_id
            
            # Запускаем таймер таймаута
            self._state_timers[storage_key] = asyncio.create_task(
                self._state_timeout_handler(storage_key, context, self._timeout_seconds)
            )
            
            logger.debug(f"State {state.state} set for user {user_id} with timeout {self._timeout_seconds}s")
            
        except Exception as e:
            logger.error(f"Error setting state {state.state}: {e}")
            raise
    
    async def _state_timeout_handler(self, storage_key: str, context: FSMContext, timeout: int):
        """Обработчик таймаута состояния"""
        try:
            await asyncio.sleep(timeout)
            
            # Получаем user_id из сохраненной связи
            user_id = self._storage_key_to_user_id.get(storage_key)
            if not user_id:
                logger.warning(f"No user_id found for storage key {storage_key}")
                return
            
            # Получаем текущее состояние перед очисткой
            current_state = await context.get_state()
            
            # Сбрасываем состояние
            await context.clear()
            # Отправляем сообщение о таймауте если есть бот
            if self._bot_instance and user_id:
                language = await self._get_user_language(user_id)
                try:
                    await self._bot_instance.send_message(
                        user_id,
                        get_message('session_expired', language)
                    )
                    logger.info(f"State timeout handled for user {user_id}, previous state: {current_state}")
                except Exception as e:
                    logger.error(f"Error sending timeout message to user {user_id}: {e}")
            
            # Очищаем данные
            await self._cleanup_storage_data(storage_key)
            
        except asyncio.CancelledError:
            # Таймер был отменен - это нормально
            pass
        except Exception as e:
            logger.error(f"Error in state timeout handler for storage key {storage_key}: {e}")

    async def _get_user_language(self, user_id: int) -> str:
        """Получение языка пользователя из базы данных"""
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from users.models import User
            
            try:
                user = await User.objects.aget(telegram_id=user_id)
                return user.language or 'ru'  # По умолчанию русский
            except User.DoesNotExist:
                logger.warning(f"User with telegram_id {user_id} not found, using default language")
                return 'ru'
            except DatabaseError as e:
                logger.error(f"Database error while getting user language for {user_id}: {e}")
                return 'ru'
                
        except ImportError:
            logger.error("Could not import User model, using default language")
            return 'ru'
        except Exception as e:
            logger.error(f"Unexpected error getting user language for {user_id}: {e}")
            return 'ru'
    
    async def stop_state(self, context: FSMContext):
        """Остановка состояния с очисткой таймера"""
        try:
            storage_key = self._get_storage_key(context.key)
            await self._cleanup_storage_data(storage_key)
            await context.clear()
            
            user_id = context.key.user_id
            logger.debug(f"State manually stopped for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error stopping state: {e}")
    
    async def _stop_timer(self, storage_key: str):
        """Остановка таймера по ключу хранилища"""
        if storage_key in self._state_timers:
            task = self._state_timers[storage_key]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._state_timers[storage_key]
    
    async def _cleanup_storage_data(self, storage_key: str):
        """Очистка данных по ключу хранилища"""
        await self._stop_timer(storage_key)
        if storage_key in self._storage_key_to_user_id:
            del self._storage_key_to_user_id[storage_key]
    
    def _get_storage_key(self, key: StorageKey) -> str:
        """Генерация уникального ключа для хранилища"""
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"
    
    # Статические методы из оригинального класса (полная обратная совместимость)
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

# Глобальный экземпляр с таймаутом 1 час
state_manager = StateManager(timeout_seconds=3600)