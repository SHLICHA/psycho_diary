# bot/utils/audio_utils.py
"""Обработка голосовых сообщений: STT + пунктуация (Telegram и REST)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple

from aiogram.types import Message

from bot.services.deepseek_api import deepseek_api_service
from bot.services.yandex_object_storage import yandex_storage_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from messages import get_message

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MIN_AUDIO_BYTES = 1024

StatusCallback = Callable[[str], Awaitable[None]]


def map_language_for_speechkit(language: str) -> str:
    """Map app language codes to SpeechKit locale tags."""
    normalized = (language or 'ru').lower().strip()
    if normalized.startswith('en'):
        return 'en-US'
    if normalized in ('ru', 'ru-ru'):
        return 'ru-RU'
    if '-' in normalized:
        return normalized
    return 'ru-RU'


def resolve_audio_format(filename: str = '', content_type: str = '') -> str:
    """Infer SpeechKit audio_format from filename / content-type."""
    name = (filename or '').lower()
    ctype = (content_type or '').lower()
    if name.endswith('.mp3') or 'mpeg' in ctype or 'mp3' in ctype:
        return 'mp3'
    if name.endswith(('.wav', '.pcm')) or 'wav' in ctype or 'pcm' in ctype:
        return 'linear16'
    return 'oggopus'


async def process_voice_bytes(
    voice_bytes: bytes,
    *,
    duration: int,
    language: str,
    context_name: str = 'VoiceAPI',
    audio_format: str = 'oggopus',
    filename_hint: str = 'voice.ogg',
    on_status: Optional[StatusCallback] = None,
) -> Tuple[bool, str, str]:
    """
    Распознаёт и пунктуирует аудио без зависимости от Telegram.

    Returns:
        (success, recognized_text, error_message)
    """
    try:
        if not voice_bytes or len(voice_bytes) < MIN_AUDIO_BYTES:
            return False, '', 'Аудиофайл слишком короткий или пустой.'
        if len(voice_bytes) > MAX_AUDIO_BYTES:
            return False, '', 'Аудиофайл превышает лимит 10 МБ.'

        speechkit_lang = map_language_for_speechkit(language)
        punct_lang = 'en' if speechkit_lang.lower().startswith('en') else (language or 'ru')
        if punct_lang not in ('ru', 'en'):
            punct_lang = 'ru'

        duration = max(0, int(duration or 0))
        rec_result = None

        if duration > yandex_speechkit_service.DURATION_THRESHOLD_SECONDS:
            logger.debug(
                '[%s] Аудио длительностью %s секунд. Используется Long Running Recognition.',
                context_name,
                duration,
            )
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                unique_id = uuid.uuid4().hex[:8]
                audio_filename = (
                    f"{context_name.lower().replace(' ', '_')}_{timestamp}_{unique_id}_{filename_hint}"
                )
                audio_uri = await yandex_storage_service.upload_audio_file(voice_bytes, audio_filename)
                init_result = await yandex_speechkit_service.recognize_long_voice(
                    audio_uri=audio_uri,
                    language=speechkit_lang,
                    audio_format=audio_format,
                )
                if not init_result.get('success'):
                    error_msg = init_result.get('message', 'Неизвестная ошибка инициализации Long Recognition')
                    logger.error('[%s] Ошибка инициализации Long Recognition: %s', context_name, error_msg)
                    return False, '', error_msg

                if on_status:
                    await on_status('long_recognition_waiting')

                operation_id = init_result['operation_id']
                rec_result = await yandex_speechkit_service.get_long_recognition_result(operation_id)
                if not rec_result.get('success'):
                    error_msg = rec_result.get('message', 'Неизвестная ошибка Long Recognition')
                    logger.error('[%s] Ошибка Long Recognition: %s', context_name, error_msg)
                    return False, '', error_msg
            except Exception as upload_or_recognition_error:
                logger.error(
                    '[%s] Ошибка при Long Recognition: %s',
                    context_name,
                    upload_or_recognition_error,
                    exc_info=True,
                )
                if on_status:
                    await on_status('long_recognition_fallback')
                rec_result = await yandex_speechkit_service.recognize_voice(
                    voice_bytes, speechkit_lang, audio_format
                )
        else:
            rec_result = await yandex_speechkit_service.recognize_voice(
                voice_bytes, speechkit_lang, audio_format
            )

        if not rec_result or not rec_result.get('success'):
            error_msg = (rec_result or {}).get('message', 'Неизвестная ошибка распознавания')
            logger.error('[%s] Ошибка распознавания голоса: %s', context_name, error_msg)
            return False, '', error_msg

        recognized_text_raw = rec_result.get('result') or ''
        if recognized_text_raw:
            punct_result = await deepseek_api_service.punctuate_and_format_text(
                recognized_text_raw, punct_lang
            )
            recognized_text = punct_result.get('result') or recognized_text_raw
        else:
            recognized_text = ''
            logger.warning('[%s] Распознанный текст пуст.', context_name)

        return True, recognized_text, ''
    except Exception as e:
        logger.error(
            '[%s] Критическая ошибка при обработке голоса: %s',
            context_name,
            e,
            exc_info=True,
        )
        return False, '', f'Критическая ошибка обработки голоса: {str(e)}'


async def process_voice_message(
    message: Message,
    context_name: str,
    language: str,
    status_msg=None,
) -> tuple[bool, str, str]:
    """
    Обрабатывает голосовое сообщение Telegram: загружает, распознает, пунктуирует.

    Returns:
        tuple[bool, str, str]: (успех, распознанный и пунктуированный текст, сообщение об ошибке).
    """
    try:
        voice = message.voice
        duration = voice.duration
        voice_file_id = voice.file_id
        file = await message.bot.get_file(voice_file_id)
        voice_bytes = (await message.bot.download_file(file.file_path)).read()

        async def _on_status(kind: str) -> None:
            if not status_msg:
                return
            try:
                if kind == 'long_recognition_waiting':
                    await status_msg.edit_text(
                        f"{get_message('processing', language)}\n"
                        'Ожидание завершения распознавания длинного аудио...'
                    )
                elif kind == 'long_recognition_fallback':
                    await status_msg.edit_text(
                        f"{get_message('processing', language)}\n"
                        '(Попытка стандартного распознавания после ошибки Long Recognition...)'
                    )
            except Exception as edit_error:
                logger.warning(
                    '[%s] Не удалось отредактировать сообщение статуса: %s',
                    context_name,
                    edit_error,
                )

        return await process_voice_bytes(
            voice_bytes,
            duration=duration,
            language=language,
            context_name=context_name,
            audio_format='oggopus',
            filename_hint=f'{message.message_id}.ogg',
            on_status=_on_status,
        )
    except Exception as e:
        logger.error(
            '[%s] Критическая ошибка при обработке голосового сообщения: %s',
            context_name,
            e,
            exc_info=True,
        )
        return False, '', f'Критическая ошибка обработки голоса: {str(e)}'
