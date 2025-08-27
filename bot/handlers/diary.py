"""
Handlers для работы с дневником
"""

import logging
import pytz

from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext
from datetime import datetime, date
from datetime import datetime

from messages import get_message, get_button_text
from diary.models import CombinedDiaryEntry, DiaryEntry, PsychoAnalysis, TherapyTask
from diary.services import analysis_service, daily_state_service
from bot.states.diary_states import DiaryStates
from bot.services.task_service import task_service
from bot.keyboards import (
    get_cancel_keyboard,
    get_month_calendar_with_navigation,
    get_calendar_back_keyboard,
    get_cancel_keyboard,
    )
from bot.keyboards.main_menu import get_back_keyboard, get_main_menu_keyboard
from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
from bot.utils.state_manager import state_manager
from bot.utils.time_utils import convert_utc_to_user_timezone
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from core.constants import TEXT_MESSAGE_MAX_LENGTH, TASK_TYPES
from bot.services.diary_service import diary_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from bot.services.diary_service import (
    create_text_entry, 
    create_voice_entry, 
    get_user_entries_for_date,
    get_combined_entry_text,
    delete_entry
)
from core.constants import TEXT_MESSAGE_MAX_LENGTH, VOICE_MESSAGE_MAX_DURATION
from users.models import User

# Создаем роутер для этого модуля
router = Router()
logger = logging.getLogger(__name__)

# ==================== ОСНОВНЫЕ HANDLERS ДНЕВНИКА ====================

@router.callback_query(F.data == "new_entry")
async def new_entry(callback: CallbackQuery, state: FSMContext, language: str):
    """Создание новой записи - предложение ввести текст или голосовое сообщение"""
    logger.info(f"Запрос на создание новой записи от пользователя {callback.from_user.id}")
    
    try:
        # Устанавливаем состояние ожидания записи (любого типа)
        await state_manager.set_state(state, DiaryStates.waiting_for_text_entry)
        
        # Предлагаем ввести запись любого типа
        entry_msg = get_message('ask_entry', language)
        
        await safe_edit_message_text(
            message=callback.message,
            text=entry_msg,
            reply_markup=get_cancel_keyboard(language)
        )
        await safe_answer_callback(callback, "")
        logger.info("Предложено ввести запись любого типа")
        
    except Exception as e:
        logger.error(f"Ошибка при предложении создания записи: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(
    DiaryStates.waiting_for_text_entry,
    F.content_type.in_({ContentType.TEXT, ContentType.VOICE})
)
async def process_any_entry(message: Message, state: FSMContext, user, language: str):
    """
    Обработка текстовой или голосовой записи с инкрементальным анализом.
    """
    logger.info(f"Обработка записи ({message.content_type}) от пользователя {message.from_user.id}")
    
    status_message = None
    try:
        # === 1. ПОЛУЧЕНИЕ И ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ ===
        entry_text = ""
        voice_file_id = None
        duration = 0
        speechkit_api_response = None
        deepseek_api_response_postproc = None # Для голоса

        if message.content_type == ContentType.TEXT:
            entry_text = message.text
            if not entry_text or len(entry_text.strip()) < 1:
                error_msg = get_message('invalid_input', language)
                await message.answer(error_msg)
                logger.warning("Получена пустая текстовая запись")
                return

            if len(entry_text) > TEXT_MESSAGE_MAX_LENGTH:
                error_msg = get_message('text_too_long', language)
                await message.answer(error_msg)
                logger.warning(f"Текст записи слишком длинный: {len(entry_text)} символов")
                return
            logger.info(f"Получен текст записи длиной: {len(entry_text)} символов")

        elif message.content_type == ContentType.VOICE:
            voice = message.voice
            if not voice:
                error_msg = get_message('invalid_input', language)
                await message.answer(error_msg)
                logger.warning("Получено сообщение без голоса")
                return

            duration = voice.duration
            voice_file_id = voice.file_id

            if duration > VOICE_MESSAGE_MAX_DURATION:
                error_msg = get_message('voice_too_long', language)
                await message.answer(error_msg)
                logger.warning(f"Голосовое сообщение слишком длинное: {duration} секунд")
                return

            if duration < 1:
                error_msg = get_message('voice_too_short', language)
                await message.answer(error_msg)
                logger.warning(f"Голосовое сообщение слишком короткое: {duration} секунд")
                return
            logger.info(f"Получено голосовое сообщение, длительность: {duration} секунд")
        # ======================================

        # === 2. ПОЛУЧЕНИЕ ЛОКАЛЬНОГО ВРЕМЕНИ ПОЛЬЗОВАТЕЛЯ ===
        user_local_datetime = await _get_user_local_datetime(user)
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Локальное время пользователя: {user_local_datetime}")
        # ===================================================

        # === 3. ПОКАЗ СООБЩЕНИЯ ОБ ОБРАБОТКЕ ===
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке записи")
        # =======================================

        # === 4. (ДЛЯ ГОЛОСА) СКАЧИВАНИЕ И РАСПОЗНАВАНИЕ ===
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
            speechkit_api_response = recognition_result # Сохраняем для записи в БД
            logger.info(f"Голос успешно распознан, длина текста: {len(recognized_text)} символов")

            # ПОСТОБРАБОТКА ТЕКСТА (пунктуация, форматирование)
            if recognized_text:
                punctuation_result = await deepseek_api_service.punctuate_and_format_text(
                    text=recognized_text,
                    language=language
                )
                if not punctuation_result['success']:
                    logger.error(f"Ошибка постобработки текста: {punctuation_result['error']}")
                    entry_text = recognized_text # Используем распознанный текст без постобработки
                else:
                    entry_text = punctuation_result['result']
                    deepseek_api_response_postproc = punctuation_result.get('api_response', {})
                    logger.info(f"Текст успешно отформатирован, длина: {len(entry_text)} символов")
            else:
                entry_text = ""
                logger.warning("Распознанный текст пустой")
        # ================================================

        # === 5. СОХРАНЕНИЕ ЗАПИСИ В БД ===
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
        logger.info(f"Запись ({message.content_type}) сохранена в БД, ID: {diary_entry.id}")
        # === 6. ПОЛУЧЕНИЕ/СОЗДАНИЕ/ОБНОВЛЕНИЕ СОСТОЯНИЯ ДНЯ ===
        combined_entry, is_first_entry_of_day = await _get_or_update_combined_entry(
            user, diary_entry
        )
        logger.info(f"CombinedDiaryEntry обработан, ID: {combined_entry.id if combined_entry else 'None'}, isFirst: {is_first_entry_of_day}")
        # === 7. ВЫБОР И ВЫПОЛНЕНИЕ МЕТОДА АНАЛИЗА ===
        user_profile_data = await _get_user_profile_data(user, language)
        analysis_result = await _perform_analysis(
            is_first_entry_of_day, combined_entry, entry_text, user_profile_data, language
        )
        # === 8. ОБРАБОТКА РЕЗУЛЬТАТА АНАЛИЗА ===
        await _handle_analysis_result(
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
    logger.info(f"Обработка ответов на уточняющие вопросы от пользователя {message.from_user.id}")
    
    status_message = None
    try:
        # === 1. ПОЛУЧЕНИЕ ДАННЫХ ИЗ СОСТОЯНИЯ FSM ===
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('clarifying_entry_id')
        clarification_questions = state_data.get('clarification_questions', []) # Список вопросов
        
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
            return # Не очищаем состояние, позволяем пользователю попробовать снова
            
        logger.info(f"Получены ответы на уточнения длиной: {len(clarification_text)} символов")
        # =============================================

        # === 2. СОХРАНЕНИЕ ОТВЕТОВ В DiaryEntry ===
        try:
            # Создаем словарь {вопрос: ответ}
            # Предполагаем, что ответы в clarification_text разделены двумя \n и соответствуют порядку clarification_questions
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
            logger.info(f"Ответы на уточнения сохранены в DiaryEntry ID {diary_entry.id}")
        except Exception as save_answers_error:
            logger.error(f"Ошибка при сохранении clarification_answers в DiaryEntry ID {diary_entry.id}: {save_answers_error}")
            # Не прерываем выполнение, продолжаем анализ
        # ===========================================

        # === 3. ПОКАЗ СООБЩЕНИЯ ОБ ОБРАБОТКЕ ===
        processing_msg = get_message('processing', language) # Используем общий processing, можно выделить отдельный
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке уточнений")
        # =======================================

        # === 4. ВЫЗОВ API ДЛЯ ФИНАЛЬНОГО АНАЛИЗА С УТОЧНЕНИЯМИ ===
        # Получаем профиль пользователя
        user_profile_data = await _get_user_profile_data(user, language)
        
        # Вызываем метод API для анализа с уточнениями
        # Передаем текст записи, ответы пользователя (в виде текста) и профиль
        final_analysis_result = await deepseek_api_service.analyze_text_with_clarifications(
            original_text=diary_entry.text,
            clarification_answers=clarification_text, # Передаем текст ответов, как и ожидалось API
            user_profile=user_profile_data,
            language=language
        )
        logger.info("Финальный анализ с уточнениями завершен через API")
        # =========================================================

        # === 5. ОБРАБОТКА ФИНАЛЬНОГО РЕЗУЛЬТАТА АНАЛИЗА ===
        # Используем существующую функцию для обработки финального результата
        await _handle_final_analysis_result(
            entry=diary_entry,
            final_analysis_result=final_analysis_result,
            status_msg=status_message,
            language=language,
            state=state,
            user=user
        )
        # ==================================================

    except Exception as e:
        logger.error(f"Ошибка при обработке ответов на уточняющие вопросы: {e}", exc_info=True)
        # Отправляем сообщение об ошибке
        try:
            await message.answer(get_message('error_processing', language))
        except:
            try:
                if status_message:
                    await status_message.edit_text(get_message('error_processing', language))
            except:
                pass # Игнорируем ошибки при отправке сообщения об ошибке
        # Очищаем состояние в случае ошибки
        await state_manager.clear_state(state)

@router.message(DiaryStates.waiting_for_text_entry)
async def handle_invalid_entry_type(message: Message, language: str):
    """Обработка недопустимого типа сообщения"""
    logger.info(f"Получено сообщение недопустимого типа от пользователя {message.from_user.id}")
    
    try:
        invalid_msg = get_message('invalid_input', language)
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=invalid_msg,
            message_to_edit=None
        )
        logger.info("Отправлено сообщение о недопустимом типе сообщения")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке недопустимого типа сообщения: {e}")
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=get_message('error_processing', language),
            message_to_edit=None
        )

