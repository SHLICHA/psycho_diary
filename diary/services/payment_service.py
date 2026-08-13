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
from users.services.identity_policy_service import IdentityPolicyService
from users.services.email_merge_service import EmailMergeService
from bot.utils.payment_utils import create_yookassa_payment, track_payment_status
from bot.utils.message_utils import send_message_to_user # <-- ИМПОРТИРУЕМ ДЛЯ track_payment_status
from messages import get_message

logger = logging.getLogger(__name__)

def is_valid_email(email: str) -> bool:
    """Проверяет валидность email."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def is_payment_cancel_command(text: str) -> bool:
    """Проверяет, является ли текст командой отмены ввода email для оплаты."""
    return text.lower() in ['назад', 'back', '/start', '/menu', 'отмена', 'cancel']

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
        cls,
        user: User,
        email: str,
        pending_payment_data: Dict[str, Any],
        *,
        source_platform: str = 'telegram',
    ) -> Dict[str, Any]:
        """
        Обрабатывает email, предоставленный пользователем для сохранения в чеке.
        Затем создает платеж в ЮKassa и запись в БД.

        Args:
            user: Объект пользователя Django.
            email: Email, введенный пользователем.
            pending_payment_data: Данные, сохраненные в FSM.
            source_platform: Канал инициатора ('telegram' | 'max' | 'web').

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

            # Единый identity policy для конфликтов email (общий для Telegram/MAX/Web).
            resolution = await IdentityPolicyService.aresolve_email_claim(email, requester_user=user)
            if resolution.status == 'conflict':
                if getattr(settings, 'EMAIL_MERGE_CONFIRMATION_ENABLED', False):
                    from users.services.email_merge_service import EmailMergeError

                    try:
                        merge_request = await EmailMergeService.acreate_merge_request(
                            requester_user=user,
                            email=email,
                            source_platform=source_platform or 'telegram',
                            source_context='payment_receipt_email',
                        )
                    except EmailMergeError as merge_error:
                        return {
                            "success": False,
                            "confirmation_url": None,
                            "error": merge_error.message,
                            "error_code": merge_error.code,
                        }
                    return {
                        "success": False,
                        "confirmation_url": None,
                        "error": "Требуется подтверждение конфликта email",
                        "error_code": "email_confirmation_required",
                        "confirmation_required": True,
                        "merge_request_id": merge_request.id,
                        "confirmation_token": merge_request.confirmation_token,
                        "target_user_id": merge_request.target_user_id,
                    }
                return {
                    "success": False,
                    "confirmation_url": None,
                    "error": "Email уже привязан к другому аккаунту",
                    "error_code": "email_already_exists",
                }

            # Сохраняем email
            user.email = email
            # email_hash должен обновляться атомарно с email, чтобы повторный claim
            # корректно определял conflict и запускал merge flow.
            await sync_to_async(user.save)(update_fields=['email', 'email_hash'])
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
                    "vat_code": "4",
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
                    "vat_code": "4",
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
            asyncio.create_task(track_payment_status(yoo_payment.id, db_payment.id, user.id))

            logger.info(f"[PaymentService] Платёж {yoo_payment.id} создан для пользователя {user.telegram_id}, тип: {payment_type}")

            return {
                "success": True,
                "requires_email": False,
                "confirmation_url": yoo_payment.confirmation.confirmation_url,
                "payment_id": db_payment.id,
                "yookassa_payment_id": yoo_payment.id,
                "error": None
            }

        except Exception as e:
            logger.error(f"[PaymentService] Ошибка при создании платежа в ЮKassa/БД для {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "requires_email": False,
                "confirmation_url": None,
                "payment_id": None,
                "yookassa_payment_id": None,
                "error": str(e)
            }

    @classmethod
    def list_products(cls) -> Dict[str, Any]:
        """Каталог продуктов и цен из settings (единый источник для bot keyboards и API)."""
        return {
            "success": True,
            "currency": "RUB",
            "subscriptions": [
                {
                    "sku": "subscription_month",
                    "plan": "month",
                    "days": 30,
                    "price": int(settings.PREMIUM_PRICE_MONTH),
                },
                {
                    "sku": "subscription_year",
                    "plan": "year",
                    "days": 365,
                    "price": int(settings.PREMIUM_PRICE_YEAR),
                },
            ],
            "token_packs": [
                {"sku": "tokens_10", "tokens": 10, "price": int(settings.TOKEN_PACK_10)},
                {"sku": "tokens_50", "tokens": 50, "price": int(settings.TOKEN_PACK_50)},
                {"sku": "tokens_100", "tokens": 100, "price": int(settings.TOKEN_PACK_100)},
                {"sku": "tokens_200", "tokens": 200, "price": int(settings.TOKEN_PACK_200)},
                {"sku": "tokens_500", "tokens": 500, "price": int(settings.TOKEN_PACK_500)},
            ],
        }

    @classmethod
    async def get_user_payment(cls, user: User, payment_id: int) -> Dict[str, Any]:
        """Возвращает платёж пользователя по внутреннему id."""
        try:
            payment = await Payment.objects.aget(id=payment_id, user=user)
            return {"success": True, "payment": payment, "error": None}
        except Payment.DoesNotExist:
            return {"success": False, "payment": None, "error": "payment_not_found"}

    @classmethod
    async def sync_payment_status(cls, user: User, payment_id: int) -> Dict[str, Any]:
        """
        Однократная синхронизация статуса с ЮKassa (для web-клиента).
        Идемпотентно начисляет premium/токены при succeeded.
        """
        lookup = await cls.get_user_payment(user, payment_id)
        if not lookup["success"]:
            return lookup
        payment = lookup["payment"]
        return await cls.confirm_payment_by_yookassa_id(payment.yookassa_payment_id)

    @classmethod
    async def confirm_payment_by_yookassa_id(
        cls,
        yookassa_payment_id: str,
        *,
        provider_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Идемпотентное подтверждение платежа по ID ЮKassa.
        Без Telegram-уведомлений (для webhook / API sync).
        """
        from bot.utils.payment_utils import check_yookassa_config
        from yookassa import Configuration, Payment as YooPayment

        try:
            check_yookassa_config()
            Configuration.account_id = settings.YOOKASSA_SHOP_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

            if provider_status is None:
                yoo_payment = await sync_to_async(YooPayment.find_one)(yookassa_payment_id)
                if not yoo_payment:
                    return {
                        "success": False,
                        "payment": None,
                        "error": "yookassa_payment_not_found",
                        "status": None,
                    }
                provider_status = yoo_payment.status

            try:
                db_payment = await Payment.objects.select_related("user").aget(
                    yookassa_payment_id=yookassa_payment_id
                )
            except Payment.DoesNotExist:
                return {
                    "success": False,
                    "payment": None,
                    "error": "payment_not_found",
                    "status": provider_status,
                }

            previous_status = db_payment.status
            if provider_status and provider_status != db_payment.status:
                db_payment.status = provider_status
                await db_payment.asave(update_fields=["status", "updated_at"])

            granted = False
            if provider_status == "succeeded" and previous_status != "succeeded":
                user = db_payment.user
                await user.process_payment(db_payment)
                granted = True
                logger.info(
                    "[PaymentService] Платёж %s подтверждён (granted=%s) для user_id=%s",
                    yookassa_payment_id,
                    granted,
                    user.id,
                )
            elif provider_status == "succeeded" and previous_status == "succeeded":
                logger.debug(
                    "[PaymentService] Платёж %s уже был succeeded — skip grant",
                    yookassa_payment_id,
                )

            await db_payment.arefresh_from_db()
            return {
                "success": True,
                "payment": db_payment,
                "status": db_payment.status,
                "granted": granted,
                "error": None,
            }
        except Exception as e:
            logger.error(
                "[PaymentService] Ошибка confirm_payment_by_yookassa_id(%s): %s",
                yookassa_payment_id,
                e,
                exc_info=True,
            )
            return {
                "success": False,
                "payment": None,
                "error": str(e),
                "status": provider_status,
            }

    @classmethod
    def build_premium_menu_view(cls, user: User, language: str) -> Dict[str, Any]:
        """Собирает text/keyboard для экрана премиум/покупки."""
        from bot.keyboards import get_manage_premium_keyboard, get_purchase_options_keyboard

        if user.is_premium_active():
            premium_msg = get_message('settings_premium', language=language).format(
                status=get_message('status_enabled', language=language)
            )
            expires_at = (
                user.premium_expires_at.strftime('%d.%m.%Y %H:%M')
                if user.premium_expires_at
                else 'Неизвестно'
            )
            premium_msg += f"\n\nДата окончания подписки: {expires_at}"
            return {
                'success': True,
                'mode': 'active',
                'text': premium_msg,
                'reply_markup': get_manage_premium_keyboard(language),
            }

        return {
            'success': True,
            'mode': 'purchase',
            'text': get_message('premium_benefits', language=language),
            'reply_markup': get_purchase_options_keyboard(language),
        }

    @classmethod
    def build_payment_link_message(
        cls,
        confirmation_url: str,
        payment_kind: str = 'subscription',
    ) -> str:
        """Текст со ссылкой на оплату (subscription/tokens)."""
        if payment_kind == 'tokens':
            return (
                f"💳 Перейдите по ссылке для оплаты токенов:\n{confirmation_url}\n\n"
                f"После оплаты вернитесь к боту."
            )
        return (
            f"💳 Перейдите по ссылке для оплаты подписки:\n{confirmation_url}\n\n"
            f"После оплаты вернитесь к боту."
        )

    @classmethod
    def build_payment_initiation_view(
        cls,
        result: Dict[str, Any],
        language: str,
        payment_kind: str = 'subscription',
    ) -> Dict[str, Any]:
        """
        Нормализует результат initiate_* в transport-friendly payload.
        modes: requires_email | payment_link | error
        """
        if not result.get('success'):
            return {
                'success': False,
                'mode': 'error',
                'error': result.get('error') or 'payment_init_failed',
                'text': get_message('error_generic', language),
            }

        if result.get('requires_email'):
            return {
                'success': True,
                'mode': 'requires_email',
                'pending_payment_data': result.get('pending_payment_data'),
                'text': get_message('ask_email_for_receipt', language),
            }

        confirmation_url = result.get('confirmation_url')
        if not confirmation_url:
            return {
                'success': False,
                'mode': 'error',
                'error': 'confirmation_url_missing',
                'text': get_message('error_generic', language),
            }

        return {
            'success': True,
            'mode': 'payment_link',
            'confirmation_url': confirmation_url,
            'text': cls.build_payment_link_message(confirmation_url, payment_kind=payment_kind),
        }

    @classmethod
    def build_token_purchase_options_view(cls, language: str) -> Dict[str, Any]:
        """Текст и клавиатура экрана выбора пакета токенов."""
        from bot.keyboards import get_token_purchase_options_keyboard

        return {
            'success': True,
            'text': "💎 <b>Выберите пакет токенов:</b>",
            'reply_markup': get_token_purchase_options_keyboard(language),
        }

    @classmethod
    def build_email_payment_result_view(
        cls,
        result: Dict[str, Any],
        payment_kind: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Нормализует результат process_user_email_for_pending_payment для transport-слоя.
        modes: payment_ready | merge_confirmation | email_exists | error
        """
        if result.get('success'):
            confirmation_url = result.get('confirmation_url')
            if confirmation_url:
                return {
                    'success': True,
                    'mode': 'payment_ready',
                    'clear_state': True,
                    'messages': [
                        cls.build_payment_link_message(confirmation_url, payment_kind=payment_kind),
                        get_message('payment_email_saved', language),
                    ],
                }
            return {
                'success': False,
                'mode': 'error',
                'clear_state': True,
                'text': get_message('error_generic', language),
            }

        error_code = result.get('error_code')
        if error_code == 'email_confirmation_required':
            return {
                'success': False,
                'mode': 'merge_confirmation',
                'clear_state': False,
                'text': get_message('merge_requester_confirmation_prompt', language),
                'merge_request_id': result.get('merge_request_id'),
            }
        if error_code == 'email_already_exists':
            return {
                'success': False,
                'mode': 'email_exists',
                'clear_state': False,
                'text': get_message('email_already_exists', language),
            }
        if error_code == 'target_messenger_unavailable':
            return {
                'success': False,
                'mode': 'target_messenger_unavailable',
                'clear_state': False,
                'text': get_message('merge_target_messenger_unavailable', language),
            }

        return {
            'success': False,
            'mode': 'error',
            'clear_state': False,
            'text': result.get('error', 'Неизвестная ошибка'),
        }


# Удобные функции для импорта в хендлеры
async def initiate_subscription_payment(user: User, plan: str) -> Dict[str, Any]:
    """Удобная функция для инициации покупки подписки."""
    return await PaymentService.initiate_subscription_payment(user, plan)

async def initiate_token_payment(user: User, token_count: int) -> Dict[str, Any]:
    """Удобная функция для инициации покупки токенов."""
    return await PaymentService.initiate_token_payment(user, token_count)

async def process_user_email_for_pending_payment(
    user: User,
    email: str,
    pending_payment_data: Dict[str, Any],
    *,
    source_platform: str = 'telegram',
) -> Dict[str, Any]:
    """Удобная функция для обработки email и создания платежа."""
    return await PaymentService.process_user_email_for_pending_payment(
        user,
        email,
        pending_payment_data,
        source_platform=source_platform,
    )

def build_premium_menu_view(user: User, language: str) -> Dict[str, Any]:
    return PaymentService.build_premium_menu_view(user, language)

def build_payment_initiation_view(
    result: Dict[str, Any],
    language: str,
    payment_kind: str = 'subscription',
) -> Dict[str, Any]:
    return PaymentService.build_payment_initiation_view(result, language, payment_kind=payment_kind)

def build_payment_link_message(confirmation_url: str, payment_kind: str = 'subscription') -> str:
    return PaymentService.build_payment_link_message(confirmation_url, payment_kind=payment_kind)

def build_token_purchase_options_view(language: str) -> Dict[str, Any]:
    return PaymentService.build_token_purchase_options_view(language)

def build_email_payment_result_view(
    result: Dict[str, Any],
    payment_kind: str,
    language: str,
) -> Dict[str, Any]:
    return PaymentService.build_email_payment_result_view(result, payment_kind, language)


def list_products() -> Dict[str, Any]:
    return PaymentService.list_products()


async def get_user_payment(user: User, payment_id: int) -> Dict[str, Any]:
    return await PaymentService.get_user_payment(user, payment_id)


async def sync_payment_status(user: User, payment_id: int) -> Dict[str, Any]:
    return await PaymentService.sync_payment_status(user, payment_id)


async def confirm_payment_by_yookassa_id(
    yookassa_payment_id: str,
    *,
    provider_status: Optional[str] = None,
) -> Dict[str, Any]:
    return await PaymentService.confirm_payment_by_yookassa_id(
        yookassa_payment_id,
        provider_status=provider_status,
    )
