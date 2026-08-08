# bot/handlers/feedback.py
"""Feedback handlers (transport-only)."""

import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
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
from messages import get_message

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("feedback"))
async def feedback_handler(message: Message, state: FSMContext, user, language: str):
    """Команда /feedback — запрос текста обращения."""
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

    result = await feedback_service.submit_user_feedback_use_case(
        user=user,
        message_text=message_text,
        language=language,
        voice_data=voice_data,
    )
    if not result.get('success'):
        await callback.message.edit_text(result.get('thanks_text') or get_message('error_generic', language))
        if result.get('clear_state'):
            await state.clear()
        await callback.answer()
        return

    try:
        notify_payload = result['notify_payload']
        await send_feedback_to_developer(
            bot=bot,
            feedback=result['feedback'],
            user=notify_payload['user'],
            message_text=notify_payload['message_text'],
            voice_data=notify_payload.get('voice_data'),
            photo_data=notify_payload.get('photo_data'),
            photo_file_id=notify_payload.get('photo_file_id'),
        )
    except Exception as e:
        logger.error(f"Ошибка отправки feedback: {e}")
        await callback.message.edit_text(get_message('error_generic', language))
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text(
        result['thanks_text'],
        parse_mode="HTML",
        reply_markup=get_back_keyboard(language)
    )
    await state.clear()
    await callback.answer()


@router.message(F.voice, FeedbackStates.waiting_message)
async def process_feedback_voice(message: Message, state: FSMContext, bot: Bot, user, language: str):
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
        data = await state.get_data()
        message_text = data.get("feedback_text", "Без текстового сообщения")
        voice_data = data.get("voice_data")
        photo_obj = message.photo[-1]
        photo_file_id = photo_obj.file_id

        try:
            photo_file = await bot.get_file(photo_obj.file_id)
        except Exception as e:
            logger.error(f"[feedback.photo] get_file failed user_id={user.id}: {e}")
            await message.answer("❌ Ошибка обработки фото. Попробуйте еще раз.")
            return

        try:
            photo_data = await bot.download_file(photo_file.file_path)
            photo_bytes = photo_data.read() if hasattr(photo_data, 'read') else photo_data
        except Exception as e:
            logger.error(f"[feedback.photo] download failed user_id={user.id}: {e}")
            await message.answer("❌ Ошибка загрузки фото. Попробуйте другое изображение.")
            return

        result = await feedback_service.submit_user_feedback_use_case(
            user=user,
            message_text=message_text,
            language=language,
            voice_data=voice_data,
            photo_bytes=photo_bytes,
            photo_file_id=photo_file_id,
            photo_file_size=photo_obj.file_size,
        )
        if result.get('mode') == 'photo_too_large':
            await message.answer(result['thanks_text'])
            return
        if not result.get('success'):
            await message.answer(result.get('thanks_text') or get_message('error_generic', language))
            if result.get('clear_state'):
                await state.clear()
            return

        try:
            notify_payload = result['notify_payload']
            await send_feedback_to_developer(
                bot=bot,
                feedback=result['feedback'],
                user=notify_payload['user'],
                message_text=notify_payload['message_text'],
                voice_data=notify_payload.get('voice_data'),
                photo_data=notify_payload.get('photo_data'),
                photo_file_id=notify_payload.get('photo_file_id'),
            )
            logger.debug(f"[feedback.photo] notified developer user_id={user.id}")
        except Exception as e:
            logger.error(f"[feedback.photo] notify developer failed user_id={user.id}: {e}")
            await message.answer("❌ Ошибка отправки сообщения разработчику.")
            return

        try:
            await message.answer(
                result['thanks_text'],
                reply_markup=get_back_keyboard(language)
            )
        except Exception as e:
            logger.error(f"[feedback.photo] thanks send failed user_id={user.id}: {e}")
        await state.clear()
    except Exception as e:
        logger.error(f"[feedback.photo] failed user_id={user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз.",
            reply_markup=get_back_keyboard(language)
        )


