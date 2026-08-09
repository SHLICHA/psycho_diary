"""Wave 5 MAX: admin — stats / feedbacks / broadcast / reply."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.conf import settings

from messages import get_button_text, get_message
from bot.handlers.max import state as max_state
from bot.transports.max.client import MaxClient
from core.services.admin_service import admin_service
from core.services.feedback_service import feedback_service

if TYPE_CHECKING:
    from bot.handlers.max.send_adapter import SendFunc
    from users.models import User

logger = logging.getLogger(__name__)

STATE_BROWSING_FEEDBACKS = 'admin_browsing_feedbacks'
STATE_WAITING_FEEDBACK_REPLY = 'admin_waiting_feedback_reply'
STATE_BROADCAST_TYPE = 'BroadcastStates:waiting_broadcast_type'
STATE_BROADCAST_MESSAGE = 'BroadcastStates:waiting_broadcast_message'

ADMIN_MENU_TEXT = (
    '🛠 <b>Админ-панель (MAX)</b>\n\n'
    '/stats — статистика\n'
    '/feedbacks — необработанные обращения\n'
    '/broadcast — рассылка пользователям MAX\n'
)


def is_max_admin(user: 'User') -> bool:
    return admin_service.is_developer_user(user)


def _build_max_client() -> MaxClient:
    return MaxClient(
        api_token=getattr(settings, 'MAX_BOT_TOKEN', ''),
        base_url=getattr(settings, 'MAX_API_BASE_URL', 'https://platform-api2.max.ru'),
        timeout_seconds=getattr(settings, 'MAX_API_TIMEOUT_SECONDS', 10),
        rate_limit_rps=getattr(settings, 'MAX_RATE_LIMIT_RPS', 10),
        rate_limit_burst=getattr(settings, 'MAX_RATE_LIMIT_BURST', 50),
        max_message_length=getattr(settings, 'MAX_MESSAGE_MAX_LENGTH', 3500),
    )


async def _deny(send_func: 'SendFunc') -> dict:
    await send_func('❌ У вас нет прав для выполнения этой команды.')
    return {'ok': True, 'handled': 'admin_forbidden', 'mode': 'forbidden'}


async def handle_admin_menu(user: 'User', send_func: 'SendFunc') -> dict:
    if not is_max_admin(user):
        return await _deny(send_func)
    await send_func(ADMIN_MENU_TEXT)
    return {'ok': True, 'handled': 'admin'}


async def handle_stats(
    user: 'User',
    send_func: 'SendFunc',
    *,
    max_id: int | None = None,
    max_client=None,
) -> dict:
    if not is_max_admin(user):
        return await _deny(send_func)
    try:
        stats = await admin_service.get_admin_stats()
        text = admin_service.build_admin_stats_report(stats)
        await send_func(text)

        if max_client is not None and max_id is not None:
            try:
                from bot.utils.activity_chart import (
                    generate_activity_chart_image,
                    generate_hourly_activity_chart_image,
                )

                daily = await generate_activity_chart_image(user, days=30)
                await max_client.send_image(
                    user_id=max_id,
                    image_bytes=daily.getvalue(),
                    caption='📈 Активность пользователей по дням',
                    filename='activity_chart.png',
                )
                hourly = await generate_hourly_activity_chart_image(user, days=30)
                await max_client.send_image(
                    user_id=max_id,
                    image_bytes=hourly.getvalue(),
                    caption='⏰ Активность пользователей по часам',
                    filename='hourly_activity_chart.png',
                )
            except Exception as chart_exc:
                logger.warning('[MAX admin] stats charts failed: %s', chart_exc)
                await send_func('ℹ️ Не удалось отправить графики активности.')
        else:
            await send_func(
                'ℹ️ Графики активности доступны при полном MAX runtime.'
            )
        return {'ok': True, 'handled': 'stats'}
    except Exception as exc:
        logger.error('[MAX admin] stats failed: %s', exc, exc_info=True)
        await send_func('❌ Ошибка при сборе статистики.')
        return {'ok': True, 'handled': 'stats', 'error': True}


async def handle_feedbacks_list(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    if not is_max_admin(user):
        return await _deny(send_func)
    language = user.language or 'ru'
    try:
        feedbacks = await feedback_service.get_unprocessed_feedbacks()
        if not feedbacks:
            await send_func('🎉 Нет новых необработанных обращений!')
            max_state.clear_fsm_state(max_id)
            return {'ok': True, 'handled': 'feedbacks', 'mode': 'empty'}

        feedback_ids = [f.id for f in feedbacks]
        max_state.set_fsm_state(
            max_id,
            STATE_BROWSING_FEEDBACKS,
            admin_feedback_list=feedback_ids,
            admin_feedback_current_index=0,
        )
        await _show_feedback_at_index(send_func, max_id, 0, language)
        return {'ok': True, 'handled': 'feedbacks', 'mode': 'list'}
    except Exception as exc:
        logger.error('[MAX admin] feedbacks list failed: %s', exc, exc_info=True)
        await send_func('❌ Ошибка при получении списка обращений')
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'feedbacks', 'error': True}


async def _show_feedback_at_index(
    send_func: 'SendFunc',
    max_id: int,
    index: int,
    language: str,
) -> None:
    raw = max_state.get_raw_state(max_id)
    feedback_ids = raw.get('admin_feedback_list') or []
    view = await feedback_service.build_admin_feedback_item_view(feedback_ids, index)
    max_state.update_state_data(
        max_id,
        admin_feedback_list=view.get('feedback_ids', []),
        admin_feedback_current_index=view.get('index', 0),
    )
    if view.get('clear_state'):
        max_state.clear_fsm_state(max_id)
    await send_func(view.get('text') or '❌ Обращение не найдено.', view.get('reply_markup'))


async def handle_broadcast_start(user: 'User', send_func: 'SendFunc', *, max_id: int) -> dict:
    if not is_max_admin(user):
        return await _deny(send_func)
    language = user.language or 'ru'
    max_state.set_fsm_state(max_id, STATE_BROADCAST_TYPE)
    await send_func(
        get_message('broadcast_select_type', language),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_button_text('broadcast_important_btn', language),
                        callback_data='broadcast_important',
                    ),
                    InlineKeyboardButton(
                        text=get_button_text('broadcast_regular_btn', language),
                        callback_data='broadcast_regular',
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=get_button_text('broadcast_cancel_btn', language),
                        callback_data='cancel_broadcast',
                    )
                ],
            ]
        ),
    )
    return {'ok': True, 'handled': 'broadcast_start'}


async def process_admin_text_message(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    """FSM: broadcast message / admin feedback reply. None if not admin FSM."""
    fsm = max_state.get_fsm_state(max_id)
    if fsm == STATE_BROADCAST_MESSAGE:
        return await _process_broadcast_message(user, text, send_func, max_id=max_id)
    if fsm == STATE_WAITING_FEEDBACK_REPLY:
        return await _process_feedback_reply(user, text, send_func, max_id=max_id)
    return None


async def _process_broadcast_message(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict:
    language = user.language or 'ru'
    if not is_max_admin(user):
        max_state.clear_fsm_state(max_id)
        return await _deny(send_func)

    raw = max_state.get_raw_state(max_id)
    is_important = bool(raw.get('is_important', False))
    client = _build_max_client()
    try:
        users = await admin_service.get_max_users_for_broadcast(is_important)
        result = await admin_service.send_max_broadcast_message(
            client, users, text, is_important
        )
        await send_func(
            get_message(
                'broadcast_success',
                language,
                broadcast_type=get_message(
                    'broadcast_type_selected_important'
                    if is_important
                    else 'broadcast_type_selected_regular',
                    language,
                ),
                success=result['success'],
                failed=result['failed'],
            )
        )
        return {'ok': True, 'handled': 'broadcast_send', 'result': result}
    except Exception as exc:
        logger.error('[MAX admin] broadcast failed: %s', exc, exc_info=True)
        await send_func(get_message('broadcast_error', language))
        return {'ok': True, 'handled': 'broadcast_send', 'error': True}
    finally:
        max_state.clear_fsm_state(max_id)
        close = client.close()
        if hasattr(close, '__await__'):
            await close


async def _process_feedback_reply(
    user: 'User',
    text: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> dict:
    language = user.language or 'ru'
    if not is_max_admin(user):
        max_state.clear_fsm_state(max_id)
        return await _deny(send_func)

    raw = max_state.get_raw_state(max_id)
    feedback_id = raw.get('replying_to_feedback_id')
    if not feedback_id:
        await send_func('❌ Ошибка: ID обращения не найден.')
        max_state.clear_fsm_state(max_id)
        return {'ok': True, 'handled': 'admin_feedback_reply', 'error': 'missing_id'}

    try:
        result = await feedback_service.process_admin_feedback_reply_use_case(
            admin_user=user,
            feedback_id=int(feedback_id),
            reply_text=text,
            language=language,
        )
        if not result.get('success'):
            await send_func(result.get('admin_ack_text') or '❌ Не удалось отправить ответ')
            if result.get('clear_state'):
                max_state.clear_fsm_state(max_id)
            return {'ok': True, 'handled': 'admin_feedback_reply', 'error': True}

        await _deliver_reply_notify(result)
        if result.get('persist_reply'):
            await feedback_service.reply_to_feedback(
                result['feedback_id'], result['reply_text']
            )
        await send_func(result['admin_ack_text'])
        return {'ok': True, 'handled': 'admin_feedback_reply'}
    except Exception as exc:
        logger.error('[MAX admin] feedback reply failed: %s', exc, exc_info=True)
        await send_func('❌ Не удалось отправить ответ')
        return {'ok': True, 'handled': 'admin_feedback_reply', 'error': True}
    finally:
        max_state.clear_fsm_state(max_id)


async def _deliver_reply_notify(result: dict) -> None:
    """Best-effort: MAX user via MaxClient; TG via bot if available."""
    notify_text = result.get('notify_text') or ''
    feedback_id = result.get('feedback_id')
    feedback = await feedback_service.get_feedback_by_id(feedback_id) if feedback_id else None
    target = getattr(feedback, 'user', None) if feedback else None

    if target and getattr(target, 'max_id', None):
        client = _build_max_client()
        try:
            await client.send_message(user_id=int(target.max_id), text=notify_text)
        except Exception as exc:
            logger.warning('[MAX admin] reply notify MAX failed: %s', exc)
        finally:
            close = client.close()
            if hasattr(close, '__await__'):
                await close

    telegram_id = result.get('notify_chat_id') or getattr(target, 'telegram_id', None)
    if telegram_id:
        try:
            from bot.utils.state_manager import state_manager

            bot = getattr(state_manager, '_bot_instance', None)
            if bot is not None:
                await bot.send_message(chat_id=telegram_id, text=notify_text)
        except Exception as exc:
            logger.warning('[MAX admin] reply notify TG failed: %s', exc)


def is_wave5_callback(payload: str) -> bool:
    if payload in {
        'broadcast_important',
        'broadcast_regular',
        'cancel_broadcast',
        'feedback_next',
        'feedback_prev',
        'refresh_feedbacks_list',
        'close_feedback_list',
        'cancel_reply',
    }:
        return True
    if payload.startswith('reply_feedback_'):
        return True
    return False


async def route_wave5_callback(
    user: 'User',
    payload: str,
    send_func: 'SendFunc',
    *,
    max_id: int,
) -> Optional[dict]:
    if not is_wave5_callback(payload):
        return None
    if not is_max_admin(user):
        return await _deny(send_func)

    language = user.language or 'ru'
    fsm = max_state.get_fsm_state(max_id)

    if payload in {'broadcast_important', 'broadcast_regular'}:
        if fsm != STATE_BROADCAST_TYPE:
            await send_func('❌ Некорректное состояние для этого действия.')
            return {'ok': True, 'handled': payload, 'error': 'wrong_state'}
        is_important = payload == 'broadcast_important'
        max_state.set_fsm_state(max_id, STATE_BROADCAST_MESSAGE, is_important=is_important)
        type_text = get_message(
            'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
            language,
        )
        await send_func(
            get_message('broadcast_enter_message', language, broadcast_type=type_text),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=get_button_text('broadcast_cancel_btn', language),
                            callback_data='cancel_broadcast',
                        )
                    ]
                ]
            ),
        )
        return {'ok': True, 'handled': payload}

    if payload == 'cancel_broadcast':
        max_state.clear_fsm_state(max_id)
        await send_func(get_message('broadcast_cancelled', language))
        return {'ok': True, 'handled': 'cancel_broadcast'}

    if payload in {'feedback_next', 'feedback_prev'}:
        if fsm != STATE_BROWSING_FEEDBACKS:
            await send_func('❌ Некорректное состояние для этого действия.')
            return {'ok': True, 'handled': payload, 'error': 'wrong_state'}
        raw = max_state.get_raw_state(max_id)
        current_index = int(raw.get('admin_feedback_current_index') or 0)
        feedback_ids = raw.get('admin_feedback_list') or []
        direction = 'next' if payload == 'feedback_next' else 'prev'
        nav = feedback_service.compute_admin_feedback_nav_index(
            feedback_ids, current_index, direction
        )
        if nav.get('success'):
            max_state.update_state_data(
                max_id, admin_feedback_current_index=nav['new_index']
            )
            await _show_feedback_at_index(send_func, max_id, nav['new_index'], language)
        else:
            await send_func(nav.get('alert_text') or 'Навигация недоступна.')
        return {'ok': True, 'handled': payload}

    if payload == 'refresh_feedbacks_list':
        return await handle_feedbacks_list(user, send_func, max_id=max_id)

    if payload == 'close_feedback_list':
        max_state.clear_fsm_state(max_id)
        await send_func('Список обращений закрыт.')
        return {'ok': True, 'handled': 'close_feedback_list'}

    if payload.startswith('reply_feedback_'):
        try:
            feedback_id = int(payload.rsplit('_', 1)[-1])
        except ValueError:
            await send_func('❌ Некорректный ID обращения.')
            return {'ok': True, 'handled': 'reply_feedback', 'error': True}
        view = await feedback_service.build_admin_reply_prompt_view(feedback_id, language)
        if not view.get('success'):
            await send_func(view.get('alert_text') or '❌ Ошибка.')
            return {'ok': True, 'handled': 'reply_feedback', 'error': True}
        max_state.clear_fsm_state(max_id)
        max_state.set_fsm_state(
            max_id,
            STATE_WAITING_FEEDBACK_REPLY,
            replying_to_feedback_id=feedback_id,
        )
        await send_func(view['text'], view.get('reply_markup'))
        return {'ok': True, 'handled': 'reply_feedback'}

    if payload == 'cancel_reply':
        if fsm != STATE_WAITING_FEEDBACK_REPLY:
            await send_func('❌ Некорректное состояние для отмены.')
            return {'ok': True, 'handled': 'cancel_reply', 'error': 'wrong_state'}
        max_state.clear_fsm_state(max_id)
        await send_func('❌ Ответ отменён')
        return {'ok': True, 'handled': 'cancel_reply'}

    return {'ok': True, 'handled': 'wave5_unhandled', 'payload': payload}
