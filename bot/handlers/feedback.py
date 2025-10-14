# bot/handlers/feedback.py

import logging
import os

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
from core.settings import DEVELOPER_CHAT_ID
from messages import get_message
from users.models import User, Feedback

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 20 * 1024 * 1024

def is_developer(user: User) -> bool:
    """
    Проверяет, является ли пользователь разработчиком.
    Сравнивает telegram_id пользователя с DEVELOPER_CHAT_ID из настроек.
    DEVELOPER_CHAT_ID в settings.py должен быть строкой, которую мы конвертируем в int.
    """
    try:
        developer_id = int(os.getenv('DEVELOPER_CHAT_ID', DEVELOPER_CHAT_ID))
        return user.telegram_id == developer_id
    except (ValueError, TypeError):
        logger.error("DEVELOPER_CHAT_ID не является допустимым числом.")
        return False

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
        photo_obj = message.photo[-1] # Выбираем самое большое фото
        photo_file_id = photo_obj.file_id # <-- Сохраняем file_id

        if photo_obj.file_size > MAX_FILE_SIZE:
            error_msg = f"Фото слишком большое ({photo_obj.file_size} bytes)"
            logger.warning(error_msg)
            await message.answer(get_message('photo_too_large', language))
            return
        try:
            photo_file = await bot.get_file(photo_obj.file_id)
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
            # --- ПЕРЕДАЕМ photo_file_id ---
            await send_feedback_to_developer(
                bot=bot,
                user=user,
                message_text=message_text,
                voice_data=voice_data,
                photo_data=photo_bytes,
                photo_file_id=photo_file_id # <-- Передаем ID файла
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
    # Проверяем, является ли пользователь разработчиком
    if not is_developer(user):
        logger.warning(f"Пользователь {user.telegram_id} попытался выполнить команду /feedbacks, но не является разработчиком.")
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        # Асинхронный вызов ORM
        @sync_to_async
        def get_feedbacks_sync():
            return list(Feedback.objects.filter(status='new')
                        .select_related('user')
                        .order_by('-created_at'))
        feedbacks = await get_feedbacks_sync()

        if not feedbacks:
            await message.answer("🎉 Нет новых необработанных обращений!")
            return

        # Сохраняем список ID обращений и устанавливаем начальный индекс
        feedback_ids = [f.id for f in feedbacks]
        current_index = 0

        await state.update_data(
            admin_feedback_list=feedback_ids,
            admin_feedback_current_index=current_index
        )
        await state.set_state("admin_browsing_feedbacks")

        # Показываем первое обращение
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

    if not is_developer(user):
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

    if not is_developer(user):
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

    if not is_developer(user):
        logger.warning(f"Пользователь {user.telegram_id} попытался обновить список feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    try:
        # Асинхронный вызов ORM
        @sync_to_async
        def get_refreshed_feedbacks_sync():
            return list(Feedback.objects.filter(status='new')
                        .select_related('user')
                        .order_by('-created_at'))
        feedbacks = await get_refreshed_feedbacks_sync()

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

    if not is_developer(user):
        logger.warning(f"Пользователь {user.telegram_id} попытался закрыть список feedbacks, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    await callback.message.edit_text("Список обращений закрыт.")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("reply_feedback_"))
async def start_reply_to_feedback_admin(callback: CallbackQuery, state: FSMContext, user, language: str):
    current_state_str = await state.get_state()
    logger.debug(f"[start_reply] Текущее состояние: {current_state_str}")
    # Проверяем, что пользователь в нужном состоянии (просмотра списка)
    if current_state_str != "admin_browsing_feedbacks":
         logger.warning(f"[start_reply] Некорректное состояние: {current_state_str}, ожидалось 'admin_browsing_feedbacks'")
         await callback.answer("❌ Некорректное состояние для этого действия.", show_alert=True)
         return

    # Проверяем, является ли пользователь разработчиком
    if not is_developer(user):
        logger.warning(f"Пользователь {user.telegram_id} попытался начать ответ на feedback, но не является разработчиком.")
        await callback.answer("❌ У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    try:
        feedback_id = int(callback.data.split('_')[-1])
        logger.debug(f"[start_reply] Извлечен feedback_id: {feedback_id}")
        # Асинхронная проверка существования и статуса
        @sync_to_async
        def check_feedback_exists_and_status():
            try:
                fb = Feedback.objects.select_related('user').get(id=feedback_id)
                return fb, fb.status == 'new'
            except Feedback.DoesNotExist:
                return None, False

        feedback, is_new = await check_feedback_exists_and_status()

        if not feedback:
            logger.warning(f"[start_reply] Обращение с ID {feedback_id} не найдено или не новый статус.")
            await callback.answer("❌ Обращение не найдено.", show_alert=True)
            return
        if not is_new:
            logger.warning(f"[start_reply] Обращение с ID {feedback_id} уже не в статусе 'new'.")
            await callback.answer("❌ Обращение уже обработано.", show_alert=True)
            return

        # --- ИЗМЕНЕНИЕ ПОРЯДКА ---
        # 1. Сохраняем ID в данных состояния
        await state.update_data(replying_to_feedback_id=feedback_id)
        logger.debug(f"[start_reply] Сохранён replying_to_feedback_id: {feedback_id}")
        # 2. Очищаем *предыдущее* состояние просмотра списка и *его* данные
        await state.clear() # <-- Теперь очищает старое состояние И данные
        logger.debug(f"[start_reply] Состояние очищено. Устанавливаем 'admin_waiting_feedback_reply'.")
        # 3. Устанавливаем новое состояние ожидания ответа
        await state.set_state("admin_waiting_feedback_reply")
        # 4. НО нужно снова сохранить данные в новом состоянии!
        # Потому что clear() удалил их. update_data нужно вызвать *после* set_state,
        # чтобы данные сохранились в новом состоянии.
        # Нет, не после. Нужно сначала получить данные, которые мы хотим сохранить, до clear.
        # Правильный способ - сохранить данные, которые нужно перенести, в переменную,
        # вызвать clear, затем set_state, затем update_data с этими данными.

        # --- ПРАВИЛЬНЫЙ ПОДХОД ---
        # Сохраняем нужные данные в переменную до очистки
        data_to_persist = {"replying_to_feedback_id": feedback_id}
        # Очищаем состояние (и данные)
        await state.clear()
        # Устанавливаем новое состояние
        await state.set_state("admin_waiting_feedback_reply")
        # Обновляем данные в новом состоянии
        await state.update_data(**data_to_persist)
        logger.debug(f"[start_reply] Новое состояние установлено: {await state.get_state()}, данные: {data_to_persist}")

        # Асинхронное получение данных для сообщения
        @sync_to_async
        def get_feedback_details_for_message():
            username = feedback.user.username or f"user_{feedback.user.telegram_id}"
            created_at = feedback.created_at.strftime('%d.%m.%Y %H:%M')
            return username, created_at

        username, created_at = await get_feedback_details_for_message()

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
    
    # Проверяем, является ли пользователь разработчиком
    if not is_developer(user):
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

    # Проверяем, является ли пользователь разработчиком
    if not is_developer(user):
        logger.warning(f"Пользователь {user.telegram_id} попытался отправить ответ на feedback, но не является разработчиком.")
        await message.answer("❌ У вас нет прав для выполнения этого действия.")
        await state.clear()
        return

    data = await state.get_data()
    logger.debug(f"[process_reply] Данные из состояния: {data}")
    feedback_id = data.get('replying_to_feedback_id')
    logger.debug(f"[process_reply] Извлечен feedback_id: {feedback_id}")
    if not feedback_id:
        logger.error(f"[process_reply] feedback_id не найден в данных состояния: {data}")
        await message.answer("❌ Ошибка: ID обращения не найден.")
        await state.clear()
        return

    try:
        # Асинхронная проверка и обновление
        @sync_to_async
        def get_and_check_feedback():
            try:
                fb = Feedback.objects.select_related('user').get(id=feedback_id)
                # Проверяем статус перед отправкой
                if fb.status not in ['new', 'processed']:
                    return fb, False # Уже обработано кем-то другим
                return fb, True
            except Feedback.DoesNotExist:
                return None, False

        feedback, can_reply = await get_and_check_feedback()

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

        # Асинхронное обновление статуса
        @sync_to_async
        def update_feedback_status():
            feedback.admin_response = message.text
            feedback.status = 'replied'
            feedback.save()

        await update_feedback_status()

        @sync_to_async
        def get_user_details_for_confirmation():
            username = feedback.user.username or f"user_{feedback.user.telegram_id}"
            created_at = feedback.created_at.strftime('%d.%m.%Y %H:%M')
            return username, created_at

        username, created_at = await get_user_details_for_confirmation()

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

    if not is_developer(user):
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
    try:
        feedback = await Feedback.aget_by_id(feedback_id)
    except Feedback.DoesNotExist:
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

    # Получаем данные пользователя и дату асинхронно
    @sync_to_async
    def get_feedback_details():
        username = feedback.user.username or f"user_{feedback.user.telegram_id}"
        created_at = feedback.created_at.strftime('%d.%m.%Y %H:%M')
        return username, created_at

    username, created_at = await get_feedback_details()

    # Подготовим текст описания
    feedback_text_preview = feedback.message[:200] + ('...' if len(feedback.message) > 200 else '')
    description_text = (
        f"📬 Обращение #{feedback.id} от {username}\n"
        f"Дата: {created_at}\n"
        f"Тип: {'голосовое' if feedback.is_voice else 'текстовое'}\n"
        f"Фото: {'да' if feedback.is_photo else 'нет'}\n\n"
        f"Сообщение:\n{feedback_text_preview}"
    )

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
    bot = message_or_callback.bot # Получаем бота из объекта callback или message

    if hasattr(message_or_callback, 'message'):
        target_chat_id = message_or_callback.message.chat.id
        target_message_id = message_or_callback.message.message_id
    else:
        # Это Message, отправляем новое
        target_chat_id = message_or_callback.chat.id
        target_message_id = None

    try:
        if feedback.is_photo and hasattr(feedback, 'photo_file_id') and feedback.photo_file_id:
            # Отправляем фото с описанием как подпись (caption)
            await bot.send_photo(
                chat_id=target_chat_id,
                photo=feedback.photo_file_id,
                caption=description_text,
                reply_markup=keyboard
            )
            # Редактируем предыдущее сообщение, чтобы удалить его (оставив только новое с фото)
            # Это не всегда возможно/нужно. Проще отправить новое и удалить старое.
            # Или отправить новое и не удалять старое, если оно служебное.
            # В данном случае, проще отправить новое фото-сообщение и не трогать старое,
            # если оно не является частью пагинации (т.е. если это ответ на /feedbacks).
            # Но если это редактирование (например, навигация), то старое сообщение нужно заменить.
            # Для пагинации, отправим фото, а затем удалим старое текстовое сообщение.
            if target_message_id:
                 try:
                     await bot.delete_message(chat_id=target_chat_id, message_id=target_message_id)
                 except Exception as del_e:
                     logger.warning(f"Не удалось удалить старое сообщение при показе фото: {del_e}")
                     # Если не удалось удалить, можно оставить как есть или попробовать edit_text с пустым текстом,
                     # но это не всегда выглядит красиво.
                     # ВАЖНО: Удаление может не сработать, если сообщение слишком старое или его нельзя удалить боту.
                     # В таком случае, старое сообщение останется.
                     # Альтернатива: редактировать старое сообщение, заменив его на новое с фото.
                     # Но бот не может редактировать сообщения с медиа на сообщения без медиа и наоборот (в одном вызове).
                     # Нужно сначала удалить, потом отправить новое, или наоборот.
                     # Попробуем сначала отправить фото, потом удалить старое.
                     # Это уже сделано выше.
                     # Лучший способ - это отправить *новое* сообщение с фото и *редактировать* старое, убрав из него фото/текст,
                     # но оставив *только* клавиатуру.
                     # Но это невозможно, если старое сообщение *содержит* фото.
                     # Итак, план: отправить фото, удалить старое (если возможно).
                     # Если удалить нельзя, оставляем оба.
                     # Это не идеально, но работает в большинстве случаев.
                     # Для простоты, отправим фото, и если при навигации будет редактирование, оно заменит текстовое сообщение.
                     # Если текущее сообщение - фото, и мы его не удаляем, то при навигации может появиться "лишнее" фото.
                     # Более сложная логика потребовала бы отслеживания типа предыдущего сообщения.
                     # Пока оставим простой вариант: отправить фото, попытаться удалить старое.
                     # Или, альтернатива: редактировать старое, убрав из него текст (оставив только клаву), и отправить фото отдельно.
                     # Это может выглядеть как два сообщения.
                     # Наиболее совместимый способ для пагинации - отправить *новое* сообщение с фото и клавой,
                     # и *редактировать* старое *текстовое* сообщение (без фото), заменив его на новое текстовое сообщение.
                     # Но если старое - с фото, его нельзя отредактировать на текстовое.
                     # Вывод: при наличии фото у обращения, *всегда* отправляем новое сообщение с фото и удаляем старое (если можно).
                     # При навигации, если текущее - фото, мы его не редактируем, а отправляем новое (текстовое или фото), и удаляем текущее.
                     # Это приведет к "миганию" сообщений, но позволит отображать фото.
                     # Более сложная логика - отдельное хранение message_id для фото-сообщений и их редактирование.
                     # Пока реализуем простой способ: отправить фото, удалить старое.
                     # Удаляем старое ТОЛЬКО если оно не является фото-сообщением, иначе мигание будет сильнее.
                     # Но мы не знаем тип старого сообщения здесь напрямую.
                     # Попробуем отправить фото, удалить старое. Если ошибка - логируем.
                     pass # Лог уже есть выше.
        else:
            # Отправляем или редактируем текстовое сообщение
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
        # Если не получилось отправить фото, отправим текстовое сообщение как обычно
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
