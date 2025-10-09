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
            "return_url": f"https://t.me/{settings.BOT_USERNAME}"
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
    user = await User.objects.aget(telegram_id=user_id)

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

            db_payment = await Payment.objects.aget(id=payment_id)
            if yoo_payment.status == db_payment.status:
                continue

            db_payment.status = yoo_payment.status
            await db_payment.asave()

            if yoo_payment.status == "succeeded":
                await user.process_payment(db_payment)
                # --- ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ ---
                await send_message_to_user(
                    bot,
                    user,
                    "✅ Платёж успешно обработан!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
                    ])
                )
                return
            elif yoo_payment.status in ("canceled", "failed"):
                # --- ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ ---
                await send_message_to_user(bot, user, "❌ Платёж не прошёл.")
                return
        except Exception as e:
            logger.error(f"Ошибка при отслеживании платежа {yookassa_payment_id}: {e}", exc_info=True)

    # --- ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ по таймауту ---
    await send_message_to_user(
        bot,
        user,
        "⌛ Время ожидания оплаты истекло. Если вы оплатили, перезапустите бота: /start"
    )