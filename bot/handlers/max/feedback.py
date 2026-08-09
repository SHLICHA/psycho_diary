"""Wave 4 MAX: user feedback / support."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from messages import get_message
from bot.handlers.max import state as max_state
from bot.keyboards import get_add_foto_kb, get_back_keyboard, get_skip_kb
from bot.states.feedback_states import FeedbackStates
from core.services.feedback_service import feedback_service

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)


async def handle_feedback_start(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    max_state.set_fsm_state(max_id, FeedbackStates.waiting_message)
    await send_func(get_message('feedback', language), get_back_keyboard(language))
    return {'ok': True, 'handled': 'feedback_start'}


async def process_feedback_text_message(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    fsm = max_state.get_fsm_state(max_id)
    if fsm != FeedbackStates.waiting_message.state:
        return None

    language = user.language or 'ru'
    max_state.set_fsm_state(
        max_id,
        FeedbackStates.waiting_photo,
        feedback_text=(text or '').strip(),
    )
    await send_func(get_message('screenshot_prompt', language), get_add_foto_kb(language))
    return {'ok': True, 'handled': 'feedback_text'}


async def handle_skip_photo(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    import base64

    language = user.language or 'ru'
    raw = max_state.get_raw_state(max_id)
    message_text = raw.get('feedback_text') or ''
    voice_data = None
    if raw.get('voice_data_b64'):
        try:
            voice_data = base64.b64decode(raw['voice_data_b64'])
        except Exception:
            voice_data = None
    result = await feedback_service.submit_user_feedback_use_case(
        user=user,
        message_text=message_text,
        language=language,
        voice_data=voice_data,
    )
    if result.get('clear_state'):
        max_state.clear_fsm_state(max_id)

    if not result.get('success'):
        await send_func(result.get('thanks_text') or get_message('error_generic', language))
        return {'ok': True, 'handled': 'skip_photo', 'error': True}

    # Developer notify is Telegram-oriented; persist already done in use case.
    # Best-effort notify if helper accepts None bot / MAX user.
    try:
        from bot.utils.admin_utils import send_feedback_to_developer
        from bot.utils.state_manager import state_manager

        notify_payload = result.get('notify_payload') or {}
        bot = getattr(state_manager, '_bot_instance', None)
        await send_feedback_to_developer(
            bot=bot,
            feedback=result['feedback'],
            user=notify_payload.get('user') or user,
            message_text=notify_payload.get('message_text') or message_text,
            voice_data=notify_payload.get('voice_data'),
            photo_data=notify_payload.get('photo_data'),
            photo_file_id=notify_payload.get('photo_file_id'),
        )
    except Exception as exc:
        logger.warning('[MAX feedback] developer notify failed: %s', exc)

    max_state.clear_fsm_state(max_id)
    await send_func(result.get('thanks_text') or get_message('feedback_thanks', language), get_back_keyboard(language))
    return {'ok': True, 'handled': 'skip_photo'}


async def handle_add_screenshot(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    """Prompt user to send a photo attachment in MAX."""
    language = user.language or 'ru'
    if not max_state.matches_state(max_id, FeedbackStates.waiting_photo):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'add_screenshot', 'error': 'wrong_state'}
    await send_func(
        get_message('screenshot_instructions', language),
        get_skip_kb(language, 'skip_photo'),
    )
    return {'ok': True, 'handled': 'add_screenshot'}


async def process_feedback_voice(
    user: 'User',
    send_func: 'SendFunc',
    *,
    max_id: int,
    voice_bytes: bytes,
) -> dict:
    import base64

    language = user.language or 'ru'
    max_state.set_fsm_state(
        max_id,
        FeedbackStates.waiting_photo,
        feedback_text='Голосовое сообщение',
        voice_data_b64=base64.b64encode(voice_bytes).decode('ascii'),
    )
    await send_func(
        get_message('voice_message_accepted', language),
        get_add_foto_kb(language),
    )
    return {'ok': True, 'handled': 'feedback_voice'}


async def process_feedback_photo(
    user: 'User',
    send_func: 'SendFunc',
    *,
    max_id: int,
    photo_bytes: bytes,
    photo_file_id: Optional[str] = None,
    photo_file_size: Optional[int] = None,
) -> dict:
    import base64

    language = user.language or 'ru'
    raw = max_state.get_raw_state(max_id)
    message_text = raw.get('feedback_text') or 'Без текстового сообщения'
    voice_data = None
    if raw.get('voice_data_b64'):
        try:
            voice_data = base64.b64decode(raw['voice_data_b64'])
        except Exception:
            voice_data = None
    elif raw.get('voice_data'):
        voice_data = raw.get('voice_data')

    result = await feedback_service.submit_user_feedback_use_case(
        user=user,
        message_text=message_text,
        language=language,
        voice_data=voice_data,
        photo_bytes=photo_bytes,
        photo_file_id=photo_file_id,
        photo_file_size=photo_file_size,
    )
    if result.get('mode') == 'photo_too_large':
        await send_func(result['thanks_text'])
        return {'ok': True, 'handled': 'feedback_photo', 'mode': 'photo_too_large'}

    if result.get('clear_state'):
        max_state.clear_fsm_state(max_id)

    if not result.get('success'):
        await send_func(result.get('thanks_text') or get_message('error_generic', language))
        return {'ok': True, 'handled': 'feedback_photo', 'error': True}

    try:
        from bot.utils.admin_utils import send_feedback_to_developer
        from bot.utils.state_manager import state_manager

        notify_payload = result.get('notify_payload') or {}
        bot = getattr(state_manager, '_bot_instance', None)
        await send_feedback_to_developer(
            bot=bot,
            feedback=result['feedback'],
            user=notify_payload.get('user') or user,
            message_text=notify_payload.get('message_text') or message_text,
            voice_data=notify_payload.get('voice_data'),
            photo_data=notify_payload.get('photo_data') or photo_bytes,
            photo_file_id=notify_payload.get('photo_file_id') or photo_file_id,
        )
    except Exception as exc:
        logger.warning('[MAX feedback] developer notify failed: %s', exc)

    max_state.clear_fsm_state(max_id)
    await send_func(
        result.get('thanks_text') or get_message('feedback_thanks', language),
        get_back_keyboard(language),
    )
    return {'ok': True, 'handled': 'feedback_photo'}


def is_wave4_callback(payload: str) -> bool:
    return payload in {'add_screenshot', 'skip_photo', 'feedback'}


async def route_wave4_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not is_wave4_callback(payload):
        return None
    if payload == 'feedback':
        return await handle_feedback_start(user, send_func, max_id=max_id)
    if payload == 'skip_photo':
        return await handle_skip_photo(user, send_func, max_id=max_id)
    if payload == 'add_screenshot':
        return await handle_add_screenshot(user, send_func, max_id=max_id)
    return {'ok': True, 'handled': 'wave4_unhandled', 'payload': payload}
