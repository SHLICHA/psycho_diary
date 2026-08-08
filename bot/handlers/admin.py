# /home/shlicha/psycho_diary/bot/handlers/admin.py
"""Admin broadcast/stats handlers (transport-only)."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from messages import get_message, get_button_text
from core.services.admin_service import admin_service
from core.services.base_service import BaseService
from bot.utils.activity_chart import generate_activity_chart_image, generate_hourly_activity_chart_image

router = Router()
logger = logging.getLogger(__name__)

class BroadcastStates(StatesGroup):
    waiting_broadcast_type = State()
    waiting_broadcast_message = State()


@router.message(Command("broadcast"))
async def broadcast_handler(message: Message, state: FSMContext):
    if not admin_service.is_admin(message.from_user.id):
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
        users = await admin_service.get_users_for_broadcast(is_important)
        result = await admin_service.send_broadcast_message(bot, users, message.text, is_important)

        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(
            get_message(
                'broadcast_success',
                language,
                broadcast_type=get_message(
                    'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
                    language
                ),
                success=result['success'],
                failed=result['failed']
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

@router.message(Command("stats"))
async def cmd_admin_stats(message: Message):
    """Transport: stats bundle → send report + charts."""
    try:
        bundle = await admin_service.get_admin_stats_bundle(message.from_user.id)
        if not bundle.get('success'):
            await message.answer(bundle.get('text') or "❌ У вас нет прав для просмотра статистики.")
            return

        await message.answer(bundle['text'], parse_mode='HTML')

        admin_user = await BaseService.get_user_by_telegram_id(message.from_user.id)
        if not admin_user:
            await message.answer("❌ Администратор не найден в базе данных.")
            return

        chart_days = bundle.get('chart_days', 30)
        for chart in bundle.get('charts') or []:
            kind = chart.get('kind')
            try:
                if kind == 'activity_daily':
                    chart_img = await generate_activity_chart_image(admin_user, days=chart_days)
                elif kind == 'activity_hourly':
                    chart_img = await generate_hourly_activity_chart_image(
                        admin_user, days=chart_days
                    )
                else:
                    continue
                input_file = BufferedInputFile(
                    chart_img.getvalue(), filename=chart.get('filename') or 'chart.png'
                )
                await message.answer_photo(
                    photo=input_file, caption=chart.get('caption') or ''
                )
            except Exception as chart_error:
                logger.error(f"Ошибка генерации графика {kind}: {chart_error}")
                await message.answer(f"❌ Ошибка при генерации графика ({kind}).")
    except Exception as e:
        logger.error(f"Ошибка при сборе статистики администратора: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сборе статистики.")