@router.callback_query(F.data == "cancel_entry")
async def cancel_entry(callback: CallbackQuery, state: FSMContext, language: str):
    """Отмена создания записи"""
    logger.info(f"Отмена создания записи пользователем {callback.from_user.id}")
    
    try:
        # Очищаем состояние
        await state_manager.clear_state(state)
        
        # Возвращаем в главное меню
        main_menu_msg = get_message('main_menu', language)
        
        await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=get_main_menu_keyboard(language)
        )
        await safe_answer_callback(callback, "")
        logger.info("Создание записи отменено, возвращен в главное меню")
        
    except Exception as e:
        logger.error(f"Ошибка при отмене создания записи: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

# ==================== HANDLERS КАЛЕНДАРЯ ====================

@router.callback_query(F.data == "archive")
async def show_archive(callback: CallbackQuery, state: FSMContext, language: str):
    """Показ архива записей с умным календарем"""
    logger.info(f"Запрос архива записей от пользователя {callback.from_user.id}")
    
    try:
        # Очищаем состояние
        await state_manager.clear_state(state)
        
        # Показываем умный календарь
        from bot.keyboards.calendar_keyboard import get_smart_calendar_keyboard
        from users.models import User
        
        # Получаем пользователя для получения его данных (если нужно)
        user = await User.objects.aget(telegram_id=callback.from_user.id)
        
        archive_msg = get_message('archive_menu', language)
        
        await safe_edit_message_text(
            message=callback.message,
            text=archive_msg,
            reply_markup=await get_smart_calendar_keyboard(user, language)
        )
        await safe_answer_callback(callback, "")
        logger.info("Показан умный календарь архива")
        
    except Exception as e:
        logger.error(f"Ошибка при показе архива: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_prev_month:"))
async def prev_month(callback: CallbackQuery, user, language: str):
    """Переход к предыдущему месяцу"""
    logger.info(f"Переход к предыдущему месяцу для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        
        # Переходим к предыдущему месяцу
        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year = year - 1
        
        logger.info(f"Переход к месяцу: {prev_month}.{prev_year}")
        
        # Показываем календарь для предыдущего месяца (ИСПРАВЛЕНО!)
        from bot.keyboards.calendar_keyboard import get_month_calendar_with_navigation
        from datetime import datetime
        
        today = datetime.now()
        current_day = today.day if today.month == prev_month and today.year == prev_year else 1
        
        # Получаем название месяца для сообщения (ИСПРАВЛЕНО!)
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[prev_month] if 1 <= prev_month <= 12 else ""
        
        # Формируем сообщение с названием месяца (ИСПРАВЛЕНО!)
        from messages import get_message
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=prev_year
        )
        
        # ИСПРАВЛЕНО: проверяем, отличается ли новое сообщение от текущего
        if callback.message.text != calendar_msg:
            logger.info("Сообщение отличается, редактируем")
            await safe_edit_message_text(
                message=callback.message,
                text=calendar_msg,
                reply_markup=await get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
            )
        else:
            logger.info("Сообщение не отличается, обновляем только клавиатуру")
            try:
                # Если сообщение такое же, обновляем только клавиатуру
                await callback.message.edit_reply_markup(
                    reply_markup=get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
                )
            except Exception as keyboard_error:
                logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                # Если не удалось обновить клавиатуру, отправляем новое сообщение
                await safe_edit_message_text(
                    message=callback.message,
                    text=calendar_msg,
                    reply_markup=get_month_calendar_with_navigation(user, prev_year, prev_month, current_day, language)
                )
        
        await safe_answer_callback(callback, "")
        logger.info("Показан календарь предыдущего месяца")
        
    except Exception as e:
        logger.error(f"Ошибка при переходе к предыдущему месяцу: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_next_month:"))
async def next_month(callback: CallbackQuery, user, language: str):
    """Переход к следующему месяцу"""
    logger.info(f"Переход к следующему месяцу для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        
        # Переходим к следующему месяцу
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1
        
        logger.info(f"Переход к месяцу: {next_month}.{next_year}")
        
        # Показываем календарь для следующего месяца
        from bot.keyboards.calendar_keyboard import get_month_calendar_with_navigation
        from datetime import datetime
        
        today = datetime.now()
        current_day = today.day if today.month == next_month and today.year == next_year else 1
        
        calendar_msg = get_message('archive_menu', language)
        
        # ИСПРАВЛЕНО: используем утилиту для безопасного редактирования сообщения
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, next_year, next_month, current_day, language)
        )
        # ИСПРАВЛЕНО: используем утилиту для безопасного ответа на callback
        await safe_answer_callback(callback, "")
        logger.info("Показан календарь следующего месяца")
        
    except Exception as e:
        logger.error(f"Ошибка при переходе к следующему месяцу: {e}")
        # ИСПРАВЛЕНО: используем утилиту для безопасного ответа на callback
        await safe_answer_callback(callback, get_message('error_generic', language))


@router.callback_query(F.data.startswith("calendar_open_year_selector:"))
async def open_year_selector(callback: CallbackQuery, language: str):
    """Открытие селектора года"""
    logger.info(f"Открытие селектора года для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год из callback_data
        year = int(callback.data.split(":")[1])
        logger.info(f"Открытие селектора для года: {year}")
        
        # Показываем выбор года
        from bot.keyboards.calendar_keyboard import get_year_selection_keyboard
        
        year_msg = get_message('archive_select_year', language)
        
        await safe_edit_message_text(
            message=callback.message,
            text=year_msg,
            reply_markup=get_year_selection_keyboard(year, language)
        )
        await safe_answer_callback(callback, "")
        logger.info("Показан выбор года")
        
    except Exception as e:
        logger.error(f"Ошибка при открытии селектора года: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_year:"))
async def select_year(callback: CallbackQuery, user, language: str):
    """Выбор года - показываем календарь выбранного года"""
    logger.info(f"Выбор года для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год из callback_data
        year = int(callback.data.split(":")[1])
        logger.info(f"Выбран год: {year}")
        
        # Показываем календарь для января выбранного года 
        today = datetime.now()
        current_day = today.day if today.year == year and today.month == 1 else 1
        
        calendar_msg = get_message('archive_menu', language)
        
        await callback.message.edit_text(
            calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, year, 1, current_day, language)
        )

        await callback.answer()
        logger.info("Показан календарь выбранного года")
        
    except Exception as e:
        logger.error(f"Ошибка при выборе года: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_quick_month:"))
