"""
Middleware для регистрации пользователей
"""
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from users.models import User

logger = logging.getLogger(__name__)

class UserMiddleware(BaseMiddleware):
    """
    Middleware для автоматической регистрации пользователей
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            user = await self._get_or_create_user(event)
            if user:
                data['user'] = user
            else:
                logger.warning("Пользователь не был создан/загружен")
        result = await handler(event, data)
        return result
        
    async def _get_or_create_user(self, event: TelegramObject) -> User:
        """
        Получение или создание пользователя
        """
        try:
            if isinstance(event, Message):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user
                logger.info(f"[Событие] Сообщения от пользователя: {username} ({telegram_id})")
            elif isinstance(event, CallbackQuery):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user
                logger.info(f"[Событие] Callback от пользователя: {username} ({telegram_id})")
            else:
                logger.warning("Неизвестный тип события для определения пользователя")
                return None
            try:
                user = await User.objects.aget(telegram_id=telegram_id)
                updated_fields = []
                if user.username != username:
                    user.username = username
                    updated_fields.append('username')
                if user.first_name != first_name:
                    user.first_name = first_name
                    updated_fields.append('first_name')
                if user.last_name != last_name:
                    user.last_name = last_name
                    updated_fields.append('last_name')
                if updated_fields:
                    await user.asave(update_fields=updated_fields)
                return user
            except User.DoesNotExist:
                logger.info("Пользователь не найден, создаем нового")
                language = self._detect_language(event)
                logger.info(f"Определен язык при регистрации: {language}")
                detected_timezone = self._detect_timezone_from_user_data(user_data)
                timezone_to_set = detected_timezone if detected_timezone and detected_timezone != 'UTC' else 'UTC'
                logger.info(f"Определен/установлен часовой пояс при регистрации: {timezone_to_set}")
                user = await User.objects.acreate(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language=language,
                    timezone=timezone_to_set
                )
                logger.info(f"Новый пользователь создан: {user.username} ({user.telegram_id}) с языком {language} и часовым поясом {timezone_to_set} (по умолчанию)")
                return user
        except Exception as e:
            logger.error(f"Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None
    
    def _detect_language(self, event: TelegramObject) -> str:
        """
        Определение языка пользователя (только при регистрации)
        """
        try:
            if isinstance(event, Message):
                lang_code = event.from_user.language_code
            elif isinstance(event, CallbackQuery):
                lang_code = event.from_user.language_code
            else:
                logger.warning("Неизвестный тип события для определения языка")
                return 'ru'
            supported_languages = ['ru', 'en']
            if lang_code and lang_code[:2] in supported_languages:
                detected_lang = lang_code[:2]
                return detected_lang
            else:
                return 'ru'  # язык по умолчанию
        except Exception as e:
            logger.error(f"Ошибка при определении языка: {e}")
            return 'ru'

    def _detect_timezone_from_user_data(self, user_data) -> str:
        """
        Попытка определения часового пояса пользователя из данных Telegram.
        Возвращает 'UTC' если определить не удалось.
        """
        try:
            if hasattr(user_data, 'timezone') and user_data.timezone:
                logger.debug(f"Часовой пояс (timezone) из Telegram: {user_data.timezone}")
                import pytz
                try:
                    pytz.timezone(user_data.timezone) # Пробуем создать объект пояса для валидации
                    return user_data.timezone
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Невалидный идентификатор часового пояса из Telegram: {user_data.timezone}. Используется UTC.")
                    return 'UTC'
            elif hasattr(user_data, 'utc_offset') and user_data.utc_offset is not None:
                utc_offset = user_data.utc_offset
                logger.debug(f"UTC offset из Telegram: {utc_offset} секунд")
                total_hours = utc_offset // 3600
                if total_hours == 0:
                    return 'UTC'
                elif total_hours > 0:
                    tz_name = f'UTC+{total_hours}'
                    return tz_name
                else:
                    tz_name = f'UTC{total_hours}'
                    logger.info(f"Автоматически определён часовой пояс: {tz_name}")
                    return tz_name
            else:
                logger.debug("Информация о часовом поясе недоступна в данных пользователя Telegram.")
                return 'UTC'
        except Exception as e:
            logger.error(f"Ошибка при попытке автоматического определения часового пояса: {e}")
            return 'UTC'
