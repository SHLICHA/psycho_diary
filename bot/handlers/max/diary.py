"""Wave 2 MAX: diary entry, archive/calendar, progress."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from messages import get_message
from bot.handlers.max import state as max_state
from bot.handlers.max.send_adapter import edit_or_send, ensure_processing_status
from bot.keyboards import (
    format_entry_text_for_editing,
    get_single_button_keyboard,
    get_smart_calendar_keyboard,
    get_month_calendar_with_navigation,
)
from bot.presenters.diary_presenter import build_entry_saved_view, build_new_entry_outcome_view
from bot.services.diary_service import diary_service
from diary.services import smart_prompt_manager
from bot.states.diary_states import DiaryStates
from bot.utils.validation_utils import validate_text_entry
from core.constants import MONTH_NAMES_EN, MONTH_NAMES_RU
from core.services.calendar_service import calendar_service
from diary.services.diary_display_service import diary_display_service
from diary.services.progress_service import build_progress_screen_view

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)


async def handle_new_entry_prompt(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    max_state.set_fsm_state(max_id, DiaryStates.waiting_for_text_entry)
    try:
        prompt_text = await smart_prompt_manager.get_prompt_for_user(user, language)
    except Exception as exc:
        logger.warning('[MAX diary] smart prompt failed: %s', exc)
        prompt_text = get_message('ask_entry', language)
    await send_func(
        prompt_text,
        get_single_button_keyboard(language, 'main_menu', 'btn_cancel'),
    )
    return {'ok': True, 'handled': 'new_entry'}


async def handle_progress(user: 'User', send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    view = await build_progress_screen_view(user, language)
    await send_func(view['text'], view.get('reply_markup'))
    return {'ok': True, 'handled': 'progress'}


async def handle_archive(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    max_state.clear_fsm_state(max_id)
    await send_func(
        get_message('archive_menu', language),
        await get_smart_calendar_keyboard(user, language),
    )
    return {'ok': True, 'handled': 'archive'}


async def handle_calendar_month_nav(user: 'User', payload: str, send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    try:
        kind, year_s, month_s = payload.split(':', 2)
        year, month = int(year_s), int(month_s)
        if kind == 'calendar_prev_month':
            year, month = calendar_service.calculate_prev_month(year, month)
        elif kind == 'calendar_next_month':
            year, month = calendar_service.calculate_next_month(year, month)
        target_date = calendar_service.get_target_date_from_callback(year, month)
        text, keyboard = await _build_calendar_month_payload(user, target_date, language)
        await send_func(text, keyboard)
        return {'ok': True, 'handled': kind}
    except Exception as exc:
        logger.error('[MAX diary] calendar nav failed: %s', exc, exc_info=True)
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'calendar_nav', 'error': True}


async def handle_calendar_select_day(user: 'User', payload: str, send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    try:
        _, year_s, month_s, day_s = payload.split(':', 3)
        target_date = date(int(year_s), int(month_s), int(day_s))
        day_view = await diary_display_service.build_day_first_entry_view(user, target_date, language)
        if not day_view.get('success'):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': 'calendar_select_day', 'error': True}
        if day_view['mode'] == 'empty':
            await send_func(day_view['text'], day_view.get('keyboard'))
            return {'ok': True, 'handled': 'calendar_select_day', 'mode': 'empty'}
        return await _send_entry_page(
            user,
            send_func,
            day_view['entry'],
            day_view['entries'],
            day_view['target_date'],
            language,
        )
    except Exception as exc:
        logger.error('[MAX diary] select day failed: %s', exc, exc_info=True)
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'calendar_select_day', 'error': True}


async def handle_entry_pagination(user: 'User', payload: str, send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    try:
        direction, entry_id_s = payload.split(':', 1)
        entry_id = int(entry_id_s)
        nav = 'prev' if direction == 'entry_prev' else 'next'
        result = await diary_display_service.get_entry_with_pagination(user, entry_id, nav)
        if result.get('success'):
            return await _send_entry_page(
                user,
                send_func,
                result['entry'],
                result['entries'],
                result['target_date'],
                language,
            )
        if result.get('error') == 'first_entry':
            await send_func('Это первая запись.')
            return {'ok': True, 'handled': direction, 'boundary': True}
        if result.get('error') == 'last_entry':
            await send_func('Это последняя запись.')
            return {'ok': True, 'handled': direction, 'boundary': True}
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': direction, 'error': True}
    except Exception as exc:
        logger.error('[MAX diary] entry pagination failed: %s', exc, exc_info=True)
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'entry_pagination', 'error': True}


async def handle_entry_edit_start(user: 'User', payload: str, send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    entry_id = int(payload.split(':', 1)[1])
    entry = await diary_service.get_user_entry_by_id(user, entry_id)
    if not entry:
        await send_func(get_message('entry_not_found', language))
        return {'ok': True, 'handled': 'entry_edit', 'error': 'not_found'}
    max_state.set_fsm_state(
        max_id,
        DiaryStates.waiting_for_entry_edit,
        editing_entry_id=entry_id,
    )
    formatted_text = format_entry_text_for_editing(entry.text)
    edit_msg = get_message('ask_entry_edit_with_text', language).format(old_text=formatted_text)
    await send_func(edit_msg, get_single_button_keyboard(language, 'main_menu', 'btn_cancel'))
    return {'ok': True, 'handled': 'entry_edit'}


async def handle_entry_delete_confirm(user: 'User', payload: str, send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    parts = payload.split(':')
    entry_id = int(parts[1])
    view = await diary_display_service.build_entry_delete_confirmation_view(
        user=user, entry_id=entry_id, language=language
    )
    if not view.get('success'):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'entry_delete_confirm', 'error': True}
    await send_func(view['text'], view.get('keyboard'))
    return {'ok': True, 'handled': 'entry_delete_confirm'}


async def handle_confirm_delete_entry(user: 'User', payload: str, send_func: 'SendFunc') -> dict:
    language = user.language or 'ru'
    parts = payload.split(':')
    entry_id = int(parts[1])
    target_date_iso = parts[2] if len(parts) > 2 else None
    response = await diary_service.process_delete_specific_entry_use_case(
        user=user,
        entry_id=entry_id,
        language=language,
        target_date_iso=target_date_iso,
    )
    if not response.success:
        await send_func(response.message or get_message('error_generic', language))
        return {'ok': True, 'handled': 'confirm_delete_specific_entry', 'error': True}
    payload_data = response.data or {}
    day_view = payload_data.get('day_view') or {}
    if day_view.get('mode') == 'entries':
        return await _send_entry_page(
            user,
            send_func,
            day_view['entry'],
            day_view['entries'],
            day_view['target_date'],
            language,
        )
    await send_func(day_view.get('text') or get_message('archive_empty', language), day_view.get('keyboard'))
    return {'ok': True, 'handled': 'confirm_delete_specific_entry'}


async def handle_request_add_comment(user: 'User', payload: str, send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    entry_id = int(payload.split(':', 1)[1])
    use_case_result = await diary_service.start_add_comment_use_case(user, entry_id)
    if use_case_result.get('mode') == 'not_found':
        await send_func(get_message('entry_not_found', language))
        return {'ok': True, 'handled': 'request_add_comment', 'error': 'not_found'}
    if use_case_result.get('mode') == 'already_added':
        await send_func(get_message('comment_already_added', language))
        return {'ok': True, 'handled': 'request_add_comment', 'error': 'already_added'}
    max_state.set_fsm_state(
        max_id,
        DiaryStates.waiting_for_user_comment,
        comment_entry_id=entry_id,
    )
    await send_func(
        get_message('ask_user_comment', language),
        get_single_button_keyboard(language, 'main_menu', 'btn_cancel'),
    )
    return {'ok': True, 'handled': 'request_add_comment'}


async def process_diary_text(user: 'User', text: str, send_func: 'SendFunc', *, max_id: int) -> Optional[dict]:
    """Handle diary FSM text. Returns None if current FSM is not diary-related."""
    fsm = max_state.get_fsm_state(max_id)
    if fsm == DiaryStates.waiting_for_text_entry.state:
        return await _process_new_entry(user, text, send_func, max_id=max_id)
    if fsm == DiaryStates.asking_clarifying_questions.state:
        return await _process_clarification(user, text, send_func, max_id=max_id)
    if fsm == DiaryStates.waiting_for_user_comment.state:
        return await _process_comment(user, text, send_func, max_id=max_id)
    if fsm == DiaryStates.waiting_for_entry_edit.state:
        return await _process_edit(user, text, send_func, max_id=max_id)
    return None


async def _process_new_entry(user, entry_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    status_id = await ensure_processing_status(send_func, language)
    response = await diary_service.process_new_entry_use_case(
        user=user,
        entry_text=entry_text,
        language=language,
        entry_datetime=None,
    )
    outcome_view = await build_new_entry_outcome_view(response, user, language)
    await edit_or_send(
        send_func,
        status_id,
        outcome_view['text'],
        outcome_view.get('reply_markup'),
    )
    if outcome_view.get('fsm_action') == 'clarification':
        max_state.set_fsm_state(
            max_id,
            DiaryStates.asking_clarifying_questions,
            clarifying_entry_id=outcome_view.get('clarifying_entry_id'),
            clarification_questions=outcome_view.get('clarification_questions') or [],
        )
        return {'ok': True, 'handled': 'new_entry_process', 'mode': 'clarification'}
    max_state.clear_fsm_state(max_id)
    return {'ok': True, 'handled': 'new_entry_process', 'mode': outcome_view.get('mode')}


async def _process_clarification(user, clarification_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    raw = max_state.get_raw_state(max_id)
    entry_id = raw.get('clarifying_entry_id')
    questions = raw.get('clarification_questions') or []
    if not entry_id:
        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'clarification', 'error': True}
    diary_entry = await diary_service.get_user_entry_by_id(user, entry_id)
    if not diary_entry:
        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'clarification', 'error': 'not_found'}
    answers = diary_service.build_clarification_answers_map(
        clarification_questions=questions,
        clarification_text=clarification_text,
    )
    status_id = await ensure_processing_status(send_func, language)
    response = await diary_service.process_clarification_answers_use_case(
        user=user,
        diary_entry=diary_entry,
        clarification_answers_dict=answers,
        language=language,
    )
    if not response.success:
        await edit_or_send(
            send_func,
            status_id,
            response.message or get_message('error_processing', language),
        )
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'clarification', 'error': True}
    result = response.data or {}
    view = await build_entry_saved_view(
        entry=result['entry'],
        analysis=result.get('analysis'),
        user=user,
        language=language,
    )
    await edit_or_send(send_func, status_id, view['text'], view.get('reply_markup'))
    max_state.clear_fsm_state(max_id)
    return {'ok': True, 'handled': 'clarification'}


async def _process_comment(user, comment_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    entry_id = max_state.get_raw_state(max_id).get('comment_entry_id')
    if not entry_id:
        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'comment', 'error': True}
    diary_entry = await diary_service.get_user_entry_by_id(user, entry_id)
    if not diary_entry:
        await send_func(get_message('entry_not_found', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'comment', 'error': 'not_found'}
    status_id = await ensure_processing_status(send_func, language)
    response = await diary_service.process_user_comment_use_case(
        user=user,
        diary_entry=diary_entry,
        user_comment_text=comment_text,
        language=language,
    )
    if not response.success:
        await edit_or_send(
            send_func,
            status_id,
            response.message or get_message('error_processing', language),
        )
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'comment', 'error': True}
    result = response.data or {}
    view = await build_entry_saved_view(
        entry=result.get('entry') or diary_entry,
        analysis=result.get('analysis'),
        user=user,
        language=language,
    )
    await edit_or_send(send_func, status_id, view['text'], view.get('reply_markup'))
    max_state.clear_fsm_state(max_id)
    return {'ok': True, 'handled': 'comment'}


async def _process_edit(user, new_text: str, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    is_valid, error_code = validate_text_entry(new_text)
    if not is_valid:
        await send_func(get_message(error_code, language))
        return {'ok': True, 'handled': 'entry_edit_process', 'error': 'invalid'}
    entry_id = max_state.get_raw_state(max_id).get('editing_entry_id')
    if not entry_id:
        await send_func(get_message('error_generic', language))
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'entry_edit_process', 'error': True}
    status_id = await ensure_processing_status(send_func, language)
    response = await diary_service.process_entry_edit_use_case(
        user=user,
        entry_id=entry_id,
        new_text=new_text,
        language=language,
        target_date_iso=None,
    )
    if not response.success:
        await edit_or_send(
            send_func,
            status_id,
            response.message or get_message('error_processing', language),
        )
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'entry_edit_process', 'error': True}
    day_view = (response.data or {}).get('day_view') or {}
    max_state.clear_fsm_state(max_id)
    if day_view.get('mode') == 'entries':
        result = await diary_display_service.format_entry_for_display(
            day_view['entry'],
            day_view['entries'],
            day_view['target_date'],
            language,
        )
        if not result.get('success'):
            await edit_or_send(send_func, status_id, get_message('error_generic', language))
            return {'ok': True, 'handled': 'entry_edit_process', 'error': True}
        await edit_or_send(send_func, status_id, result['text'], result.get('keyboard'))
        return {'ok': True, 'handled': 'entry_edit_process'}
    await edit_or_send(
        send_func,
        status_id,
        get_message('archive_empty', language),
        day_view.get('keyboard'),
    )
    return {'ok': True, 'handled': 'entry_edit_process'}


async def _send_entry_page(user, send_func, entry, entries, target_date, language) -> dict:
    result = await diary_display_service.format_entry_for_display(
        entry, entries, target_date, language
    )
    if not result.get('success'):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'entry_page', 'error': True}
    await send_func(result['text'], result.get('keyboard'))
    return {'ok': True, 'handled': 'entry_page'}


async def _build_calendar_month_payload(user, target_date: date, language: str) -> tuple[str, Any]:
    year, month = target_date.year, target_date.month
    user_local_date = user.get_local_datetime().date()
    current_day = (
        user_local_date.day
        if user_local_date.year == year and user_local_date.month == month
        else 1
    )
    month_names = MONTH_NAMES_RU if language == 'ru' else MONTH_NAMES_EN
    month_name = month_names[month] if 1 <= month <= 12 else ''
    text = get_message('archive_select_month', language).format(month=month_name, year=year)
    keyboard = await get_month_calendar_with_navigation(
        user, year, month, current_day, language
    )
    return text, keyboard


async def route_wave2_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict | None:
    """Route Wave 2 diary/archive/progress callbacks. None if not Wave 2."""
    if not is_wave2_callback(payload):
        return None

    if payload == 'new_entry':
        return await handle_new_entry_prompt(user, send_func, max_id=max_id)
    if payload == 'archive':
        return await handle_archive(user, send_func, max_id=max_id)
    if payload == 'progress':
        return await handle_progress(user, send_func)
    if payload.startswith('calendar_prev_month:') or payload.startswith('calendar_next_month:'):
        return await handle_calendar_month_nav(user, payload, send_func)
    if payload.startswith('calendar_select_day:'):
        return await handle_calendar_select_day(user, payload, send_func)
    if payload.startswith('calendar_return_to_month:'):
        try:
            _, year_s, month_s = payload.split(':', 2)
            target = calendar_service.get_target_date_from_callback(int(year_s), int(month_s))
            text, keyboard = await _build_calendar_month_payload(user, target, user.language or 'ru')
            await send_func(text, keyboard)
            return {'ok': True, 'handled': 'calendar_return_to_month'}
        except Exception as exc:
            logger.error('[MAX diary] return to month failed: %s', exc)
            await send_func(get_message('error_generic', user.language or 'ru'))
            return {'ok': True, 'handled': 'calendar_return_to_month', 'error': True}
    if payload.startswith('entry_prev:') or payload.startswith('entry_next:'):
        return await handle_entry_pagination(user, payload, send_func)
    if payload.startswith('entry_edit:'):
        return await handle_entry_edit_start(user, payload, send_func, max_id=max_id)
    if payload.startswith('entry_delete_confirm') or payload.startswith('request_delete_specific_entry:'):
        # normalize request_delete_specific_entry:id → entry_delete_confirm:id
        if payload.startswith('request_delete_specific_entry:'):
            payload = 'entry_delete_confirm:' + payload.split(':', 1)[1]
        return await handle_entry_delete_confirm(user, payload, send_func)
    if payload.startswith('confirm_delete_specific_entry:'):
        return await handle_confirm_delete_entry(user, payload, send_func)
    if payload.startswith('cancel_delete_specific_entry:'):
        # reopen day via date in payload: cancel_delete_specific_entry:entry_id:YYYY-MM-DD
        parts = payload.split(':')
        if len(parts) >= 3:
            try:
                target = date.fromisoformat(parts[2])
                day_view = await diary_display_service.build_day_first_entry_view(
                    user, target, user.language or 'ru'
                )
                if day_view.get('mode') == 'entries':
                    return await _send_entry_page(
                        user,
                        send_func,
                        day_view['entry'],
                        day_view['entries'],
                        day_view['target_date'],
                        user.language or 'ru',
                    )
                await send_func(day_view.get('text') or '', day_view.get('keyboard'))
                return {'ok': True, 'handled': 'cancel_delete_specific_entry'}
            except Exception as exc:
                logger.warning('[MAX diary] cancel delete reopen failed: %s', exc)
        return await handle_archive(user, send_func, max_id=max_id)
    if payload.startswith('request_add_comment:'):
        return await handle_request_add_comment(user, payload, send_func, max_id=max_id)
    if payload.startswith('rate_analysis:'):
        return await handle_rate_analysis(user, payload, send_func, max_id=max_id)
    if payload == 'calendar_empty':
        return {'ok': True, 'handled': 'calendar_empty', 'ignored': True}

    return {'ok': True, 'handled': 'wave2_unhandled', 'payload': payload}


async def handle_rate_analysis(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict:
    """Сохраняет оценку анализа (callback rate_analysis:{analysis_id}:{rating})."""
    language = user.language or 'ru'
    try:
        parts = payload.split(':')
        if len(parts) != 3:
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': 'rate_analysis', 'error': 'bad_payload'}
        analysis_id = int(parts[1])
        rating = int(parts[2])
    except (TypeError, ValueError):
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'rate_analysis', 'error': 'bad_payload'}

    try:
        result = await diary_display_service.submit_analysis_rating_use_case(
            analysis_id, user, rating
        )
        if result.get('success'):
            logger.info(
                '[MAX diary] rate_analysis saved user_id=%s analysis_id=%s rating=%s',
                user.id,
                analysis_id,
                rating,
            )
            from bot.handlers.max.commands import handle_main_menu

            menu_result = await handle_main_menu(user, send_func, max_id=max_id)
            return {
                'ok': True,
                'handled': 'rate_analysis',
                'mode': 'saved',
                'menu': menu_result.get('handled'),
            }
        if result.get('error') == 'already_rated':
            await send_func(get_message('rating_already_submitted', language))
            return {'ok': True, 'handled': 'rate_analysis', 'mode': 'already_rated'}
        await send_func(get_message('error_generic', language))
        return {
            'ok': True,
            'handled': 'rate_analysis',
            'error': result.get('error') or True,
        }
    except Exception as exc:
        logger.error('[MAX diary] rate_analysis failed: %s', exc, exc_info=True)
        await send_func(get_message('error_generic', language))
        return {'ok': True, 'handled': 'rate_analysis', 'error': True}


def is_wave2_callback(payload: str) -> bool:
    exact = {'new_entry', 'archive', 'progress', 'calendar_empty'}
    if payload in exact:
        return True
    prefixes = (
        'calendar_prev_month:',
        'calendar_next_month:',
        'calendar_select_day:',
        'calendar_return_to_month:',
        'entry_prev:',
        'entry_next:',
        'entry_edit:',
        'entry_delete_confirm',
        'confirm_delete_specific_entry:',
        'cancel_delete_specific_entry:',
        'request_add_comment:',
        'request_delete_specific_entry:',
        'rate_analysis:',
    )
    return any(payload.startswith(p) for p in prefixes)