async def quick_month_navigation(callback: CallbackQuery, user, language: str):
    """Быстрая навигация по месяцам"""
    logger.info(f"Быстрая навигация по месяцам для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        
        logger.info(f"Быстрый переход к месяцу: {month}.{year}")
        
        # Показываем календарь для выбранного месяца
        from bot.keyboards.calendar_keyboard import get_month_calendar_with_navigation
        from datetime import datetime
        
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        
        # Получаем название месяца
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        
        # ИСПРАВЛЕНО: используем утилиту для безопасного редактирования сообщения
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        # ИСПРАВЛЕНО: используем утилиту для безопасного ответа на callback
        await safe_answer_callback(callback, "")
        logger.info("Показан календарь выбранного месяца")
        
    except Exception as e:
        logger.error(f"Ошибка при быстрой навигации по месяцам: {e}")
        # ИСПРАВЛЕНО: используем утилиту для безопасного ответа на callback
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_open_month_selector:"))
async def open_month_selector(callback: CallbackQuery, language: str):
    """Открытие селектора месяцев"""
    logger.info(f"Открытие селектора месяцев для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        logger.info(f"Открытие селектора месяцев для года: {year}, текущий месяц: {month}")
        
        # Показываем выбор месяцев
        from bot.keyboards.calendar_keyboard import get_month_selection_keyboard
        
        month_msg = get_message('archive_select_month', language).format(year=year)
        
        await callback.message.edit_text(
            month_msg,
            reply_markup=get_month_selection_keyboard(year, month, language)
        )
        await callback.answer()
        logger.info("Показан выбор месяцев")
        
    except Exception as e:
        logger.error(f"Ошибка при открытии селектора месяцев: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_specific_month:"))
async def select_specific_month(callback: CallbackQuery, user, language: str):
    """Выбор конкретного месяца"""
    logger.info(f"Выбор конкретного месяца для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        
        logger.info(f"Выбран месяц: {month}.{year}")
        
        # Показываем календарь для выбранного месяца
        from bot.keyboards.calendar_keyboard import get_month_calendar_with_navigation
        from datetime import datetime
        
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        
        # Получаем название месяца
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        
        await callback.message.edit_text(
            calendar_msg,
            reply_markup=get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await callback.answer()
        logger.info("Показан календарь выбранного месяца")
        
    except Exception as e:
        logger.error(f"Ошибка при выборе конкретного месяца: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_return_to_month:"))
async def return_to_month(callback: CallbackQuery, user, language: str):
    """Возврат к конкретному месяцу календаря"""
    logger.info(f"Возврат к календарю месяца для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год и месяц из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        logger.info(f"Возврат к календарю: {month}.{year}")
        
        # Сохраняем текущий месяц и год для будущих возвратов
        user.current_calendar_year = year
        user.current_calendar_month = month
        
        # Показываем календарь для выбранного месяца#
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        
        # Получаем название месяца
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        
        from messages import get_message
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=await get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await safe_answer_callback(callback, "")
        logger.info(f"Возвращен к календарю {month}.{year}")
        
    except Exception as e:
        logger.error(f"Ошибка при возврате к календарю: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("calendar_select_day:"))
async def select_day(callback: CallbackQuery, user, language: str):
    """Выбор дня для просмотра записей"""
    logger.info(f"Выбор дня для просмотра записей для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год, месяц и день из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        logger.info(f"Выбран день: {day}.{month}.{year}")
        
        # Сохраняем текущий месяц и год для кнопки "назад"
        user.current_calendar_year = year
        user.current_calendar_month = month
        # await user.asave(update_fields=['current_calendar_year', 'current_calendar_month']) # Опционально, сохранить в БД
        
        # Ищем записи за выбранный день
        from datetime import date
        from bot.services.diary_service import diary_service
        selected_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, selected_date)
        
        if entries:
            # Показываем объединенный текст всех записей дня
            combined_text = await diary_service.get_combined_entry_text(user, selected_date)
            
            # Получаем анализ первой записи (если есть) - ИСПРАВЛЕНО!
            analysis_text = "Анализ не доступен"
            mood_score = 5
            recommendation = "Продолжайте в том же духе"
            mood_text = get_message(f'mood_{mood_score}', language) # <-- Добавлено
            
            try:
                first_entry = entries[0]
                if hasattr(first_entry, 'analysis'):
                    from diary.models import PsychoAnalysis
                    try:
                        # === ИСПРАВЛЕНО: Используем await + aget ===
                        analysis = await PsychoAnalysis.objects.aget(entry=first_entry)
                        # =========================================
                        analysis_text = analysis.analysis_text or analysis.comment or "Анализ записан"
                        mood_score = analysis.mood_score
                        recommendation = analysis.recommendation or "Продолжайте в том же духе"
                        # === ИСПРАВЛЕНО: Получаем текст настроения ===
                        mood_text = get_message(f'mood_{mood_score}', language)
                        # ===========================================
                    except PsychoAnalysis.DoesNotExist:
                        logger.info("Анализ для первой записи не найден")
                    except Exception as analysis_error:
                        # === ИСПРАВЛЕНО: Более конкретная обработка ошибки ===
                        logger.error(f"Ошибка при получении анализа: {analysis_error}")
                        # ==================================================
            except Exception as e:
                logger.error(f"Общая ошибка при работе с анализом: {e}")

            # === ИСПРАВЛЕНО: Передаем параметр 'mood' ===
            # Формируем сообщение с записью
            archive_entry_msg = get_message('archive_entry', language,
                date=selected_date.strftime("%d.%m.%Y"),
                text=combined_text[:1000] + "..." if len(combined_text) > 1000 else combined_text,
                score=mood_score,
                mood=mood_text, # <-- Добавлено
                analysis=analysis_text
            )
            # ==========================================
            
            # Используем клавиатуру просмотра записи
            from bot.keyboards.calendar_keyboard import get_entry_view_keyboard
            await callback.message.edit_text(archive_entry_msg, 
                reply_markup=get_entry_view_keyboard(language, year, month, day))
            logger.info(f"Показана запись за {day}.{month}.{year}")
        else:
            # Нет записей за день
            no_entries_msg = get_message('archive_empty', language)
            
            await callback.message.edit_text(no_entries_msg, 
                reply_markup=get_calendar_back_keyboard(language, year, month))
            logger.info(f"Нет записей за {day}.{month}.{year}")
            
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при выборе дня: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("delete_entry:"))
async def delete_selected_entry(callback: CallbackQuery, user, language: str):
    """Удаление выбранной записи"""
    logger.info(f"Удаление записи для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID записи из callback_data
        entry_id = int(callback.data.split(":")[1])
        logger.info(f"Удаление записи ID: {entry_id}")
        
        # Удаляем запись через сервис
        success = await delete_entry(entry_id, user)
        
        if success:
            entry_deleted_msg = get_message('entry_deleted', language)
            await callback.answer(entry_deleted_msg)
            
            # Возвращаем в архив или календарь
            from bot.keyboards.main_menu import get_back_keyboard
            back_msg = get_message('archive_menu', language)
            await callback.message.edit_text(
                back_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Запись {entry_id} успешно удалена")
        else:
            error_msg = get_message('error_generic', language)
            await callback.answer(error_msg)
            logger.warning(f"Не удалось удалить запись {entry_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data == "calendar_empty")
async def handle_empty_calendar_button(callback: CallbackQuery):
    """Обработка пустых кнопок в календаре"""
    logger.info(f"Нажата пустая кнопка календаря пользователем {callback.from_user.id}")
    # Просто подтверждаем callback без действий
    await safe_answer_callback(callback, "")

@router.callback_query(F.data == "back_to_calendar")
async def back_to_calendar(callback: CallbackQuery, user, language: str):
    """Возврат к календарю после просмотра записи"""
    logger.info(f"Возврат к календарю для пользователя {callback.from_user.id}")
    
    try:
        # Используем сохраненный месяц и год из предыдущего просмотра
        year = getattr(user, 'current_calendar_year', datetime.now().year)
        month = getattr(user, 'current_calendar_month', datetime.now().month)
        logger.info(f"Возврат к календарю: {month}.{year}")
        today = datetime.now()
        current_day = today.day if today.month == month and today.year == year else 1
        
        # Получаем название месяца
        month_names_ru = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        month_names_en = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        month_names = month_names_ru if language == 'ru' else month_names_en
        month_name = month_names[month] if 1 <= month <= 12 else ""
        
        calendar_msg = get_message('archive_select_month', language).format(
            month=month_name,
            year=year
        )
        
        await safe_edit_message_text(
            message=callback.message,
            text=calendar_msg,
            reply_markup=get_month_calendar_with_navigation(user, year, month, current_day, language)
        )
        await safe_answer_callback(callback, "")
        logger.info("Возвращен к календарю")
        
    except Exception as e:
        logger.error(f"Ошибка при возврате к календарю: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

    
# ==================== HANDLERS ДЛЯ ПРОСМОТРА ИСТОРИИ ЗАПИСЕЙ ====================

@router.callback_query(F.data.startswith("view_entry_history:"))
async def view_entry_history(callback: CallbackQuery, user, language: str):
    """Просмотр истории записей за день"""
    logger.info(f"Просмотр истории записей за день для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год, месяц и день из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        logger.info(f"Просмотр истории записей за {day}.{month}.{year}")
        
        # Получаем записи пользователя за выбранный день
        selected_date = date(year, month, day)
        entries = await get_user_entries_for_date(user, selected_date)
        
        if entries:
            # Формируем сообщение с историей записей
            history_msg = f"📝 <b>История записей за {day}.{month}.{year}</b>\n\n"
            
            for i, entry in enumerate(entries, 1):
                entry_type = "🎙 Голосовая" if hasattr(entry, 'voice_to_text') else "✍️ Текстовая"
                history_msg += f"<b>{i}. {entry_type} запись</b>\n"
                history_msg += f"🕒 {entry.created_at.strftime('%H:%M')}\n"
                history_msg += f"🔤 {entry.word_count} слов\n"
                history_msg += f"📄 {entry.text[:100]}...\n\n"
            
            # Добавляем кнопки для управления записями
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            buttons = []
            for i, entry in enumerate(entries, 1):
                buttons.append([
                    InlineKeyboardButton(
                        text=f"👁 Просмотреть запись {i}",
                        callback_data=f"view_specific_entry:{entry.id}"
                    )
                ])
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗑 Удалить запись {i}",
                        callback_data=f"delete_entry:{entry.id}"
                    )
                ])
            
            # Кнопка "Назад"
            buttons.append([
                InlineKeyboardButton(
                    text=get_message('btn_back', language),
                    callback_data=f"calendar_select_day:{year}:{month}:{day}"
                )
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(
                history_msg,
                reply_markup=keyboard
            )
            logger.info(f"Показана история {len(entries)} записей за {day}.{month}.{year}")
        else:
            # Нет записей за этот день
            no_entries_msg = get_message('archive_empty', language)
            
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                no_entries_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Нет записей за {day}.{month}.{year}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре истории записей: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_specific_entry:"))
async def view_specific_entry(callback: CallbackQuery, user, language: str):
    """Просмотр конкретной записи из истории"""
    logger.info(f"Просмотр конкретной записи из истории для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID записи из callback_data
        entry_id = int(callback.data.split(":")[1])
        logger.info(f"Просмотр записи ID: {entry_id}")
        
        # Получаем запись с проверкой владельца
        from diary.models import DiaryEntry
        try:
            entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
            
            # Получаем анализ записи (если есть)
            analysis_text = "Анализ не доступен"
            mood_score = 5
            recommendation = "Продолжайте в том же духе"
            
            # Проверяем существование анализа
            try:
                if hasattr(entry, 'analysis'):
                    from diary.models import PsychoAnalysis
                    try:
                        analysis = await PsychoAnalysis.objects.aget(entry=entry)
                        analysis_text = analysis.comment or "Анализ записан"
                        mood_score = analysis.mood_score
                        recommendation = analysis.recommendation or "Продолжайте в том же духе"
                    except PsychoAnalysis.DoesNotExist:
                        logger.info("Анализ для записи не найден")
            except Exception as analysis_error:
                logger.error(f"Ошибка при получении анализа: {analysis_error}")
                # Используем значения по умолчанию
            
            # Формируем сообщение с записью
            from messages import get_message
            specific_entry_msg = get_message(
                'archive_entry',
                language,
                date=entry.created_at.strftime("%d.%m.%Y %H:%M"),
                text=entry.text[:1000] + "..." if len(entry.text) > 1000 else entry.text,
                score=mood_score,
                analysis=analysis_text,
                recommendation=recommendation
            )
            
            # Извлекаем год, месяц и день из даты записи для кнопки "назад"
            entry_date = entry.created_at.date()
            year = entry_date.year
            month = entry_date.month
            day = entry_date.day
            
            # Используем клавиатуру просмотра конкретной записи
            from bot.keyboards.calendar_keyboard import get_specific_entry_view_keyboard
            await callback.message.edit_text(
                specific_entry_msg,
                reply_markup=get_specific_entry_view_keyboard(language, entry_id, year, month, day)
            )
            logger.info(f"Показана конкретная запись ID: {entry_id}")
            
        except DiaryEntry.DoesNotExist:
            from messages import get_message
            error_msg = get_message('entry_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре конкретной записи: {e}")
        from messages import get_message
        await callback.answer(get_message('error_generic', language))

# ==================== HANDLERS ДЛЯ РЕДАКТИРОВАНИЯ И УДАЛЕНИЯ ИСТОРИИ ЗАПИСЕЙ ====================        

@router.callback_query(F.data.startswith("edit_entry:"))
async def edit_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование записи за день"""
    logger.info(f"Редактирование записи за день для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год, месяц и день из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        logger.info(f"Редактирование записи за {day}.{month}.{year}")
        
        # Сохраняем текущий месяц и год для кнопки "назад"
        user.current_calendar_year = year
        user.current_calendar_month = month
        
        # Ищем записи за выбранный день (ИСПРАВЛЕНО!)
        from datetime import date
        from bot.services.diary_service import diary_service
        
        selected_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, selected_date)
        
        if entries:
            if len(entries) == 1:
                # Если одна запись, редактируем её напрямую
                entry = entries[0]
                
                # Сохраняем ID записи в состоянии
                from bot.utils.state_manager import state_manager
                await state_manager.set_state(state, DiaryStates.waiting_for_entry_edit)
                await state_manager.update_state_data(state, editing_entry_id=entry.id)
                
                # Предлагаем ввести новый текст (ИСПРАВЛЕНО!)
                from messages import get_message
                edit_msg = get_message('ask_entry_edit', language).format(
                    old_text=entry.text[:200] + "..." if len(entry.text) > 200 else entry.text
                )
                
                # ИСПРАВЛЕНО: используем правильную клавиатуру
                await callback.message.edit_text(
                    edit_msg,
                    reply_markup=get_cancel_keyboard(language)
                )
                logger.info(f"Предложено редактировать запись {entry.id}")
            else:
                # Если несколько записей, показываем историю
                await show_entry_history(callback, user, language, year, month, day, entries)
        else:
            # Нет записей за этот день
            from messages import get_message
            no_entries_msg = get_message(
                'archive_empty',
                language
            )
            
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                no_entries_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Нет записей за {day}.{month}.{year}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при редактировании записи: {e}", exc_info=True)
        from messages import get_message
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("edit_specific_entry:"))
async def edit_specific_entry(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование конкретной записи"""
    logger.info(f"Редактирование конкретной записи для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID записи из callback_data
        entry_id = int(callback.data.split(":")[1])
        logger.info(f"Редактирование записи ID: {entry_id}")
        
        # Получаем запись с проверкой владельца
        from diary.models import DiaryEntry
        try:
            entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
            
            # Сохраняем ID записи в состоянии
            await state_manager.set_state(state, DiaryStates.waiting_for_entry_edit)
            await state_manager.update_state_data(state, editing_entry_id=entry_id)
            
            # Предлагаем ввести новый текст (ИСПРАВЛЕНО!)
            from messages import get_message
            edit_msg = get_message('ask_entry_edit', language).format(
                old_text=entry.text[:200] + "..." if len(entry.text) > 200 else entry.text
            )
            
            # ИСПРАВЛЕНО: используем правильную клавиатуру
            await callback.message.edit_text(
                edit_msg,
                reply_markup=get_cancel_keyboard(language)
            )
            logger.info(f"Предложено редактировать запись {entry_id}")
            
        except DiaryEntry.DoesNotExist:
            from messages import get_message
            error_msg = get_message('entry_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при редактировании конкретной записи: {e}")
        from messages import get_message
        await callback.answer(get_message('error_generic', language))

@router.message(DiaryStates.waiting_for_entry_edit)
async def process_entry_edit(message: Message, state: FSMContext, user, language: str):
    """Обработка отредактированной записи"""
    logger.info(f"Обработка отредактированной записи от пользователя {message.from_user.id}")
    
    try:
        # Получаем текст новой записи
        new_text = message.text
        logger.info(f"Получен новый текст записи длиной {len(new_text)} символов")
        
        # Проверяем минимальную длину
        if len(new_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получена пустая запись при редактировании")
            return
        
        # Проверяем максимальную длину
        from core.constants import TEXT_MESSAGE_MAX_LENGTH
        if len(new_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст записи слишком длинный: {len(new_text)} символов")
            return
        
        # Получаем ID редактируемой записи из состояния
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('editing_entry_id')
        
        if not entry_id:
            error_msg = get_message('error_generic', language)
            await message.answer(error_msg)
            logger.error("Не найден ID редактируемой записи в состоянии")
            return
        
        # === ИЗМЕНЕНО: Анализ отредактированного текста ===
        # 1. Показываем сообщение об обработке анализа
        processing_msg = get_message('processing', language) # Используем существующее сообщение
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке анализа отредактированной записи")

        # 2. Получаем объект записи для дальнейшей работы (обновление, анализ)
        from diary.models import DiaryEntry
        try:
            entry_obj = await DiaryEntry.objects.aget(id=entry_id, user=user)
            logger.info(f"Запись {entry_id} найдена для обновления и анализа")
        except DiaryEntry.DoesNotExist:
            logger.error(f"Запись с ID {entry_id} не найдена для пользователя {user.telegram_id}")
            await status_message.edit_text(get_message('entry_not_found', language))
            await state_manager.clear_state(state)
            return

        # 3. Обновляем текст и мета-данные записи в БД *до* анализа
        entry_obj.text = new_text
        entry_obj.word_count = len(new_text.split())
        # entry_obj.updated_at будет обновлено автоматически при asave(), или можно явно установить
        # entry_obj.updated_at = datetime.now() 
        await entry_obj.asave(update_fields=['text', 'word_count']) # updated_at обновится автоматически
        logger.info(f"Текст записи {entry_id} успешно обновлен в БД")

        # 4. Вызываем DeepSeek API для анализа нового текста
        from bot.services.deepseek_api import deepseek_api_service
        analysis_result = await deepseek_api_service.analyze_text(
            text=new_text, # <-- Новый текст
            language=language,
            analysis_type='emotion' # Или другой нужный тип
        )

        # 5. Обрабатываем результат анализа (используем вашу улучшенную логику)
        mood_score = 5
        comment = 'Анализ записан'
        recommendation = 'Продолжайте в том же духе'
        analysis_text = "Анализ не доступен"

        try:
            logger.info(f"Обработка результата повторного анализа. Success: {analysis_result.get('success', 'unknown')}")
            logger.debug(f"Полный результат анализа: {analysis_result}") # Для отладки

            if analysis_result.get('success', False):
                result_data = analysis_result.get('result', {})
                logger.debug(f"Данные результата (result): {result_data}")

                # Функция для безопасного извлечения значения из словаря
                def safe_get(data, key, default):
                    if isinstance(data, dict):
                        return data.get(key, default)
                    return default

                # Пытаемся извлечь данные
                if isinstance(result_data, dict):
                    mood_score = safe_get(result_data, 'mood_score', mood_score)
                    comment = safe_get(result_data, 'comment', comment)
                    recommendation = safe_get(result_data, 'recommendation', recommendation)
                    analysis_text = safe_get(result_data, 'analysis', analysis_text)
                    # Если analysis_text пуст, попробуем взять comment
                    if not analysis_text or analysis_text == "Анализ не доступен":
                         analysis_text = comment
                else:
                    # Если result_data не словарь, используем его как analysis_text
                    analysis_text = str(result_data) if result_data else analysis_text

                # Если не удалось извлечь осмысленные данные, используем message из API ответа
                if mood_score == 5 and comment == 'Анализ записан':
                     api_message = analysis_result.get('message', '')
                     if api_message and api_message != 'Текст успешно проанализирован':
                          comment = f"{comment} ({api_message})"

                logger.info(f"Повторный анализ успешно обработан. Оценка: {mood_score}/10")
            else:
                # Обработка ошибки API
                error_msg = analysis_result.get('message', 'Неизвестная ошибка API')
                logger.error(f"Ошибка API при повторном анализе: {error_msg}")
                comment = f'Анализ записан (ошибка API: {error_msg})'
                recommendation = 'Попробуйте позже'
                analysis_text = f"Анализ не доступен из-за ошибки: {error_msg}"

        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке результата повторного анализа: {e}", exc_info=True)
            comment = 'Анализ записан (ошибка обработки результата)'
            recommendation = 'Попробуйте позже'
            analysis_text = "Анализ не доступен из-за внутренней ошибки"

        logger.info(f"Отредактированная запись проанализирована, оценка: {mood_score}/10")

        # 6. Извлекаем ответ API для сохранения
        api_response_data = analysis_result.get('api_response', {})

        # 7. Обновляем анализ в БД
        try:
            from bot.services.diary_service import diary_service
            # Предполагается, что entry_obj - это объект DiaryEntry
            await diary_service.update_entry_analysis(
                entry=entry_obj, # Передаем объект записи
                mood_score=mood_score,
                comment=comment,
                recommendation=recommendation,
                analysis_text=analysis_text,
                api_response=api_response_data # Передаем ответ API
            )
            logger.info("Анализ отредактированной записи обновлен в БД")
        except Exception as db_error:
            logger.error(f"Ошибка при обновлении анализа отредактированной записи в БД: {db_error}")

        # 8. Очищаем состояние
        await state_manager.clear_state(state)
        
        # 9. Формируем и отправляем финальное сообщение с реальными данными анализа
        entry_updated_msg = get_message(
            'entry_updated',
            language,
            score=mood_score,
            mood=get_message(f'mood_{mood_score}', language), # Получаем текст настроения
            comment=comment,
            recommendation=recommendation
            # analysis=analysis_text - если хотите добавить в шаблон
        )

        # Редактируем сообщение о процессе (предпочтительнее)
        await status_message.edit_text(entry_updated_msg, reply_markup=get_back_keyboard(language))

        logger.info("Отредактированная запись успешно проанализирована и сохранена")

    except Exception as e:
        logger.error(f"Ошибка при обработке отредактированной записи: {e}", exc_info=True)
        # Пытаемся сообщить об ошибке
        try:
            await message.answer(get_message('error_processing', language))
        except:
             try:
                 # Если message.answer не работает, пытаемся отредактировать status_message
                 await status_message.edit_text(get_message('error_processing', language))
             except:
                 pass # Игнорируем ошибки при отправке сообщения об ошибке

@router.callback_query(F.data.startswith("delete_entry:"))
async def delete_entry(callback: CallbackQuery, user, language: str):
    """Удаление записи за день"""
    logger.info(f"Удаление записи за день для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем год, месяц и день из callback_data
        parts = callback.data.split(":")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        logger.info(f"Удаление записи за {day}.{month}.{year}")
        
        # Получаем записи пользователя за выбранный день
        from datetime import date
        from bot.services.diary_service import diary_service
        
        selected_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, selected_date)
        
        if entries:
            if len(entries) == 1:
                # Если одна запись, подтверждаем удаление
                entry = entries[0]
                confirm_msg = get_message('confirm_delete_entry', language)
                
                from bot.keyboards.calendar_keyboard import get_confirm_delete_keyboard
                await callback.message.edit_text(
                    confirm_msg,
                    reply_markup=get_confirm_delete_keyboard(language, entry.id)
                )
                logger.info(f"Запрошено подтверждение удаления записи {entry.id}")
            else:
                # Если несколько записей, показываем историю для выбора
                await show_entry_history(callback, user, language, year, month, day, entries)
        else:
            # Нет записей за этот день
            no_entries_msg = get_message('archive_empty', language)
            
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                no_entries_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Нет записей за {day}.{month}.{year}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при удалении записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("delete_specific_entry:"))
async def delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Удаление конкретной записи"""
    logger.info(f"Удаление конкретной записи для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID записи из callback_data
        entry_id = int(callback.data.split(":")[1])
        logger.info(f"Удаление записи ID: {entry_id}")
        
        # Подтверждаем удаление
        confirm_msg = get_message('confirm_delete_entry', language)
        
        from bot.keyboards.calendar_keyboard import get_confirm_delete_keyboard
        await callback.message.edit_text(
            confirm_msg,
            reply_markup=get_confirm_delete_keyboard(language, entry_id)
        )
        await callback.answer()
        logger.info(f"Запрошено подтверждение удаления записи {entry_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при запросе удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("confirm_delete_entry:"))
async def confirm_delete_entry(callback: CallbackQuery, user, language: str):
    """Подтверждение удаления записи"""
    logger.info(f"Подтверждение удаления записи для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем ID записи из callback_data
        entry_id = int(callback.data.split(":")[1])
        logger.info(f"Подтверждение удаления записи ID: {entry_id}")
        
        # Удаляем запись через сервис
        from bot.services.diary_service import diary_service
        success = await diary_service.delete_entry(entry_id, user)
        
        if success:
            entry_deleted_msg = get_message('entry_deleted', language)
            
            from bot.keyboards.main_menu import get_back_keyboard
            await callback.message.edit_text(
                entry_deleted_msg,
                reply_markup=get_back_keyboard(language)
            )
            logger.info(f"Запись {entry_id} успешно удалена")
        else:
            error_msg = get_message('entry_not_found', language)
            await callback.answer(error_msg)
            logger.warning(f"Не удалось удалить запись {entry_id}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data == "cancel_delete_entry")
async def cancel_delete_entry(callback: CallbackQuery, language: str):
    """Отмена удаления записи"""
    logger.info(f"Отмена удаления записи для пользователя {callback.from_user.id}")
    
    try:
        cancel_msg = get_message('entry_delete_cancelled', language)
        
        from bot.keyboards.main_menu import get_back_keyboard
        await callback.message.edit_text(
            cancel_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Удаление записи отменено")
        
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления записи: {e}")
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_assigned_task(callback: CallbackQuery, user, language: str):
    """
    Обработчик нажатия кнопки "Отменить задание".
    Удаляет назначенное задание, показывает уведомление и обновляет исходное сообщение.
    """
    logger.info(f"Пользователь {callback.from_user.id} запросил отмену задания через callback.")
    try:
        # --- Извлечение ID задания и ID сообщения ---
        parts = callback.data.split(":")
        if len(parts) < 2:
             raise ValueError("Некорректный формат callback_data")
        task_id_str = parts[1]
        task_id = int(task_id_str)
        
        # Извлекаем message_id, если он есть
        original_message_id = None
        if len(parts) > 2:
            try:
                original_message_id = int(parts[2])
                logger.info(f"ID исходного сообщения из callback_data: {original_message_id}")
            except ValueError:
                logger.warning(f"Некорректный формат message_id в callback_data: {parts[2]}")
        # -----------------------------------------------------

        logger.info(f"Попытка отмены (удаления) задания ID: {task_id}")

        # --- Получение и удаление задания ---
        try:
            # Получаем задание, принадлежащее пользователю
            task_to_cancel = await TherapyTask.objects.aget(id=task_id, user=user)
            task_title = task_to_cancel.title
            logger.info(f"Задание '{task_title}' (ID: {task_id}) найдено.")
            
            # Удаляем задание асинхронно
            await task_to_cancel.adelete()
            logger.info(f"Задание '{task_title}' (ID: {task_id}) успешно удалено.")
            
            # --- Отправка show_alert пользователю ---
            confirmation_message = get_message(
                'task_cancelled_confirmation',
                language,
                title=task_title
            )
            await safe_answer_callback(callback, confirmation_message, show_alert=True)
            logger.info("Пользователю отправлено show_alert о подтверждении отмены задания.")
            # ---------------------------------------
            
            # --- ОБНОВЛЕНИЕ ИСХОДНОГО СООБЩЕНИЯ ---
            # Цель: Убрать информацию о задании и кнопки.
            try:
                # --- Получаем связанную DiaryEntry ---
                diary_entry = task_to_cancel.related_entry # Получаем связанную запись
                if not diary_entry:
                    raise ValueError("Задание не связано с записью дневника")
                logger.debug(f"Связанная DiaryEntry: {diary_entry.id}")
                # ------------------------------------

                # --- Получаем связанный PsychoAnalysis ---
                try:
                    psycho_analysis = await diary_entry.analysis.aget() # aget для OneToOne
                    logger.debug("PsychoAnalysis успешно загружен.")
                except PsychoAnalysis.DoesNotExist:
                    logger.error("PsychoAnalysis не найден для связанной DiaryEntry.")
                    raise ValueError("Анализ записи не найден.")
                # ---------------------------------------

                # --- Формируем новое сообщение без информации о задании ---
                entry_saved_msg = get_message(
                    'entry_saved',
                    language,
                    score=psycho_analysis.mood_score,
                    mood=get_message(f'mood_{psycho_analysis.mood_score}', language),
                    comment=psycho_analysis.comment,
                    recommendation=psycho_analysis.recommendation
                    # analysis=psycho_analysis.analysis_text - можно добавить, если нужно
                )
                # ----------------------------------------------------------

                # --- Отправляем обновлённое сообщение ---
                # Используем существующую утилиту для безопасного редактирования
                # Всегда используем клавиатуру "Назад"
                await safe_edit_message_text(
                    message=callback.message, # Сообщение с кнопкой "Отменить задание"
                    text=entry_saved_msg,
                    reply_markup=get_back_keyboard(language) # Клавиатура "Назад"
                )
                logger.info("Исходное сообщение обновлено: информация о задании и кнопки удалены.")
                # ---------------------------------------

            except Exception as edit_error:
                logger.warning(f"Не удалось обновить исходное сообщение после отмены задания: {edit_error}")
                # Если не удалось отредактировать, ничего критичного. show_alert был отправлен.
            
            # ------------------------------------

        except TherapyTask.DoesNotExist:
            logger.warning(f"Задание ID {task_id} не найдено или не принадлежит пользователю {user.telegram_id}.")
            await safe_answer_callback(
                callback, 
                get_message('task_not_found_for_cancellation', language),
                show_alert=True
            )
        # -----------------------------------

    except ValueError as ve:
        logger.error(f"Некорректные данные в callback_data: {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отмене задания через callback: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_processing', language), show_alert=True)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def show_entry_history(callback: CallbackQuery, user, language: str, year: int, month: int, day: int, entries: list):
    """Показ истории записей за день"""
    logger.info(f"Показ истории записей за {day}.{month}.{year} для пользователя {callback.from_user.id}")
    
    try:
        # Формируем сообщение с историей записей
        history_msg = f"📝 <b>История записей за {day}.{month}.{year}</b>\n\n"
        
        for i, entry in enumerate(entries, 1):
            def _format_entry_for_history(e):
                return {
                'type': "🎙 Голосовая" if hasattr(e, 'voice_to_text') else "✍️ Текстовая",
                'time': e.localized_created_at, # <-- Теперь это безопасный синхронный вызов
                'date': e.entry_date.strftime('%d.%m.%Y'),
                'words': e.word_count,
                'preview': e.text[:100] + "..." if len(e.text) > 100 else e.text
            }
            entry_data = await sync_to_async(_format_entry_for_history)(entry)
    
            history_msg += f"\n<b>{i}. {entry_data['type']} запись</b>\n"
            history_msg += f"🕒 Время: {entry_data['time']}\n" # <-- Используем результат
            history_msg += f"🔤 Слов: {entry_data['words']}\n"
            history_msg += f"📄 {entry_data['preview']}\n"
        
        # Используем клавиатуру истории записей
        from bot.keyboards.calendar_keyboard import get_entry_history_keyboard
        await callback.message.edit_text(
            history_msg,
            reply_markup=get_entry_history_keyboard(language, entries, year, month, day)
        )
        logger.info(f"Показана история {len(entries)} записей за {day}.{month}.{year}")
        
    except Exception as e:
        logger.error(f"Ошибка при показе истории записей: {e}")
        await callback.answer(get_message('error_generic', language))

async def _get_user_profile_data(user, language: str) -> dict:
    """Получение данных профиля пользователя для API."""
    return {
        'username': user.username or f"user_{user.telegram_id}",
        'first_name': user.first_name or "",
        'language': user.language,
        'awareness_level': user.awareness_level,
        # Добавить другие релевантные данные при необходимости
    }

async def _get_user_local_datetime(user) -> datetime:
    """Получение текущего времени в часовом поясе пользователя."""
    try:
        user_tz_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_tz_str)
        user_local_datetime = datetime.now(user_tz)
        return user_local_datetime
    except Exception as e:
        logger.error(f"Ошибка при получении локального времени пользователя: {e}")
        return datetime.now(pytz.utc)

async def _show_final_analysis_result(
    status_message: Message, 
    diary_entry, 
    analysis_result: dict, 
    language: str
):
    """Показ финального результата анализа"""
    logger.info(f"Показ финального результата анализа для записи {diary_entry.id}")
    
    try:
        # Извлекаем данные анализа
        analysis_data = analysis_result.get('result', {})
        mood_score = analysis_data.get('mood_score', 5)
        comment = analysis_data.get('comment', 'Анализ записан')
        recommendation = analysis_data.get('recommendation', 'Продолжайте в том же духе')
        analysis_text = analysis_data.get('analysis', 'Анализ выполнен')
        
        # Форматируем сообщение с результатом
        entry_saved_msg = get_message(
            'entry_saved', 
            language,
            score=mood_score,
            mood=get_message(f'mood_{mood_score}', language),
            comment=comment,
            recommendation=recommendation,
            analysis=analysis_text
        )
        
        # Обновляем запись в БД с результатами анализа
        from bot.services.diary_service import diary_service
        await diary_service.update_entry_analysis(
            entry_id=diary_entry.id,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text
        )
        logger.info(f"Анализ записи {diary_entry.id} обновлен в БД")
        
        from bot.keyboards.main_menu import get_back_keyboard
        await status_message.edit_text(
            entry_saved_msg,
            reply_markup=get_back_keyboard(language)
        )
        logger.info("Финальный результат анализа показан")
        
    except Exception as e:
        logger.error(f"Ошибка при показе финального результата анализа: {e}")
        await status_message.edit_text(get_message('error_processing', language))

async def _get_or_update_combined_entry(user, diary_entry: DiaryEntry):
    """Получает или создает/обновляет CombinedDiaryEntry."""
    entry_date = diary_entry.entry_date
    combined_entry = await daily_state_service.get_daily_state(user, entry_date)
    
    if combined_entry is None:
        logger.info("Первая запись дня. Создаем CombinedDiaryEntry.")
        combined_entry = await daily_state_service.create_daily_state_from_entry(diary_entry)
        is_first_entry_of_day = True
    else:
        logger.info("Последующая запись дня. Обновляем текст в CombinedDiaryEntry.")
        combined_text = await diary_service.get_combined_entry_text(user, entry_date)
        entries_today = await diary_service.get_user_entries_for_date(user, entry_date)
        entry_count = len(entries_today)
        await daily_state_service.update_daily_state_text_and_count(
            combined_entry, combined_text, entry_count
        )
        is_first_entry_of_day = False
        
    return combined_entry, is_first_entry_of_day

async def _perform_analysis(is_first, combined_entry, text, profile, lang):
    """Выбирает и выполняет метод анализа."""
    if is_first:
        logger.info("Вызов analyze_text_with_profile для первой записи дня")
        return await deepseek_api_service.analyze_text_with_profile(
            text=text, user_profile=profile, language=lang
        )
    else:
        logger.info("Вызов analyze_text_with_previous_state для последующей записи дня")
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

async def _handle_analysis_result(entry: DiaryEntry, analysis_result: dict, status_msg, language: str, state: FSMContext, user):
    """
    Обрабатывает результат анализа и выполняет все последующие действия.
    """
    try:
        logger.info("Начало обработки результата анализа.")
        
        # --- 1. ИЗВЛЕЧЕНИЕ ДАННЫХ АНАЛИЗА ---
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
            logger.error(f"Ошибка анализа API: {analysis_result.get('error', 'Unknown error')}")
            # Обработка ошибки API
            error_type = analysis_result.get('error', 'unknown_error')
            error_message = analysis_result.get('message', 'Неизвестная ошибка API')
            logger.error(f"Ошибка анализа API: {error_type} - {error_message}")
            
            # Устанавливаем значения по умолчанию с пометкой об ошибке
            if error_type == 'timeout':
                comment = 'Анализ записан (превышено время ожидания)'
            else:
                comment = f'Анализ записан (ошибка API: {error_type})'
            recommendation = 'Попробуйте позже'
            analysis_text = f"Анализ не доступен из-за ошибки API: {error_message}"
            # result_data, suggested_task_data, needs_clarification, clarification_questions остаются по умолчанию
        else:
            # Успешный результат API
            logger.info("Анализ API завершен успешно.")
            api_response_data = analysis_result.get('api_response', {})
            result_data_raw = analysis_result.get('result', {})
            if not isinstance(result_data_raw, dict):
                logger.error("Поле 'result' в ответе API не является словарем.")
                result_data = {}
            else:
                result_data = result_data_raw
                
            # Извлекаем данные из result_data с валидацией
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

        logger.info(f"Данные анализа извлечены. Оценка: {mood_score}/10, Требуются уточнения: {needs_clarification}")
        # =================================

        # --- 2. ОБРАБОТКА УТОЧНЕНИЙ ---
        if needs_clarification and clarification_questions:
            logger.info("Требуются уточнения. Переводим в состояние уточнения.")
            
            try:
                entry.clarification_questions_asked = clarification_questions
                await sync_to_async(entry.save)(update_fields=['clarification_questions_asked'])
                logger.info(f"Вопросы уточнений сохранены в DiaryEntry ID {entry.id}")
            except Exception as save_error:
                logger.error(f"Ошибка при сохранении clarification_questions_asked в DiaryEntry ID {entry.id}: {save_error}")
            
            await state_manager.update_state_data(
                state,
                clarifying_entry_id=entry.id,
                clarification_questions=clarification_questions
            )
            await state_manager.set_state(state, DiaryStates.asking_clarifying_questions)
            
            questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clarification_questions)])
            clarification_msg = f"{get_message('clarification_needed', language)}\n\n{questions_text}"
            
            await status_msg.edit_text(
                clarification_msg,
                reply_markup=get_cancel_keyboard(language)
            )
            logger.info(f"Отправлено {len(clarification_questions)} вопросов для уточнения.")
            return
        # ============================

        # --- 3. ОБРАБОТКА РЕЗУЛЬТАТА БЕЗ УТОЧНЕНИЙ ---
        logger.info("Обработка результата без уточнений.")

        # --- Создание/Обновление PsychoAnalysis ---
        logger.info("Создание/обновление PsychoAnalysis для записи.")
        psycho_analysis = await diary_service.create_initial_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=api_response_data
        )
        logger.info(f"PsychoAnalysis создан/обновлен, ID: {psycho_analysis.id}")
        # --------------------------------------------

        # --- Обновление CombinedDiaryEntry.ai_state_data ---
        logger.info("Обновление состояния дня (CombinedDiaryEntry).")
        combined_entry = await daily_state_service.get_daily_state(user, entry.entry_date)
        update_success = False
        if combined_entry:
            new_ai_state_data = analysis_text
            update_success = await daily_state_service.update_daily_state(
                combined_entry, new_ai_state_data, latest_mood_score=mood_score
            )
            logger.info(f"CombinedDiaryEntry.ai_state_data обновлен: {'Успешно' if update_success else 'Ошибка'}")
        else:
            logger.warning("CombinedDiaryEntry не найден для обновления состояния.")
        # ---------------------------------------------------

        # --- (Асинхронно) Обновление инсайтов ---
        logger.info("Обновление инсайтов и ключевых моментов...")
        try:
            from diary.services.analysis_service import analysis_service
            await analysis_service.extract_and_save_insights_and_keypoints(entry, result_data)
            logger.info("Инсайты и ключевые моменты пользователя обновлены.")
        except Exception as insight_error:
            logger.error(f"Ошибка при обновлении инсайтов: {insight_error}")
        # -----------------------------------------

        # --- (Асинхронно) Обработка задания от ИИ ---
        task_info_text = ""
        final_reply_markup = None # <-- Инициализируем как None
        
        if suggested_task_data and isinstance(suggested_task_data, dict):
            logger.info("Обнаружено предложенное задание от ИИ. Обработка...")
            
            therapy_task = await _create_task_from_suggested_data(
                user, suggested_task_data, entry.entry_date, related_diary_entry=entry
            )
            
            if therapy_task:
                logger.info(f"Задание от ИИ создано, ID: {therapy_task.id}")
                
                # --- Формирование текста о задании ---
                task_desc_preview = therapy_task.description[:150] + "..." if len(therapy_task.description) > 150 else therapy_task.description
                task_info_text = f"\n\n📌 <b>Новое задание от ИИ:</b>\n<b>{therapy_task.title}</b>\n{task_desc_preview}"
                # -------------------------------------
                
                # --- НОВОЕ: Создание клавиатуры действий с заданием ---
                # Получаем активные задания пользователя для пагинации
                task_index = 0
                if therapy_task:
                    final_reply_markup = get_task_pagination_keyboard(
                        task_id=therapy_task.id,
                        current_index=task_index,
                        total_tasks=1,
                        language=language
                    )
                    logger.info(f"Клавиатура действий с заданием создана для задания ID {therapy_task.id}.")
                else:
                    # На всякий случай, если задания не нашлись
                    logger.warning("Не удалось получить активные задания для клавиатуры пагинации.")
                    final_reply_markup = get_back_keyboard(language)                
                '''active_tasks = await diary_service.get_user_active_tasks(user)
                if active_tasks:
                    # Находим индекс созданного задания
                    task_index = next((i for i, t in enumerate(active_tasks) if t.id == therapy_task.id), 0)
                    # Создаем клавиатуру с пагинацией и действиями
                    final_reply_markup = get_task_pagination_keyboard(
                        task_id=therapy_task.id,
                        current_index=task_index,
                        total_tasks=len(active_tasks),
                        language=language
                    )
                    logger.info(f"Клавиатура действий с заданием создана для задания ID {therapy_task.id}.")
                else:
                    # На всякий случай, если задания не нашлись
                    logger.warning("Не удалось получить активные задания для клавиатуры пагинации.")
                    final_reply_markup = get_back_keyboard(language)'''
            else:
                logger.warning("Не удалось создать задание от ИИ.")
                # Можно добавить короткое сообщение об ошибке создания задания
                # task_info_text = "\n\n⚠️ <i>Ошибка при создании задания от ИИ.</i>"
                final_reply_markup = get_back_keyboard(language)
        else:
            logger.info("Задание от ИИ не предложено или данные некорректны.")
            # --- НОВОЕ: Клавиатура "Назад" если задания нет ---
            final_reply_markup = get_back_keyboard(language)
            # --------------------------------------------------
        # -------------------------------------------

        # --- Отправка финального результата пользователю ---
        entry_saved_msg = get_message(
            'entry_saved',
            language,
            score=mood_score,
            mood=get_message(f'mood_{mood_score}', language),
            comment=comment,
            recommendation=recommendation
        )

        final_message_text = entry_saved_msg + task_info_text
        
        # Используем сформированную клавиатуру (с действиями или "Назад")
        await status_msg.edit_text(
            final_message_text,
            reply_markup=final_reply_markup
        )
        logger.info("Финальный результат анализа (с информацией о задании и кнопками) отправлен пользователю.")
        # ---------------------------------------------------

        # --- Очистка состояния FSM ---
        logger.info("Очистка состояния FSM.")
        await state_manager.clear_state(state)
        # -----------------------------

        logger.info("Обработка результата анализа успешно завершена.")

    except Exception as e:
        logger.error(f"Критическая ошибка в _handle_analysis_result: {e}", exc_info=True)
        try:
            await status_msg.edit_text(get_message('error_processing', language))
        except:
            pass
        await state_manager.clear_state(state)
        raise 

# === ОБНОВЛЁННЫЙ _handle_final_analysis_result ===
async def _handle_final_analysis_result(entry: DiaryEntry, final_analysis_result: dict, status_msg, language: str, state: FSMContext, user):
    """
    Обрабатывает финальный результат анализа (после уточнений) и выполняет все последующие действия.
    """
    try:
        logger.info("Начало обработки ФИНАЛЬНОГО результата анализа (после уточнений).")
        
        # --- ИЗВЛЕЧЕНИЕ ДАННЫХ ФИНАЛЬНОГО АНАЛИЗА ---
        mood_score = 5
        comment = 'Анализ записан'
        recommendation = 'Продолжайте в том же духе'
        analysis_text = "Текст проанализирован."
        api_response_data = {}
        suggested_task_data = None
        result_data = {}

        if not final_analysis_result or not final_analysis_result.get('success', False):
            logger.error(f"Ошибка финального анализа API: {final_analysis_result.get('error', 'Unknown error')}")
            mood_score = 5
            comment = 'Анализ записан (ошибка API)'
            recommendation = 'Попробуйте позже'
            analysis_text = "Финальный анализ не доступен из-за ошибки API"
            api_response_data = final_analysis_result.get('api_response', {}) if final_analysis_result else {}
            suggested_task_data = None
            result_data = {}
        else:
            result_data_raw = final_analysis_result.get('result', {})
            if not isinstance(result_data_raw, dict):
                logger.error("Поле 'result' в ответе финального API не является словарем.")
                result_data = {}
            else:
                result_data = result_data_raw
                
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте в том же духе')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')
            api_response_data = final_analysis_result.get('api_response', {})
            suggested_task_data = result_data.get('suggested_task')
            
            if mood_score is None or not (1 <= mood_score <= 10):
                mood_score = 5
            if not comment or not isinstance(comment, str):
                comment = 'Анализ записан'
            if not recommendation or not isinstance(recommendation, str):
                recommendation = 'Продолжайте в том же духе'
            if not analysis_text or not isinstance(analysis_text, str):
                analysis_text = 'Текст проанализирован.'
            if not isinstance(suggested_task_data, dict) and suggested_task_data is not None:
                logger.warning(f"Некорректное значение suggested_task: {suggested_task_data}. Игнорируется.")
                suggested_task_data = None
                
        logger.info(f"Данные финального анализа извлечены. Оценка: {mood_score}/10")
        # ------------------------------------

        # --- Создание/Обновление PsychoAnalysis ---
        logger.info("Создание/обновление PsychoAnalysis для записи после уточнений.")
        psycho_analysis = await diary_service.create_initial_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=api_response_data
        )
        logger.info(f"PsychoAnalysis (после уточнений) создан/обновлен, ID: {psycho_analysis.id}")
        # --------------------------------------------

        # --- Обновление CombinedDiaryEntry.ai_state_data ---
        logger.info("Обновление состояния дня (CombinedDiaryEntry) после финального анализа.")
        combined_entry = await daily_state_service.get_daily_state(user, entry.entry_date)
        update_success = False
        if combined_entry:
            new_ai_state_data = analysis_text
            update_success = await daily_state_service.update_daily_state(
                combined_entry, new_ai_state_data, latest_mood_score=mood_score
            )
            logger.info(f"CombinedDiaryEntry.ai_state_data обновлен: {'Успешно' if update_success else 'Ошибка'}")
        else:
            logger.warning("CombinedDiaryEntry не найден для обновления состояния после финального анализа.")
        # ---------------------------------------------------

        # --- (Асинхронно) Обновление инсайтов ---
        logger.info("Обновление инсайтов и ключевых моментов (после уточнений)...")
        try:
            from diary.services.analysis_service import analysis_service
            await analysis_service.extract_and_save_insights_and_keypoints(entry, result_data)
            logger.info("Инсайты и ключевые моменты пользователя обновлены (после уточнений).")
        except Exception as insight_error:
            logger.error(f"Ошибка при обновлении инсайтов (после уточнений): {insight_error}")
        # -----------------------------------------

        # --- (Асинхронно) Обработка задания от ИИ ---
        task_info_text = ""
        final_reply_markup = None # <-- Инициализируем как None
        
        if suggested_task_data and isinstance(suggested_task_data, dict):
            logger.info("Обнаружено предложенное задание от ИИ (после уточнений). Обработка...")
            
            therapy_task = await _create_task_from_suggested_data(
                user, suggested_task_data, entry.entry_date, related_diary_entry=entry
            )
            
            if therapy_task:
                logger.info(f"Задание от ИИ (после уточнений) создано, ID: {therapy_task.id}")
                
                # --- Формирование текста о задании ---
                task_desc_preview = therapy_task.description[:150] + "..." if len(therapy_task.description) > 150 else therapy_task.description
                task_info_text = f"\n\n📌 <b>Новое задание от ИИ:</b>\n<b>{therapy_task.title}</b>\n{task_desc_preview}"
                # -------------------------------------
                
                # --- НОВОЕ: Создание клавиатуры действий с заданием ---
                # Получаем активные задания пользователя для пагинации
                task_index = 0
                if therapy_task:
                    final_reply_markup = get_task_pagination_keyboard(
                        task_id=therapy_task.id,
                        current_index=task_index,
                        total_tasks=1,
                        language=language
                    )
                    logger.info(f"Клавиатура действий с заданием создана для задания ID {therapy_task.id}.")
                else:
                    # На всякий случай, если задания не нашлись
                    logger.warning("Не удалось получить активные задания для клавиатуры пагинации.")
                    final_reply_markup = get_back_keyboard(language)  
                '''active_tasks = await diary_service.get_user_active_tasks(user)
                if active_tasks:
                    # Находим индекс созданного задания
                    task_index = next((i for i, t in enumerate(active_tasks) if t.id == therapy_task.id), 0)
                    # Создаем клавиатуру с пагинацией и действиями
                    final_reply_markup = get_task_pagination_keyboard(
                        task_id=therapy_task.id,
                        current_index=task_index,
                        total_tasks=len(active_tasks),
                        language=language
                    )
                    logger.info(f"Клавиатура действий с заданием (после уточнений) создана для задания ID {therapy_task.id}.")
                else:
                    # На всякий случай, если задания не нашлись
                    logger.warning("Не удалось получить активные задания для клавиатуры пагинации (после уточнений).")
                    final_reply_markup = get_back_keyboard(language)'''
            else:
                logger.warning("Не удалось создать задание от ИИ (после уточнений).")
                # Можно добавить короткое сообщение об ошибке создания задания
                # task_info_text = "\n\n⚠️ <i>Ошибка при создании задания от ИИ.</i>"
                final_reply_markup = get_back_keyboard(language)
        else:
            logger.info("Задание от ИИ не предложено или данные некорректны (после уточнений).")
            # --- НОВОЕ: Клавиатура "Назад" если задания нет ---
            final_reply_markup = get_back_keyboard(language)
            # --------------------------------------------------
        # -------------------------------------------

        # --- Отправка финального результата пользователю ---
        entry_saved_msg = get_message(
            'entry_saved',
            language,
            score=mood_score,
            mood=get_message(f'mood_{mood_score}', language),
            comment=comment,
            recommendation=recommendation
        )

        final_message_text = entry_saved_msg + task_info_text
        
        # Используем сформированную клавиатуру (с действиями или "Назад")
        await status_msg.edit_text(
            final_message_text,
            reply_markup=final_reply_markup
        )
        logger.info("Финальный результат анализа (после уточнений, с информацией о задании и кнопками) отправлен пользователю.")
        # ---------------------------------------------------

        # --- Очистка состояния FSM ---
        logger.info("Очистка состояния FSM после финальной обработки.")
        await state_manager.clear_state(state)
        # -----------------------------

        logger.info("Обработка ФИНАЛЬНОГО результата анализа успешно завершена.")

    except Exception as e:
        logger.error(f"Критическая ошибка в _handle_final_analysis_result: {e}", exc_info=True)
        try:
            await status_msg.edit_text(get_message('error_processing', language))
        except:
            pass
        await state_manager.clear_state(state)
        raise 

# === ОБНОВЛЁННЫЙ ОБРАБОТЧИК: Отмена задания ===
@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_assigned_task(callback: CallbackQuery, user, language: str):
    """
    Обработчик нажатия кнопки "Отменить задание".
    Удаляет назначенное задание и обновляет исходное сообщение.
    """
    logger.info(f"Пользователь {callback.from_user.id} запросил отмену задания через callback.")
    try:
        # --- Извлечение ID задания ---
        parts = callback.data.split(":")
        if len(parts) < 2:
             raise ValueError("Некорректный формат callback_data")
        task_id_str = parts[1]
        task_id = int(task_id_str)
        logger.info(f"Попытка отмены (удаления) задания ID: {task_id}")
        # -----------------------------------------------------

        # --- Получение и удаление задания ---
        try:
            task_to_cancel = await TherapyTask.objects.aget(id=task_id, user=user)
            task_title = task_to_cancel.title
            logger.info(f"Задание '{task_title}' (ID: {task_id}) найдено.")
            
            await task_to_cancel.adelete()
            logger.info(f"Задание '{task_title}' (ID: {task_id}) успешно удалено.")
            
            # --- Отправка show_alert пользователю ---
            confirmation_message = get_message(
                'task_cancelled_confirmation',
                language,
                title=task_title
            )
            await safe_answer_callback(callback, confirmation_message, show_alert=True)
            logger.info("Пользователю отправлено show_alert о подтверждении отмены задания.")
            # ---------------------------------------
            
            # --- ОБНОВЛЕНИЕ ИСХОДНОГО СООБЩЕНИЯ ---
            # Цель: Убрать информацию о задании и кнопки действий с заданием.
            try:
                # Формируем сообщение без информации о задании
                # Нам нужно получить DiaryEntry, связанную с этим заданием
                diary_entry = task_to_cancel.related_entry
                if not diary_entry:
                    raise ValueError("Задание не связано с записью дневника")
                
                # Получаем анализ записи
                psycho_analysis = await diary_entry.analysis.aget()
                
                # Формируем сообщение без задания, используя данные анализа
                entry_saved_msg = get_message(
                    'entry_saved',
                    language,
                    score=psycho_analysis.mood_score,
                    mood=get_message(f'mood_{psycho_analysis.mood_score}', language),
                    comment=psycho_analysis.comment,
                    recommendation=psycho_analysis.recommendation
                )
                
                # Отправляем обновленное сообщение с клавиатурой "Назад"
                await safe_edit_message_text(
                    message=callback.message,
                    text=entry_saved_msg,
                    reply_markup=get_back_keyboard(language)
                )
                logger.info("Исходное сообщение обновлено: информация о задании и кнопки действий с заданием удалены.")
                
            except Exception as edit_error:
                logger.warning(f"Не удалось обновить исходное сообщение после отмены задания: {edit_error}")
                # Если не удалось отредактировать, ничего критичного. show_alert был отправлен.
            
            # ------------------------------------

        except TherapyTask.DoesNotExist:
            logger.warning(f"Задание ID {task_id} не найдено или не принадлежит пользователю {user.telegram_id}.")
            await safe_answer_callback(
                callback, 
                get_message('task_not_found_for_cancellation', language),
                show_alert=True
            )
        # -----------------------------------

    except ValueError as ve:
        logger.error(f"Некорректные данные в callback_data: {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отмене задания через callback: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_processing', language), show_alert=True)

async def _create_task_from_suggested_data(user, task_data: dict, entry_date: date, related_diary_entry: DiaryEntry = None):
    """
    Создает TherapyTask из данных, предложенных ИИ.
    
    Args:
        user: Объект пользователя Django.
        task_data: Словарь с данными задания от API.
        entry_date: Дата записи, к которой относится задание.
    """
    logger.info("Начало создания задания из данных ИИ.")
    try:
        # --- Проверка на существование задания за день ---
        # TODO: Реализовать проверку, было ли уже задание назначено в этот день.
        # Например, можно искать последнее задание пользователя, созданное сегодня.
        # Пока что создаем новое задание без проверки.
        # --------------------------------------------------

        # Импортируем сервис заданий
        
        
        # --- Обработка и валидация данных задания ---
        title = task_data.get('title', 'Задание от ИИ')
        description = task_data.get('description', 'Выполните задание, предложенное ИИ.')
        task_type_raw = task_data.get('type', 'daily')
        priority_str = task_data.get('priority', 'medium').lower()
        
        # Валидация типа задания
        
        valid_task_types = [t[0] for t in TASK_TYPES] # ['daily', 'reflection', ...]
        task_type = task_type_raw if task_type_raw in valid_task_types else 'daily'
        
        # Преобразование приоритета из строки в число
        priority_str_to_int = {
            'low': 1, 
            'medium': 2, 
            'high': 3, 
            'critical': 4
        }
        priority_int = priority_str_to_int.get(priority_str, 2) # По умолчанию medium
        # ---------------------------------------------

        # --- Создание задания через сервис ---
        logger.info(f"Создание задания: '{title}', тип: {task_type}, приоритет: {priority_int}")
        therapy_task = await task_service.assign_task(
            user=user,
            title=title,
            description=description,
            task_type=task_type,
            priority=priority_int,
            related_entry=related_diary_entry
        )
        logger.info(f"Новое задание от ИИ успешно создано, ID: {therapy_task.id}")
        return therapy_task

    except Exception as task_error:
        logger.error(f"Ошибка при создании задания от ИИ: {task_error}", exc_info=True)
        # Ошибка создания задания не должна прерывать основной поток обработки записи