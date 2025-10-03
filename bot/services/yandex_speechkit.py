# /home/shlicha/psycho_diary/bot/services/yandex_speechkit.py
import aiohttp
import logging
import asyncio
import json
from typing import Dict, Any
from core.settings import YANDEX_SPEECHKIT_API_KEY

logger = logging.getLogger(__name__)

class YandexSpeechKitService:
    """Сервис для работы с Yandex SpeechKit"""

    DURATION_THRESHOLD_SECONDS = 25

    def __init__(self):
        """Инициализация сервиса Yandex SpeechKit"""
        if not YANDEX_SPEECHKIT_API_KEY:
            logger.warning("YANDEX_SPEECHKIT_API_KEY не настроен")
        else:
            logger.debug("YANDEX_SPEECHKIT_API_KEY найден")

    async def recognize_voice_auto(
        self,
        voice_data: bytes,
        duration: int,
        language: str = 'ru-RU',
        audio_format: str = 'oggopus'
    ) -> Dict[str, Any]:
        """
        Автоматический выбор метода распознавания на основе длительности аудио.
        
        Args:
            voice_ Байты голосового сообщения
            duration: Длительность аудио в секундах
            language: Язык распознавания
            audio_format: Формат аудио файла
            
        Returns:
            Dict[str, Any]: Результат распознавания
        """
        try:
            duration_int = int(duration)
        except (ValueError, TypeError) as e:
            logger.error(f"Некорректный формат duration: {duration}. Используется значение по умолчанию 0. Ошибка: {e}")
            duration_int = 0
            
        if duration_int > self.DURATION_THRESHOLD_SECONDS:
            logger.debug(f"Используется Long Running Recognition для аудио длительностью {duration_int} секунд")
            return await self.recognize_voice(voice_data, language, audio_format)
        else:
            logger.debug(f"Используется стандартное распознавание для аудио длительностью {duration_int} секунд")
            return await self.recognize_voice(voice_data, language, audio_format)

    async def recognize_voice(
        self, 
        voice_data: bytes, 
        language: str = 'ru-RU',
        audio_format: str = 'oggopus'
    ) -> Dict[str, Any]:
        """
        Распознавание голоса через Yandex SpeechKit (короткие аудио до 1 минуты).
        Также используется как fallback для более длинных аудио.

        Args:
            voice_ Байты голосового сообщения
            language: Язык распознавания
            audio_format: Формат аудио файла

        Returns:
            Dict[str, Any]: Результат распознавания
        """
        if not voice_data or len(voice_data) < 1024:
            logger.error("Голосовые данные слишком маленькие или пустые")
            return {
                'success': False,
                'error': 'voice_data_too_small',
                'message': 'Голосовые данные слишком маленькие или пустые',
                'result': ''
            }
        if len(voice_data) > 10 * 1024 * 1024: 
            logger.error("Голосовые данные слишком большие")
            return {
                'success': False,
                'error': 'voice_data_too_large',
                'message': 'Голосовые данные слишком большие',
                'result': ''
            }
        if not YANDEX_SPEECHKIT_API_KEY:
            logger.error("SpeechKit API key not configured")
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ Yandex SpeechKit не настроен',
                'result': ''
            }
        params = {
            'lang': language,
            'format': audio_format,
        }
        if audio_format == 'oggopus':
            params['sampleRateHertz'] = 48000
        url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "Authorization": f"Api-Key {YANDEX_SPEECHKIT_API_KEY}",
                        "Content-Type": "audio/ogg" if audio_format == 'oggopus' else "audio/mpeg" if audio_format == 'mp3' else "application/octet-stream"
                    },
                    params=params,
                    data=voice_data,
                    timeout=aiohttp.ClientTimeout(total=60) 
                ) as response:
                    raw_response_text = await response.text()
                    if response.status == 200:
                        result = await response.json()
                        recognized_text = result.get("result", "")
                        return {
                            'success': True,
                            'error': None,
                            'message': 'Голос успешно распознан',
                            'result': recognized_text,
                            'processing_time': result.get('processingTime', 0),
                            'word_count': len(recognized_text.split()) if recognized_text else 0,
                            'confidence': result.get('confidence', 0.0),
                            'raw_response': raw_response_text
                        }
                    else:
                        logger.error(f"SpeechKit error: {response.status} - {raw_response_text}")
                        return {
                            'success': False,
                            'error': f'speechkit_error_{response.status}',
                            'message': f'Ошибка Yandex SpeechKit: {response.status} - {raw_response_text[:200]}',
                            'result': '',
                            'raw_response': raw_response_text
                        }
        except asyncio.TimeoutError:
            logger.warning("SpeechKit timeout")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от Yandex SpeechKit. Аудио может быть слишком длинным.',
                'result': '',
                'raw_response': '{"error": "timeout"}'
            }
        except Exception as e:
            logger.error(f"SpeechKit request failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': 'general_error',
                'message': f'Произошла ошибка при распознавании голоса: {str(e)}',
                'result': '',
                'raw_response': f'{{"error": "{str(e)}"}}'
            }

    async def recognize_long_voice(
        self,
        audio_uri: str,
        language: str = 'ru-RU',
        audio_format: str = 'oggopus',
        model: str = 'general',
        sample_rate: int = 48000
    ) -> Dict[str, Any]:
        """
        Распознавание длинных голосовых сообщений через Yandex SpeechKit Long Running Recognition API.
        Принимает URI файла, загруженного в Yandex Object Storage.

        Args:
            audio_uri: URI аудиофайла в формате s3://bucket/key
            language: Язык распознавания (например, 'ru-RU')
            audio_format: Формат аудио файла ('oggopus', 'mp3', 'linear16')
            model: Языковая модель ('general', 'phone_calls', 'meetings', etc.)
            sample_rate: Частота дискретизации (48000, 16000, 8000)
            
        Returns:
            Dict[str, Any]: Результат распознавания (включает operation_id для опроса)
        """
        if not audio_uri:
            logger.error("URI аудиофайла не предоставлен")
            return {
                'success': False,
                'error': 'no_audio_uri',
                'message': 'URI аудиофайла не предоставлен',
                'result': ''
            }
        if not YANDEX_SPEECHKIT_API_KEY:
            logger.error("SpeechKit API key not configured")
            return {
                'success': False,
                'error': 'api_key_missing',
                'message': 'API ключ Yandex SpeechKit не настроен',
                'result': ''
            }
        audio_encoding_map = {
            'oggopus': 'OGG_OPUS',
            'mp3': 'MP3',
            'linear16': 'LINEAR16_PCM'
        }
        if audio_format not in audio_encoding_map:
            logger.error(f"Неподдерживаемый формат аудио: {audio_format}")
            return {
                'success': False,
                'error': 'unsupported_audio_format',
                'message': f'Неподдерживаемый формат аудио: {audio_format}',
                'result': ''
            }
        config = {
            "specification": {
                "languageCode": language,
                "model": model,
                "audioEncoding": audio_encoding_map[audio_format],
                "sampleRateHertz": sample_rate
            }
        }
        if audio_format == 'linear16':
            config["specification"]["audioChannelCount"] = 1
        url = "https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "Authorization": f"Api-Key {YANDEX_SPEECHKIT_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "config": config,
                        "audio": {
                            "uri": audio_uri
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raw_response_text = await response.text()
                        logger.error(f"SpeechKit long recognition init error: {response.status} - {raw_response_text}")
                        return {
                            'success': False,
                            'error': f'speechkit_init_error_{response.status}',
                            'message': f'Ошибка инициализации распознавания: {response.status}',
                            'result': '',
                            'raw_response': raw_response_text
                        }
                    operation_result = await response.json()
                    operation_id = operation_result.get("id")
                    if not operation_id:
                        logger.error("Не удалось получить ID операции распознавания")
                        return {
                            'success': False,
                            'error': 'no_operation_id',
                            'message': 'Не удалось получить ID операции распознавания',
                            'result': '',
                            'raw_response': json.dumps(operation_result)
                        }
                    return {
                        'success': True,
                        'operation_id': operation_id,
                        'message': 'Операция распознавания начата',
                        'result': '',
                        'raw_response': json.dumps(operation_result)
                    }    
        except asyncio.TimeoutError:
            logger.warning("SpeechKit long recognition init timeout")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от Yandex SpeechKit при инициализации',
                'result': '',
                'raw_response': '{"error": "timeout"}'
            }
        except Exception as e:
            logger.error(f"SpeechKit long recognition request failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': 'general_error',
                'message': f'Произошла ошибка при инициализации распознавания длинного голосового сообщения: {str(e)}',
                'result': '',
                'raw_response': f'{{"error": "{str(e)}"}}'
            }

    async def get_long_recognition_result(self, operation_id: str, max_attempts: int = 120) -> Dict[str, Any]:
        """
        Опрос статуса операции распознавания и получение результата.
        
        Args:
            operation_id: ID операции распознавания.
            max_attempts: Максимальное количество попыток опроса (по умолчанию 120 попыток с интервалом 5 сек = 10 минут).
            
        Returns:
            Dict[str, Any]: Результат распознавания или информация об ошибке.
        """
        if not operation_id:
            logger.error("Не предоставлен operation_id для опроса")
            return {
                'success': False,
                'error': 'no_operation_id',
                'message': 'Не предоставлен ID операции для опроса',
                'result': ''
            }
        url = f"https://operation.api.cloud.yandex.net/operations/{operation_id}"
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers={
                            "Authorization": f"Api-Key {YANDEX_SPEECHKIT_API_KEY}"
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            raw_response_text = await response.text()
                            logger.error(f"SpeechKit operation status error (attempt {attempt+1}): {response.status} - {raw_response_text}")
                            await asyncio.sleep(5)
                            continue
                        operation_data = await response.json()
                        if operation_data.get("done", False):
                            if "response" in operation_data:
                                response_data = operation_data["response"]
                                chunks = response_data.get("chunks", [])
                                full_text = ""
                                total_confidence = 0.0
                                word_count = 0
                                for chunk in chunks:
                                    alternatives = chunk.get("alternatives", [])
                                    if alternatives:
                                        best_alternative = alternatives[0]
                                        chunk_text = best_alternative.get("text", "").strip()
                                        chunk_confidence = best_alternative.get("confidence", 0.0)
                                        if full_text and chunk_text:
                                            full_text += " "
                                        full_text += chunk_text
                                        total_confidence += chunk_confidence
                                        word_count += len(chunk_text.split()) if chunk_text else 0
                                avg_confidence = total_confidence / len(chunks) if chunks else 0.0
                                logger.debug(f"Long recognition completed successfully. Operation ID: {operation_id}")
                                return {
                                    'success': True,
                                    'error': None,
                                    'message': 'Голос успешно распознан',
                                    'result': full_text,
                                    'processing_time': None,
                                    'word_count': word_count,
                                    'confidence': avg_confidence,
                                    'raw_response': json.dumps(operation_data)
                                }
                            elif "error" in operation_data:
                                error_data = operation_data["error"]
                                error_message = error_data.get("message", "Неизвестная ошибка")
                                error_code = error_data.get("code", "UNKNOWN")
                                logger.error(f"SpeechKit operation error: {error_code} - {error_message}")
                                return {
                                    'success': False,
                                    'error': f'operation_error_{error_code}',
                                    'message': f'Ошибка в процессе распознавания: {error_message}',
                                    'result': '',
                                    'raw_response': json.dumps(operation_data)
                                }
                            else:
                                logger.error("Неизвестный формат ответа от операции распознавания")
                                return {
                                    'success': False,
                                    'error': 'unknown_response_format',
                                    'message': 'Неизвестный формат ответа от операции распознавания',
                                    'result': '',
                                    'raw_response': json.dumps(operation_data)
                                }
                        await asyncio.sleep(5)            
            except Exception as e:
                logger.error(f"Ошибка при опросе статуса операции {operation_id} (attempt {attempt+1}): {e}", exc_info=True)
                await asyncio.sleep(5)
        logger.warning(f"Превышено максимальное количество попыток ожидания результата операции {operation_id}")
        return {
            'success': False,
            'error': 'max_attempts_exceeded',
            'message': 'Превышено максимальное время ожидания результата распознавания',
            'result': '',
            'raw_response': '{"error": "max_attempts_exceeded"}'
        }
    
yandex_speechkit_service = YandexSpeechKitService()

async def recognize_voice_auto(
    voice_data: bytes,
    duration: int,
    language: str = 'ru-RU',
    audio_format: str = 'oggopus'
) -> Dict[str, Any]:
    """
    Удобная функция для автоматического выбора метода распознавания.
    """
    return await yandex_speechkit_service.recognize_voice_auto(voice_data, duration, language, audio_format)

async def recognize_voice(voice_data: bytes, language: str = 'ru-RU', audio_format: str = 'oggopus') -> Dict[str, Any]:
    """
    Удобная функция для распознавания голоса (короткие аудио).
    """
    return await yandex_speechkit_service.recognize_voice(voice_data, language, audio_format)

async def recognize_long_voice(
    audio_uri: str,
    language: str = 'ru-RU',
    audio_format: str = 'oggopus',
    model: str = 'general',
    sample_rate: int = 48000
) -> Dict[str, Any]:
    """
    Удобная функция для инициализации распознавания длинных голосовых сообщений.
    """
    return await yandex_speechkit_service.recognize_long_voice(audio_uri, language, audio_format, model, sample_rate)

async def get_long_recognition_result(operation_id: str, max_attempts: int = 120) -> Dict[str, Any]:
    """
    Удобная функция для получения результата длинного распознавания.
    """
    return await yandex_speechkit_service.get_long_recognition_result(operation_id, max_attempts)