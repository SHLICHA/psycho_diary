"""
Утилиты для работы с сообщениями бота
"""

import logging
from typing import Optional, Callable, Any, Awaitable
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

from bot.utils.callback_utils import is_message_not_modified_error 
from users.models import User
from messages import get_message

logger = logging.getLogger(__name__)

async def edit_or_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    message_to_edit: Optional[Message] = None
) -> Message:
    """
    Редактирование сообщения или отправка нового если редактирование невозможно
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        text: Текст сообщения
        reply_markup: Клавиатура сообщения
        message_to_edit: Сообщение для редактирования (если есть)
        
    Returns:
        Message: Отправленное или отредактированное сообщение
    """
    try:
        if message_to_edit:
            if message_to_edit.text != text:
                edited_message = await message_to_edit.edit_text(
                    text=text,
                    reply_markup=reply_markup
                )
                return edited_message
            else:
                try:
                    edited_message = await message_to_edit.edit_reply_markup(
                        reply_markup=reply_markup
                    )
                    return edited_message
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    new_message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                    return new_message
        else:
            new_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )
            return new_message
    except Exception as e:
        logger.error(f"Ошибка при редактировании/отправке сообщения: {e}")
        try:
            new_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )
            return new_message
        except Exception as fallback_error:
            logger.error(f"Ошибка при резервной отправке сообщения: {fallback_error}")
            raise

async def safe_edit_message_text(
    message: Message,
    text: str,
    reply_markup=None
) -> bool:
    """
    Безопасное редактирование текста и клавиатуры сообщения с обработкой ошибок.

    Args:
        message: Сообщение для редактирования.
        text: Новый текст сообщения.
        reply_markup: Новая клавиатура сообщения.

    Returns:
        bool: Успешность редактирования (True, даже если ничего не изменилось).
    """
    text_changed = (message.text != text)
    if text_changed:
        success, _, _ = await safe_telegram_call(
            message.edit_text, 
            text=text, 
            reply_markup=reply_markup,
            operation_name=f"edit_text (message_id={message.message_id})"
        )
        return success
    else:
        try:
            success, _, error = await safe_telegram_call(
                message.edit_reply_markup,
                reply_markup=reply_markup,
                operation_name=f"edit_reply_markup (message_id={message.message_id})"
            )
            if success or (error and is_message_not_modified_error(error)):
                 return True
            else:
                 logger.warning(f"Не удалось обновить клавиатуру: {error}. Пробуем отредактировать всё сообщение.")
                 success_full_edit, _, _ = await safe_telegram_call(
                     message.edit_text,
                     text=text,
                     reply_markup=reply_markup,
                     operation_name=f"edit_text (fallback, message_id={message.message_id})"
                 )
                 return success_full_edit
        except Exception as general_error:
            logger.error(f"Общая ошибка при попытке обновить клавиатуру: {general_error}")
            success_fallback, _, _ = await safe_telegram_call(
                message.edit_text,
                text=text,
                reply_markup=reply_markup,
                operation_name=f"edit_text (general fallback, message_id={message.message_id})"
            )
            return success_fallback

async def safe_edit_message_reply_markup(
    message: Message,
    reply_markup=None
) -> bool:
    """
    Безопасное редактирование клавиатуры сообщения.

    Args:
        message: Сообщение для редактирования клавиатуры.
        reply_markup: Новая клавиатура сообщения.

    Returns:
        bool: Успешность редактирования клавиатуры.
    """
    success, _, _ = await safe_telegram_call(
        message.edit_reply_markup,
        reply_markup=reply_markup,
        operation_name=f"edit_reply_markup (message_id={message.message_id})"
    )
    return success

async def send_processing_message(
    bot: Bot,
    chat_id: int,
    language: str = 'ru'
) -> Message:
    """
    Отправка сообщения об обработке
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        language: Язык сообщения
        
    Returns:
        Message: Сообщение об обработке
    """
    try:
        processing_msg = get_message('processing', language)
        processing_message = await bot.send_message(
            chat_id=chat_id,
            text=processing_msg
        )
        return processing_message
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об обработке: {e}")
        raise

