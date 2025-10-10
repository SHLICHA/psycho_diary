# bot/handlers/payments.py
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
    get_token_custom_amount_keyboard,
    get_manage_premium_keyboard
)
from bot.utils.payment_utils import create_yookassa_payment, track_payment_status
from users.models import Payment, User
from bot.states.payment_states import PaymentStates
from bot.utils.state_manager import state_manager

router = Router()
logger = logging.getLogger(__name__)

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

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
        if plan == 'month':
            amount = settings.PREMIUM_PRICE_MONTH
            days = 30
            description = "Подписка PRO на 30 дней"
            payment_type = 'subscription_month'
        elif plan == 'year':
            amount = settings.PREMIUM_PRICE_YEAR
            days = 365
            description = "Подписка PRO на 365 дней"
            payment_type = 'subscription_year'
        else:
            await callback.answer("❌ Неверный тип подписки", show_alert=True)
            return

        # Проверяем email
        if not user.email:
            await state_manager.set_state(
                state, PaymentStates.waiting_for_email,
                pending_payment_data={
                    'amount': amount,
                    'days': days,
                    'description': description,
                    'payment_type': payment_type
                }
            )
            await callback.message.edit_text(
                get_message('ask_email_for_receipt', language),
                reply_markup=get_single_button_keyboard(language, 'user_profile', 'btn_cancel')
            )
            await callback.answer()
            return

        # Если email есть, сразу создаём платеж
        await _initiate_payment(user, amount, days, description, payment_type, callback, language)

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

        if not is_valid_email(email):
            await message.answer(get_message('email_invalid_format', language))
            return

        # Сохраняем email
        user.email = email
        await user.asave(update_fields=['email'])

        # Получаем сохранённые данные платежа
        data = await state_manager.get_state_data(state)
        payment_data = data.get('pending_payment_data')
        if not payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        await state_manager.clear_state(state)

        # Создаём платеж
        await _initiate_payment(
            user,
            payment_data['amount'],
            payment_data['days'],
            payment_data['description'],
            payment_data['payment_type'],
            message, # <-- Message, но мы можем вызвать .answer()
            language
        )
        await message.answer(get_message('payment_email_saved', language))

    except Exception as e:
        logger.error(f"Ошибка при обработке email для подписки: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.callback_query(F.data == "purchase_tokens:start")
async def start_token_purchase(callback: CallbackQuery, language: str):
    """Начало покупки токенов — показываем варианты."""
    try:
        await callback.message.edit_text(
            "💎 <b>Выберите пакет токенов или введите количество вручную:</b>",
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

        if action == 'custom':
            await state_manager.set_state(state, PaymentStates.waiting_for_custom_tokens_amount)
            await callback.message.edit_text(
                "🔢 <b>Введите количество токенов, которое хотите купить:</b>",
                reply_markup=get_token_custom_amount_keyboard(language)
            )
            await callback.answer()
            return

        try:
            token_count = int(action)
        except ValueError:
            await callback.answer("❌ Неверный выбор", show_alert=True)
            return

        # Сопоставляем количество с ценой
        price_map = {
            10: settings.TOKEN_PACK_10,
            100: settings.TOKEN_PACK_100,
            200: settings.TOKEN_PACK_200,
            500: settings.TOKEN_PACK_500,
        }
        if token_count not in price_map:
            await callback.answer("❌ Неверный выбор пакета", show_alert=True)
            return

        amount = price_map[token_count]
        description = f"Покупка {token_count} токенов"
        payment_type = f"tokens_{token_count}"

        # Проверяем email
        if not user.email:
            await state_manager.set_state(
                state, PaymentStates.waiting_for_tokens_email,
                pending_payment_data={
                    'amount': amount,
                    'token_count': token_count,
                    'description': description,
                    'payment_type': payment_type
                }
            )
            await callback.message.edit_text(
                get_message('ask_email_for_receipt', language),
                reply_markup=get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel')
            )
            await callback.answer()
            return

        # Если email есть, сразу создаём платеж
        await _initiate_token_payment(user, amount, token_count, description, payment_type, callback, language)

    except Exception as e:
        logger.error(f"Ошибка при обработке покупки токенов: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

@router.message(PaymentStates.waiting_for_custom_tokens_amount)
async def process_custom_token_amount(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода произвольного количества токенов."""
    try:
        amount_str = message.text.strip()
        if amount_str.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await start_token_purchase(message, language)
            return

        try:
            token_count = int(amount_str)
            if token_count <= 0:
                await message.answer("❌ Количество токенов должно быть положительным числом.")
                return
        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректное число.")
            return

        amount = token_count * settings.TOKEN_PRICE_PER_UNIT
        description = f"Покупка {token_count} токенов (произвольно)"
        payment_type = 'tokens_custom'

        # Проверяем email
        if not user.email:
            await state_manager.set_state(
                state, PaymentStates.waiting_for_tokens_email,
                pending_payment_data={
                    'amount': amount,
                    'token_count': token_count,
                    'description': description,
                    'payment_type': payment_type
                }
            )
            await message.answer(
                get_message('ask_email_for_receipt', language),
                reply_markup=get_single_button_keyboard(language, 'cancel_payment', 'btn_cancel')
            )
            return

        # Если email есть, сразу создаём платеж
        await _initiate_token_payment(user, amount, token_count, description, payment_type, message, language)

    except Exception as e:
        logger.error(f"Ошибка при обработке ввода количества токенов: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

@router.message(PaymentStates.waiting_for_tokens_email)
async def process_email_for_tokens(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода email для покупки токенов."""
    try:
        email = message.text.strip()
        if email.lower() in ['назад', 'back', '/start', '/menu', 'отмена', 'cancel']:
            await state_manager.clear_state(state)
            await start_token_purchase(message, language)
            return

        if not is_valid_email(email):
            await message.answer(get_message('email_invalid_format', language))
            return

        # Сохраняем email
        user.email = email
        await user.asave(update_fields=['email'])

        # Получаем сохранённые данные платежа
        data = await state_manager.get_state_data(state)
        payment_data = data.get('pending_payment_data')
        if not payment_data:
            await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать сначала.")
            await state_manager.clear_state(state)
            return

        await state_manager.clear_state(state)

        # Создаём платеж
        await _initiate_token_payment(
            user,
            payment_data['amount'],
            payment_data['token_count'],
            payment_data['description'],
            payment_data['payment_type'],
            message,
            language
        )
        await message.answer(get_message('payment_email_saved', language))

    except Exception as e:
        logger.error(f"Ошибка при обработке email для токенов: {e}", exc_info=True)
        await message.answer(get_message('error_generic', language=language))
        await state_manager.clear_state(state)

# --- Вспомогательные функции для инициации платежей ---

async def _initiate_payment(user, amount, days, description, payment_type, message_or_callback, language: str):
    """Создаёт платеж в ЮKassa и запись в БД для подписки."""
    try:
        # Создаём платёж в ЮKassa СНАЧАЛА
        receipt_items = [{
            "description": description,
            "quantity": "1", # <-- 1 подписка
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"}, # <-- Общая цена за 1 шт.
            "vat_code": "1", # <-- СТРОКА
            "payment_mode": "full_payment",
            "payment_subject": "service"
        }]

        metadata = {
            "days": str(days),
            "bot_username": settings.BOT_USERNAME
        }

        yoo_payment = await create_yookassa_payment(
            user=user,
            amount=amount, # <-- Общая сумма
            description=description,
            receipt_items=receipt_items,
            metadata=metadata
        )

        # ТЕПЕРЬ создаём запись в БД
        db_payment = await Payment.objects.acreate(
            user=user,
            yookassa_payment_id=yoo_payment.id,
            amount_rub=Decimal(amount),
            payment_type=payment_type,
            subscription_days_granted=days,
            status='pending'
        )

        # Отправляем ссылку на оплату
        confirmation_url = yoo_payment.confirmation.confirmation_url
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer( # <-- Отправляем сообщение с ссылкой
                f"💳 Перейдите по ссылке для оплаты подписки:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer( # <-- Отправляем сообщение с ссылкой
                f"💳 Перейдите по ссылке для оплаты подписки:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )

        # --- УБРАЛИ ОБНОВЛЕНИЕ СООБЩЕНИЯ ---
        # confirmation_message = ... # <-- УБРАЛИ
        # if confirmation_message: # <-- УБРАЛИ
        #     processing_message = await confirmation_message.edit_text( # <-- УБРАЛИ
        #         "⏳ Обработка платежа за подписку..."
        #     ) # <-- УБРАЛИ

        # Запускаем отслеживание статуса в фоне
        asyncio.create_task(track_payment_status(yoo_payment.id, db_payment.id, user.telegram_id))

    except Exception as e:
        logger.error(f"Ошибка при инициации платежа для подписки: {e}", exc_info=True)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(get_message('error_generic', language=language))
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(get_message('error_generic', language=language))

async def _initiate_token_payment(user, amount, token_count, description, payment_type, message_or_callback, language: str):
    """Создаёт платеж в ЮKassa и запись в БД для токенов."""
    try:
        # --- ОПРЕДЕЛЯЕМ ЦЕНУ ЗА ЕДИНИЦУ ---
        unit_price = amount / token_count

        # Создаём платёж в ЮKassa СНАЧАЛА
        receipt_items = [{
            "description": description,
            "quantity": str(token_count), # <-- Количество токенов
            "amount": {"value": f"{unit_price:.2f}", "currency": "RUB"}, # <-- Цена за 1 токен
            "vat_code": "1", # <-- СТРОКА
            "payment_mode": "full_payment",
            "payment_subject": "commodity" # или "service", если токены — услуга
        }]

        metadata = {
            "tokens": str(token_count),
            "bot_username": settings.BOT_USERNAME
        }

        yoo_payment = await create_yookassa_payment(
            user=user,
            amount=amount, # <-- Общая сумма
            description=description,
            receipt_items=receipt_items,
            metadata=metadata
        )

        # ТЕПЕРЬ создаём запись в БД
        db_payment = await Payment.objects.acreate(
            user=user,
            yookassa_payment_id=yoo_payment.id,
            amount_rub=Decimal(amount),
            payment_type=payment_type,
            tokens_granted=token_count,
            status='pending'
        )

        # Отправляем ссылку на оплату
        confirmation_url = yoo_payment.confirmation.confirmation_url
        # --- ИСПРАВЛЕНИЕ: Правильно отправляем сообщение ---
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer( # <-- Отправляем сообщение с ссылкой
                f"💳 Перейдите по ссылке для оплаты токенов:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer( # <-- Отправляем сообщение с ссылкой
                f"💳 Перейдите по ссылке для оплаты токенов:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )

        # --- УБРАЛИ ОБНОВЛЕНИЕ СООБЩЕНИЯ ---
        # confirmation_message = ... # <-- УБРАЛИ
        # if confirmation_message: # <-- УБРАЛИ
        #     processing_message = await confirmation_message.edit_text( # <-- УБРАЛИ
        #         "⏳ Обработка платежа за токены..."
        #     ) # <-- УБРАЛИ

        # Запускаем отслеживание статуса в фоне
        asyncio.create_task(track_payment_status(yoo_payment.id, db_payment.id, user.telegram_id))

    except Exception as e:
        logger.error(f"Ошибка при инициации платежа за токены: {e}", exc_info=True)
        # --- ИСПРАВЛЕНИЕ: Правильно отправляем сообщение об ошибке ---
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(get_message('error_generic', language=language))
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Отмена ввода email и возврат в меню."""
    await state_manager.clear_state(state)
    # Возвращаем в меню, откуда был вызов. Для простоты — в премиум.
    await show_premium(callback, user, language)
    await callback.answer("Оплата отменена")
