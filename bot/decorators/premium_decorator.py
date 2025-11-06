import logging
from functools import wraps
from typing import Callable, Any, Awaitable, Union

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from messages.messages_utils import get_message
from users.models import User

logger = logging.getLogger(__name__)

def requires_premium(alert_message_key: str = 'premium_required'):
    """
    Декоратор для хендлеров, требующих премиум-подписку.
    Ищет объект User в аргументах (args, kwargs) и в словаре data (например, через UserMiddleware).

    Args:
        alert_message_key (str): Ключ сообщения из messages для show_alert или сообщения.
                                 По умолчанию 'premium_required'.
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Пытаемся извлечь объекты Message/CallbackQuery и User
            message: Union[Message, CallbackQuery, None] = None
            user: Union[User, None] = None
            language: str = 'ru' # Язык по умолчанию

            # --- 1. Поиск User в args ---
            for arg in args:
                if isinstance(arg, User):
                    user = arg
                    break
            # --- /Поиск User в args ---

            # --- 2. Поиск User в kwargs ---
            if user is None:
                user = kwargs.get('user') # Если 'user' передан как именованный аргумент
            # --- /Поиск User в kwargs ---

            # --- 3. Поиск User в словаре data (в args или kwargs) ---
            # Словарь data, вероятно, находится в args или kwargs, передаваемых aiogram
            # Обычно это {'event': <Message|CallbackQuery>, 'data': {...}, 'bot': <Bot>}
            # Но мы ищем в args, как это делает aiogram внутри
            # aiogram передаёт event и data как *args, например, handler(message, data, ...)
            # или handler(callback, data, ...)
            # Но в нашем случае, если middleware внедрили 'user' в data, и другой middleware
            # передал его как аргумент, то он будет в args/kwargs.
            # Если же 'user' остался в data, его нужно искать там.
            # Ищем словарь data в args
            data = None
            for arg in args:
                if isinstance(arg, dict) and 'user' in arg and isinstance(arg['user'], User):
                    data = arg
                    break
            # Если не нашли в args, проверим kwargs
            if data is None:
                # Обычно data передаётся как часть внутреннего вызова aiogram, но на уровне хендлера
                # мы его не получаем напрямую, если только middleware не делает это явно.
                # В данном случае, если 'user' не был внедрён как аргумент, но был в data,
                # и middleware, который внедряет 'user' в аргументы, не сработал,
                # то 'user' может быть в data, который передаётся как аргумент в *args.
                # Это маловероятно, но на всякий случай.
                # Более вероятно, что data - это словарь, передаваемый aiogram внутрь, и он может быть
                # недоступен напрямую в *args или **kwargs хендлера, если middleware его уже обработал.
                # Однако, если 'user' был в data, но не внедрён как аргумент, ищем его так:
                # Словарь data обычно передаётся как последний аргумент, но это не точно.
                # Проверим kwargs на наличие 'data', содержащего 'user'
                if 'data' in kwargs and isinstance(kwargs['data'], dict) and 'user' in kwargs['data'] and isinstance(kwargs['data']['user'], User):
                    data = kwargs['data']

            # Если user не найден в аргументах, пробуем получить его из найденного data
            if user is None and data is not None:
                user = data.get('user')
            # --- /Поиск User в словаре data ---

            if user is None:
                logger.error(f"requires_premium: Не найден объект User в аргументах или data для функции {func.__name__}")
                # Если пользователь не найден, вызываем оригинальную функцию
                return await func(*args, **kwargs)

            # --- 4. Поиск Message или CallbackQuery в args ---
            # aiogram передаёт event (Message или CallbackQuery) как первый аргумент
            event = None
            for arg in args:
                if isinstance(arg, (Message, CallbackQuery)):
                    event = arg
                    message = arg # Сохраняем для отправки сообщения
                    break
            # --- /Поиск Message или CallbackQuery в args ---

            if event is None:
                logger.error(f"requires_premium: Не найдено событие (Message или CallbackQuery) в аргументах для функции {func.__name__}")
                return await func(*args, **kwargs)

            # --- 5. Получение языка из объекта User ---
            try:
                language = getattr(user, 'language', 'ru') or 'ru'
            except AttributeError:
                logger.warning(f"requires_premium: У объекта User нет атрибута 'language', используем 'ru'.")
                language = 'ru'
            # --- /Получение языка ---

            # --- 6. Проверка статуса подписки ---
            try:
                is_premium = await user.ais_premium_active()
                # logger.debug(f"requires_premium: Проверка подписки для user {user.telegram_id}: is_premium = {is_premium}")
            except Exception as e:
                logger.error(f"requires_premium: Ошибка при проверке статуса подписки для user {user.telegram_id}: {e}")
                # В случае ошибки при проверке, вызываем оригинальную функцию
                return await func(*args, **kwargs)
            # --- /Проверка статуса подписки ---

            if not is_premium:
                # Подписка не активна, отправляем alert или сообщение и завершаем выполнение
                alert_text = get_message(alert_message_key, language)
                try:
                    if isinstance(event, CallbackQuery):
                        # Для CallbackQuery используем метод answer
                        await event.answer(text=alert_text, show_alert=True)
                    else:
                        # Для Message: show_alert не применимо напрямую.
                        # Отправим обычное сообщение.
                        await event.answer(alert_text)
                        # Важно: для Message не вызываем func, так как это бессмысленно без show_alert.
                        # Для CallbackQuery мы уже ответили, и вызов func может быть не нужен,
                        # но в некоторых сценариях (например, если логика в func не зависит от результата проверки)
                        # можно вызвать. Однако, обычно, если проверка не прошла, логику не выполняют.
                        # Лучше вернуть None или специальное значение.
                        return # Не вызываем оригинальную функцию
                except TelegramBadRequest as e:
                    if "query is too old" in str(e).lower() or "bot was blocked by the user" in str(e).lower():
                        logger.debug(f"requires_premium: Не удалось отправить show_alert (CallbackQuery просрочен или бот заблокирован): {e}")
                    else:
                        logger.error(f"requires_premium: Ошибка TelegramBadRequest при отправке show_alert: {e}")
                except Exception as e:
                    logger.error(f"requires_premium: Неожиданная ошибка при отправке show_alert или сообщения: {e}")
                # Не вызываем оригинальную функцию
                return

            # Подписка активна, вызываем оригинальную функцию
            return await func(*args, **kwargs)

        return wrapper
    return decorator