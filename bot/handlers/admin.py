# /home/shlicha/psycho_diary/bot/handlers/broadcast_handlers.py
"""
Хендлеры для рассылки сообщений администратором
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from django.conf import settings
from asgiref.sync import sync_to_async

from messages import get_message, get_button_text
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

class BroadcastStates(StatesGroup):
    waiting_broadcast_type = State()
    waiting_broadcast_message = State()

def is_admin(telegram_id: int) -> bool:
    dev_chat_id_str = settings.DEVELOPER_CHAT_ID
    if not dev_chat_id_str:
        return False
    try:
        dev_chat_id = int(dev_chat_id_str)
        return telegram_id == dev_chat_id
    except (ValueError, TypeError):
        return False

@router.message(Command("broadcast"))
async def broadcast_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
    await state.set_state(BroadcastStates.waiting_broadcast_type)
    await message.answer(
        get_message('broadcast_select_type', language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_button_text('broadcast_important_btn', language),
                    callback_data="broadcast_important"
                ),
                InlineKeyboardButton(
                    text=get_button_text('broadcast_regular_btn', language),
                    callback_data="broadcast_regular"
                )
            ],
            [InlineKeyboardButton(
                text=get_button_text('broadcast_cancel_btn', language),
                callback_data="cancel_broadcast"
            )]
        ])
    )

@router.callback_query(F.data.startswith("broadcast_"), BroadcastStates.waiting_broadcast_type)
async def set_broadcast_type(callback: CallbackQuery, state: FSMContext):
    try:
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        is_important = callback.data == "broadcast_important"
        await state.update_data(is_important=is_important)
        await state.set_state(BroadcastStates.waiting_broadcast_message)
        broadcast_type_text = get_message(
            'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
            language
        )
        await callback.message.edit_text(
            get_message('broadcast_enter_message', language, broadcast_type=broadcast_type_text),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=get_button_text('broadcast_cancel_btn', language),
                    callback_data="cancel_broadcast"
                )]
            ])
        )
    except Exception as e:
        logger.error(f"Error setting broadcast type: {e}")
        await callback.answer(get_message('broadcast_error', language), show_alert=True)
    finally:
        await callback.answer()

@router.message(BroadcastStates.waiting_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext, bot):
    data = await state.get_data()
    is_important = data.get('is_important', False)
    try:
        if is_important:
            users = await sync_to_async(list)(
                User.objects.filter(
                    is_blocked=False,
                    deletion_status='active',
                    deleted_at__isnull=True
                ).values_list('telegram_id', 'language')
            )
        else:
            users = await sync_to_async(list)(
                User.objects.filter(
                    is_blocked=False,
                    deletion_status='active',
                    deleted_at__isnull=True,
                    notifications_enabled=True
                ).values_list('telegram_id', 'language')
            )

        success = 0
        failed = 0
        for user_id, user_lang in users:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=get_button_text('btn_main_menu', user_lang),
                        callback_data="main_menu"
                    )]
                ])
                await bot.send_message(
                    chat_id=user_id,
                    text=f"{'🔴 ' if is_important else '🔵 '}{get_message('broadcast_prefix', user_lang)}\n\n{message.text}",
                    reply_markup=kb
                )
                success += 1
            except Exception as e:
                if "bot was blocked" in str(e).lower():
                    await User.mark_blocked(user_id)
                failed += 1

        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(
            get_message(
                'broadcast_success',
                language,
                broadcast_type=get_message(
                    'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
                    language
                ),
                success=success,
                failed=failed
            )
        )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(get_message('broadcast_error', language))
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    try:
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        await callback.message.edit_text(get_message('broadcast_cancelled', language))
        await state.clear()
    except Exception as e:
        logger.error(f"Error canceling broadcast: {e}")
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        await callback.answer(get_message('broadcast_failed_cancel', language), show_alert=True)
    finally:
        await callback.answer()