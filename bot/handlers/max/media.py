"""MAX media helpers: download + STT + photo bytes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from bot.utils.audio_utils import process_voice_bytes, resolve_audio_format

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from bot.transports.max.client import MaxClient
    from bot.transports.max.inbound import MaxMediaInfo

logger = logging.getLogger(__name__)


async def download_media_bytes(
    max_client: 'MaxClient',
    media: 'MaxMediaInfo',
) -> Optional[bytes]:
    if not media or not media.url:
        logger.warning('[MAX media] missing url for kind=%s', getattr(media, 'kind', None))
        return None
    return await max_client.download_file(media.url)


async def recognize_max_voice(
    max_client: 'MaxClient',
    media: 'MaxMediaInfo',
    *,
    language: str,
    context_name: str,
    send_func: Optional['SendFunc'] = None,
) -> Tuple[bool, str, str]:
    """
    Download MAX audio and run shared STT pipeline.
    Returns (success, text, error_message).
    """
    voice_bytes = await download_media_bytes(max_client, media)
    if not voice_bytes:
        return False, '', 'Не удалось скачать голосовое сообщение.'

    if send_func is not None:
        from messages import get_message

        await send_func(get_message('processing', language))

    filename = media.filename or 'voice.ogg'
    audio_format = resolve_audio_format(filename, media.content_type or '')
    duration = int(media.duration or 0)

    return await process_voice_bytes(
        voice_bytes,
        duration=duration,
        language=language,
        context_name=context_name,
        audio_format=audio_format,
        filename_hint=filename,
    )
