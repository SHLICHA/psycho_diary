import asyncio
import logging
import re

from decimal import Decimal
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from django.conf import settings
from django.utils import timezone

from messages import get_message
from bot.keyboards import (
    get_single_button_keyboard,
    get_premium_keyboard,
    get_purchase_options_keyboard,
    get_token_purchase_options_keyboard,
    get_manage_premium_keyboard
)
# УБРАНО: from bot.utils.payment_utils import create_yookassa_payment, track_payment_status
from users.models import Payment, User
from bot.states.payment_states import PaymentStates
from bot.utils.state_manager import state_manager

# ИМПОРТ НОВОГО СЕРВИСА
from diary.services.payment_service import (
    initiate_subscription_payment,
    initiate_token_payment,
    process_user_email_for_pending_payment,
    is_valid_email # Импортируем валидатор
)

router = Router()
logger = logging.getLogger(__name__)

# УБРАНО: def is_valid_email(email: str) -> bool: ...

@router.message(F.text == "/pay")
async def cmd_pay(message: Message, user, language: str):
    """
    Обработчик команды /pay — открывает меню оплаты.
    """
    try:
        if user.is_premium_active():
            premium_msg = get_message('settings_premium', language=language)
            expires_at = user.premium_expires_at.strftime('%d.%m.%Y %H:%M') if user.premium_expires_at else 'Неизвестно'
            premium_msg += f"\n\nДата окончания подписки: {expires_at}"
            keyboard = get_manage_premium_keyboard(language)
        else:
            premium_msg = get_message('premium_benefits', language=language)
            keyboard = get_purchase_options_keyboard(language)
        await message.answer(
            premium_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /pay: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_premium")
async def show_premium(callback: CallbackQuery, user, language: str):
    """Показ премиум функций или вариантов покупки"""
    try:
        if user.is_premium_active():  # Используем наш новый метод
            # Показываем статус подписки и кнопку "Управление"
            premium_msg = get_message('settings_premium', language=language).format(
                status=get_message('status_enabled', language=language)
            )
            # Можно добавить дату окончания
            expires_at = user.premium_expires_at.strftime('%d.%m.%Y %H:%M') if user.premium_expires_at else 'Неизвестно'
            premium_msg += f"\n\nДата окончания подписки: {expires_at}"

            # Обновляем клавиатуру — добавим кнопку "Продлить"
            keyboard = get_manage_premium_keyboard(language)
        else:
            # Показываем преимущества и кнопки покупки
            premium_msg = get_message('premium_benefits', language=language)

            # Обновляем клавиатуру — теперь там кнопки "Купить"
            keyboard = get_purchase_options_keyboard(language)

        await callback.message.edit_text(
            premium_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе премиум функций: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("purchase_subscription:"))
async def handle_subscription_purchase(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Обработка покупки подписки (месяц/год)."""
    try:
        plan = callback.data.split(":")[1]

        # Вызов сервиса
        result = await initiate_subscription_payment(user, plan)

        if not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            logger.error(f"[Payment Handler] Ошибка при инициации подписки: {error_msg}")
            await callback.answer(get_message('error_generic', language=language), show_alert=True)
            return

        if result['requires_email']:
            # Сохраняем данные в FSM
            await state_manager.set_state(
                state, PaymentStates.waiting_for_email,
                pending_payment_data=result['pending_payment_data']
            )
            await callback.message.edit_text(
                get_message('ask_email_for_receipt', language),
                reply_markup=get_single_button_keyboard(language, 'user_profile', 'btn_cancel')
            )
        else: # Платёж создан
            confirmation_url = result.get('confirmation_url')
            if confirmation_url:
                await callback.message.answer(
                    f"💳 Перейдите по ссылке для оплаты подписки:\n{confirmation_url}\n\n"
                    f"После оплаты вернитесь к боту."
                )
            else:
                # Должно быть, но на всякий случай
                logger.warning(f"[Payment Handler] Платёж создан, но confirmation_url отсутствует для {user.telegram_id}")
                await callback.answer(get_message('error_generic', language=language), show_alert=True)
                return

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при создании платежа для подписки: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.message(PaymentStates.waiting_for_email)
async def process_email_for_subscription(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода email для подписки."""
    try:
        email = message.text.strip()
        if email.lower() in ['назад', 'back', '/start', '/menu', 'отмена', 'cancel']:
            await state_manager.clear_state(state)
            await show_premium(message, user, language) # Возврат в меню премиума
            return

        # Вызов сервиса с валидацией
        data = await state_manager.get_state_data(state)
        pending_payment_data = data.get('pending_payment_data')
        if not pending_payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        result = await process_user_email_for_pending_payment(user, email, pending_payment_data)

        if not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            await message.answer(error_msg) # Валидатор возвращает строку ошибки
            return

        await state_manager.clear_state(state)

        # Платёж создан, отправляем ссылку
        confirmation_url = result.get('confirmation_url')
        if confirmation_url:
            await message.answer(
                f"💳 Перейдите по ссылке для оплаты подписки:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )
            await message.answer(get_message('payment_email_saved', language))
        else:
            # Должно быть, но на всякий случай
            logger.warning(f"[Payment Handler] Платёж (email) создан, но confirmation_url отсутствует для {user.telegram_id}")
            await message.answer(get_message('error_generic', language=language))

    except Exception as e:
        logger.error(f"Ошибка при обработке email для подписки: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.callback_query(F.data == "purchase_tokens:start")
async def start_token_purchase(callback: CallbackQuery, language: str):
    """Начало покупки токенов — показываем варианты."""
    try:
        await callback.message.edit_text(
            "💎 <b>Выберите пакет токенов:</b>",
            reply_markup=get_token_purchase_options_keyboard(language)
        )
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

        # Вызов сервиса
        result = await initiate_token_payment(user, token_count)

        if not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            logger.error(f"[Payment Handler] Ошибка при инициации покупки токенов: {error_msg}")
            await callback.answer(get_message('error_generic', language=language), show_alert=True)
            return

        if result['requires_email']:
            # Сохраняем данные в FSM
            await state_manager.set_state(
                state, PaymentStates.waiting_for_tokens_email,
                pending_payment_data=result['pending_payment_data']
            )
            await callback.message.edit_text(
                get_message('ask_email_for_receipt', language),
                reply_markup=get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel')
            )
        else: # Платёж создан
            confirmation_url = result.get('confirmation_url')
            if confirmation_url:
                await callback.message.answer(
                    f"💳 Перейдите по ссылке для оплаты токенов:\n{confirmation_url}\n\n"
                    f"После оплаты вернитесь к боту."
                )
            else:
                # Должно быть, но на всякий случай
                logger.warning(f"[Payment Handler] Платёж за токены создан, но confirmation_url отсутствует для {user.telegram_id}")
                await callback.answer(get_message('error_generic', language=language), show_alert=True)
                return

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при обработке покупки токенов: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.message(PaymentStates.waiting_for_tokens_email)
async def process_email_for_tokens(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода email для покупки токенов."""
    try:
        email = message.text.strip()
        if email.lower() in ['назад', 'back', '/start', '/menu', 'отмена', 'cancel']:
            await state_manager.clear_state(state)
            await start_token_purchase(message, language)
            return

        # Вызов сервиса с валидацией
        data = await state_manager.get_state_data(state)
        pending_payment_data = data.get('pending_payment_data')
        if not pending_payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        result = await process_user_email_for_pending_payment(user, email, pending_payment_data)

        if not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            await message.answer(error_msg) # Валидатор возвращает строку ошибки
            return

        await state_manager.clear_state(state)

        # Платёж создан, отправляем ссылку
        confirmation_url = result.get('confirmation_url')
        if confirmation_url:
            await message.answer(
                f"💳 Перейдите по ссылке для оплаты токенов:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )
            await message.answer(get_message('payment_email_saved', language))
        else:
            # Должно быть, но на всякий случай
            logger.warning(f"[Payment Handler] Платёж за токены (email) создан, но confirmation_url отсутствует для {user.telegram_id}")
            await message.answer(get_message('error_generic', language=language))

    except Exception as e:
        logger.error(f"Ошибка при обработке email для токенов: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

# --- Вспомогательные функции для инициации платежей ---

# УБРАНО: async def _initiate_payment(...)
# УБРАНО: async def _initiate_token_payment(...)

@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Отмена ввода email и возврат в меню."""
    await state_manager.clear_state(state)
    # Возвращаем в меню, откуда был вызов. Для простоты — в премиум.
    await show_premium(callback, user, language)
    await callback.answer("Оплата отменена")
