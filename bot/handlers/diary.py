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

from messages import get_message
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_cancel_keyboard,
    get_month_calendar_with_navigation,
    get_calendar_back_keyboard,
    get_cancel_keyboard
    )
from bot.keyboards.main_menu import get_back_keyboard, get_main_menu_keyboard
from bot.utils.state_manager import state_manager
from bot.utils.time_utils import convert_utc_to_user_timezone
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from core.constants import TEXT_MESSAGE_MAX_LENGTH
from bot.services.diary_service import diary_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from bot.services.diary_service import (
    create_text_entry, 
    create_voice_entry, 
    get_user_entries_for_date,
    get_combined_entry_text,
    delete_entry,
    update_entry_analysis
)
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

@router.message(DiaryStates.waiting_for_text_entry, F.content_type == ContentType.TEXT)
async def process_text_entry(message: Message, state: FSMContext, user, language: str):
    """Обработка текстовой записи"""
    logger.info(f"Обработка текстовой записи от пользователя {message.from_user.id}")
    
    try:
        # === ИЗМЕНЕНО: Получение времени в часовом поясе пользователя ===
        # 1. Получаем текущее UTC время
        current_utc_dt = datetime.utcnow()
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Текущее UTC время: {current_utc_dt}")

        # 2. Локализуем его как UTC
        utc_dt_aware = pytz.utc.localize(current_utc_dt)
        logger.debug(f"[СОЗДАНИЕ ЗАПИСИ] Локализованное UTC время: {utc_dt_aware}")

        # 3. Получаем часовой пояс пользователя из настроек
        user_tz_str = user.timezone
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Часовой пояс пользователя из настроек: '{user_tz_str}'")

        # 4. Конвертируем UTC время в пользовательский часовой пояс
        try:
            user_tz = pytz.timezone(user_tz_str)
            user_local_datetime = utc_dt_aware.astimezone(user_tz)
            logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Локальное время пользователя для записи: {user_local_datetime} (tzinfo: {user_local_datetime.tzinfo})")
        except pytz.UnknownTimeZoneError:
            logger.error(f"[СОЗДАНИЕ ЗАПИСИ] Неизвестный часовой пояс '{user_tz_str}', используем UTC.")
            user_local_datetime = utc_dt_aware # Остаётся UTC
        # ================================================

        # Получаем текст записи
        entry_text = message.text
        logger.info(f"Получен текст записи длиной {len(entry_text)} символов")
        
        # Проверяем минимальную длину
        if len(entry_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получена пустая запись при обработке")
            return
        
        # Проверяем максимальную длину
        from core.constants import TEXT_MESSAGE_MAX_LENGTH
        if len(entry_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Текст записи слишком длинный: {len(entry_text)} символов")
            return
        
        # Показываем сообщение об обработке
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке текстовой записи")
        
        # === 1. СОХРАНЯЕМ ЗАПИСЬ В БД с локальным временем ===
        diary_entry = await diary_service.create_text_entry(
            user=user, 
            text=entry_text, 
            language=language,
            entry_datetime=user_local_datetime # Передаем локальное время
        )
        logger.info(f"Текстовая запись сохранена в БД, ID: {diary_entry.id}")
        
        # === 2. АНАЛИЗИРУЕМ ЗАПИСЬ ЧЕРЕЗ DEEPSEEK ===
        from bot.services.deepseek_api import deepseek_api_service
        
        analysis_result = await deepseek_api_service.analyze_text(
            text=entry_text,
            language=language,
            analysis_type='emotion'
        )
        
        # === 3. УЛУЧШЕННАЯ ОБРАБОТКА РЕЗУЛЬТАТА АНАЛИЗА ===
        
        # Инициализируем значения по умолчанию
        mood_score = 5
        comment = 'Анализ записан'
        recommendation = 'Продолжайте в том же духе'
        analysis_text = "Анализ не доступен"

        try:
            logger.info(f"Обработка результата анализа. Success: {analysis_result.get('success', 'unknown')}")
            logger.debug(f"Полный результат анализа: {analysis_result}") # Для отладки

            if analysis_result.get('success', False):
                result_data = analysis_result.get('result', {})
                logger.debug(f"Данные результата (result): {result_data}")

                # Функция для безопасного извлечения значения из словаря
                def safe_get(data, key, default):
                    if isinstance(data, dict):
                        return data.get(key, default)
                    return default

                # Пытаемся извлечь данные, спускаясь вглубь словаря, если нужно
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
                    # Остальные значения остаются по умолчанию

                # Если не удалось извлечь осмысленные данные, используем message из API ответа
                if mood_score == 5 and comment == 'Анализ записан':
                     api_message = analysis_result.get('message', '')
                     if api_message and api_message != 'Текст успешно проанализирован':
                          comment = f"{comment} ({api_message})"

                logger.info(f"Анализ успешно обработан. Оценка: {mood_score}/10")
            else:
                # Обработка ошибки API
                error_msg = analysis_result.get('message', 'Неизвестная ошибка API')
                logger.error(f"Ошибка API при анализе: {error_msg}")
                comment = f'Анализ записан (ошибка API: {error_msg})'
                recommendation = 'Попробуйте позже'
                analysis_text = f"Анализ не доступен из-за ошибки: {error_msg}"

        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке результата анализа: {e}", exc_info=True)
            comment = 'Анализ записан (ошибка обработки результата)'
            recommendation = 'Попробуйте позже'
            analysis_text = "Анализ не доступен из-за внутренней ошибки"

        logger.info(f"Запись проанализирована, оценка настроения: {mood_score}/10")
        
        # === ИЗВЛЕКАЕМ api_response ИЗ РЕЗУЛЬТАТА ===
        api_response_data = analysis_result.get('api_response', {})
        
        # === 4. ОБНОВЛЯЕМ АНАЛИЗ В БД ===
        try:   
            await diary_service.update_entry_analysis(
            #await update_entry_analysis(
                entry=diary_entry, # Передаем объект записи
                mood_score=mood_score,
                comment=comment,
                recommendation=recommendation,
                analysis_text=analysis_text,
                # === ДОБАВИТЬ ===
                api_response=api_response_data # Передаем ответ API
                # ===============
            )
            logger.info(f"Анализ записи обновлен в БД")
                
        except Exception as db_error:
            logger.error(f"Ошибка при сохранении/обновлении анализа в БД: {db_error}")
            # Не критично - продолжаем работу
        
        await state_manager.clear_state(state)
        
        entry_saved_msg = get_message(
            'entry_saved', 
            language,
            score=mood_score, 
            mood=get_message(f'mood_{mood_score}', language), 
            comment=comment, 
            recommendation=recommendation,
            analysis=analysis_text
        )
        
        await status_message.edit_text(
            entry_saved_msg,
            reply_markup=get_back_keyboard(language)
        )
        logger.info("Текстовая запись успешно обработана, проанализирована и сохранена с корректным временем")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке текстовой записи: {e}", exc_info=True)
        # Проверяем, существует ли status_message
        try:
            await message.answer(get_message('error_processing', language))
        except:
            # Если message.answer не работает, пытаемся отредактировать status_message
            try:
                from bot.utils.message_utils import safe_edit_message_text
                await safe_edit_message_text(
                    message=status_message,
                    text=get_message('error_processing', language)
                )
            except:
                pass # Игнорируем ошибки при отправке сообщения об ошибке

# --- Обработчики для голосовых записей ---

@router.message(DiaryStates.waiting_for_voice_entry, F.content_type == ContentType.VOICE)
async def process_voice_entry(message: Message, state: FSMContext, user, language: str):
    """Обработка голосовой записи"""
    logger.info(f"Обработка голосовой записи от пользователя {message.from_user.id}")
    
    
    try:
        # === ИЗМЕНЕНО: Получение времени в часовом поясе пользователя ===
        # 1. Получаем текущее UTC время
        current_utc_dt = datetime.utcnow()
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Текущее UTC время: {current_utc_dt}")

        # 2. Локализуем его как UTC
        utc_dt_aware = pytz.utc.localize(current_utc_dt)
        logger.debug(f"[СОЗДАНИЕ ЗАПИСИ] Локализованное UTC время: {utc_dt_aware}")

        # 3. Получаем часовой пояс пользователя из настроек
        user_tz_str = user.timezone
        logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Часовой пояс пользователя из настроек: '{user_tz_str}'")

        # 4. Конвертируем UTC время в пользовательский часовой пояс
        try:
            user_tz = pytz.timezone(user_tz_str)
            user_local_datetime = utc_dt_aware.astimezone(user_tz)
            logger.info(f"[СОЗДАНИЕ ЗАПИСИ] Локальное время пользователя для записи: {user_local_datetime} (tzinfo: {user_local_datetime.tzinfo})")
        except pytz.UnknownTimeZoneError:
            logger.error(f"[СОЗДАНИЕ ЗАПИСИ] Неизвестный часовой пояс '{user_tz_str}', используем UTC.")
            user_local_datetime = utc_dt_aware # Остаётся UTC
        # ================================================

        # Получаем информацию о голосовом сообщении
        voice = message.voice
        file_id = voice.file_id
        duration = voice.duration
        
        logger.info(f"Получено голосовое сообщение: ID={file_id}, Длительность={duration} секунд")
        
        # Проверяем минимальную длительность
        from core.constants import VOICE_MESSAGE_MIN_DURATION
        if duration < VOICE_MESSAGE_MIN_DURATION:
            error_msg = get_message('voice_too_short', language)
            await message.answer(error_msg)
            logger.warning(f"Голосовое сообщение слишком короткое: {duration} секунд")
            return
        
        # Проверяем максимальную длительность
        from core.constants import VOICE_MESSAGE_MAX_DURATION
        if duration > VOICE_MESSAGE_MAX_DURATION:
            error_msg = get_message('voice_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Голосовое сообщение слишком длинное: {duration} секунд")
            return
        
        # Показываем сообщение об обработке
        processing_msg = get_message('processing', language)
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке голосовой записи")
        
        # === 1. РЕАЛЬНОЕ РАСПОЗНАВАНИЕ ГОЛОСА ===
        logger.info("Начало реального распознавания голоса через Yandex SpeechKit")
        
        # 1. Скачиваем голосовое сообщение правильно
        try:
            file_info = await message.bot.get_file(file_id)
            file_path = file_info.file_path
            logger.info(f"Получен путь к файлу: {file_path}")
            
            # Скачиваем файл и конвертируем в bytes
            voice_data_io = await message.bot.download_file(file_path)
            # Конвертируем BytesIO в bytes
            voice_data = voice_data_io.read() if hasattr(voice_data_io, 'read') else bytes(voice_data_io)
            logger.info(f"Голосовое сообщение скачано, размер: {len(voice_data)} байт")
        except Exception as download_error:
            logger.error(f"Ошибка при скачивании голосового сообщения: {download_error}")
            await safe_edit_message_text(message=status_message, text=get_message('error_processing', language))
            return
        
        # 2. Распознаем голос через Yandex SpeechKit
        from bot.services.yandex_speechkit import yandex_speechkit_service
        recognition_result = await yandex_speechkit_service.recognize_voice(voice_data, language)
        
        if not recognition_result['success']:
            logger.error(f"Ошибка распознавания голоса: {recognition_result['error']}")
            error_msg = recognition_result['message']
            await safe_edit_message_text(message=status_message, text=get_message('error_processing', language) + f"\n\n{error_msg}")
            return
        
        recognized_text = recognition_result['result']
        processing_time = recognition_result.get('processing_time', 2.5)
        word_count = recognition_result.get('word_count', len(recognized_text.split()))
        confidence = recognition_result.get('confidence', 0.95)
        logger.info(f"Голос успешно распознан, длина текста: {len(recognized_text)} символов")
        logger.info(f"Время обработки: {processing_time} секунд")
        logger.info(f"Количество слов: {word_count}")
        logger.info(f"Уверенность: {confidence}")
        
        # 3. Постобработка текста через DeepSeek (расстановка знаков препинания)
        logger.info("Начало постобработки текста через DeepSeek API")
        # from bot.services.deepseek_api import deepseek_api_service # Уже импортирован вверху
        punctuation_result = await deepseek_api_service.punctuate_and_format_text(text=recognized_text, language=language)
        
        if not punctuation_result['success']:
            logger.error(f"Ошибка постобработки текста: {punctuation_result['error']}")
            # Используем распознанный текст без постобработки
            formatted_text = recognized_text
        else:
            formatted_text = punctuation_result['result']
        logger.info(f"Текст успешно отформатирован, длина: {len(formatted_text)} символов")

        # === 4. Создаем запись через сервис с локальным временем ===
        from bot.services.diary_service import diary_service # Убедиться, что импортирован
        
        # === ИЗВЛЕКАЕМ api_response ИЗ РЕЗУЛЬТАТА АНАЛИЗА ===
        analysis_api_response = punctuation_result.get('api_response', {})
        
        diary_entry = await diary_service.create_voice_entry(
            user=user,
            voice_file_id=file_id,
            duration=duration,
            recognized_text=formatted_text,
            language=language,
            entry_datetime=user_local_datetime # Передаем локальное время
            # Если вы хотите сохранить ответ SpeechKit и DeepSeek в VoiceToText, 
            # передайте их здесь (как обсуждали ранее).
            # speechkit_api_response=recognition_result, 
            # deepseek_api_response=punctuation_result.get('api_response', {})
        )
        logger.info(f"Голосовая запись создана и сохранена в БД, ID: {diary_entry.id}")

        # === 5. АНАЛИЗИРУЕМ ЗАПИСЬ ЧЕРЕЗ DEEPSEEK ===
        logger.info("Начало анализа записи через DeepSeek API")
        analysis_result = await deepseek_api_service.analyze_text(text=formatted_text, language=language, analysis_type='emotion')
        
        # === ИЗВЛЕКАЕМ РЕЗУЛЬТАТ АНАЛИЗА ===
        # Инициализируем значения по умолчанию
        mood_score = 5
        comment = 'Анализ записан'
        recommendation = 'Продолжайте в том же духе'
        analysis_text = "Анализ не доступен"

        try:
            logger.info(f"Обработка результата анализа голосовой записи. Success: {analysis_result.get('success', 'unknown')}")
            logger.debug(f"Полный результат анализа: {analysis_result}") # Для отладки

            if analysis_result.get('success', False):
                result_data = analysis_result.get('result', {})
                logger.debug(f"Данные результата (result): {result_data}")

                # Функция для безопасного извлечения значения из словаря
                def safe_get(data, key, default):
                    if isinstance(data, dict):
                        return data.get(key, default)
                    return default

                # Пытаемся извлечь данные, спускаясь вглубь словаря, если нужно
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
                    # Остальные значения остаются по умолчанию

                # Если не удалось извлечь осмысленные данные, используем message из API ответа
                if mood_score == 5 and comment == 'Анализ записан':
                     api_message = analysis_result.get('message', '')
                     if api_message and api_message != 'Текст успешно проанализирован':
                          comment = f"{comment} ({api_message})"

                logger.info(f"Анализ голосовой записи успешно обработан. Оценка: {mood_score}/10")
            else:
                # Обработка ошибки API
                error_msg = analysis_result.get('message', 'Неизвестная ошибка API')
                logger.error(f"Ошибка API при анализе голосовой записи: {error_msg}")
                comment = f'Анализ записан (ошибка API: {error_msg})'
                recommendation = 'Попробуйте позже'
                analysis_text = f"Анализ не доступен из-за ошибки: {error_msg}"

        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке результата анализа голосовой записи: {e}", exc_info=True)
            comment = 'Анализ записан (ошибка обработки результата)'
            recommendation = 'Попробуйте позже'
            analysis_text = "Анализ не доступен из-за внутренней ошибки"

        logger.info(f"Голосовая запись проанализирована, оценка настроения: {mood_score}/10")

        # === ИЗВЛЕКАЕМ api_response ИЗ РЕЗУЛЬТАТА АНАЛИЗА ===
        analysis_api_response = analysis_result.get('api_response', {})

        # === 6. ОБНОВЛЯЕМ АНАЛИЗ В БД ===
        try:
            await diary_service.update_entry_analysis(
                entry=diary_entry, # Передаем объект записи
                mood_score=mood_score,
                comment=comment,
                recommendation=recommendation,
                analysis_text=analysis_text,
                # === ДОБАВИТЬ ===
                api_response=analysis_api_response # Передаем ответ API анализа
                # ===============
            )
            logger.info(f"Анализ голосовой записи обновлен в БД")
        except Exception as db_error:
            logger.error(f"Ошибка при обновлении анализа голосовой записи в БД: {db_error}")
            # Не критично - продолжаем работу

        # === 7. Формируем и отправляем финальный результат ===
        await state_manager.clear_state(state)
        
        entry_saved_msg = get_message(
            'entry_saved', 
            language,
            score=mood_score, 
            mood=get_message(f'mood_{mood_score}', language), 
            comment=comment, 
            recommendation=recommendation,
            analysis=analysis_text
        )
        
        await safe_edit_message_text(
            message=status_message,
            text=entry_saved_msg,
            reply_markup=get_back_keyboard(language)
        )
        logger.info("Голосовая запись успешно обработана, распознана, проанализирована и сохранена с корректным временем")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке голосовой записи: {e}", exc_info=True)
        # Проверяем, существует ли status_message
        try:
            await message.answer(get_message('error_processing', language))
        except:
            # Если message.answer не работает, пытаемся отредактировать status_message
            try:
                from bot.utils.message_utils import safe_edit_message_text
                await safe_edit_message_text(
                    message=status_message,
                    text=get_message('error_processing', language)
                )
            except:
                pass # Игнорируем ошибки при отправке сообщения об ошибке

@router.message(DiaryStates.waiting_for_clarification)
async def process_clarification_answers(message: Message, state: FSMContext, user, language: str):
    """Обработка ответов на уточняющие вопросы"""
    logger.info(f"Обработка ответов на уточняющие вопросы от пользователя {message.from_user.id}")
    
    try:
        # Получаем текст ответов
        clarification_text = message.text
        logger.info(f"Получены ответы на уточнения длиной {len(clarification_text)} символов")
        
        # Проверяем минимальную длину
        if len(clarification_text.strip()) < 1:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            logger.warning("Получены пустые ответы на уточнения")
            return
        
        # Проверяем максимальную длину
        from core.constants import TEXT_MESSAGE_MAX_LENGTH
        if len(clarification_text) > TEXT_MESSAGE_MAX_LENGTH:
            error_msg = get_message('text_too_long', language)
            await message.answer(error_msg)
            logger.warning(f"Ответы на уточнения слишком длинные: {len(clarification_text)} символов")
            return
        
        # Получаем данные состояния
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('clarifying_entry_id')
        questions = state_data.get('clarification_questions', [])
        initial_analysis = state_data.get('initial_analysis', {})
        
        if not entry_id:
            logger.error("Не найден ID записи для уточнений")
            await message.answer(get_message('error_generic', language))
            return
        
        # Показываем сообщение об обработке уточнений
        processing_msg = get_message('processing_clarifications', language)
        status_message = await message.answer(processing_msg)
        logger.info("Отправлено сообщение об обработке уточнений")
        
        # === ВЫЗЫВАЕМ DEEPSEEK API С УТОЧНЕНИЯМИ ===
        from bot.services.deepseek_api import deepseek_api_service
        
        # Получаем данные пользователя для персонализации
        user_profile_data = await _get_user_profile_data(user, language)
        logger.info(f"Получены данные профиля пользователя для анализа уточнений")
        
        # Вызываем DeepSeek API с уточнениями
        final_analysis_result = await deepseek_api_service.analyze_text_with_clarifications(
            text=clarification_text,
            user_profile=user_profile_data,
            language=language,
            initial_analysis=initial_analysis,
            questions=questions
        )
        
        if not final_analysis_result['success']:
            logger.error(f"Ошибка финального анализа: {final_analysis_result['error']}")
            error_msg = final_analysis_result['message']
            await status_message.edit_text(get_message('error_processing', language) + f"\n\n{error_msg}")
            return
        
        # Очищаем состояние
        await state_manager.clear_state(state)
        
        # Получаем запись для обновления
        from diary.models import DiaryEntry
        try:
            diary_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
            logger.info(f"Запись найдена для обновления анализа: {diary_entry.id}")
        except DiaryEntry.DoesNotExist:
            logger.error(f"Запись {entry_id} не найдена")
            await status_message.edit_text(get_message('entry_not_found', language))
            return
        
        # Показываем финальный результат
        await _show_final_analysis_result(
            status_message, 
            diary_entry, 
            final_analysis_result, 
            language
        )
        logger.info("Ответы на уточнения обработаны, показан финальный результат")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке ответов на уточнения: {e}", exc_info=True)
        await message.answer(get_message('error_processing', language))

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
            '''entry_type = "🎙 Голосовая" if hasattr(entry, 'voice_to_text') else "✍️ Текстовая"
            try:
                # Получаем время создания записи в часовом поясе пользователя
                # diary_entry.entry_date и diary_entry.localized_created_at из diary/models.py
                creation_time = entry.localized_created_at # Это уже строка, отформатированная с учетом часового пояса
            except Exception as time_error:
                logger.error(f"Ошибка при получении времени записи {entry.id}: {time_error}")
                # Альтернатива: форматируем напрямую
                try:
                    # Убедимся, что created_at это aware datetime
                    from django.utils import timezone
                    import pytz
                    user_tz = pytz.timezone(user.timezone)
                    localized_time = entry.created_at.astimezone(user_tz)
                    creation_time = localized_time.strftime('%H:%M')
                except Exception:
                    # Если не удалось, используем UTC или просто время
                    creation_time = entry.created_at.strftime('%H:%M')
            history_msg += f"<b>{i}. {entry_type} запись</b>\n"
            history_msg += f"🕒 Время: {creation_time}\n"
            history_msg += f"🔤 {entry.word_count} слов\n"
            history_msg += f"📄 {entry.text[:100]}...\n\n"'''
        
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
    """Получение данных профиля пользователя для анализа"""
    logger.info(f"Получение данных профиля пользователя {user.telegram_id} для анализа")
    
    try:
        # Получаем последние 10 записей пользователя
        from bot.services.diary_service import diary_service
        from datetime import datetime, timedelta
        
        # Получаем записи за последние 30 дней
        recent_entries = await diary_service.get_user_recent_entries(
            user=user,
            days=30,
            limit=10
        )
        logger.info(f"Получено {len(recent_entries)} последних записей")
        
        # Формируем историю записей
        entry_history = []
        for entry in recent_entries:
            entry_history.append({
                'date': entry.created_at.strftime('%d.%m.%Y'),
                'text': entry.text[:200] + "..." if len(entry.text) > 200 else entry.text,
                'word_count': entry.word_count,
                'created_at': entry.created_at.isoformat()
            })
        
        # Получаем историю инсайтов
        from diary.models import UserInsight
        user_insights = []
        async for insight in UserInsight.objects.filter(user=user).order_by('-weight')[:20]:
            user_insights.append({
                'text': insight.text,
                'category': insight.category,
                'weight': insight.weight,
                'last_mentioned': insight.last_mentioned.isoformat() if insight.last_mentioned else None
            })
        
        logger.info(f"Получено {len(user_insights)} инсайтов пользователя")
        
        # Формируем данные профиля
        profile_data = {
            'telegram_id': user.telegram_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'language': user.language,
            'awareness_level': user.awareness_level,
            'is_premium': user.is_premium,
            'entry_history': entry_history,
            'user_insights': user_insights,
            'registration_date': user.created_at.isoformat() if user.created_at else None,
            'last_activity': user.last_activity.isoformat() if user.last_activity else None,
            'entries_count': len(entry_history)
        }
        
        logger.info("Данные профиля пользователя получены успешно")
        return profile_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных профиля пользователя: {e}")
        # Возвращаем минимальные данные
        return {
            'telegram_id': user.telegram_id,
            'username': user.username,
            'language': user.language,
            'awareness_level': user.awareness_level or 1,
            'is_premium': user.is_premium or False,
            'entry_history': [],
            'user_insights': [],
            'registration_date': user.created_at.isoformat() if user.created_at else None
        }
    
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