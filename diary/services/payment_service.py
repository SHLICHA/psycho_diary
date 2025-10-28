# /diary/services/payment_service.py
"""
Сервис для обработки платежей (подписка, токены).
Выносит бизнес-логику из хендлеров Telegram.
"""

import asyncio
import logging
import re
from decimal import Decimal
from typing import Dict, Any, Optional

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from users.models import Payment, User
from bot.utils.payment_utils import create_yookassa_payment, track_payment_status
from bot.utils.message_utils import send_message_to_user # <-- ИМПОРТИРУЕМ ДЛЯ track_payment_status

logger = logging.getLogger(__name__)

def is_valid_email(email: str) -> bool:
    """Проверяет валидность email."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

class PaymentService:
    """Сервис для работы с платежами."""

    @classmethod
    async def initiate_subscription_payment(cls, user: User, plan: str) -> Dict[str, Any]:
        """
        Инициирует процесс покупки подписки.
        Если у пользователя нет email, возвращает информацию для запроса email.
        В противном случае, создает платеж в ЮKassa и запись в БД.

        Args:
            user: Объект пользователя Django.
            plan: 'month' или 'year'.

        Returns:
            Dict[str, Any]: Результат инициации.
                - success (bool): Успешность операции (True, если платеж создан или нужен email).
                - requires_email (bool): Нужно ли запрашивать email.
                - pending_payment_data (Optional[Dict]): Данные для сохранения в FSM при запросе email.
                - confirmation_url (Optional[str]): Ссылка для оплаты (если платеж создан).
                - error (Optional[str]): Сообщение об ошибке.
        """
        try:
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
                return {
                    "success": False,
                    "requires_email": False,
                    "pending_payment_data": None,
                    "confirmation_url": None,
                    "error": "Неверный тип подписки"
                }

            if not user.email:
                pending_data = {
                    'amount': amount,
                    'days': days,
                    'description': description,
                    'payment_type': payment_type
                }
                return {
                    "success": True,
                    "requires_email": True,
                    "pending_payment_data": pending_data,
                    "confirmation_url": None,
                    "error": None
                }

            # Email есть, создаем платеж
            result = await cls._create_db_and_yookassa_payment(
                user=user,
                amount=amount,
                description=description,
                payment_type=payment_type,
                subscription_days_granted=days,
                tokens_granted=0 # Для подписки
            )
            return result

        except Exception as e:
            logger.error(f"[PaymentService] Ошибка при инициации платежа за подписку для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "requires_email": False,
                "pending_payment_data": None,
                "confirmation_url": None,
                "error": str(e)
            }

    @classmethod
    async def initiate_token_payment(cls, user: User, token_count: int) -> Dict[str, Any]:
        """
        Инициирует процесс покупки токенов.
        Если у пользователя нет email, возвращает информацию для запроса email.
        В противном случае, создает платеж в ЮKassa и запись в БД.

        Args:
            user: Объект пользователя Django.
            token_count: Количество токенов.

        Returns:
            Dict[str, Any]: Результат инициации.
                - success (bool): Успешность операции (True, если платеж создан или нужен email).
                - requires_email (bool): Нужно ли запрашивать email.
                - pending_payment_data (Optional[Dict]): Данные для сохранения в FSM при запросе email.
                - confirmation_url (Optional[str]): Ссылка для оплаты (если платеж создан).
                - error (Optional[str]): Сообщение об ошибке.
        """
        try:
            price_map = {
                10: settings.TOKEN_PACK_10,
                50: settings.TOKEN_PACK_50,
                100: settings.TOKEN_PACK_100,
                200: settings.TOKEN_PACK_200,
                500: settings.TOKEN_PACK_500,
            }
            if token_count not in price_map:
                return {
                    "success": False,
                    "requires_email": False,
                    "pending_payment_data": None,
                    "confirmation_url": None,
                    "error": "Неверный выбор пакета"
                }

            amount = price_map[token_count]
            description = f"Покупка {token_count} токенов"
            payment_type = f"tokens_{token_count}"

            if not user.email:
                pending_data = {
                    'amount': amount,
                    'token_count': token_count,
                    'description': description,
                    'payment_type': payment_type
                }
                return {
                    "success": True,
                    "requires_email": True,
                    "pending_payment_data": pending_data,
                    "confirmation_url": None,
                    "error": None
                }

            # Email есть, создаем платеж
            result = await cls._create_db_and_yookassa_payment(
                user=user,
                amount=amount,
                description=description,
                payment_type=payment_type,
                subscription_days_granted=0, # Для токенов
                tokens_granted=token_count
            )
            return result

        except Exception as e:
            logger.error(f"[PaymentService] Ошибка при инициации платежа за токены для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "requires_email": False,
                "pending_payment_data": None,
                "confirmation_url": None,
                "error": str(e)
            }

    @classmethod
    async def process_user_email_for_pending_payment(
        cls, user: User, email: str, pending_payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Обрабатывает email, предоставленный пользователем для сохранения в чеке.
        Затем создает платеж в ЮKassa и запись в БД.

        Args:
            user: Объект пользователя Django.
            email: Email, введенный пользователем.
            pending_payment_data: Данные, сохраненные в FSM.

        Returns:
            Dict[str, Any]: Результат обработки email и создания платежа.
                - success (bool): Успешность операции.
                - confirmation_url (Optional[str]): Ссылка для оплаты (если платеж создан).
                - error (Optional[str]): Сообщение об ошибке.
        """
        try:
            if not is_valid_email(email):
                 return {
                    "success": False,
                    "confirmation_url": None,
                    "error": "Неверный формат email"
                }

            # Сохраняем email
            user.email = email
            await sync_to_async(user.save)(update_fields=['email'])
            logger.debug(f"[PaymentService] Email {email} сохранен для пользователя {user.telegram_id}")

            # Создаем платеж
            result = await cls._create_db_and_yookassa_payment(
                user=user,
                amount=pending_payment_data['amount'],
                description=pending_payment_data['description'],
                payment_type=pending_payment_data['payment_type'],
                subscription_days_granted=pending_payment_data.get('days', 0),
                tokens_granted=pending_payment_data.get('token_count', 0)
            )
            return result

        except Exception as e:
            logger.error(f"[PaymentService] Ошибка при обработке email и создании платежа для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "confirmation_url": None,
                "error": str(e)
            }

    @classmethod
    async def _create_db_and_yookassa_payment(
        cls,
        user: User,
        amount: float,
        description: str,
        payment_type: str,
        subscription_days_granted: int,
        tokens_granted: int
    ) -> Dict[str, Any]:
        """
        Внутренний метод для создания платежа в ЮKassa и записи в БД.
        Запускает отслеживание статуса платежа.

        Args:
            user: Объект пользователя Django.
            amount: Сумма платежа.
            description: Описание платежа.
            payment_type: Тип платежа (из моделей).
            subscription_days_granted: Количество дней подписки.
            tokens_granted: Количество токенов.

        Returns:
            Dict[str, Any]: Результат создания платежа.
                - success (bool): Успешность операции.
                - confirmation_url (str): Ссылка для оплаты.
                - error (Optional[str]): Сообщение об ошибке.
        """
        try:
            # Определяем receipt_items и metadata в зависимости от типа платежа
            if subscription_days_granted > 0: # Подписка
                receipt_items = [{
                    "description": description,
                    "quantity": "1",
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "vat_code": "1",
                    "payment_mode": "full_payment",
                    "payment_subject": "service"
                }]
                metadata = {
                    "days": str(subscription_days_granted),
                    "bot_username": settings.BOT_USERNAME
                }
            else: # Токены
                token_count = tokens_granted
                unit_price = amount / token_count
                receipt_items = [{
                    "description": description,
                    "quantity": str(token_count),
                    "amount": {"value": f"{unit_price:.2f}", "currency": "RUB"},
                    "vat_code": "1",
                    "payment_mode": "full_payment",
                    "payment_subject": "commodity" # или "service"
                }]
                metadata = {
                    "tokens": str(token_count),
                    "bot_username": settings.BOT_USERNAME
                }

            # 1. Создаём платёж в ЮKassa
            yoo_payment = await create_yookassa_payment(
                user=user,
                amount=amount,
                description=description,
                receipt_items=receipt_items,
                metadata=metadata
            )

            # 2. Создаём запись в БД
            db_payment = await Payment.objects.acreate(
                user=user,
                yookassa_payment_id=yoo_payment.id,
                amount_rub=Decimal(amount),
                payment_type=payment_type,
                subscription_days_granted=subscription_days_granted,
                tokens_granted=tokens_granted,
                status='pending'
            )

            # 3. Запускаем отслеживание статуса в фоне
            # NOTE: track_payment_status использует send_message_to_user, что делает его Telegram-зависимым.
            # В идеале, логика отслеживания и уведомления должна быть отделена.
            # Пока что мы оставляем вызов здесь, понимая, что track_payment_status остается в bot.utils.
            asyncio.create_task(track_payment_status(yoo_payment.id, db_payment.id, user.telegram_id))

            logger.info(f"[PaymentService] Платёж {yoo_payment.id} создан для пользователя {user.telegram_id}, тип: {payment_type}")

            return {
                "success": True,
                "confirmation_url": yoo_payment.confirmation.confirmation_url,
                "error": None
            }

        except Exception as e:
            logger.error(f"[PaymentService] Ошибка при создании платежа в ЮKassa/БД для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "confirmation_url": None,
                "error": str(e)
            }

# Удобные функции для импорта в хендлеры
async def initiate_subscription_payment(user: User, plan: str) -> Dict[str, Any]:
    """Удобная функция для инициации покупки подписки."""
    return await PaymentService.initiate_subscription_payment(user, plan)

async def initiate_token_payment(user: User, token_count: int) -> Dict[str, Any]:
    """Удобная функция для инициации покупки токенов."""
    return await PaymentService.initiate_token_payment(user, token_count)

async def process_user_email_for_pending_payment(
    user: User, email: str, pending_payment_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Удобная функция для обработки email и создания платежа."""
    return await PaymentService.process_user_email_for_pending_payment(user, email, pending_payment_data)
