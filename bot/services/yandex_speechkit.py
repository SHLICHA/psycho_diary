"""
Заглушка для Yandex SpeechKit
"""
import aiohttp
import logging
import asyncio
from typing import Optional, Dict, Any
from core.settings import YANDEX_SPEECHKIT_API_KEY

logger = logging.getLogger(__name__)

class YandexSpeechKitService:
    """Сервис для работы с Yandex SpeechKit"""
    
    def __init__(self):
        """Инициализация сервиса Yandex SpeechKit"""
        if not YANDEX_SPEECHKIT_API_KEY:
            logger.warning("YANDEX_SPEECHKIT_API_KEY не настроен")
        else:
            logger.info("YANDEX_SPEECHKIT_API_KEY найден")
    
    async def recognize_voice(
        self, 
        voice_data, 
        language: str = 'ru-RU',
        audio_format: str = 'oggopus'
    ) -> Dict[str, Any]:
        """
        Распознавание голоса через Yandex SpeechKit
        
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
        if len(voice_data) > 1024 * 1024:
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
                        "Content-Type": "audio/ogg"
                    },
                    params=params,
                    data=voice_data,
                    timeout=aiohttp.ClientTimeout(total=15)
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
                            'message': f'Ошибка Yandex SpeechKit: {response.status}',
                            'result': '',
                            'raw_response': raw_response_text
                        }    
        except asyncio.TimeoutError:
            logger.warning("SpeechKit timeout")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Превышено время ожидания ответа от Yandex SpeechKit',
                'result': '',
                'raw_response': '{"error": "timeout"}'
            }
        except Exception as e:
            logger.error(f"SpeechKit request failed: {e}")
            return {
                'success': False,
                'error': 'general_error',
                'message': 'Произошла ошибка при распознавании голоса',
                'result': '',
                'raw_response': f'{{"error": "{str(e)}"}}'
            }

yandex_speechkit_service = YandexSpeechKitService()

async def recognize_voice(
    voice_data: bytes, 
    language: str = 'ru-RU',
    audio_format: str = 'oggopus'
) -> Dict[str, Any]:
    """
    Удобная функция для распознавания голоса
    
    Args:
        voice_data: Байты голосового сообщения
        language: Язык распознавания
        audio_format: Формат аудио файла
        
    Returns:
        Dict[str, Any]: Результат распознавания
    """
    return await yandex_speechkit_service.recognize_voice(voice_data, language, audio_format)
