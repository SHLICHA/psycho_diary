"""Wave 1 MAX text message handlers (FSM-aware)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from messages import get_message
from bot.handlers.max import state as max_state
from bot.handlers.max.send_adapter import edit_or_send, ensure_processing_status
from bot.handlers.max.commands import (
    handle_fallback,
    handle_help,
    handle_main_menu,
    handle_settings,
    handle_start,
)
from bot.keyboards import get_settings_keyboard
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.diary_service import diary_service
from bot.states.diary_states import DiaryStates
from bot.states.feedback_states import FeedbackStates
from bot.states.onboarding_states import OnboardingStates
from bot.states.settings_states import SettingsStates
from bot.states.task_states import TaskStates
from bot.states.therapy_chat_states import TherapyChatStates
from diary.services.onboarding_service import build_first_onboarding_entry_result_view
from diary.services.settings_service import (
    build_city_timezone_lookup_view,
    process_city_timezone_lookup,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from bot.transports.max.client import MaxClient
    from bot.transports.max.inbound import MaxMediaInfo
    from users.models import User

logger = logging.getLogger(__name__)

_VOICE_FSM_STATES = {
    DiaryStates.waiting_for_text_entry.state,
    DiaryStates.waiting_for_clarification.state,
    DiaryStates.waiting_for_entry_edit.state,
    DiaryStates.waiting_for_user_comment.state,
    DiaryStates.waiting_for_voice_entry.state,
    OnboardingStates.waiting_for_first_entry.state,
    TaskStates.waiting_for_task_completion.state,
    TaskStates.describing_feelings.state,
    TherapyChatStates.in_therapy_chat.state,
}


async def route_text_message(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
    media: Optional['MaxMediaInfo'] = None,
    max_client: Optional['MaxClient'] = None,
) -> dict:
    text = (text or '').strip()
    language = user.language or 'ru'
    fsm = max_state.get_fsm_state(max_id)

    # Media-first: photo for feedback, voice → STT or feedback voice blob
    if media is not None and max_client is not None:
        media_result = await _handle_inbound_media(
            user,
            text,
            send_func,
            max_id=max_id,
            media=media,
            max_client=max_client,
            fsm=fsm,
        )
        if media_result is not None:
            return media_result

    # Commands (MAX delivers /start etc. as plain text)
    lower = text.lower()
    if lower.startswith('/start') or lower == 'start':
        return await handle_start(user, send_func, max_id=max_id)
    if lower.startswith('/help') or lower == 'help':
        return await handle_help(user, send_func)
    if lower.startswith('/settings') or lower == 'settings':
        return await handle_settings(user, send_func)
    if lower.startswith('/menu') or lower == 'menu':
        return await handle_main_menu(user, send_func, max_id=max_id)
    if lower.startswith('/progress') or lower == 'progress':
        from bot.handlers.max.diary import handle_progress
        return await handle_progress(user, send_func)
    if lower.startswith('/archive') or lower == 'archive' or lower.startswith('/history'):
        from bot.handlers.max.diary import handle_archive
        return await handle_archive(user, send_func, max_id=max_id)
    if (
        lower.startswith('/pay')
        or lower.startswith('/premium')
        or lower in {'pay', 'premium'}
    ):
        from bot.handlers.max.payments import handle_premium_menu
        return await handle_premium_menu(user, send_func, max_id=max_id)
    if lower.startswith('/admin') or lower == 'admin':
        from bot.handlers.max.admin import handle_admin_menu
        return await handle_admin_menu(user, send_func)
    if lower.startswith('/stats') or lower == 'stats':
        from bot.handlers.max.admin import handle_stats
        return await handle_stats(user, send_func, max_id=max_id, max_client=max_client)
    # /feedbacks before /feedback (startswith overlap)
    if lower.startswith('/feedbacks') or lower == 'feedbacks':
        from bot.handlers.max.admin import handle_feedbacks_list
        return await handle_feedbacks_list(user, send_func, max_id=max_id)
    if lower.startswith('/broadcast') or lower == 'broadcast':
        from bot.handlers.max.admin import handle_broadcast_start
        return await handle_broadcast_start(user, send_func, max_id=max_id)
    if (
        lower.startswith('/feedback')
        or lower.startswith('/support')
        or lower in {'feedback', 'support'}
    ):
        from bot.handlers.max.feedback import handle_feedback_start
        return await handle_feedback_start(user, send_func, max_id=max_id)
    if lower.startswith('/tasks') or lower == 'tasks':
        from bot.handlers.max.tasks import handle_show_tasks
        return await handle_show_tasks(user, send_func, max_id=max_id)
    if lower.startswith('/profile') or lower == 'profile':
        from bot.handlers.max.profile import handle_user_profile
        return await handle_user_profile(user, send_func)

    if fsm == OnboardingStates.waiting_for_first_entry.state:
        return await _process_first_entry(user, text, send_func, max_id=max_id)

    if fsm == SettingsStates.waiting_for_city_input.state:
        return await _process_city_input(user, text, send_func, max_id=max_id)

    from bot.handlers.max.feedback import process_feedback_text_message

    feedback_result = await process_feedback_text_message(user, text, send_func, max_id=max_id)
    if feedback_result is not None:
        return feedback_result

    from bot.handlers.max.admin import process_admin_text_message

    admin_result = await process_admin_text_message(user, text, send_func, max_id=max_id)
    if admin_result is not None:
        return admin_result

    from bot.handlers.max.therapy import process_therapy_text

    therapy_result = await process_therapy_text(user, text, send_func, max_id=max_id)
    if therapy_result is not None:
        return therapy_result

    from bot.handlers.max.tasks import process_tasks_text

    tasks_result = await process_tasks_text(user, text, send_func, max_id=max_id)
    if tasks_result is not None:
        return tasks_result

    from bot.handlers.max.profile import process_profile_text

    profile_result = await process_profile_text(user, text, send_func, max_id=max_id)
    if profile_result is not None:
        return profile_result

    from bot.handlers.max.payments import process_payment_email_text

    payment_result = await process_payment_email_text(user, text, send_func, max_id=max_id)
    if payment_result is not None:
        return payment_result

    from bot.handlers.max.diary import process_diary_text

    diary_result = await process_diary_text(user, text, send_func, max_id=max_id)
    if diary_result is not None:
        return diary_result

    # bot_started / empty text during onboarding → restart
    if not text:
        if not user.is_onboarding_completed:
            return await handle_start(user, send_func, max_id=max_id)
        return await handle_fallback(user, send_func)

    return await handle_fallback(user, send_func)


async def _handle_inbound_media(
    user,
    text: str,
    send_func,
    *,
    max_id: int,
    media: 'MaxMediaInfo',
    max_client: 'MaxClient',
    fsm: Optional[str],
) -> Optional[dict]:
    language = user.language or 'ru'

    if media.kind == 'image' and fsm == FeedbackStates.waiting_photo.state:
        from bot.handlers.max.feedback import process_feedback_photo
        from bot.handlers.max.media import download_media_bytes

        photo_bytes = await download_media_bytes(max_client, media)
        if not photo_bytes:
            await send_func('❌ Ошибка загрузки фото. Попробуйте другое изображение.')
            return {'ok': True, 'handled': 'feedback_photo', 'error': 'download'}
        return await process_feedback_photo(
            user,
            send_func,
            max_id=max_id,
            photo_bytes=photo_bytes,
            photo_file_id=media.file_id,
            photo_file_size=media.size,
        )

    if media.kind == 'audio':
        if fsm == FeedbackStates.waiting_message.state:
            from bot.handlers.max.feedback import process_feedback_voice
            from bot.handlers.max.media import download_media_bytes

            voice_bytes = await download_media_bytes(max_client, media)
            if not voice_bytes:
                await send_func(
                    '❌ Не удалось обработать голосовое сообщение. Попробуйте еще раз.'
                )
                return {'ok': True, 'handled': 'feedback_voice', 'error': 'download'}
            return await process_feedback_voice(
                user, send_func, max_id=max_id, voice_bytes=voice_bytes
            )

        if fsm in _VOICE_FSM_STATES or (
            fsm
            and (
                fsm.startswith('DiaryStates:')
                or fsm.startswith('TaskStates:')
                or fsm.startswith('TherapyChatStates:')
                or fsm.startswith('OnboardingStates:waiting_for_first_entry')
            )
        ):
            from bot.handlers.max.media import recognize_max_voice

            ok, recognized, err, status_id = await recognize_max_voice(
                max_client,
                media,
                language=language,
                context_name='MAX Voice',
                send_func=send_func,
            )
            if not ok:
                await edit_or_send(
                    send_func,
                    status_id,
                    f"{get_message('error_processing', language)}: {err}",
                )
                return {'ok': True, 'handled': 'voice_stt', 'error': True}
            # Передаём status_id дальше: diary/therapy/tasks переиспользуют его.
            try:
                send_func.pending_status_id = status_id  # type: ignore[attr-defined]
            except Exception:
                pass
            return await route_text_message(
                user, recognized, send_func, max_id=max_id, media=None, max_client=max_client
            )

        return await handle_fallback(user, send_func, is_voice=True)

    return None


async def _process_first_entry(user, entry_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    if not entry_text.strip():
        await send_func(get_message('entry_empty', language))
        return {'ok': True, 'handled': 'first_entry', 'error': 'empty'}

    status_id = await ensure_processing_status(send_func, language)
    response = await diary_service.process_first_onboarding_entry_use_case(
        user=user,
        entry_text=entry_text,
        language=language,
        entry_datetime=None,
    )
    view = build_first_onboarding_entry_result_view(response, language)
    if not view.get('success'):
        await edit_or_send(
            send_func,
            status_id,
            view.get('text') or get_message('error_generic', language),
        )
        return {'ok': True, 'handled': 'first_entry', 'error': True}

    markup = await get_main_menu_keyboard(language, user)
    await edit_or_send(send_func, status_id, view['text'], markup)
    if view.get('clear_state'):
        max_state.clear_fsm_state(max_id)
    await user.arefresh_from_db()
    return {'ok': True, 'handled': 'first_entry', 'mode': view.get('mode')}


async def _process_city_input(user, city_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    lookup = await process_city_timezone_lookup(city_text, language)
    view = build_city_timezone_lookup_view(lookup, language, city_name=city_text)
    if view.get('mode') == 'cancel':
        max_state.clear_fsm_state(max_id)
        await send_func(view['text'], get_settings_keyboard(user, language))
        return {'ok': True, 'handled': 'city_input', 'mode': 'cancel'}
    await send_func(
        view.get('text') or get_message('error_generic', language),
        view.get('reply_markup'),
    )
    return {'ok': True, 'handled': 'city_input', 'mode': view.get('mode')}
