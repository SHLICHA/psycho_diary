"""
Утилиты для работы с сообщениями бота
"""

import logging
from typing import Optional, Union
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
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
    logger.info(f"Редактирование или отправка сообщения в чат {chat_id}")
    logger.info(f"Длина текста: {len(text)} символов")
    
    try:
        if message_to_edit:
            # Проверяем, отличается ли новый текст от текущего
            if message_to_edit.text != text:
                logger.info("Текст отличается, редактируем сообщение")
                edited_message = await message_to_edit.edit_text(
                    text=text,
                    reply_markup=reply_markup
                )
                logger.info(f"Сообщение отредактировано, message_id: {edited_message.message_id}")
                return edited_message
            else:
                logger.info("Текст не изменился, обновляем только клавиатуру")
                try:
                    edited_message = await message_to_edit.edit_reply_markup(
                        reply_markup=reply_markup
                    )
                    logger.info("Клавиатура обновлена")
                    return edited_message
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    # Если не удалось обновить клавиатуру, отправляем новое сообщение
                    new_message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                    logger.info(f"Новое сообщение отправлено, message_id: {new_message.message_id}")
                    return new_message
        else:
            logger.info("Нет сообщения для редактирования, отправляем новое")
            new_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )
            logger.info(f"Новое сообщение отправлено, message_id: {new_message.message_id}")
            return new_message
            
    except Exception as e:
        logger.error(f"Ошибка при редактировании/отправке сообщения: {e}")
        # В случае ошибки отправляем новое сообщение
        try:
            new_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )
            logger.info(f"Резервное сообщение отправлено, message_id: {new_message.message_id}")
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
    Безопасное редактирование текста сообщения
    
    Args:
        message: Сообщение для редактирования
        text: Новый текст сообщения
        reply_markup: Новая клавиатура сообщения
        
    Returns:
        bool: Успешность редактирования
    """
    logger.info(f"Безопасное редактирование текста сообщения {message.message_id}")
    logger.info(f"Длина нового текста: {len(text)} символов")
    
    try:
        # Проверяем, отличается ли новый текст от текущего
        if message.text != text:
            logger.info("Текст отличается, редактируем сообщение")
            await message.edit_text(
                text=text,
                reply_markup=reply_markup
            )
            logger.info("Сообщение успешно отредактировано")
            return True
        else:
            logger.info("Текст не изменился, обновляем только клавиатуру")
            try:
                await message.edit_reply_markup(
                    reply_markup=reply_markup
                )
                logger.info("Клавиатура успешно обновлена")
                return True
            except Exception as keyboard_error:
                logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                # Если не удалось обновить клавиатуру, отправляем новое сообщение
                await message.edit_text(
                    text=text,
                    reply_markup=reply_markup
                )
                logger.info("Сообщение отредактировано с новой клавиатурой")
                return True
                
    except Exception as e:
        logger.error(f"Ошибка при безопасном редактировании сообщения: {e}")
        return False

async def safe_edit_message_reply_markup(
    message: Message,
    reply_markup=None
) -> bool:
    """
    Безопасное редактирование клавиатуры сообщения
    
    Args:
        message: Сообщение для редактирования клавиатуры
        reply_markup: Новая клавиатура сообщения
        
    Returns:
        bool: Успешность редактирования клавиатуры
    """
    logger.info(f"Безопасное редактирование клавиатуры сообщения {message.message_id}")
    
    try:
        await message.edit_reply_markup(
            reply_markup=reply_markup
        )
        logger.info("Клавиатура успешно отредактирована")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при редактировании клавиатуры: {e}")
        return False

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
    logger.info(f"Отправка сообщения об обработке в чат {chat_id}")
    
    try:
        processing_msg = get_message('processing', language)
        processing_message = await bot.send_message(
            chat_id=chat_id,
            text=processing_msg
        )
        logger.info(f"Сообщение об обработке отправлено, message_id: {processing_message.message_id}")
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
    logger.info(f"Обновление сообщения об обработке {message.message_id}")
    logger.info(f"Длина нового текста: {len(new_text)} символов")
    
    try:
        await message.edit_text(
            text=new_text,
            reply_markup=reply_markup
        )
        logger.info("Сообщение об обработке успешно обновлено")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения об обработке: {e}")
        return False

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
    logger.info(f"Обрезка текста длиной {len(text)} символов до {max_length} символов")
    
    try:
        if len(text) > max_length:
            truncated_text = text[:max_length] + "..."
            logger.info(f"Текст обрезан до {len(truncated_text)} символов")
            return truncated_text
        else:
            logger.info("Текст не требует обрезки")
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
    logger.info(f"Форматирование сообщения с эмодзи длиной {len(text)} символов")
    
    try:
        # Простое форматирование с эмодзи (заглушка)
        formatted_text = text.replace("хорошо", "😊 хорошо").replace("плохо", "😞 плохо")
        logger.info(f"Сообщение отформатировано с эмодзи")
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
    logger.info(f"Экранирование HTML символов в тексте длиной {len(text)} символов")
    
    try:
        escaped_text = text.replace("&", "&amp;").replace("<", "<").replace(">", ">")
        logger.info("HTML символы экранированы")
        return escaped_text
        
    except Exception as e:
        logger.error(f"Ошибка при экранировании HTML символов: {e}")
        return text