# bot/utils/audio_utils.py
import logging
from aiogram.types import Message
from bot.services.yandex_object_storage import yandex_storage_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from messages import get_message

logger = logging.getLogger(__name__)

# Обновленная сигнатура - добавлен status_msg
async def process_voice_message(
    message: Message, 
    context_name: str,
    language: str,
    status_msg=None # Новый аргумент, необязательный
) -> tuple[bool, str, str]:
    """
    Обрабатывает голосовое сообщение: загружает, распознает, пунктуирует.
    
    Args:
        message: Объект сообщения Aiogram.
        context_name: Название контекста для логов (например, "Clarification").
        language: Язык пользователя.
        status_msg: Сообщение статуса для редактирования (например, "Обработка...").
        
    Returns:
        tuple[bool, str, str]: (успех, распознанный и пунктуированный текст, сообщение об ошибке или пустая строка).
    """
    try:
        # --- Извлечение данных ---
        voice = message.voice
        duration = voice.duration
        voice_file_id = voice.file_id

        # --- Скачивание файла ---
        file = await message.bot.get_file(voice_file_id)
        voice_bytes = (await message.bot.download_file(file.file_path)).read()

        recognized_text = ""
        
        # --- Распознавание голоса ---
        if duration > yandex_speechkit_service.DURATION_THRESHOLD_SECONDS:
            logger.info(f"[{context_name}] Аудио длительностью {duration} секунд. Используется Long Running Recognition.")
            try:
                # 1. Загружаем файл в Object Storage
                import uuid
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                unique_id = uuid.uuid4().hex[:8]
                audio_filename = f"{context_name.lower().replace(' ', '_')}_{message.message_id}_{timestamp}_{unique_id}.ogg"
                
                audio_uri = await yandex_storage_service.upload_audio_file(voice_bytes, audio_filename)
                logger.info(f"[{context_name}] Аудио загружено в Object Storage. URI: {audio_uri}")

                # 2. Инициируем Long Running Recognition
                init_result = await yandex_speechkit_service.recognize_long_voice(
                    audio_uri=audio_uri,
                    language=language,
                    audio_format='oggopus'
                )
                
                if not init_result['success']:
                    error_msg = init_result.get('message', 'Неизвестная ошибка инициализации Long Recognition')
                    logger.error(f"[{context_name}] Ошибка инициализации Long Recognition: {error_msg}")
                    return False, "", error_msg

                operation_id = init_result['operation_id']
                logger.info(f"[{context_name}] Long Recognition operation started. ID: {operation_id}")

                # 3. Опрашиваем результат
                # Редактируем сообщение статуса, если оно передано
                if status_msg:
                     try:
                         await status_msg.edit_text(f"{get_message('processing', language)}\nОжидание завершения распознавания длинного аудио...")
                     except Exception as edit_error:
                         logger.warning(f"[{context_name}] Не удалось отредактировать сообщение статуса: {edit_error}")
                
                rec_result = await yandex_speechkit_service.get_long_recognition_result(operation_id)
                
                if not rec_result['success']:
                    error_msg = rec_result.get('message', 'Неизвестная ошибка Long Recognition')
                    logger.error(f"[{context_name}] Ошибка Long Recognition: {error_msg}")
                    return False, "", error_msg

            except Exception as upload_or_recognition_error:
                logger.error(f"[{context_name}] Ошибка при Long Recognition: {upload_or_recognition_error}", exc_info=True)
                # Fallback: пробуем стандартный метод
                logger.info(f"[{context_name}] Попытка fallback на стандартный метод распознавания.")
                # Редактируем сообщение статуса, если оно передано
                if status_msg:
                     try:
                         await status_msg.edit_text(f"{get_message('processing', language)}\n(Попытка стандартного распознавания после ошибки Long Recognition...)")
                     except Exception as edit_error:
                         logger.warning(f"[{context_name}] Не удалось отредактировать сообщение статуса: {edit_error}")
                rec_result = await yandex_speechkit_service.recognize_voice(voice_bytes, language, 'oggopus')
            
        else:
            logger.info(f"[{context_name}] Аудио длительностью {duration} секунд. Используется стандартное распознавание.")
            # Используем стандартный метод
            rec_result = await yandex_speechkit_service.recognize_voice(voice_bytes, language, 'oggopus')

        # --- Обработка результата распознавания (одинакова для обоих методов) ---
        if not rec_result['success']:
             error_msg = rec_result.get('message', 'Неизвестная ошибка распознавания')
             logger.error(f"[{context_name}] Ошибка распознавания голоса: {error_msg}")
             return False, "", error_msg

        recognized_text_raw = rec_result['result']
        if recognized_text_raw:
            punct_result = await deepseek_api_service.punctuate_and_format_text(recognized_text_raw, language)
            recognized_text = punct_result.get('result') or recognized_text_raw
        else:
            recognized_text = ""
            logger.warning(f"[{context_name}] Распознанный текст пуст.")
        
        logger.info(f"[{context_name}] Голос успешно распознан. Длина текста: {len(recognized_text)} символов.")
        return True, recognized_text, ""
            
    except Exception as e:
        logger.error(f"[{context_name}] Критическая ошибка при обработке голосового сообщения: {e}", exc_info=True)
        return False, "", f"Критическая ошибка обработки голоса: {str(e)}"