async def update_processing_message(
    message: Message,
    new_text: str,
    reply_markup=None
) -> bool:
    """
    Обновление сообщения об обработке
    
    Args:
        message: Сообщение для обновления
        new_text: Новый текст сообщения
        reply_markup: Новая клавиатура сообщения
        
    Returns:
        bool: Успешность обновления
    """
    try:
        await message.edit_text(
            text=new_text,
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения об обработке: {e}")
        return False

async def safe_telegram_call(
    operation: Callable[..., Awaitable[Any]], 
    *args, 
    operation_name: str = "Telegram operation",
    **kwargs
) -> tuple[bool, Optional[Any], Optional[Exception]]:
    """
    Безопасно выполняет асинхронный вызов Telegram API, обрабатывая 
    специфичные ошибки, такие как "message is not modified".

    Args:
        operation: Асинхронная функция для вызова (например, message.edit_text).
        *args: Позиционные аргументы для функции operation.
        operation_name: Имя операции для логирования.
        **kwargs: Именованные аргументы для функции operation.

    Returns:
        tuple[bool, Optional[Any], Optional[Exception]]: 
            Кортеж из (успех, результат или None, исключение или None).
            Успех будет False только для критических ошибок, 
            не включая "message is not modified".
    """
    try:
        result = await operation(*args, **kwargs)
        return True, result, None

    except Exception as e:
        if is_message_not_modified_error(e):
            return True, None, e 
        else:
            logger.error(f"Ошибка при выполнении операции '{operation_name}': {e}")
            return False, None, e

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def truncate_text(text: str, max_length: int = 1000) -> str:
    """
    Обрезка текста до максимальной длины
    
    Args:
        text: Текст для обрезки
        max_length: Максимальная длина текста
        
    Returns:
        str: Обрезанный текст
    """
    try:
        if len(text) > max_length:
            truncated_text = text[:max_length] + "..."
            logger.debug(f"Текст обрезан до {len(truncated_text)} символов")
            return truncated_text
        else:
            return text
    except Exception as e:
        logger.error(f"Ошибка при обрезке текста: {e}")
        return text[:max_length] + "..." if len(text) > max_length else text

def format_message_with_emojis(text: str) -> str:
    """
    Форматирование сообщения с эмодзи
    
    Args:
        text: Текст сообщения
        
    Returns:
        str: Отформатированный текст с эмодзи
    """
    try:
        formatted_text = text.replace("хорошо", "😊 хорошо").replace("плохо", "😞 плохо")
        return formatted_text
    except Exception as e:
        logger.error(f"Ошибка при форматировании сообщения с эмодзи: {e}")
        return text

def escape_html(text: str) -> str:
    """
    Экранирование HTML символов в тексте
    
    Args:
        text: Текст для экранирования
        
    Returns:
        str: Экранированный текст
    """
    try:
        escaped_text = text.replace("&", "&amp;").replace("<", "<").replace(">", ">")
        return escaped_text
    except Exception as e:
        logger.error(f"Ошибка при экранировании HTML символов: {e}")
        return text
    
async def send_message_to_user(
    bot: Bot,
    user: User,
    text: str,
    reply_markup=None,
    disable_notification: bool = False
) -> bool:
    """
    Безопасная отправка сообщения пользователю с обработкой исключений.
    
    Args:
        bot: Экземпляр бота
        user: Пользователь (модель User)
        text: Текст сообщения
        reply_markup: Клавиатура сообщения
        disable_notification: Отключить уведомление
        
    Returns:
        bool: True если сообщение отправлено успешно, False в противном случае
    """
    try:
        if user.is_blocked:
            return False
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=reply_markup,
            disable_notification=disable_notification
        )
        if user.is_blocked:
            user.is_blocked = False
            await user.asave(update_fields=['is_blocked'])
            logger.info(f"Пользователь {user.telegram_id} разблокировал бота")
        return True  
    except TelegramBadRequest as e:
        error_message = str(e).lower()
        if "chat not found" in error_message or "bot was blocked" in error_message:
            if not user.is_blocked:
                user.is_blocked = True
                await user.asave(update_fields=['is_blocked'])
                logger.info(f"Пользователь {user.telegram_id} заблокировал бота")
            return False
        elif "chat unavailable" in error_message:
            logger.warning(f"Чат пользователя {user.telegram_id} недоступен: {e}")
            return False
        else:
            logger.error(f"TelegramBadRequest при отправке сообщения пользователю {user.telegram_id}: {e}")
            return False
    except TelegramAPIError as e:
        logger.error(f"TelegramAPIError при отправке сообщения пользователю {user.telegram_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке сообщения пользователю {user.telegram_id}: {e}")
        return False