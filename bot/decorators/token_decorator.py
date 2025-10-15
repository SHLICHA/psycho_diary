# /home/shlicha/psycho_diary/bot/decorators/token_decorator.py
import logging
from functools import wraps
from typing import Callable, Any, Awaitable
from aiogram.types import Message, CallbackQuery
from aiogram import Router
from asgiref.sync import sync_to_async

from users.models import User, TokenTransaction
from messages import get_message
from bot.keyboards import get_purchase_options_keyboard

logger = logging.getLogger(__name__)

def requires_tokens(cost: int):
    """
    Декоратор для проверки и списания токенов у пользователя.

    Args:
        cost (int): Количество токенов, необходимое для выполнения функции.

    Пример использования: @requires_tokens(cost=5)
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = None
            event = None
            language = 'ru'
            bot = None
            for arg in args:
                if isinstance(arg, User):
                    user = arg
                    break
            if not user:
                for key, value in kwargs.items():
                    if isinstance(value, User):
                        user = value
                        break
            for arg in args:
                if isinstance(arg, (Message, CallbackQuery)):
                    event = arg
                    break
            if not event:
                for key, value in kwargs.items():
                    if isinstance(value, (Message, CallbackQuery)):
                        event = value
                        break
            if 'language' in kwargs:
                language = kwargs['language']
            if 'bot' in kwargs:
                bot = kwargs['bot']
            if not user:
                logger.error("Декоратор requires_tokens: объект User не найден в аргументах функции.")
                return await func(*args, **kwargs)
            if user.is_premium:
                logger.debug(f"Пользователь {user.telegram_id} является премиумом. Пропускаем списание токенов для функции {func.__name__}.")
                return await func(*args, **kwargs)
            current_balance = user.token_balance
            if current_balance < cost:
                logger.info(f"Недостаточно токенов у пользователя {user.telegram_id}. Баланс: {current_balance}, Стоимость: {cost}")
                if event:
                    try:
                        insufficient_msg = get_message('insufficient_tokens', language)
                        keyboard = get_purchase_options_keyboard(language) # <-- Создаём клавиатуру

                        if isinstance(event, CallbackQuery):
                            # Для CallbackQuery используем answer, но можно отправить новое сообщение
                            # Ответ на callback (маленькое уведомление)
                            await event.answer(insufficient_msg, show_alert=True)
                            # И отправляем новое сообщение с клавиатурой
                            await event.message.answer(insufficient_msg, reply_markup=keyboard)
                        elif isinstance(event, Message):
                            # Для Message отправляем ответ с клавиатурой
                            if bot: # <-- Проверяем, есть ли bot
                                # Используем bot, чтобы отправить сообщение с клавиатурой
                                await bot.send_message(chat_id=event.chat.id, text=insufficient_msg, reply_markup=keyboard)
                            else:
                                # Если bot нет, можно попробовать event.answer (но это может не работать для Message)
                                # В этом случае, лучше убедиться, что bot передаётся в хендлеры.
                                logger.error("Объект bot не найден, невозможно отправить сообщение с клавиатурой пользователю.")
                                await event.answer(insufficient_msg, show_alert=True) # Только уведомление
                    except Exception as e:
                        logger.error(f"Ошибка при отправке сообщения о недостатке токенов с клавиатурой: {e}")
                else:
                    logger.warning("Объект event не найден, невозможно отправить сообщение о недостатке токенов.")
                return
            try:
                transaction = await sync_to_async(TokenTransaction.create_and_update_balance)(
                    user=user,
                    amount=-cost,
                    transaction_type='feature_usage',
                    description=f"Использование платной функции: {func.__name__}"
                )
                logger.debug(f"Списано {cost} токенов у пользователя {user.telegram_id} через create_and_update_balance. Новый баланс (в БД): {user.token_balance}, ID транзакции: {transaction.id}")
            except Exception as e:
                logger.error(f"Критическая ошибка при списании токенов для пользователя {user.telegram_id}: {e}")
                if event:
                    try:
                        if bot:
                            await event.answer(get_message('error_processing', language), show_alert=True)
                        elif isinstance(event, CallbackQuery):
                            await event.answer(get_message('error_processing', language), show_alert=True)
                        else:
                            logger.error("Невозможно отправить сообщение об ошибке: bot не передан, event - Message.")
                    except Exception as send_error:
                        logger.error(f"Ошибка при отправке сообщения об ошибке списания: {send_error}")
                return
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"Функция {func.__name__} выполнена успешно для пользователя {user.telegram_id}.")
                return result
            except Exception as func_error:
                logger.error(f"Ошибка при выполнении функции {func.__name__} для пользователя {user.telegram_id}: {func_error}", exc_info=True)
                try:
                    user.token_balance += cost
                    await sync_to_async(user.save)(update_fields=['token_balance'])
                    logger.debug(f"Токены ({cost}) возвращены пользователю {user.telegram_id} из-за ошибки в функции {func.__name__}. Новый баланс: {user.token_balance}")
                    await TokenTransaction.objects.acreate(
                        user=user,
                        amount=cost,
                        transaction_type='refund_on_error',
                        description=f"Возврат токенов за ошибку в функции: {func.__name__}"
                    )
                    logger.debug(f"Создана транзакция возврата {cost} токенов для пользователя {user.telegram_id} после ошибки в {func.__name__}")
                except Exception as refund_error:
                    logger.error(f"Критическая ошибка при возврате токенов пользователю {user.telegram_id} после ошибки в {func.__name__}: {refund_error}")
                if event:
                    try:
                        if bot:
                            await event.answer(get_message('error_processing', language), show_alert=True)
                        elif isinstance(event, CallbackQuery):
                            await event.answer(get_message('error_processing', language), show_alert=True)
                        else:
                            logger.error("Невозможно отправить show_alert при ошибке выполнения функции: bot не передан, event - Message.")
                    except Exception as send_error:
                        logger.error(f"Ошибка при отправке сообщения об ошибке выполнения: {send_error}")
                return
        return wrapper
    return decorator