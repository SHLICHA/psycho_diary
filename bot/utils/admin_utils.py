import asyncio
import logging

from aiogram import Bot
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
    photo_data: bytes = None
):
    """Отправляет обратную связь разработчику и сохраняет в БД"""
    from asgiref.sync import sync_to_async
    try:
        is_voice = voice_data is not None
        is_photo = photo_data is not None
        feedback = await sync_to_async(Feedback.objects.create)(
            user=user,
            message=message_text or ("Голосовое сообщение" if is_voice else "Фото" if is_photo else "Сообщение"),
            is_voice=is_voice,
            is_photo=is_photo,
            status='new'
        )
        username = await sync_to_async(lambda: user.username or f"user_{user.telegram_id}")()
        created_at = await sync_to_async(lambda: feedback.created_at.strftime('%d.%m.%Y %H:%M'))()
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_feedback_{feedback.id}")]
        ])
        if is_photo:
            caption = (f"📷 Обращение #{feedback.id} от {username}\n"
                      f"Дата: {created_at}\n\n"
                      f"{message_text or 'Фото без описания'}")
            
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
                    caption=caption[:1024],
                    reply_markup=reply_markup
                ) 
            if is_voice:
                await bot.send_voice(
                    chat_id=settings.DEVELOPER_CHAT_ID,
                    voice=BufferedInputFile(voice_data, filename="voice.ogg"),
                    caption=f"🎤 Голосовое сообщение к обращению #{feedback.id}",
                    reply_markup=reply_markup
                )
        elif is_voice:
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