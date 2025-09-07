"""
Handlers для работы с дневником
"""

# TODO Типы в инсайтах

import asyncio
import logging

from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import date, timedelta

from messages import get_message, get_button_text
from diary.models import CombinedDiaryEntry, DiaryEntry, KeyPoint, UserInsight
from diary.services import analysis_service, daily_state_service
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_cancel_keyboard,
    get_day_entries_edit_keyboard, 
    get_confirmation_keyboard,
    format_entry_text_for_editing,
    get_back_keyboard,
    get_task_pagination_keyboard,
    get_smart_calendar_keyboard,
    get_delete_entry_confirmation_keyboard,
    get_delete_confirmation_keyboard
    )
from bot.utils.api_utils import format_api_error_for_analysis
from bot.utils.validation_utils import validate_incoming_message, validate_text_entry
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from bot.services.task_service import task_service
from bot.services.diary_service import diary_service, update_daily_state
from bot.services.psycho_analysis_service import psycho_analysis_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from core.constants import TEXT_MESSAGE_MAX_LENGTH, VOICE_MESSAGE_MAX_DURATION, TASK_TYPES
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

# ==================== ОСНОВНЫЕ HANDLERS ДНЕВНИКА ====================

@router.callback_query(F.data == "new_entry")
async def new_entry(callback: CallbackQuery, state: FSMContext, language: str):
    """Создание новой записи - предложение ввести текст или голосовое сообщение"""
    logger.info(f"Запрос на создание новой записи от пользователя {callback.from_user.id}")
    
    try:
        await state_manager.set_state(state, DiaryStates.waiting_for_text_entry)
        entry_msg = get_message('ask_entry', language)
        await safe_edit_message_text(
            message=callback.message,
            text=entry_msg,
            reply_markup=get_cancel_keyboard(language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при предложении создания записи: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(DiaryStates.waiting_for_text_entry, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def process_any_entry(message: Message, state: FSMContext, user, language: str):
    """
    Обработка текстовой или голосовой записи с инкрементальным анализом.
    """
    logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Обработка записи ({message.content_type}) от пользователя {message.from_user.id}")
    status_message = None
    try:
        is_valid, error_code = validate_incoming_message(message)
        if not is_valid:
            error_msg = get_message(error_code, language) 
            await message.answer(error_msg)
            logger.warning(f"Валидация не пройдена: {error_code}")
            # Не очищаем состояние, чтобы пользователь мог попробовать снова
            # Если нужно очистить при определенных ошибках, можно добавить логику
            return
        entry_text = ""
        voice_file_id = None
        duration = 0
        speechkit_api_response = None
        deepseek_api_response_postproc = None
        if message.content_type == ContentType.TEXT:
            entry_text = message.text
        elif message.content_type == ContentType.VOICE:
            voice = message.voice
            duration = voice.duration
            voice_file_id = voice.file_id
        user_local_datetime = await user.aget_local_datetime()
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Локальное время пользователя: {user_local_datetime}")
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        if message.content_type == ContentType.VOICE:
            try:
                file = await message.bot.get_file(voice_file_id)
                file_path = file.file_path
                voice_data = await message.bot.download_file(file_path)
                voice_bytes = voice_data.read()
                logger.info(f"Голосовое сообщение скачано, размер: {len(voice_bytes)} байт")
            except Exception as download_error:
                logger.error(f"Ошибка при скачивании голосового сообщения: {download_error}")
                await _send_error_message(status_message, message, language)
                return
            recognition_result = await yandex_speechkit_service.recognize_voice(
                voice_data=voice_bytes,
                language=language,
                audio_format='oggopus'
            )
            if not recognition_result['success']:
                logger.error(f"Ошибка распознавания голоса: {recognition_result['error']}")
                error_detail = recognition_result.get('message', 'Неизвестная ошибка распознавания')
                await status_message.edit_text(f"{get_message('error_processing', language)} (Распознавание: {error_detail})")
                return
            recognized_text = recognition_result['result']
            speechkit_api_response = recognition_result
        # ПОСТОБРАБОТКА ТЕКСТА (пунктуация, форматирование)
            if recognized_text:
                punctuation_result = await deepseek_api_service.punctuate_and_format_text(
                    text=recognized_text,
                    language=language
                )
                if not punctuation_result['success']:
                    logger.error(f"Ошибка постобработки текста: {punctuation_result['error']}")
                    entry_text = recognized_text
                else:
                    entry_text = punctuation_result['result']
                    deepseek_api_response_postproc = punctuation_result.get('api_response', {})
                    logger.info(f"Текст успешно отформатирован, длина: {len(entry_text)} символов")
            else:
                entry_text = ""
                logger.warning("Распознанный текст пустой")
        # === СОХРАНЕНИЕ ЗАПИСИ В БД ===
        diary_entry = None
        if message.content_type == ContentType.TEXT:
            diary_entry = await diary_service.create_text_entry(
                user=user,
                text=entry_text,
                language=language,
                entry_datetime=user_local_datetime
            )
        elif message.content_type == ContentType.VOICE:
            diary_entry = await diary_service.create_voice_entry(
                user=user,
                voice_file_id=voice_file_id,
                duration=duration,
                recognized_text=entry_text,
                language=language,
                entry_datetime=user_local_datetime,
                speechkit_api_response=speechkit_api_response,
                deepseek_api_response=deepseek_api_response_postproc
            )
        # === ПОЛУЧЕНИЕ/СОЗДАНИЕ/ОБНОВЛЕНИЕ СОСТОЯНИЯ ДНЯ ===
        combined_entry, is_first_entry_of_day = await _get_or_update_combined_entry(
            user, diary_entry
        )
        # === ВЫБОР И ВЫПОЛНЕНИЕ МЕТОДА АНАЛИЗА ===
        user_profile_data = await user.aget_profile_data()
        analysis_result = await _perform_analysis(
            is_first_entry_of_day, combined_entry, entry_text, user_profile_data, language
        )
        # === ОБРАБОТКА РЕЗУЛЬТАТА АНАЛИЗА ===
        await _process_analysis_result(
            diary_entry, analysis_result, status_message, language, state, user
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке записи ({message.content_type}): {e}", exc_info=True)
        await _send_error_message(status_message, message, language)
        await state_manager.clear_state(state)

@router.message(DiaryStates.asking_clarifying_questions)
async def process_clarification_answers(message: Message, state: FSMContext, user, language: str):
    """
    Обработка ответов на уточняющие вопросы.
    """
    status_message = None
    try:
        # === ПОЛУЧЕНИЕ ДАННЫХ ИЗ СОСТОЯНИЯ FSM ===
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('clarifying_entry_id')
        clarification_questions = state_data.get('clarification_questions', [])
        if not entry_id:
            logger.error("Не найден ID записи для уточнений в состоянии FSM")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        # Получаем объект записи
        try:
            diary_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            logger.error(f"Запись с ID {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        clarification_text = message.text
        if not clarification_text or len(clarification_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получен пустой ответ на уточнения")
            return
        logger.info(f"Получены ответы на уточнения длиной: {len(clarification_text)} символов")
        # === СОХРАНЕНИЕ ОТВЕТОВ В DiaryEntry ===
        try:
            answers_list = [ans.strip() for ans in clarification_text.split("\n\n") if ans.strip()]
            clarification_answers_dict = {}
            for i, question in enumerate(clarification_questions):
                if i < len(answers_list):
                    clarification_answers_dict[question] = answers_list[i]
                else:
                    clarification_answers_dict[question] = "[Ответ не получен или пуст]"
        # Сохраняем словарь ответов в поле DiaryEntry
            diary_entry.clarification_answers = clarification_answers_dict
            await sync_to_async(diary_entry.save)(update_fields=['clarification_answers'])
        except Exception as save_answers_error:
            logger.error(f"Ошибка при сохранении clarification_answers в DiaryEntry ID {diary_entry.id}: {save_answers_error}")
        # === ПОКАЗ СООБЩЕНИЯ ОБ ОБРАБОТКЕ ===
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        # === ВЫЗОВ API ДЛЯ ФИНАЛЬНОГО АНАЛИЗА С УТОЧНЕНИЯМИ ===
        user_profile_data = await user.get_profile_data()
        final_analysis_result = await deepseek_api_service.analyze_text_with_clarifications(
            original_text=diary_entry.text,
            clarification_answers=clarification_text,
            user_profile=user_profile_data,
            language=language
        )
        # === ОБРАБОТКА ФИНАЛЬНОГО РЕЗУЛЬТАТА АНАЛИЗА ===
        await _process_analysis_result(
            entry=diary_entry,
            final_analysis_result=final_analysis_result,
            status_msg=status_message,
            language=language,
            state=state,
            user=user
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке ответов на уточняющие вопросы: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_processing', language))
        except:
            try:
                if status_message:
                    await status_message.edit_text(get_message('error_processing', language))
            except:
                pass
        # Очищаем состояние в случае ошибки
        await state_manager.clear_state(state)

@router.message(DiaryStates.waiting_for_text_entry)
async def handle_invalid_entry_type(message: Message, language: str):
    """Обработка недопустимого типа сообщения"""
    try:
        # Сообщение об ошибке для недопустимого типа
        invalid_msg = get_message('invalid_input', language)
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=invalid_msg,
            message_to_edit=None
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке недопустимого типа сообщения: {e}")
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=get_message('error_processing', language),
            message_to_edit=None
        )

# ==================== HANDLERS ДЛЯ РЕДАКТИРОВАНИЯ И УДАЛЕНИЯ ИСТОРИИ ЗАПИСЕЙ ==================== 

@router.callback_query(F.data.startswith("delete_entry:"))
async def delete_selected_entry(callback: CallbackQuery, user, language: str):
    """Удаление записей за день, в зависимости от callback_data."""
    try:
        parts = callback.data.split(":")
        if len(parts) == 4:
            year = int(parts[1])
            month = int(parts[2])
            day = int(parts[3])
            target_date = date(year, month, day)
            # Используем get_message с форматированием
            confirm_msg = get_message('confirm_delete_entire_day_prompt', language).format(date=target_date.strftime('%d.%m.%Y')) 
            
            confirm_keyboard = get_confirmation_keyboard(
                language=language,
                confirm_text_key='btn_confirm_delete_day', # Ключ для "✅ Да, удалить день"
                cancel_text_key='btn_cancel',              # Ключ для "❌ Нет, отмена"
                confirm_callback_data=f"confirm_delete_entire_day:{target_date.isoformat()}",
                cancel_callback_data=f"calendar_select_day:{year}:{month}:{day}"
)
            await safe_edit_message_text(
                message=callback.message,
                text=confirm_msg,
                reply_markup=confirm_keyboard
            )
            await safe_answer_callback(callback, "")
        else:
            raise ValueError(f"Неподдерживаемый формат callback_data: {callback.data}")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки callback_data для удаления: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Неожиданная ошибка в delete_selected_entry: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("edit_entry:"))
async def edit_entry_day(callback: CallbackQuery, user, language: str):
    """Вход в режим редактирования записей за день."""
    try:
        # Извлекаем год, месяц и день из callback_data
        parts = callback.data.split(":")
        if len(parts) < 4:
             raise ValueError("Некорректный формат callback_data для edit_entry")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        target_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        if not entries:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_entries_msg,
                reply_markup=get_back_keyboard(language)
            )
            await safe_answer_callback(callback, "")
            return
        try:
            combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_date)
            is_day_analyzed = combined_entry.is_analyzed
        except CombinedDiaryEntry.DoesNotExist:
            is_day_analyzed = False
        edit_keyboard = get_day_entries_edit_keyboard(entries, target_date, language, is_day_analyzed)
        header_msg = get_message('edit_entries_header', language).format(date=target_date.strftime("%d.%m.%Y"))
        await safe_edit_message_text(
            message=callback.message,
            text=header_msg,
            reply_markup=edit_keyboard
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при входе в режим редактирования записей за день: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("edit_specific_entry:"))
async def edit_specific_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование конкретной записи."""
    try:
        entry_id = int(callback.data.split(":")[1])
        try:
            entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        await state_manager.set_state(state, DiaryStates.waiting_for_entry_edit)
        await state_manager.update_state_data(state, editing_entry_id=entry_id)
        formatted_old_text = format_entry_text_for_editing(entry.text)
        edit_prompt_msg = get_message('ask_entry_edit_with_text', language).format(old_text=formatted_old_text)
        await callback.message.answer(
            edit_prompt_msg,
            reply_markup=get_cancel_keyboard(language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при начале редактирования конкретной записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
        
@router.message(DiaryStates.waiting_for_entry_edit)
async def process_entry_edit(message: Message, state: FSMContext, user, language: str):
    """Обработка отредактированного текста записи."""  
    target_date_for_navigation = None
    try:
        new_text = message.text
        is_valid, error_code = validate_text_entry(new_text)
        if not is_valid:
            # Используем get_message для локализации сообщения об ошибке
            error_msg = get_message(error_code, language)
            await message.answer(error_msg)
            logger.warning(f"Валидация отредактированного текста не пройдена: {error_code}")
            # Не очищаем состояние, чтобы пользователь мог попробовать снова
            return
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('editing_entry_id')
        if not entry_id:
            logger.error("Не найден ID редактируемой записи в состоянии")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        success = await diary_service.update_entry_text(entry_id, user, new_text)
        if not success:
            logger.error(f"Сервис не смог обновить запись {entry_id}")
            await message.answer(get_message('error_processing', language))
            await state_manager.clear_state(state)
            return
        try:
            entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
            target_date_for_navigation = entry.entry_date
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена при попытке получить дату для навигации.")
        await _navigate_back_to_edit_day(
            message=message, 
            user=user, 
            language=language, 
            target_date=target_date_for_navigation, 
            status_message=None
        )
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке отредактированного текста записи: {e}", exc_info=True)
        await message.answer(get_message('error_processing', language))
        try:
            await state_manager.clear_state(state)
        except:
            pass

@router.callback_query(F.data.startswith("request_delete_specific_entry:"))
async def request_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения удаления конкретной записи."""
    try:
        entry_id = int(callback.data.split(":")[1])
        try:
            entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            target_date = entry.entry_date
        except DiaryEntry.DoesNotExist:
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        # Используем get_message для запроса подтверждения
        confirm_msg = get_message('confirm_delete_entry_prompt', language) # Новый ключ
        confirm_keyboard = get_delete_entry_confirmation_keyboard(entry_id, target_date, language)
        await safe_edit_message_text(message=callback.message, text=confirm_msg, reply_markup=confirm_keyboard)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при запросе подтверждения удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("delete_entire_day:"))
async def request_delete_entire_day(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения на удаление всех записей за день."""
    try:
        date_str = callback.data.split(":", 1)[1]
        target_date = date.fromisoformat(date_str)
        # Используем get_message с форматированием
        confirm_msg = get_message('confirm_delete_entire_day_prompt', language).format(date=target_date.strftime('%d.%m.%Y'))
        
        confirm_buttons = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_confirm_delete_day', language), # Используем ключ из messages.py
                    callback_data=f"confirm_delete_entire_day:{date_str}"
                ),
                InlineKeyboardButton(
                    text=get_button_text('btn_cancel', language), # Используем общий ключ для кнопки "Отмена"
                    callback_data="archive"
                )
            ]
        ]
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=confirm_buttons)
        await safe_edit_message_text(
            message=callback.message,
            text=confirm_msg,
            reply_markup=confirm_keyboard
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data для удаления дня: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при запросе подтверждения удаления дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("delete_specific_entry:"))
async def delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Удаление конкретной записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        confirm_msg = get_message('confirm_delete_entry', language)
        await callback.message.edit_text(
            confirm_msg,
            reply_markup=get_delete_confirmation_keyboard(language, entry_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_entry:"))
async def confirm_delete_entry(callback: CallbackQuery, user, language: str):
    """Подтверждение удаления записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        from bot.services.diary_service import diary_service
        success = await diary_service.delete_entry(entry_id, user)
        if success:
            entry_deleted_msg = get_message('entry_deleted', language)
            await callback.message.edit_text(
                entry_deleted_msg,
                reply_markup=get_back_keyboard(language)
            )
        else:
            error_msg = get_message('entry_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Не удалось удалить запись {entry_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_specific_entry:"))
async def confirm_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Подтверждение удаления конкретной записи."""
    try:
        parts = callback.data.split(":")
        entry_id = int(parts[1])
        target_date_iso = parts[2]
        target_date = date.fromisoformat(target_date_iso)
        logger.info(f"Подтверждение удаления записи ID: {entry_id} за {target_date}")
        success = await diary_service.delete_entry_and_update_combined(entry_id, user)
        if success:
            # Используем get_message для сообщения об успешном удалении
            alert_msg = get_message('entry_deleted_success', language) # Новый ключ
            await safe_answer_callback(callback, text=alert_msg, show_alert=True)
            logger.info(f"Show alert 'Запись удалена' отправлен для записи {entry_id}.")
            await _navigate_back_to_edit_day(callback.message, user, language, target_date)
        else:
            error_alert_msg = get_message('error_processing', language)
            await safe_answer_callback(callback, text=error_alert_msg, show_alert=True)
            logger.warning(f"Show alert об ошибке отправлен для записи {entry_id}.")
            await _navigate_back_to_edit_day(callback.message, user, language, target_date)
        await safe_answer_callback(callback, "")
    except DiaryEntry.DoesNotExist:
        logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
        await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
        try:
            if 'target_date' in locals():
                 await _navigate_back_to_edit_day(callback.message, user, language, target_date)
        except:
             pass

@router.callback_query(F.data == "cancel_delete_entry")
async def cancel_delete_entry(callback: CallbackQuery, language: str):
    """Отмена удаления записи"""
    try:
        cancel_msg = get_message('entry_delete_cancelled', language)
        await callback.message.edit_text(
            cancel_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_entire_day:"))
async def confirm_delete_entire_day(callback: CallbackQuery, user, language: str):
    """Подтверждение и выполнение удаления всех записей за день."""
    logger.info(f"Пользователь {callback.from_user.id} подтвердил удаление всех записей за день.")
    try:
        date_str = callback.data.split(":", 1)[1]
        target_date = date.fromisoformat(date_str)
        logger.info(f"Подтверждение удаления записей за {target_date}")
        success = await diary_service.delete_all_entries_for_day(user, target_date)
        if success:
            success_msg = get_message('day_deleted_success', language)
            await safe_answer_callback(callback, success_msg, show_alert=True)
            try:
                calendar_keyboard = await get_smart_calendar_keyboard(user, language)
                calendar_msg = get_message('archive_menu', language)
                await safe_edit_message_text(
                    message=callback.message,
                    text=calendar_msg,
                    reply_markup=calendar_keyboard
                )
            except Exception as nav_error:
                logger.error(f"Ошибка при возврате в календарь: {nav_error}", exc_info=True)
                try:
                    calendar_keyboard = await get_smart_calendar_keyboard(user, language)
                    await callback.message.answer(text=calendar_msg, reply_markup=calendar_keyboard)
                except Exception as fallback_error:
                    logger.error(f"Фолбэк ошибка при отправке календаря: {fallback_error}")
                    await callback.message.answer(get_message('archive_menu', language), reply_markup=await get_smart_calendar_keyboard(user, language))
        else:
            error_msg = get_message('error_processing', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(f"Не удалось удалить записи за {target_date}.")
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("cancel_delete_specific_entry:"))
async def cancel_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Отмена удаления конкретной записи."""
    try:
        parts = callback.data.split(":")
        entry_id = int(parts[1])
        target_date_iso = parts[2]
        target_date = date.fromisoformat(target_date_iso)
        # Используем get_message для сообщения об отмене
        cancel_msg = get_message('entry_delete_cancelled', language) # Новый ключ   
        await _navigate_back_to_edit_day(callback.message, user, language, target_date, cancel_msg)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_day_analysis:"))
async def confirm_day_analysis(callback: CallbackQuery, user, language: str):
    """Обработчик нажатия кнопки "Подтвердить" для анализа дня."""
    try:
        date_str = callback.data.split(":")[1]
        target_date = date.fromisoformat(date_str)
        await callback.answer(get_message('day_analysis_confirmed', language), show_alert=True)
        asyncio.create_task(_reanalyze_day_background_silent(user, target_date, language))
        year = target_date.year
        month = target_date.month
        day = target_date.day
        fake_callback_data = f"calendar_select_day:{year}:{month}:{day}"
        class FakeCallbackForSelectDay:
            def __init__(self, original_callback, data):
                self.from_user = original_callback.from_user
                self.message = original_callback.message
                self.data = data
                async def mock_answer(*args, **kwargs):
                    pass
                self.answer = mock_answer
        fake_callback = FakeCallbackForSelectDay(callback, fake_callback_data)
        from bot.handlers.calendar import select_day
        await select_day(fake_callback, user, language)
    except Exception as e:
        logger.error(f"Ошибка в confirm_day_analysis: {e}", exc_info=True)

# ==================== HANDLERS ДЛЯ ПРОСМОТРА ИНСАЙТОВ И КЛЮЧЕВЫХ МОМЕНТОВ ==================== 
@router.callback_query(F.data.startswith("view_day_insights:"))
async def view_day_insights(callback: CallbackQuery, user, language: str):
    """Просмотр инсайтов за день."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            raise ValueError("Некорректный формат callback_data для view_day_insights")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        target_date = date(year, month, day)
        target_date_str = target_date.strftime("%d.%m.%Y")
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        entry_ids = [entry.id for entry in entries]
        back_button = [[InlineKeyboardButton(text=get_button_text('btn_back', language), callback_data=f"calendar_select_day:{year}:{month}:{day}")]]
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=back_button)
        if not entry_ids:
             no_data_msg = get_message('no_insights_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_data_msg, reply_markup=back_keyboard)
             await safe_answer_callback(callback, "")
             return
        insights = await diary_service.get_insights_for_entries(entry_ids)

        if not insights:
             no_insights_msg = get_message('no_insights_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_insights_msg, reply_markup=back_keyboard)
        else:
             insights_header = get_message('header_insights', language, date=target_date_str)
             insights_msg = f"<b>{insights_header}</b>\n"
             for i, insight in enumerate(insights, 1):
                 category_display = getattr(insight, 'get_category_display', lambda: insight.category)()
                 insights_msg += f"<b>{i}. {insight.text}</b>\n"
                 insights_msg += f"   🏷 {category_display}\n"
                 insights_msg += f"   ⭐ {insight.weight}\n"
                 insights_msg += f"   🕒 {insight.last_mentioned.strftime('%d.%m.%Y %H:%M')}\n"
             await safe_edit_message_text(message=callback.message, text=insights_msg, reply_markup=back_keyboard)
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_day_insights: {e}")
        error_msg = get_message('error_loading_insights', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре инсайтов за день: {e}", exc_info=True)
        error_msg = get_message('error_loading_insights', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)

@router.callback_query(F.data.startswith("view_day_keypoints:"))
async def view_day_keypoints(callback: CallbackQuery, user, language: str):
    """Просмотр ключевых моментов за день."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            raise ValueError("Некорректный формат callback_data для view_day_keypoints")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        target_date = date(year, month, day)
        target_date_str = target_date.strftime("%d.%m.%Y")
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        entry_ids = [entry.id for entry in entries]
        back_button = [[InlineKeyboardButton(text=get_button_text('btn_back', language), callback_data=f"calendar_select_day:{year}:{month}:{day}")]]
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=back_button)
        if not entry_ids:
             no_data_msg = get_message('no_key_points_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_data_msg, reply_markup=back_keyboard)
             await safe_answer_callback(callback, "")
             return
        keypoints = await diary_service.get_keypoints_for_entries(entry_ids)
        if not keypoints:
             no_keypoints_msg = get_message('no_key_points_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_keypoints_msg, reply_markup=back_keyboard)
        else:
             keypoints_header = get_message('header_key_points', language, date=target_date_str)
             keypoints_msg = f"<b>{keypoints_header}</b>\n"
             keypoints_by_type = {}
             for kp in keypoints:
                 kp_type = getattr(kp, 'get_type_display', lambda: kp.type)()
                 if kp_type not in keypoints_by_type:
                     keypoints_by_type[kp_type] = []
                 keypoints_by_type[kp_type].append(kp)
             for kp_type, kp_list in keypoints_by_type.items():
                 keypoints_msg += f"<b>{kp_type}:</b>\n"
                 for i, kp in enumerate(kp_list, 1):
                     kp_text_display = (kp.text[:50] + "...") if len(kp.text) > 50 else kp.text
                     keypoints_msg += f"  {i}. {kp_text_display} ({kp.confidence:.2f})\n"
                 keypoints_msg += "\n"
             await safe_edit_message_text(message=callback.message, text=keypoints_msg, reply_markup=back_keyboard)
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_day_keypoints: {e}")
        error_msg = get_message('error_loading_key_points', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре ключевых моментов за день: {e}", exc_info=True)
        error_msg = get_message('error_loading_key_points', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

# TODO: Пересмотреть
async def _reanalyze_day_background_silent(user: User, target_date: date, language: str):
    """
    Фоновая задача для пересчета CombinedDiaryEntry.
    Не отправляет сообщений пользователю напрямую.
    """
    try:
        from bot.services.diary_service import diary_service
        combined_text = await diary_service.get_combined_entry_text(user, target_date)
        if not combined_text.strip():
            logger.warning(f"[Фоновая задача Silent] Объединенный текст за {target_date} пуст. Пропуск анализа.")
            combined_entry = await daily_state_service.get_daily_state(user, target_date)
            if combined_entry:
                 await sync_to_async(lambda ce: setattr(ce, 'is_analyzed', False))()
                 await sync_to_async(lambda ce: ce.save(update_fields=['is_analyzed']))(combined_entry)
            return
        combined_entry = await daily_state_service.get_daily_state(user, target_date)
        if not combined_entry:
            logger.warning(f"[Фоновая задача Silent] CombinedDiaryEntry за {target_date} не найден. Создание невозможно без первой записи.")
            return
        user_profile_data = await user.get_profile_data()
        previous_combined_entry = await daily_state_service.get_daily_state(user, target_date - timedelta(days=1))
        analysis_result = await deepseek_api_service.analyze_text_with_previous_state(
            previous_state_context=previous_combined_entry.ai_state_data,
            new_text=combined_text,
            user_profile=user_profile_data,
            language=language
            )
        if not analysis_result:
             logger.error("[Фоновая задача Silent] Результат анализа пустой")
             return
        result_data = analysis_result.get('result_data', {})
        mood_score = result_data.get('mood_score')
        ai_state_data = result_data.get('ai_state_data', '')
        update_success = await update_daily_state(
            combined_entry=combined_entry,
            new_ai_state_data=ai_state_data,
            latest_mood_score=mood_score
        )
        if update_success:
            logger.debug(f"[Фоновая задача Silent] CombinedDiaryEntry ID {combined_entry.id} успешно обновлен после анализа.")
        else:
            logger.error(f"[Фоновая задача Silent] Не удалось обновить CombinedDiaryEntry ID {combined_entry.id}.")
    except TypeError as te:
        if "You cannot call this from an async context" in str(te):
            logger.critical(f"[Фоновая задача Silent] Критическая ошибка синхронизации: {te}")
            logger.critical("[Фоновая задача Silent] Убедитесь, что все ORM-запросы обернуты в sync_to_async или вызываются через асинхронные сервисы.")
        else:
            logger.error(f"[Фоновая задача Silent] TypeError: {te}", exc_info=True)
    except Exception as e:
        logger.error(f"[Фоновая задача Silent] Критическая ошибка: {e}", exc_info=True)

async def _get_or_update_combined_entry(user, diary_entry: DiaryEntry):
    """Получает или создает/обновляет CombinedDiaryEntry."""
    entry_date = diary_entry.entry_date
    combined_entry = await daily_state_service.get_daily_state(user, entry_date)
    if combined_entry is None:
        # Если CombinedDiaryEntry не существует, создаем его на основе первой записи
        combined_entry = await daily_state_service.create_daily_state_from_entry(diary_entry)
        is_first_entry_of_day = True
    else:
        # === ОПТИМИЗАЦИЯ ===
        # Сначала получаем список записей
        logger.debug("[_get_or_update_combined_entry] Получение записей для обновления CombinedDiaryEntry...")
        entries_today = await diary_service.get_user_entries_for_date(user, entry_date)
        entry_count = len(entries_today)
        
        # Затем получаем объединенный текст, передавая уже полученный список
        logger.debug("[_get_or_update_combined_entry] Получение объединенного текста с использованием уже полученного списка...")
        combined_text = await diary_service.get_combined_entry_text(user, entry_date, entries_list=entries_today)
        
        # Обновляем CombinedDiaryEntry
        await daily_state_service.update_daily_state_text_and_count(
            combined_entry, combined_text, entry_count
        )
        is_first_entry_of_day = False
        
    return combined_entry, is_first_entry_of_day

async def _perform_analysis(is_first, combined_entry, text, profile, lang):
    """Выбирает и выполняет метод анализа."""
    if is_first:
        return await deepseek_api_service.analyze_text_with_profile(
            text=text, user_profile=profile, language=lang
        )
    else:
        previous_state = combined_entry.ai_state_data
        if not previous_state:
            logger.warning("ai_state_data в CombinedDiaryEntry пуст. Используем analyze_text_with_profile.")
            return await deepseek_api_service.analyze_text_with_profile(
                text=text, user_profile=profile, language=lang
            )
        else:
            return await deepseek_api_service.analyze_text_with_previous_state(
                previous_state_context=previous_state,
                new_text=text,
                user_profile=profile,
                language=lang
            )

async def _send_error_message(status_msg, original_msg, language: str):
    """Отправляет сообщение об ошибке, стараясь использовать любой доступный способ."""
    error_message_sent = False
    if status_msg:
        try:
            await status_msg.edit_text(get_message('error_processing', language))
            error_message_sent = True
        except:
            pass
    if not error_message_sent:
        try:
            await original_msg.answer(get_message('error_processing', language))
        except:
            pass

async def _process_analysis_result(
    entry: DiaryEntry, 
    analysis_result: dict, 
    status_msg, 
    language: str, 
    state: FSMContext, 
    user,
    is_final: bool = False
):
    """
    Обрабатывает результат анализа (первичного или финального) и выполняет все последующие действия.
    """
    try:
        mood_score = 5
        comment = 'Анализ записан'
        recommendation = 'Продолжайте вести дневник'
        analysis_text = "Текст проанализирован."
        api_response_data = {}
        suggested_task_data = None
        needs_clarification = False
        clarification_questions = []
        result_data = {}
        if not analysis_result or not analysis_result.get('success', False):
            comment, recommendation, analysis_text, log_message = format_api_error_for_analysis(
                analysis_result, language, is_final
            )
        else:
            logger.info(f"{'Финальный ' if is_final else ''}Анализ API завершен успешно.")
            api_response_data = analysis_result.get('api_response', {})
            result_data_raw = analysis_result.get('result', {})
            if not isinstance(result_data_raw, dict):
                logger.error("Поле 'result' в ответе API не является словарем.")
                result_data = {}
            else:
                result_data = result_data_raw
            mood_score_raw = result_data.get('mood_score')
            if mood_score_raw is not None and isinstance(mood_score_raw, int) and 1 <= mood_score_raw <= 10:
                mood_score = mood_score_raw
            else:
                logger.warning(f"Некорректное значение mood_score: {mood_score_raw}. Используется значение по умолчанию: {mood_score}")    

            comment_raw = result_data.get('comment')
            if comment_raw and isinstance(comment_raw, str):
                comment = comment_raw
            else:
                logger.warning(f"Некорректное значение comment: {comment_raw}. Используется значение по умолчанию.")   

            recommendation_raw = result_data.get('recommendation')
            if recommendation_raw and isinstance(recommendation_raw, str):
                recommendation = recommendation_raw
            else:
                logger.warning(f"Некорректное значение recommendation: {recommendation_raw}. Используется значение по умолчанию.")    

            analysis_text_raw = result_data.get('analysis')
            if analysis_text_raw and isinstance(analysis_text_raw, str):
                analysis_text = analysis_text_raw
            else:
                logger.warning(f"Некорректное значение analysis: {analysis_text_raw}. Используется значение по умолчанию.")
            if not is_final:
                needs_clarification = result_data.get('needs_clarification', False)
                if not isinstance(needs_clarification, bool):
                    logger.debug(f"Некорректное значение needs_clarification: {needs_clarification}. Используется False.")
                    needs_clarification = False

                clarification_questions_raw = result_data.get('clarification_questions')
                if isinstance(clarification_questions_raw, list):
                    if all(isinstance(q, str) for q in clarification_questions_raw):
                        clarification_questions = clarification_questions_raw
                    else:
                        logger.warning("Элементы clarification_questions не являются строками. Используется пустой список.")
                        clarification_questions = []
                else:
                    logger.warning(f"Некорректное значение clarification_questions: {clarification_questions_raw}. Используется пустой список.")
                    clarification_questions = []
            suggested_task_data = result_data.get('suggested_task')
            if suggested_task_data is not None and not isinstance(suggested_task_data, dict):
                logger.warning(f"Некорректное значение suggested_task: {suggested_task_data}. Игнорируется.")
                suggested_task_data = None
        if not is_final and needs_clarification and clarification_questions:
            try:
                entry.clarification_questions_asked = clarification_questions
                await sync_to_async(entry.save)(update_fields=['clarification_questions_asked'])
            except Exception as save_error:
                logger.error(f"Ошибка при сохранении clarification_questions_asked в DiaryEntry ID {entry.id}: {save_error}")
            
            await state_manager.update_state_data(
                state,
                clarifying_entry_id=entry.id,
                clarification_questions=clarification_questions
            )
            await state_manager.set_state(state, DiaryStates.asking_clarifying_questions)
            
            questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clarification_questions)])
            clarification_msg = f"{get_message('clarification_needed', language)}\n{questions_text}"
            await status_msg.edit_text(
                clarification_msg,
                reply_markup=get_cancel_keyboard(language)
            )
            return
        psycho_analysis = await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=api_response_data
        )
        combined_entry = await daily_state_service.get_daily_state(user, entry.entry_date)
        update_success = False
        if combined_entry:
            new_ai_state_data = analysis_text
            update_success = await daily_state_service.update_daily_state(
                combined_entry, new_ai_state_data, latest_mood_score=mood_score 
            )
        else:
            logger.warning("CombinedDiaryEntry не найден для обновления состояния.")
        try:
            await analysis_service.extract_and_save_insights_and_keypoints(entry, result_data)
        except Exception as insight_error:
            logger.error(f"Ошибка при обновлении инсайтов: {insight_error}")
        task_info_text = ""
        final_reply_markup = None
        if suggested_task_data and isinstance(suggested_task_data, dict):
            therapy_task = await _create_task_from_suggested_data(
                user, suggested_task_data, entry.entry_date, related_diary_entry=entry
            )
            if therapy_task:
                task_desc_preview = therapy_task.description[:150] + "..." if len(therapy_task.description) > 150 else therapy_task.description
                task_info_text = f"\n📌 <b>Новое задание от ИИ:</b>\n<b>{therapy_task.title}</b>\n{task_desc_preview}"
                # TODO: Логика пагинации требует доработки, если предполагается больше одного задания
                task_index = 0 
                final_reply_markup = get_task_pagination_keyboard(
                    task_id=therapy_task.id,
                    current_index=task_index,
                    total_tasks=1,
                    language=language
                )
            else:
                logger.warning(f"Не удалось создать задание от ИИ ({'финальный' if is_final else 'первичный'} анализ).")
                final_reply_markup = get_back_keyboard(language)
        else:
            final_reply_markup = get_back_keyboard(language)
        entry_saved_msg = get_message(
            'entry_saved',
            language,
            score=mood_score,
            mood=get_message(f'mood_{mood_score}', language),
            comment=comment,
            recommendation=recommendation
        )
        final_message_text = entry_saved_msg + task_info_text
        await status_msg.edit_text(
            final_message_text,
            reply_markup=final_reply_markup
        )
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Критическая ошибка в _process_analysis_result (is_final={is_final}): {e}", exc_info=True)
        try:
            await status_msg.edit_text(get_message('error_processing', language))
        except:
            pass
        await state_manager.clear_state(state)
        raise 

# TODO: Реализовать проверку, было ли уже задание назначено в этот день.
async def _create_task_from_suggested_data(user, task_data: dict, entry_date: date, related_diary_entry: DiaryEntry = None):
    """
    Создает TherapyTask из данных, предложенных ИИ.
    
    Args:
        user: Объект пользователя Django.
        task_data: Словарь с данными задания от API.
        entry_date: Дата записи, к которой относится задание.
    """
    try:
        title = task_data.get('title', 'Задание от ИИ')
        description = task_data.get('description', 'Выполните задание, предложенное ИИ.')
        task_type_raw = task_data.get('type', 'daily')
        priority_str = task_data.get('priority', 'medium').lower()
        valid_task_types = [t[0] for t in TASK_TYPES]
        task_type = task_type_raw if task_type_raw in valid_task_types else 'daily'
        priority_str_to_int = {
            'low': 1, 
            'medium': 2, 
            'high': 3, 
            'critical': 4
        }
        priority_int = priority_str_to_int.get(priority_str, 2)
        logger.info(f"Создание задания: '{title}', тип: {task_type}, приоритет: {priority_int}")
        therapy_task = await task_service.assign_task(
            user=user,
            title=title,
            description=description,
            task_type=task_type,
            priority=priority_int,
            related_entry=related_diary_entry
        )
        return therapy_task

    except Exception as task_error:
        logger.error(f"Ошибка при создании задания от ИИ: {task_error}", exc_info=True)

async def _navigate_back_to_edit_day(
    message: Message, 
    user, 
    language: str, 
    target_date: date, 
    status_message: str = None
):
    """
    Утилита для навигации назад к меню редактирования записей дня.
    
    Args:
        message: Сообщение Telegram для редактирования.
        user: Пользователь.
        language: Язык.
        target_date: Дата для возврата.
        status_message: Дополнительное сообщение статуса для отображения.
    """
    try:
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        try:
            combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_date)
            is_day_analyzed = combined_entry.is_analyzed
        except CombinedDiaryEntry.DoesNotExist:
            is_day_analyzed = False
        if not entries:
            msg_text = status_message if status_message else get_message('archive_empty', language)
            reply_markup = get_back_keyboard(language)
        else:
            header_msg = get_message('edit_entries_header', language).format(date=target_date.strftime("%d.%m.%Y"))
            if status_message:
                msg_text = f"{status_message}\n\n{header_msg}"
            else:
                msg_text = header_msg
            reply_markup = get_day_entries_edit_keyboard(entries, target_date, language, is_day_analyzed)
        edit_success = await safe_edit_message_text(message=message, text=msg_text, reply_markup=reply_markup)
        
        if not edit_success:
            logger.warning(f"Не удалось отредактировать сообщение {message.message_id} (возможно, это сообщение пользователя или оно слишком старое). Отправляем новое сообщение.")
            try:
                sent_message = await message.answer(text=msg_text, reply_markup=reply_markup)
            except Exception as send_error:
                logger.error(f"Критическая ошибка при отправке нового сообщения как fallback: {send_error}")
                raise
    except Exception as e:
        logger.error(f"Критическая ошибка в _navigate_back_to_edit_day для пользователя {user.telegram_id}, дата {target_date}: {e}", exc_info=True)
        try:
             error_msg = get_message('error_generic', language)
             fallback_edit_success = await safe_edit_message_text(
                 message=message,
                 text=error_msg,
                 reply_markup=get_back_keyboard(language)
             )
             if not fallback_edit_success:
                 await message.answer(text=error_msg, reply_markup=get_back_keyboard(language))
        except Exception as fallback_error:
             logger.error(f"Критическая ошибка при отправке сообщения об ошибке навигации: {fallback_error}")
             try:
                 await message.answer("Произошла ошибка при обновлении интерфейса. Пожалуйста, начните сначала.")
             except:
                 pass
