import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from messages import get_message
from bot.keyboards.identity_merge_keyboard import get_requester_merge_confirmation_keyboard
from bot.keyboards import get_single_button_keyboard
from bot.states.payment_states import PaymentStates
from bot.utils.state_manager import state_manager
from diary.services.payment_service import (
    initiate_subscription_payment,
    initiate_token_payment,
    process_user_email_for_pending_payment,
    build_premium_menu_view,
    build_payment_initiation_view,
    build_token_purchase_options_view,
    build_email_payment_result_view,
    is_payment_cancel_command,
)

router = Router()
logger = logging.getLogger(__name__)


async def _render_premium_menu(message_or_callback, user, language: str):
    view = build_premium_menu_view(user, language)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(view['text'], reply_markup=view['reply_markup'])
    else:
        await message_or_callback.message.edit_text(
            view['text'],
            reply_markup=view['reply_markup'],
        )


async def _apply_email_payment_result(message: Message, result: dict, payment_kind: str, language: str, state: FSMContext):
    view = build_email_payment_result_view(result, payment_kind, language)
    if view.get('clear_state'):
        await state_manager.clear_state(state)

    if view['mode'] == 'payment_ready':
        for msg_text in view['messages']:
            await message.answer(msg_text)
        return

    if view['mode'] == 'merge_confirmation':
        merge_request_id = view.get('merge_request_id')
        await message.answer(
            view['text'],
            reply_markup=(
                get_requester_merge_confirmation_keyboard(merge_request_id, language)
                if merge_request_id
                else None
            ),
        )
        return

    await message.answer(view['text'])


@router.message(F.text == "/pay")
async def cmd_pay(message: Message, user, language: str):
    """Обработчик команды /pay — открывает меню оплаты."""
    try:
        await _render_premium_menu(message, user, language)
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /pay: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))


@router.callback_query(F.data == "settings_premium")
async def show_premium(callback: CallbackQuery, user, language: str):
    """Показ премиум функций или вариантов покупки"""
    try:
        await _render_premium_menu(callback, user, language)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе премиум функций: {e}")
        await callback.answer(get_message('error_generic', language=language))


@router.callback_query(F.data.startswith("purchase_subscription:"))
async def handle_subscription_purchase(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Обработка покупки подписки (месяц/год)."""
    try:
        plan = callback.data.split(":")[1]
        result = await initiate_subscription_payment(user, plan)
        view = build_payment_initiation_view(result, language, payment_kind='subscription')

        if view['mode'] == 'error':
            logger.error(f"[Payment Handler] Ошибка при инициации подписки: {view.get('error')}")
            await callback.answer(get_message('error_generic', language=language), show_alert=True)
            return

        if view['mode'] == 'requires_email':
            await state_manager.set_state(
                state, PaymentStates.waiting_for_email,
                pending_payment_data=view['pending_payment_data']
            )
            await callback.message.edit_text(
                view['text'],
                reply_markup=get_single_button_keyboard(language, 'user_profile', 'btn_cancel')
            )
        else:
            await callback.message.answer(view['text'])

        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при создании платежа для подписки: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.message(PaymentStates.waiting_for_email)
async def process_email_for_subscription(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода email для подписки."""
    try:
        email = message.text.strip()
        if is_payment_cancel_command(email):
            await state_manager.clear_state(state)
            await _render_premium_menu(message, user, language)
            return

        data = await state_manager.get_state_data(state)
        pending_payment_data = data.get('pending_payment_data')
        if not pending_payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        result = await process_user_email_for_pending_payment(user, email, pending_payment_data)
        await _apply_email_payment_result(message, result, 'subscription', language, state)
    except Exception as e:
        logger.error(f"Ошибка при обработке email для подписки: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)


async def _show_token_purchase_options(target, language: str):
    view = build_token_purchase_options_view(language)
    if isinstance(target, Message):
        await target.answer(view['text'], reply_markup=view['reply_markup'])
    else:
        await target.message.edit_text(view['text'], reply_markup=view['reply_markup'])


@router.callback_query(F.data == "purchase_tokens:start")
async def start_token_purchase(callback: CallbackQuery, language: str):
    """Начало покупки токенов — показываем варианты."""
    try:
        await _show_token_purchase_options(callback, language)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале покупки токенов: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.callback_query(F.data.startswith("purchase_tokens:"))
async def handle_token_purchase(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Обработка покупки токенов (пакет или произвольное количество)."""
    try:
        data = callback.data.split(":", 1)
        action = data[1]
        try:
            token_count = int(action)
        except ValueError:
            await callback.answer("❌ Неверный выбор", show_alert=True)
            return

        result = await initiate_token_payment(user, token_count)
        view = build_payment_initiation_view(result, language, payment_kind='tokens')

        if view['mode'] == 'error':
            logger.error(f"[Payment Handler] Ошибка при инициации покупки токенов: {view.get('error')}")
            await callback.answer(get_message('error_generic', language=language), show_alert=True)
            return

        if view['mode'] == 'requires_email':
            await state_manager.set_state(
                state, PaymentStates.waiting_for_tokens_email,
                pending_payment_data=view['pending_payment_data']
            )
            await callback.message.edit_text(
                view['text'],
                reply_markup=get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel')
            )
        else:
            await callback.message.answer(view['text'])

        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при обработке покупки токенов: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.message(PaymentStates.waiting_for_tokens_email)
async def process_email_for_tokens(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода email для покупки токенов."""
    try:
        email = message.text.strip()
        if is_payment_cancel_command(email):
            await state_manager.clear_state(state)
            await _show_token_purchase_options(message, language)
            return

        data = await state_manager.get_state_data(state)
        pending_payment_data = data.get('pending_payment_data')
        if not pending_payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        result = await process_user_email_for_pending_payment(user, email, pending_payment_data)
        await _apply_email_payment_result(message, result, 'tokens', language, state)
    except Exception as e:
        logger.error(f"Ошибка при обработке email для токенов: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Отмена ввода email и возврат в меню."""
    await state_manager.clear_state(state)
    await show_premium(callback, user, language)
    await callback.answer("Оплата отменена")
