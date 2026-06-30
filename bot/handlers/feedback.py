# bot/handlers/feedback.py

import logging

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
from bot.utils.admin_utils import send_feedback_to_developer
from core.services.feedback_service import feedback_service
from core.services.base_service import BaseService
from messages import get_message

logger = logging.getLogger(__name__)
router = Router()


# --- СТАРЫЕ ПОЛЬЗОВАТЕЛЬСКИЕ ОБРАБОТЧИКИ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ) ---

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
    db_user = await BaseService.get_user_by_telegram_id(callback.from_user.id)
    if not db_user:
        await callback.message.edit_text(get_message('error_generic', language))
        await state.clear()
        await callback.answer()
        return
    await send_feedback_to_developer(
        bot=bot,
        user=db_user,
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
        await state.set_state(FeedbackStates.waiting_photo)
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
        photo_obj = message.photo[-1]
        photo_file_id = photo_obj.file_id

        if not feedback_service.validate_photo_size(photo_obj.file_size):
            logger.warning(f"Фото слишком большое ({photo_obj.file_size} bytes)")
            await message.answer(get_message('photo_too_large', language))
            return

        try:
            photo_file = await bot.get_file(photo_obj.file_id)
            logger.info(f"Получен файл фото: {photo_file.file_path}")
        except Exception as e:
            logger.error(f"Ошибка получения файла фото: {str(e)}")
            await message.answer("❌ Ошибка обработки фото. Попробуйте еще раз.")
            return

        try:
            photo_data = await bot.download_file(photo_file.file_path)
            photo_bytes = photo_data.read() if hasattr(photo_data, 'read') else photo_data
        except Exception as e:
            logger.error(f"Ошибка скачивания фото: {str(e)}")
            await message.answer("❌ Ошибка загрузки фото. Попробуйте другое изображение.")
            return

        try:
            user = await BaseService.get_user_by_telegram_id(message.from_user.id)
            if not user:
                raise ValueError("User not found by telegram_id")
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
                photo_data=photo_bytes,
                photo_file_id=photo_file_id
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

# --- КОНЕЦ СТАРЫХ ОБРАБОТЧИКОВ ---

# --- НОВАЯ АДМИНИСТРАТИВНАЯ ЛОГИКА (БЕЗ StateFilter) ---

@router.message(Command("feedbacks"))
async def list_feedbacks(message: Message, user, language: str, state: FSMContext):
    """Просмотр необработанных обращений (только для разработчика) с пагинацией и кнопкой ответа."""
    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался выполнить команду /feedbacks, но не является разработчиком.")
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        feedbacks = await feedback_service.get_unprocessed_feedbacks()

        if not feedbacks:
            await message.answer("🎉 Нет новых необработанных обращений!")
            return

        feedback_ids = [f.id for f in feedbacks]
        current_index = 0

        await state.update_data(
            admin_feedback_list=feedback_ids,
            admin_feedback_current_index=current_index
        )
        await state.set_state("admin_browsing_feedbacks")

        await _show_feedback_at_index(message, state, current_index, language)

    except Exception as e:
        logger.error(f"Error listing feedbacks: {e}")
        await message.answer("❌ Ошибка при получении списка обращений")
        await state.clear()


@router.callback_query(F.data == "feedback_next")
async def feedback_next(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    if current_state_str != "admin_browsing_feedbacks":
        await callback.answer("❌ Некорректное состояние для этого действия.", show_alert=True)
        return

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался выполнить навигацию по feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    data = await state.get_data()
    current_index = data.get('admin_feedback_current_index', 0)
    feedback_ids = data.get('admin_feedback_list', [])
    new_index = current_index + 1
    if new_index < len(feedback_ids):
        await state.update_data(admin_feedback_current_index=new_index)
        await _show_feedback_at_index(callback, state, new_index, language)
    else:
        await callback.answer("Больше обращений нет.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "feedback_prev")
async def feedback_prev(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    if current_state_str != "admin_browsing_feedbacks":
        await callback.answer("❌ Некорректное состояние для этого действия.", show_alert=True)
        return

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался выполнить навигацию по feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    data = await state.get_data()
    current_index = data.get('admin_feedback_current_index', 0)
    feedback_ids = data.get('admin_feedback_list', [])
    new_index = current_index - 1
    if new_index >= 0:
        await state.update_data(admin_feedback_current_index=new_index)
        await _show_feedback_at_index(callback, state, new_index, language)
    else:
        await callback.answer("Это первое обращение.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "refresh_feedbacks_list")
async def refresh_feedbacks_list(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    if current_state_str != "admin_browsing_feedbacks":
        await callback.answer("❌ Некорректное состояние для этого действия.", show_alert=True)
        return

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался обновить список feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    try:
        feedbacks = await feedback_service.get_unprocessed_feedbacks()

        if not feedbacks:
            await callback.message.edit_text("🎉 Нет новых необработанных обращений!")
            await state.clear()
            await callback.answer()
            return

        feedback_ids = [f.id for f in feedbacks]
        current_index = 0

        await state.update_data(
            admin_feedback_list=feedback_ids,
            admin_feedback_current_index=current_index
        )

        await _show_feedback_at_index(callback, state, current_index, language)
        await callback.answer("Список обновлён.")
    except Exception as e:
        logger.error(f"Error refreshing feedback list: {e}")
        await callback.message.edit_text("❌ Ошибка при обновлении списка обращений")
        await state.clear()
        await callback.answer()


@router.callback_query(F.data == "close_feedback_list")
async def close_feedback_list(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    if current_state_str != "admin_browsing_feedbacks":
        await callback.answer("❌ Некорректное состояние для этого действия.", show_alert=True)
        return

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался закрыть список feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    await callback.message.edit_text("Список обращений закрыт.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("reply_feedback_"))
async def start_reply_to_feedback_admin(callback: CallbackQuery, state: FSMContext, user, language: str):
    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался начать ответ на feedback, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    try:
        feedback_id = int(callback.data.split('_')[-1])
        logger.debug(f"[start_reply] Извлечен feedback_id: {feedback_id}")

        can_reply, feedback = await feedback_service.can_reply_to_feedback(feedback_id)

        if not feedback:
            logger.warning(f"[start_reply] Обращение с ID {feedback_id} не найдено или не новый статус.")
            await callback.answer("❌ Обращение не найдено.", show_alert=True)
            return
        if not can_reply:
            logger.warning(f"[start_reply] Обращение с ID {feedback_id} уже не в статусе 'new'.")
            await callback.answer("❌ Обращение уже обработано.", show_alert=True)
            return

        await state.clear()
        logger.debug(f"[start_reply] Состояние очищено. Устанавливаем 'admin_waiting_feedback_reply'.")
        await state.set_state("admin_waiting_feedback_reply")
        await state.update_data(replying_to_feedback_id=feedback_id)
        logger.debug(f"[start_reply] Новое состояние установлено: {await state.get_state()}, данные: {{'replying_to_feedback_id': {feedback_id}}}")

        display_data = await feedback_service.format_feedback_for_display(feedback)
        username = display_data.username
        created_at = display_data.created_at

        reply_prompt = get_message(
            'reply_feedback_prompt',
            language,
            feedback_id=feedback_id,
            username=username,
            created_at=created_at,
            message_text=feedback.message
        )

        await callback.message.answer(
            reply_prompt,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=get_message('btn_cancel_reply', language),
                    callback_data="cancel_reply"
                )]
            ])
        )
        await callback.answer()

    except ValueError:
        logger.error(f"Invalid feedback ID in callback data: {callback.data}")
        await callback.answer("❌ Некорректный ID обращения.", show_alert=True)
    except Exception as e:
        logger.error(f"Error starting feedback reply (admin): {e}")
        await callback.answer(
            get_message('error_feedback_reply_start', language),
            show_alert=True
        )


@router.message(StateFilter("admin_waiting_feedback_reply"), F.text)
async def process_feedback_reply_admin(message: Message, state: FSMContext, bot: Bot, user, language: str):
    """Обрабатывает текстовый ответ администратора на обращение."""
    logger.debug(f"[process_reply] Обработка ответа в состоянии 'admin_waiting_feedback_reply'")

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался отправить ответ на feedback, но не является разработчиком.")
        await message.answer("❌ У вас нет прав для выполнения этого действия.")
        await state.clear()
        return

    data = await state.get_data()
    feedback_id = data.get('replying_to_feedback_id')
    if not feedback_id:
        logger.error(f"[process_reply] feedback_id не найден в данных состояния: {data}")
        await message.answer("❌ Ошибка: ID обращения не найден.")
        await state.clear()
        return

    try:
        can_reply, feedback = await feedback_service.can_reply_to_feedback(feedback_id)

        if not feedback:
            await message.answer("❌ Обращение больше не существует.")
            await state.clear()
            return
        if not can_reply:
            await message.answer("❌ Обращение уже обработано кем-то другим.")
            await state.clear()
            return

        await bot.send_message(
            chat_id=feedback.user.telegram_id,
            text=get_message(
                'support_response',
                language,
                feedback_id=feedback_id,
                message_text=message.text
            )
        )

        await feedback_service.reply_to_feedback(feedback_id, message.text)

        display_data = await feedback_service.format_feedback_for_display(feedback)
        username = display_data.username

        await message.answer(f"✅ Ответ на обращение #{feedback_id} отправлен пользователю {username}!")
    except Exception as e:
        logger.error(f"Error processing feedback reply (admin): {e}")
        await message.answer("❌ Не удалось отправить ответ")
    finally:
        await state.clear()


@router.callback_query(F.data == "cancel_reply")
async def cancel_feedback_reply_admin(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    if current_state_str != "admin_waiting_feedback_reply":
        await callback.answer("❌ Некорректное состояние для отмены.", show_alert=True)
        return

    if not feedback_service.is_developer(user.telegram_id):
        logger.warning(f"Пользователь {user.telegram_id} попытался отменить ответ на feedback, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    await callback.message.edit_text("❌ Ответ отменён")
    await state.clear()
    await callback.answer()


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---

async def _show_feedback_at_index(message_or_callback, state: FSMContext, index: int, language: str):
    """Вспомогательная функция для отображения обращения по индексу."""
    data = await state.get_data()
    feedback_ids = data.get('admin_feedback_list', [])
    if not feedback_ids or index < 0 or index >= len(feedback_ids):
        await (message_or_callback.message.edit_text if hasattr(message_or_callback, 'message') else message_or_callback.answer)("❌ Обращение не найдено.")
        await state.clear()
        return

    feedback_id = feedback_ids[index]
    feedback = await feedback_service.get_feedback_by_id(feedback_id)
    if not feedback:
        logger.error(f"Обращение с ID {feedback_id} не найдено при отображении.")
        await (message_or_callback.message.edit_text if hasattr(message_or_callback, 'message') else message_or_callback.answer)(f"❌ Обращение с ID {feedback_id} больше не существует.")
        feedback_ids.remove(feedback_id)
        await state.update_data(admin_feedback_list=feedback_ids)
        if not feedback_ids:
            await state.clear()
            await (message_or_callback.message.answer if hasattr(message_or_callback, 'message') else message_or_callback.answer)("Список обращений пуст.")
            return
        if index >= len(feedback_ids):
            index = len(feedback_ids) - 1
        await state.update_data(admin_feedback_current_index=index)
        await _show_feedback_at_index(message_or_callback, state, index, language)
        return

    display_data = await feedback_service.format_feedback_for_display(feedback)
    description_text = feedback_service.build_description_text(display_data)

    # Подготовим клавиатуру
    keyboard_buttons = []
    nav_buttons = []
    nav_buttons.append(
        InlineKeyboardButton(
            text='Ответить',
            callback_data=f"reply_feedback_{feedback.id}"
        )
    )

    if index > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущее",
                callback_data="feedback_prev"
            )
        )
    if index < len(feedback_ids) - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Следующее ➡️",
                callback_data="feedback_next"
            )
        )

    keyboard_buttons.append(nav_buttons)
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔄 Обновить список",
            callback_data="refresh_feedbacks_list"
        )
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data="close_feedback_list"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # --- ОТПРАВКА СООБЩЕНИЯ С ФОТО ИЛИ БЕЗ ---
    bot = message_or_callback.bot

    if hasattr(message_or_callback, 'message'):
        target_chat_id = message_or_callback.message.chat.id
        target_message_id = message_or_callback.message.message_id
    else:
        target_chat_id = message_or_callback.chat.id
        target_message_id = None

    try:
        if feedback.is_photo and hasattr(feedback, 'photo_file_id') and feedback.photo_file_id:
            await bot.send_photo(
                chat_id=target_chat_id,
                photo=feedback.photo_file_id,
                caption=description_text,
                reply_markup=keyboard
            )
            if target_message_id:
                 try:
                     await bot.delete_message(chat_id=target_chat_id, message_id=target_message_id)
                 except Exception as del_e:
                     logger.warning(f"Не удалось удалить старое сообщение при показе фото: {del_e}")
                     pass
        else:
            if target_message_id:
                await bot.edit_message_text(
                    chat_id=target_chat_id,
                    message_id=target_message_id,
                    text=description_text,
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    chat_id=target_chat_id,
                    text=description_text,
                    reply_markup=keyboard
                )
    except Exception as send_photo_e:
        logger.error(f"Ошибка при отправке фото или редактировании сообщения: {send_photo_e}")
        if target_message_id:
            await bot.edit_message_text(
                chat_id=target_chat_id,
                message_id=target_message_id,
                text=description_text,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=target_chat_id,
                text=description_text,
                reply_markup=keyboard
            )
