import logging

from asgiref.sync import sync_to_async
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Voice
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from bot.states.feedback_states import FeedbackStates
from bot.keyboards import (
    get_back_keyboard,
    get_skip_kb,
    get_add_foto_kb
)
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.admin_utils import send_feedback_to_developer
from messages import get_message
from users.models import User, Feedback

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 20 * 1024 * 1024

@router.message(Command("feedback"))
async def feedback_handler(message: Message, state: FSMContext, user, language: str):
    """Обработчик команды для отправки обратной связи"""
    await message.answer(
        get_message('feedback', language),
        reply_markup=get_back_keyboard(language)
    )
    await state.set_state(FeedbackStates.waiting_message)

@router.message(F.text, FeedbackStates.waiting_message)
async def process_feedback_text(message: Message, state: FSMContext, user, language: str):
    await state.update_data(feedback_text=message.text)
    await message.answer(
        get_message('screenshot_prompt', language),
        reply_markup=get_add_foto_kb(language),
        parse_mode="HTML"
    )
    await state.set_state(FeedbackStates.waiting_photo)

@router.callback_query(F.data == "add_screenshot", FeedbackStates.waiting_photo)
async def add_screenshot_handler(callback: CallbackQuery, state: FSMContext, user, language: str):
    await callback.message.edit_text(
        get_message('screenshot_instructions', language),
        reply_markup=get_skip_kb(language, 'skip_photo'),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "skip_photo", FeedbackStates.waiting_photo)
async def skip_photo_handler(callback: CallbackQuery, state: FSMContext, bot: Bot, user, language: str):
    data = await state.get_data()
    message_text = data.get("feedback_text", "")
    voice_data = data.get("voice_data")
    user = await User.objects.aget(telegram_id=callback.from_user.id)
    await send_feedback_to_developer(
        bot=bot,
        user=user,
        message_text=message_text,
        voice_data=voice_data
    )
    await callback.message.edit_text(
        get_message('feedback_thanks', language),
        parse_mode="HTML",
        reply_markup=get_back_keyboard(language)
    )
    await state.clear()
    await callback.answer()

@router.message(F.voice, FeedbackStates.waiting_message)
async def process_feedback_voice(message: Voice, state: FSMContext, bot: Bot, user, language: str):
    try:
        file = await bot.get_file(message.voice.file_id)
        voice_data = await bot.download(file.file_path)
        
        await state.update_data(
            voice_data=voice_data.read() if hasattr(voice_data, 'read') else voice_data,
            feedback_text="Голосовое сообщение"
        )
        await message.answer(
            get_message('voice_message_accepted', language),
            reply_markup=get_add_foto_kb(),
            parse_mode="HTML"
        )
        await state.set_state(FeedbackStates.waiting_feedback_photo)
    except Exception as e:
        logger.error(f"Error processing voice feedback: {e}")
        await message.answer("❌ Не удалось обработать голосовое сообщение. Попробуйте еще раз.")

@router.message(F.photo, FeedbackStates.waiting_photo)
async def process_feedback_photo(message: Message, state: FSMContext, bot: Bot, user, language: str):
    try:
        logger.info(f"Начало обработки фото от пользователя {message.from_user.id}")
        data = await state.get_data()
        message_text = data.get("feedback_text", "Без текстового сообщения")
        voice_data = data.get("voice_data")
        photo = message.photo[-1]
        if photo.file_size > MAX_FILE_SIZE:
            error_msg = f"Фото слишком большое ({photo.file_size} bytes)"
            logger.warning(error_msg)
            await message.answer(get_message('photo_too_large', language))
            return
        try:
            photo_file = await bot.get_file(photo.file_id)
            logger.info(f"Получен файл фото: {photo_file.file_path}")
        except Exception as e:
            logger.error(f"Ошибка получения файла фото: {str(e)}")
            await message.answer("❌ Ошибка обработки фото. Попробуйте еще раз."
                                 )
            return
        try:
            photo_data = await bot.download_file(photo_file.file_path)
            photo_bytes = photo_data.read() if hasattr(photo_data, 'read') else photo_data
        except Exception as e:
            logger.error(f"Ошибка скачивания фото: {str(e)}")
            await message.answer("❌ Ошибка загрузки фото. Попробуйте другое изображение.")
            return
        try:
            user = await User.objects.aget(telegram_id=message.from_user.id)
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {str(e)}")
            await message.answer("❌ Ошибка идентификации пользователя.")
            return
        try:
            await send_feedback_to_developer(
                bot=bot,
                user=user,
                message_text=message_text,
                voice_data=voice_data,
                photo_data=photo_bytes
            )
            logger.info("Feedback успешно отправлен разработчику")
        except Exception as e:
            logger.error(f"Ошибка отправки feedback: {str(e)}")
            await message.answer("❌ Ошибка отправки сообщения разработчику.")
            return
        try:
            await message.answer(
                get_message('feedback_thanks', language),
                reply_markup=get_back_keyboard(language)
            )
        except Exception as e:
            logger.error(f"Ошибка отправки подтверждения: {str(e)}")
        await state.clear()
    except Exception as e:
        logger.error(f"Критическая ошибка в обработчике фото: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз.",
            reply_markup=get_back_keyboard(language)
        )