@router.message(Command("feedbacks"))
async def list_feedbacks(message: Message, user, language: str, state: FSMContext):
    """Список необработанных обращений (developer-only)."""
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
    nav = feedback_service.compute_admin_feedback_nav_index(
        feedback_ids, current_index, 'next'
    )
    if nav.get('success'):
        await state.update_data(admin_feedback_current_index=nav['new_index'])
        await _show_feedback_at_index(callback, state, nav['new_index'], language)
    else:
        await callback.answer(nav.get('alert_text') or 'Больше обращений нет.', show_alert=True)
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
    nav = feedback_service.compute_admin_feedback_nav_index(
        feedback_ids, current_index, 'prev'
    )
    if nav.get('success'):
        await state.update_data(admin_feedback_current_index=nav['new_index'])
        await _show_feedback_at_index(callback, state, nav['new_index'], language)
    else:
        await callback.answer(nav.get('alert_text') or 'Это первое обращение.', show_alert=True)
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
        view = await feedback_service.build_admin_reply_prompt_view(feedback_id, language)
        if not view.get('success'):
            logger.warning(
                f"[start_reply] Нельзя ответить на #{feedback_id}: {view.get('mode')}"
            )
            await callback.answer(view.get('alert_text') or '❌ Ошибка.', show_alert=True)
            return

        await state.clear()
        await state.set_state("admin_waiting_feedback_reply")
        await state.update_data(replying_to_feedback_id=feedback_id)
        await callback.message.answer(view['text'], reply_markup=view['reply_markup'])
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
        result = await feedback_service.process_admin_feedback_reply_use_case(
            admin_user=user,
            feedback_id=feedback_id,
            reply_text=message.text,
            language=language,
        )

        if not result.get('success'):
            await message.answer(result.get('admin_ack_text') or '❌ Не удалось отправить ответ')
            if result.get('clear_state'):
                await state.clear()
            return

        await bot.send_message(
            chat_id=result['notify_chat_id'],
            text=result['notify_text'],
        )
        if result.get('persist_reply'):
            await feedback_service.reply_to_feedback(
                result['feedback_id'], result['reply_text']
            )
        await message.answer(result['admin_ack_text'])
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


async def _show_feedback_at_index(message_or_callback, state: FSMContext, index: int, language: str):
    """Transport: service payload → send/edit feedback item."""
    data = await state.get_data()
    feedback_ids = data.get('admin_feedback_list', [])
    view = await feedback_service.build_admin_feedback_item_view(feedback_ids, index)

    await state.update_data(
        admin_feedback_list=view.get('feedback_ids', []),
        admin_feedback_current_index=view.get('index', 0),
    )
    if view.get('clear_state'):
        await state.clear()

    bot = message_or_callback.bot
    if hasattr(message_or_callback, 'message'):
        target_chat_id = message_or_callback.message.chat.id
        target_message_id = message_or_callback.message.message_id
    else:
        target_chat_id = message_or_callback.chat.id
        target_message_id = None

    async def _send_text(text: str, reply_markup=None):
        if target_message_id:
            await bot.edit_message_text(
                chat_id=target_chat_id,
                message_id=target_message_id,
                text=text,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id=target_chat_id,
                text=text,
                reply_markup=reply_markup,
            )

    if view.get('mode') != 'item':
        await _send_text(view.get('text') or '❌ Обращение не найдено.')
        if view.get('mode') == 'empty' and view.get('empty_text'):
            await bot.send_message(chat_id=target_chat_id, text=view['empty_text'])
        return

    description_text = view['text']
    keyboard = view['reply_markup']
    try:
        if view.get('has_photo') and view.get('photo_file_id'):
            await bot.send_photo(
                chat_id=target_chat_id,
                photo=view['photo_file_id'],
                caption=description_text,
                reply_markup=keyboard,
            )
            if target_message_id:
                try:
                    await bot.delete_message(chat_id=target_chat_id, message_id=target_message_id)
                except Exception as del_e:
                    logger.warning(f"Не удалось удалить старое сообщение при показе фото: {del_e}")
        else:
            await _send_text(description_text, reply_markup=keyboard)
    except Exception as send_photo_e:
        logger.error(f"Ошибка при отправке фото или редактировании сообщения: {send_photo_e}")
        await _send_text(description_text, reply_markup=keyboard)
