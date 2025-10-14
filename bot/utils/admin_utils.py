import asyncio
import logging

from io import BytesIO
from aiogram import Bot
from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, Voice
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from typing import Optional

from users.models import Feedback, User

logger = logging.getLogger(__name__)

async def send_feedback_to_developer(
    bot: Bot,
    user: User,
    message_text: str = None,
    voice_data: bytes = None,
    photo_data: bytes = None,
    photo_file_id: str = None # <-- Новый аргумент
):
    """Отправляет обратную связь разработчику и сохраняет в БД"""

    logger = logging.getLogger(__name__) # <-- Инициализируем логгер внутри функции или используем глобальный

    try:
        is_voice = voice_data is not None
        is_photo = photo_data is not None or photo_file_id is not None # Теперь is_photo может быть True и без photo_data
        feedback_message = message_text or ("Голосовое сообщение" if is_voice else "Фото" if is_photo else "Сообщение")

        # --- Создание Feedback с photo_file_id ---
        feedback = await sync_to_async(Feedback.objects.create)(
            user=user,
            message=feedback_message,
            is_voice=is_voice,
            is_photo=is_photo,
            # Добавляем новое поле, если оно было передано
            photo_file_id=photo_file_id if photo_file_id else None,
            status='new'
        )
        # --- Конец создания Feedback ---

        username = await sync_to_async(lambda: user.username or f"user_{user.telegram_id}")()
        created_at = await sync_to_async(lambda: feedback.created_at.strftime('%d.%m.%Y %H:%M'))()
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_feedback_{feedback.id}")]
        ])
        if is_photo:
            caption = (f"📷 Обращение #{feedback.id} от {username}\n"
                      f"Дата: {created_at}\n\n"
                      f"{message_text or 'Фото без описания'}")

            # --- Отправка фото ---
            # Проверяем, есть ли photo_data (байты) или photo_file_id
            if photo_data:
                # Отправляем фото как документ или фото, используя байты
                try:
                    await bot.send_photo(
                        chat_id=settings.DEVELOPER_CHAT_ID,
                        photo=BufferedInputFile(photo_data, filename="photo.jpg"),
                        caption=caption,
                        reply_markup=reply_markup
                    )
                except Exception as photo_error:
                    logger.error(f"Error sending photo: {photo_error}")
                    await bot.send_document(
                        chat_id=settings.DEVELOPER_CHAT_ID,
                        document=BufferedInputFile(photo_data, filename=f"photo_{feedback.id}.jpg"),
                        caption=caption[:1024], # Telegram ограничивает длину caption
                        reply_markup=reply_markup
                    )
            elif photo_file_id:
                # Отправляем фото, используя file_id (копируем)
                try:
                    await bot.copy_message(
                        chat_id=settings.DEVELOPER_CHAT_ID,
                        from_chat_id=user.telegram_id, # Или откуда пришло фото
                        message_id=photo_file_id, # Это не message_id, а file_id медиа
                        caption=caption,
                        reply_markup=reply_markup
                    )
                    await bot.send_photo(
                        chat_id=settings.DEVELOPER_CHAT_ID,
                        photo=photo_file_id,
                        caption=caption,
                        reply_markup=reply_markup
                    )
                except Exception as photo_by_id_error:
                    logger.error(f"Error sending photo by file_id: {photo_by_id_error}")
                    # Если не получилось отправить по file_id, и у нас есть байты, пробуем через них
                    if photo_data:
                        try:
                            await bot.send_photo(
                                chat_id=settings.DEVELOPER_CHAT_ID,
                                photo=BufferedInputFile(photo_data, filename="photo.jpg"),
                                caption=caption,
                                reply_markup=reply_markup
                            )
                        except Exception as photo_bytes_error:
                            logger.error(f"Error sending photo by bytes after file_id failed: {photo_bytes_error}")
                            await bot.send_document(
                                chat_id=settings.DEVELOPER_CHAT_ID,
                                document=BufferedInputFile(photo_data, filename=f"photo_{feedback.id}.jpg"),
                                caption=caption[:1024],
                                reply_markup=reply_markup
                            )
                    else:
                        # Если байтов нет, и отправка по file_id не удалась, ошибка
                        logger.error(f"Could not send photo for feedback {feedback.id} by file_id or bytes.")
            # --- Конец отправки фото ---

            if is_voice and voice_data:
                await bot.send_voice(
                    chat_id=settings.DEVELOPER_CHAT_ID,
                    voice=BufferedInputFile(voice_data, filename="voice.ogg"),
                    caption=f"🎤 Голосовое сообщение к обращению #{feedback.id}",
                    reply_markup=reply_markup
                )
        elif is_voice and voice_data:
            await bot.send_voice(
                chat_id=settings.DEVELOPER_CHAT_ID,
                voice=BufferedInputFile(voice_data, filename="voice.ogg"),
                caption=(f"🎤 Обращение #{feedback.id} от {username}\n"
                        f"Дата: {created_at}\n\n"
                        f"{message_text or 'Голосовое сообщение'}"),
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=settings.DEVELOPER_CHAT_ID,
                text=(f"✉️ Обращение #{feedback.id} от {username}\n"
                     f"Дата: {created_at}\n\n"
                     f"{message_text}"),
                reply_markup=reply_markup
            )
        logger.info(f"Feedback #{feedback.id} sent from {user.telegram_id}")
        return feedback
    except Exception as e:
        logger.error(f"Feedback sending error: {e}")
        raise