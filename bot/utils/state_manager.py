"""
Менеджер состояний FSM с автоматическим таймаутом
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Awaitable, Callable
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram import Bot
from django.db import DatabaseError

from messages import get_message
from bot.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)

async def send_main_menu_callback(bot_instance: Bot, user_id: int, language: str):
    """
    Функция-коллбэк для отправки главного меню пользователю.
    """
    # --- ДОБАВИМ ЛОГ ---
    logger.info(f"send_main_menu_callback вызвана для user_id {user_id}, language {language}, bot_instance is None: {bot_instance is None}")
    # --- КОНЕЦ ДОБАВКИ ---
    try:
        if not bot_instance:
            logger.error(f"Bot instance is None in send_main_menu_callback for user {user_id}")
            return

        from messages import get_message
        from bot.keyboards import get_main_menu_keyboard # Убедитесь, что импорт корректен

        main_menu_text = get_message('main_menu', language)
        # Попробуем получить пользователя для клавиатуры, если она принимает user
        # user = await User.objects.aget(telegram_id=user_id) # Если нужно
        main_menu_keyboard = get_main_menu_keyboard(language) # user=user, если нужно

        await bot_instance.send_message(
            chat_id=user_id,
            text=main_menu_text,
            reply_markup=main_menu_keyboard
        )
        logger.info(f"Главное меню отправлено пользователю {user_id} после таймаута FSM.")
    except Exception as e:
        logger.error(f"Ошибка при отправке главного меню пользователю {user_id} после таймаута FSM: {e}", exc_info=True) # exc_info=True покажет трейсбек


class StateManager:
    """Менеджер для работы с состояниями FSM с автоматическим таймаутом"""
    
    def __init__(self, timeout_seconds: int = 3600, on_timeout_callback: Optional[Callable[[Bot, int, str], Awaitable[None]]] = None): # bot_instance, user_id, language
        self._timeout_seconds = timeout_seconds
        self._state_timers: Dict[str, asyncio.Task] = {}
        self._bot_instance: Optional[Bot] = None
        self._storage_key_to_user_id: Dict[str, int] = {}
        self._on_timeout_callback = on_timeout_callback
        
    def set_bot(self, bot: Bot):
        """Установка экземпляра бота для отправки сообщений"""
        self._bot_instance = bot
        logger.info("Bot instance установлен в StateManager")
    
    async def set_state(self, context: FSMContext, state: State, **data):
        """Установка состояния с автоматическим таймаутом"""
        try:
            user_id = context.key.user_id
            storage_key = self._get_storage_key(context.key)

            await self._stop_timer(storage_key)

            await context.set_state(state)
            if data:
                await context.update_data(**data)

            self._storage_key_to_user_id[storage_key] = user_id

            # Передаём user_id в _state_timeout_handler
            self._state_timers[storage_key] = asyncio.create_task(
                self._state_timeout_handler(storage_key, context, self._timeout_seconds, user_id)
            )

            logger.debug(f"State {state.state} set for user {user_id} with timeout {self._timeout_seconds}s")

        except Exception as e:
            logger.error(f"Error setting state {state.state}: {e}")
            raise
    
    async def _state_timeout_handler(self, storage_key: str, context: FSMContext, timeout: int, user_id: int):
        """Обработчик таймаута состояния"""
        try:
            await asyncio.sleep(timeout)

            current_state = await context.get_state()

            await context.clear()
            language = await self._get_user_language(user_id)

            # --- НОВАЯ ЛОГИКА ---
            # 1. Отправляем сообщение о таймауте
            if self._bot_instance:
                try:
                    # Импортируем внутри функции
                    await self._bot_instance.send_message(
                        user_id,
                        get_message('session_expired', language)
                    )
                    logger.info(f"State timeout notification sent to user {user_id}, previous state: {current_state}")
                except Exception as e:
                    logger.error(f"Error sending timeout notification to user {user_id}: {e}")

            # 2. Вызываем внешнюю функцию для возврата в главное меню (если она установлена)
            if self._on_timeout_callback: # <-- Проверка, что коллбэк установлен
                logger.debug(f"Вызов on_timeout_callback для user {user_id}") # --- ДОБАВИМ ЛОГ ---
                try:
                    # Передаём bot_instance, user_id и language в коллбэк
                    await self._on_timeout_callback(self._bot_instance, user_id, language)
                except Exception as callback_error:
                    logger.error(f"Error in on_timeout_callback for user {user_id}: {callback_error}", exc_info=True) # exc_info=True покажет трейсбек
            else:
                logger.warning(f"on_timeout_callback не установлен для user {user_id}") # --- ДОБАВИМ ЛОГ ---
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

            await self._cleanup_storage_data(storage_key)
            logger.info(f"State timeout handled for user {user_id}, previous state: {current_state}")

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
        """Очистка состояния с остановкой таймера"""
        try:
            logger.debug(f"StateManager.clear_state вызван для FSMContext с key: {context.key}")
            
            # Сначала останавливаем таймер
            storage_key = state_manager._get_storage_key(context.key)
            await state_manager._stop_timer(storage_key)
            
            # Затем очищаем данные состояния
            await context.clear()
            
            logger.debug(f"State cleared and timer stopped for user {context.key.user_id}")
            
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
state_manager = StateManager(timeout_seconds=3600, on_timeout_callback=send_main_menu_callback)