@router.callback_query(F.data.startswith("reply_feedback_"))
async def start_reply_to_feedback(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Начало ответа на обратную связь"""
    try:
        feedback_id = int(callback.data.split('_')[-1])
        feedback = await Feedback.aget_by_id(feedback_id)
        get_username = lambda: feedback.user.username or f"user_{feedback.user.telegram_id}"
        username = await sync_to_async(get_username)()
        get_date = lambda: feedback.created_at.strftime('%d.%m.%Y %H:%M')
        created_at = await sync_to_async(get_date)()
        await state.update_data(
            feedback_id=feedback_id,
            user_id=feedback.user.telegram_id,
            original_message_id=callback.message.message_id
        )
        await callback.message.edit_text(
            f"✍️ Ответ на обращение #{feedback_id} от {username} ({created_at}):\n\n"
            f"Сообщение:\n{feedback.message}\n\n"
            "Введите ваш ответ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_reply")]
            ])
        )
        await state.set_state("waiting_feedback_reply")
        await callback.answer()
    except Exception as e:
        logger.error(f"Error starting feedback reply: {e}")
        await callback.answer("❌ Ошибка при обработке обращения", show_alert=True)

@router.message(StateFilter("waiting_feedback_reply"))
async def process_feedback_reply(message: Message, state: FSMContext, bot: Bot, user, language: str):
    """Обработка ответа на обратную связь"""
    from asgiref.sync import sync_to_async
    data = await state.get_data()
    feedback_id = data.get('feedback_id')
    user_id = data.get('user_id')
    original_message_id = data.get('original_message_id')
    if not all([feedback_id, user_id, original_message_id]):
        await message.answer("❌ Ошибка: неполные данные обращения")
        await state.clear()
        return
    try:
        get_feedback = lambda: Feedback.objects.get(id=feedback_id)
        feedback = await sync_to_async(get_feedback)()
        await bot.send_message(
            chat_id=user_id,
            text=get_message(
                'support_response',
                language,
                feedback_id=feedback_id,
                message_text=message.text
            )
        )
        def update_feedback():
            feedback.admin_response = message.text
            feedback.status = 'replied'
            feedback.save()
        await sync_to_async(update_feedback)()
        get_username = lambda: feedback.user.username or f"user_{feedback.user.telegram_id}"
        username = await sync_to_async(get_username)()
        created_at = await sync_to_async(lambda: feedback.created_at.strftime('%d.%m.%Y %H:%M'))()
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=original_message_id,
            text=f"✅ Ответ отправлен на обращение #{feedback_id}\n"
                 f"Пользователь: {username}\n"
                 f"Дата: {created_at}\n\n"
                 f"Оригинал:\n{feedback.message}\n\n"
                 f"Ответ:\n{message.text}",
            reply_markup=None
        )
        await message.answer(f"✅ Ответ на обращение #{feedback_id} отправлен!")
    except Exception as e:
        logger.error(f"Error processing feedback reply: {e}")
        await message.answer("❌ Не удалось отправить ответ")
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_reply", StateFilter("waiting_feedback_reply"))
async def cancel_feedback_reply(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Отмена ответа на обратную связь"""
    await callback.message.edit_text("❌ Ответ отменён")
    await state.clear()
    await callback.answer()

@router.message(Command("feedbacks"))
async def list_feedbacks(message: Message, user, language: str):
    """Просмотр необработанных обращений (только для разработчика)"""
    try:
        feedbacks = await sync_to_async(list)(
            Feedback.objects.filter(status='new')
            .select_related('user')
            .order_by('-created_at')[:20]
        )
        if not feedbacks:
            await message.answer("🎉 Нет новых необработанных обращений!")
            return
        messages = []
        for feedback in feedbacks:
            status_icon = "🆕"
            username = feedback.user.username or f"user_{feedback.user.telegram_id}"
            created_at = feedback.created_at.strftime('%d.%m.%Y %H:%M')
            msg = (
                f"{status_icon} #{feedback.id} от {username}\n"
                f"Дата: {created_at}\n"
                f"Тип: {'голосовое' if feedback.is_voice else 'текстовое'}\n"
                f"Сообщение: {feedback.message[:100]}{'...' if len(feedback.message) > 100 else ''}"
            )
            messages.append(msg)
        for i in range(0, len(messages), 5):
            chunk = messages[i:i+5]
            await message.answer(
                "📬 Список необработанных обращений:\n\n" + "\n\n".join(chunk),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_feedbacks")]
                ])
            )
    except Exception as e:
        logger.error(f"Error listing feedbacks: {e}")
        await message.answer("❌ Ошибка при получении списка обращений")