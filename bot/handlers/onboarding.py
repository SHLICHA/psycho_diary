"""
Handlers для процесса онбординга (знакомства) нового пользователя.
"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.types import ContentType

from asgiref.sync import sync_to_async

from messages import get_message
from bot.states.onboarding_states import OnboardingStates
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from users.models import User # Импортируем User для обновления onboarding_step

router = Router()
logger = logging.getLogger(__name__)

# --- НОВЫЙ ХЕНДЛЕР: Переход от приветствия к инструкции ---
@router.callback_query(F.data == "onboarding_info_next")
async def onboarding_info_next(callback: CallbackQuery, user, language: str):
    """
    Обновляет onboarding_step с 'start' на 'welcome_shown'.
    Отправляет инструкцию.
    """
    try:
        if user.onboarding_step != 'start':
            logger.warning(f"[Onboarding] Пользователь {user.telegram_id} пытается выполнить onboarding_info_next, но его шаг: {user.onboarding_step}")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return

        user.onboarding_step = 'welcome_shown'
        await sync_to_async(user.save)(update_fields=['onboarding_step'])
        logger.info(f"[Onboarding] Шаг onboarding обновлён для {user.telegram_id} с 'start' на 'welcome_shown'.")

        # --- НОВОЕ: Отправляем инструкцию сразу ---
        from messages import get_message
        from bot.keyboards.onboarding_keyboards import get_next_after_info_keyboard
        info_text = get_message('onboarding_project_info', language)
        keyboard = get_next_after_info_keyboard(language) # <-- Кнопка "Готов ввести запись"
        await callback.message.edit_text(text=info_text, reply_markup=keyboard) # <-- Редактируем сообщение с приветствием
        # --- /НОВОЕ ---

        # Отвечаем на callback (необязательно, если edit_text уже подтверждает)
        # await safe_answer_callback(callback, "")

    except Exception as e:
        logger.error(f"Ошибка при обновлении шага onboarding_info_next для пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_ready_for_entry")
async def onboarding_ready_for_entry(callback: CallbackQuery, user, language: str):
    """
    Обновляет onboarding_step с 'welcome_shown' на 'info_shown'.
    Отправляет просьбу ввести запись.
    """
    try:
        if user.onboarding_step != 'welcome_shown':
            logger.warning(f"[Onboarding] Пользователь {user.telegram_id} пытается выполнить onboarding_ready_for_entry, но его шаг: {user.onboarding_step}")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return

        user.onboarding_step = 'info_shown'
        await sync_to_async(user.save)(update_fields=['onboarding_step'])
        logger.info(f"[Onboarding] Шаг onboarding обновлён для {user.telegram_id} с 'welcome_shown' на 'info_shown'.")

        # --- НОВОЕ: Отправляем просьбу ввести запись ---
        from messages import get_message
        prompt_text = get_message('onboarding_prompt_first_entry', language)
        # Убираем клавиатуру
        await callback.message.edit_text(text=prompt_text) # <-- Редактируем сообщение с инструкцией
        # --- /НОВОЕ ---

        await safe_answer_callback(callback, "")

    except Exception as e:
        logger.error(f"Ошибка при обновлении шага onboarding_ready_for_entry для пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data == "onboarding_start_first_entry_new")
async def onboarding_start_first_entry_new(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Обновляет onboarding_step с 'info_shown' на 'first_entry_created'.
    Затем вызывает логику создания первой записи.
    """
    try:
        # Проверяем текущий шаг (опционально, для надежности)
        if user.onboarding_step != 'info_shown':
            logger.warning(f"[Onboarding] Пользователь {user.telegram_id} пытается выполнить onboarding_start_first_entry_new, но его шаг: {user.onboarding_step}")
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        from bot.handlers.diary import start_first_entry_flow
        # Вызываем
        await start_first_entry_flow(callback, state, user, language) # Передаем callback, т.к. он вызывается как хендлер

        # Обновлять onboarding_step тут не будем, пусть diary.py обновляет после успешного сохранения.
        # await safe_answer_callback(callback, "") # start_first_entry_flow уже ответит на callback или отправит сообщение

    except Exception as e:
        logger.error(f"Ошибка при запуске создания первой записи из онбординга для пользователя {user.telegram_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def handle_first_entry_input(message: Message, state: FSMContext, user, language: str):
    """
    Ловит сообщение пользователя, когда onboarding_step = 'info_shown'.
    Вызывает сервисную функцию для обработки первой записи.
    """
    # Проверяем onboarding_step ВНУТРИ хендлера
    if user.onboarding_step != 'info_shown':
         logger.debug(f"[Onboarding] handle_first_entry_input вызван, но onboarding_step = {user.onboarding_step} для {user.telegram_id}. Игнорируем.")
         # Не делаем ничего, пусть другие хендлеры обработают, или можно вернуть.
         # Но т.к. фильтр F.content_type.in_... всё равно сработал, и middleware не перехватила (предположим, что _is_onboarding_event работает),
         # то это сообщение действительно может быть целевым.
         # Лучше обработать как ошибка или неожиданный ввод, если шаг не тот.
         # Например, отправить сообщение, что шаг не соответствует.
         # Но для простоты, просто игнорируем.
         return # Или отправить сообщение типа "Сначала завершите предыдущий шаг"

    try:
        # Вызываем сервисную функцию
        from bot.services.diary_service import process_first_entry_from_onboarding_message_service
        result = await process_first_entry_from_onboarding_message_service(message, user, language)

        if result['success']:
             logger.info(f"[Onboarding] Первая запись успешно создана и обработана для пользователя {user.telegram_id} через onboarding.")
             # onboarding_step обновляется внутри сервисной функции при успехе
             # Middleware при следующем действии увидит 'first_entry_created' и направит к следующему шагу.
        else:
             error_msg = result.get('message', get_message('error_processing', language))
             # Отправляем сообщение об ошибке пользователю и повторяем просьбу ввести запись
             await message.answer(f"{error_msg}")
             # onboarding_step остаётся 'info_shown', пользователь может попробовать снова
             logger.info(f"[Onboarding] Повторный запрос ввода первой записи для {user.telegram_id} после ошибки.")

    except Exception as e:
        logger.error(f"[Onboarding] Критическая ошибка при обработке сообщения пользователя {user.telegram_id} для первой записи: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language))
    