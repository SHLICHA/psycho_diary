import asyncio
import logging
import uuid

from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from django.conf import settings
from yookassa import Configuration, Payment as YooPayment

from users.models import Payment, User
from bot.utils.message_utils import send_message_to_user
from bot.utils.state_manager import state_manager # <-- ИМПОРТИРУЕМ state_manager
from messages import get_message, get_button_text

logger = logging.getLogger(__name__)

def check_yookassa_config():
    if not all([settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY]):
        raise ValueError("Не настроены ключи ЮKassa в settings.py")
    return True

async def create_yookassa_payment(
    user: User,
    amount: float,
    description: str,
    receipt_items: list,
    metadata: dict
):
    """Универсальное создание платежа в ЮKassa"""
    check_yookassa_config()
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

    payment_data = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{settings.BOT_USERNAME}" # <-- ИСПРАВЛЕНО: убран лишний пробел
        },
        "capture": True,
        "description": description,
        "receipt": {
            "customer": {"email": user.email or "user@example.com"},
            "items": receipt_items
        },
        "metadata": {
            "user_id": str(user.telegram_id),
            **metadata
        }
    }

    payment = await asyncio.to_thread(
        lambda: YooPayment.create(payment_data, str(uuid.uuid4()))
    )
    if not payment or not hasattr(payment, 'id'):
        raise ValueError("Не удалось создать платёж в ЮKassa")
    return payment

async def track_payment_status(yookassa_payment_id: str, payment_id: int, user_id: int):
    logger.info(f"Отслеживание платежа {yookassa_payment_id} для {user_id}")
    # user = await User.objects.aget(telegram_id=user_id) # <-- ЗАГРУЖАЕМ НАЧАЛЬНЫЙ ОБЪЕКТ, МОЖЕТ БЫТЬ НЕАКТУАЛЬНО ПОЗЖЕ

    # --- ПОЛУЧАЕМ bot через state_manager ---
    bot = state_manager._bot_instance
    if not bot:
        logger.error("Bot instance не установлен в state_manager, невозможно отправить сообщение.")
        return

    for attempt in range(1, 46):  # ~15 минут
        await asyncio.sleep(20)
        try:
            yoo_payment = await sync_to_async(YooPayment.find_one)(yookassa_payment_id)
            if not yoo_payment:
                continue

            # db_payment = await Payment.objects.aget(id=payment_id) # <-- МОЖЕТ БЫТЬ НЕАКТУАЛЬНО ПОЗЖЕ
            # if yoo_payment.status == db_payment.status:
            #     continue

            # Получаем обновлённый статус платежа из БД
            db_payment = await Payment.objects.aget(id=payment_id)
            if yoo_payment.status == db_payment.status:
                continue

            db_payment.status = yoo_payment.status
            await db_payment.asave()

            if yoo_payment.status == "succeeded":
                # Перед обработкой получаем свежий объект пользователя
                user_before_processing = await User.objects.aget(telegram_id=user_id)
                auto_analysis_was_enabled_before = user_before_processing.auto_analysis_enabled

                # Обрабатываем оплату
                await user_before_processing.process_payment(db_payment)

                # После обработки получаем обновлённый объект пользователя
                user_after_processing = await User.objects.aget(telegram_id=user_id)
                auto_analysis_is_now_enabled = user_after_processing.auto_analysis_enabled
                user_language = user_after_processing.language or 'ru'

                success_message = get_message('payment_successful', user_language) + "\n\n" # "✅ Платёж успешно обработан!"
                # Проверяем, был ли активирована подписка (а не просто токены) и включился ли автоанализ
                if db_payment.subscription_days_granted > 0 and auto_analysis_is_now_enabled and not auto_analysis_was_enabled_before:
                    success_message += get_message('auto_analysis_enabled_on_subscription', user_language) + "\n\n"
                success_message += get_message('thank_you_for_support', user_language) + '\n\n'"Спасибо за поддержку!"
                success_message += get_message('insufficient_tokens_in_chat_hint', user_language)
                await send_message_to_user(
                    bot,
                    user_after_processing, # Используем обновлённый объект
                    success_message,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_button_text('btn_back', user_language), callback_data="main_menu")]
                    ])
                )
                return
            elif yoo_payment.status in ("canceled", "failed"):
                # Получаем пользователя для отправки сообщения
                user_on_failure = await User.objects.aget(telegram_id=user_id)
                user_language = user_on_failure.language or 'ru'
                # --- ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ ---
                await send_message_to_user(bot, user_on_failure, get_message('payment_failed', user_language), language=user_language) # Предполагаем, что 'payment_failed' есть
                return
        except Exception as e:
            logger.error(f"Ошибка при отслеживании платежа {yookassa_payment_id}: {e}", exc_info=True)

    # --- ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ по таймауту ---
    # Получаем пользователя для отправки сообщения
    user_on_timeout = await User.objects.aget(telegram_id=user_id)
    user_language = user_on_timeout.language or 'ru'
    await send_message_to_user(
        bot,
        user_on_timeout,
        get_message('payment_timeout', user_language) # Предполагаем, что 'payment_timeout' есть, например, "Время ожидания оплаты истекло..."
    )