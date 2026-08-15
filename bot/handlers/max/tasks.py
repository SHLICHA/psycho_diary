"""Wave 6 MAX: therapy tasks (list / complete / history)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from messages import get_message
from bot.handlers.max import state as max_state
from bot.handlers.max.send_adapter import edit_or_send, ensure_processing_status
from bot.keyboards import (
    get_confirm_delete_task_keyboard,
    get_single_button_keyboard,
    get_task_history_list_keyboard,
    get_task_history_main_keyboard,
)
from bot.states.task_states import TaskStates
from diary.services.task_display_service import task_display_service
from diary.services.task_management_service import (
    analyze_completed_task_for_notification_use_case,
    complete_task_with_feelings_use_case,
    delete_task,
    get_user_task_by_id,
    restore_skipped_task_use_case,
    skip_task,
)

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)


async def handle_show_tasks(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    language = user.language or 'ru'
    max_state.clear_fsm_state(max_id)
    view = await task_display_service.build_active_tasks_view(user, language)
    await send_func(view['text'], view.get('keyboard'))
    return {'ok': True, 'handled': 'tasks'}


async def process_tasks_text(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    fsm = max_state.get_fsm_state(max_id)
    if fsm == TaskStates.waiting_for_task_completion.state:
        return await _process_completion_text(user, text, send_func, max_id=max_id)
    if fsm == TaskStates.describing_feelings.state:
        return await _process_feelings_text(user, text, send_func, max_id=max_id)
    return None


async def _process_completion_text(user, text, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    completion_text = (text or '').strip()
    if len(completion_text) < 1:
        await send_func(get_message('invalid_input', language))
        return {'ok': True, 'handled': 'task_completion', 'error': 'empty'}
    raw = max_state.get_raw_state(max_id)
    max_state.set_fsm_state(
        max_id,
        TaskStates.describing_feelings,
        completing_task_id=raw.get('completing_task_id'),
        task_description=raw.get('task_description'),
        completion_text=completion_text,
    )
    await send_func(
        get_message('ask_feelings_description', language),
        get_single_button_keyboard(language, 'tasks', 'btn_back'),
    )
    return {'ok': True, 'handled': 'task_completion'}


async def _process_feelings_text(user, text, send_func, *, max_id: int) -> dict:
    language = user.language or 'ru'
    feelings_text = (text or '').strip()
    if len(feelings_text) < 1:
        await send_func(get_message('invalid_input', language))
        return {'ok': True, 'handled': 'task_feelings', 'error': 'empty'}

    status_id = await ensure_processing_status(send_func, language, 'task_processing')
    raw = max_state.get_raw_state(max_id)
    task_id = raw.get('completing_task_id')
    completion_text = raw.get('completion_text') or ''
    if not task_id:
        max_state.clear_fsm_state(max_id)
        await edit_or_send(send_func, status_id, get_message('error_generic', language))
        return {'ok': True, 'handled': 'task_feelings', 'error': 'missing_task'}

    completion_response = await complete_task_with_feelings_use_case(
        user=user,
        task_id=task_id,
        completion_text=completion_text,
        feelings_text=feelings_text,
        language=language,
    )
    max_state.clear_fsm_state(max_id)

    if not completion_response.success:
        await edit_or_send(
            send_func,
            status_id,
            completion_response.message or get_message('error_processing', language),
        )
        return {'ok': True, 'handled': 'task_feelings', 'error': True}

    task_completion_obj = (completion_response.data or {}).get('task_completion')
    if task_completion_obj:
        # Нельзя create_task: webhook идёт через async_to_sync, клиент закрывается
        # в finally dispatch — фон отменяется и TaskCompletionAnalysis не пишется.
        await _notify_analysis(
            task_completion_obj, user, send_func, status_id=status_id
        )
    else:
        await edit_or_send(
            send_func,
            status_id,
            get_message('error_processing', language),
        )
    return {'ok': True, 'handled': 'task_feelings'}


async def _notify_analysis(task_completion, user, send_func, *, status_id=None) -> None:
    language = getattr(user, 'language', None) or 'ru'
    try:
        response = await analyze_completed_task_for_notification_use_case(
            task_completion=task_completion,
            user=user,
            language=language,
        )
        payload = response.data or {}
        text = payload.get('notification_text') or get_message(
            'task_analysis_error_formatted', language
        )
        keyboard = payload.get('notification_keyboard')
        await edit_or_send(send_func, status_id, text, keyboard)
    except Exception as exc:
        logger.error('[MAX tasks] analysis notify failed: %s', exc, exc_info=True)
        try:
            await edit_or_send(
                send_func,
                status_id,
                get_message('task_analysis_error_formatted', language),
            )
        except Exception:
            pass


def is_wave6_tasks_callback(payload: str) -> bool:
    if payload in {
        'tasks',
        'back_to_tasks',
        'task_history_main',
        'cancel_delete_task',
        'tasks_empty',
        'task_history_empty',
        'show_task_impact_chart',
    }:
        return True
    prefixes = (
        'tasks_paginate:',
        'view_task:',
        'complete_task:',
        'skip_task:',
        'delete_task:',
        'confirm_delete_task:',
        'task_history_paginate:',
        'task_history_restore:',
        'view_detailed_task_analysis:',
    )
    return any(payload.startswith(p) for p in prefixes)


async def route_wave6_tasks_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
    max_client=None,
) -> Optional[dict]:
    if not is_wave6_tasks_callback(payload):
        return None

    language = user.language or 'ru'

    if payload in {'tasks', 'back_to_tasks'}:
        return await handle_show_tasks(user, send_func, max_id=max_id)

    if payload in {'tasks_empty', 'task_history_empty'}:
        return {'ok': True, 'handled': payload, 'mode': 'noop'}

    if payload == 'show_task_impact_chart':
        if not getattr(user, 'is_premium', False):
            await send_func(get_message('feature_requires_premium', language))
            return {'ok': True, 'handled': 'show_task_impact_chart', 'mode': 'premium_required'}
        if max_client is None:
            await send_func(
                'ℹ️ График влияния заданий временно недоступен.'
            )
            return {'ok': True, 'handled': 'show_task_impact_chart', 'mode': 'no_client'}
        status_id = None
        try:
            from bot.utils.task_impact_chart import generate_task_impact_chart_image

            ack = getattr(send_func, 'ack_callback', None)
            if callable(ack):
                await ack('✓')
            status_id = await ensure_processing_status(send_func, language, 'chart_processing')
            days = 30
            caption = get_message('task_impact_chart_caption', language, days=days)
            chart_buf = await generate_task_impact_chart_image(
                user, days=days, language=language
            )
            ok = await max_client.send_image(
                user_id=max_id,
                image_bytes=chart_buf.getvalue(),
                caption=caption,
                filename='task_impact_chart.png',
            )
            if not ok:
                await edit_or_send(
                    send_func,
                    status_id,
                    get_message('error_processing', language),
                )
                return {'ok': True, 'handled': 'show_task_impact_chart', 'error': True}
            # Картинку нельзя «вшить» в status-текст — превращаем статус в подпись.
            await edit_or_send(send_func, status_id, caption)
            return {'ok': True, 'handled': 'show_task_impact_chart'}
        except Exception as exc:
            logger.error('[MAX tasks] impact chart failed: %s', exc, exc_info=True)
            await edit_or_send(
                send_func,
                status_id,
                get_message('error_processing', language),
            )
            return {'ok': True, 'handled': 'show_task_impact_chart', 'error': True}

    if payload.startswith('tasks_paginate:'):
        parts = payload.split(':')
        direction, current_index = parts[1], int(parts[2])
        view = await task_display_service.build_active_tasks_page_view(
            user,
            language,
            index=current_index,
            direction=direction,
            empty_reply_mode='back_only',
        )
        await send_func(view['text'], view.get('keyboard'))
        return {'ok': True, 'handled': 'tasks_paginate'}

    if payload.startswith('view_task:'):
        task_id = int(payload.split(':')[1])
        view = await task_display_service.build_task_detail_view(user, task_id, language)
        if view.get('success'):
            await send_func(view['text'], view.get('keyboard'))
        else:
            await send_func(view.get('alert_text') or get_message('task_not_found', language))
        return {'ok': True, 'handled': 'view_task'}

    if payload.startswith('complete_task:'):
        task_id = int(payload.split(':')[1])
        view = await task_display_service.build_start_completion_view(user, task_id, language)
        if not view.get('success'):
            await send_func(view.get('alert_text') or get_message('task_not_found', language))
            return {'ok': True, 'handled': 'complete_task', 'error': True}
        max_state.set_fsm_state(max_id, view['fsm_state'], **(view.get('fsm_data') or {}))
        await send_func(view['text'], view.get('keyboard'))
        return {'ok': True, 'handled': 'complete_task'}

    if payload.startswith('skip_task:'):
        task_id = int(payload.split(':')[1])
        success = await skip_task(task_id, user)
        if success:
            await send_func(get_message('task_skipped', language))
            return await handle_show_tasks(user, send_func, max_id=max_id)
        await send_func(get_message('task_not_found', language))
        return {'ok': True, 'handled': 'skip_task', 'error': True}

    if payload.startswith('delete_task:'):
        task_id = int(payload.split(':')[1])
        await send_func(
            get_message('confirm_delete_task', language),
            get_confirm_delete_task_keyboard(task_id, language),
        )
        return {'ok': True, 'handled': 'delete_task'}

    if payload.startswith('confirm_delete_task:'):
        task_id = int(payload.split(':')[1])
        success = await delete_task(task_id, user)
        if success:
            await send_func(
                get_message('task_deleted', language),
                get_single_button_keyboard(language, 'tasks', 'btn_back'),
            )
        else:
            await send_func(get_message('task_not_found', language))
        return {'ok': True, 'handled': 'confirm_delete_task'}

    if payload == 'cancel_delete_task':
        await send_func(
            get_message('task_delete_cancelled', language),
            get_single_button_keyboard(language, 'tasks', 'btn_back'),
        )
        return {'ok': True, 'handled': 'cancel_delete_task'}

    if payload == 'task_history_main':
        view = await task_display_service.build_task_history_view(user, language)
        if view.get('mode') == 'list':
            max_state.update_state_data(max_id, task_history_ids=view.get('task_ids', []))
        await send_func(view['text'], view.get('keyboard'))
        return {'ok': True, 'handled': 'task_history_main'}

    if payload.startswith('task_history_paginate:'):
        target_index = int(payload.split(':')[1])
        raw = max_state.get_raw_state(max_id)
        task_ids = raw.get('task_history_ids') or []
        if not task_ids or not (0 <= target_index < len(task_ids)):
            await send_func(get_message('error_generic', language))
            return {'ok': True, 'handled': 'task_history_paginate', 'error': True}
        task_id = task_ids[target_index]
        task = await get_user_task_by_id(user, task_id)
        if not task:
            await send_func(get_message('task_not_found', language))
            return {'ok': True, 'handled': 'task_history_paginate', 'error': True}
        detail = await task_display_service.format_task_history_detail(task, language)
        await send_func(
            detail.text,
            get_task_history_list_keyboard(
                task_ids=task_ids,
                current_index=target_index,
                current_task_status=task.status,
                language=language,
            ),
        )
        return {'ok': True, 'handled': 'task_history_paginate'}

    if payload.startswith('task_history_restore:'):
        task_id = int(payload.split(':')[1])
        raw = max_state.get_raw_state(max_id)
        task_history_ids = raw.get('task_history_ids') or []
        use_case_result = await restore_skipped_task_use_case(
            user, task_id, task_history_ids=task_history_ids
        )
        await send_func(get_message(use_case_result['alert_text_key'], language))
        if use_case_result.get('success'):
            max_state.update_state_data(
                max_id,
                task_history_ids=use_case_result.get('updated_task_history_ids') or [],
            )
            return await handle_show_tasks(user, send_func, max_id=max_id)
        return {'ok': True, 'handled': 'task_history_restore', 'error': True}

    if payload.startswith('view_detailed_task_analysis:'):
        task_id = int(payload.split(':')[1])
        result = await task_display_service.get_task_analysis_detail(user, task_id)
        if not result.get('success'):
            await send_func(
                result.get('message') or get_message('error_generic', language),
                get_task_history_main_keyboard(language),
            )
            return {'ok': True, 'handled': 'view_detailed_task_analysis', 'error': True}
        await send_func(result['text'], result.get('keyboard'))
        return {'ok': True, 'handled': 'view_detailed_task_analysis'}

    return {'ok': True, 'handled': 'tasks_unhandled', 'payload': payload}
