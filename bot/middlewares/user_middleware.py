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
        logger.info("Вызов UserMiddleware")
        
        # Обрабатываем только сообщения и callback query
        if isinstance(event, (Message, CallbackQuery)):
            logger.info(f"Обработка пользователя для события от {event.from_user.id}")
            user = await self._get_or_create_user(event)
            if user:
                data['user'] = user
                logger.info(f"Пользователь {user.username} ({user.telegram_id}) добавлен в данные")
            else:
                logger.warning("Пользователь не был создан/загружен")
        else:
            logger.info("Событие не является сообщением или callback, пропускаем обработку пользователя")
        
        logger.info("Вызов следующего middleware/handler")
        result = await handler(event, data)
        logger.info("Handler выполнен успешно")
        return result
        
        # Обрабатываем только сообщения и callback query
    async def _get_or_create_user(self, event: TelegramObject) -> User:
        """
        Получение или создание пользователя
        """
        try:
            logger.info("Начало процесса создания/загрузки пользователя")

            # Определяем telegram_id, username и т.д. (как и было)
            if isinstance(event, Message):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user # Сохраняем для определения часового пояса
                logger.info(f"Событие сообщения от пользователя: {username} ({telegram_id})")
            elif isinstance(event, CallbackQuery):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user # Сохраняем для определения часового пояса
                logger.info(f"Событие callback от пользователя: {username} ({telegram_id})")
            else:
                logger.warning("Неизвестный тип события для определения пользователя")
                return None

            logger.info(f"Поиск пользователя с telegram_id: {telegram_id}")

            # Пытаемся получить существующего пользователя
            try:
                user = await User.objects.aget(telegram_id=telegram_id)
                logger.info(f"Пользователь найден: {user.username}")

                # Обновляем информацию пользователя если она изменилась
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

                # === ИЗМЕНЕНО ===
                # При обновлении НЕ пытаемся автоматически определять часовой пояс.
                # Часовой пояс обновляется только через настройки пользователя.
                # Это упрощает логику и делает её более предсказуемой.
                # Таким образом, если пользователь установил 'Europe/Moscow' через настройки,
                # оно так и останется, даже если Telegram вдруг начнёт присылать utc_offset.
                # Если у пользователя 'UTC' (значение по умолчанию) и он не менял настройки,
                # это тоже приемлемо.
                # ===================

                if updated_fields:
                    await user.asave(update_fields=updated_fields)
                    logger.info(f"Информация пользователя обновлена: {updated_fields}")

                return user
            except User.DoesNotExist:
                logger.info("Пользователь не найден, создаем нового")

                # Определяем язык пользователя ТОЛЬКО ПРИ РЕГИСТРАЦИИ
                language = self._detect_language(event)
                logger.info(f"Определен язык при регистрации: {language}")

                # === ИЗМЕНЕНО ===
                # Определяем часовой пояс ПРИ РЕГИСТРАЦИИ
                # Сначала пытаемся автоматически определить
                detected_timezone = self._detect_timezone_from_user_data(user_data)
                # Если автоматическое определение не дало результата или вернуло 'UTC',
                # устанавливаем 'UTC' как значение по умолчанию.
                # Пользователь сможет изменить это в настройках.
                timezone_to_set = detected_timezone if detected_timezone and detected_timezone != 'UTC' else 'UTC'
                logger.info(f"Определен/установлен часовой пояс при регистрации: {timezone_to_set}")
                # ===================

                # Создаем нового пользователя
                user = await User.objects.acreate(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language=language,  # Язык устанавливается только при регистрации
                    # === ИЗМЕНЕНО ===
                    timezone=timezone_to_set   # Часовой пояс устанавливается при регистрации (по умолчанию UTC)
                    # ===================
                )
                logger.info(f"Новый пользователь создан: {user.username} ({user.telegram_id}) с языком {language} и часовым поясом {timezone_to_set} (по умолчанию)")
                return user

        except Exception as e:
            logger.error(f"Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None

        except Exception as e:
            logger.error(f"Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None
    
    def _detect_language(self, event: TelegramObject) -> str:
        """
        Определение языка пользователя (только при регистрации)
        """
        try:
            logger.info("Определение языка пользователя")
            
            if isinstance(event, Message):
                lang_code = event.from_user.language_code
            elif isinstance(event, CallbackQuery):
                lang_code = event.from_user.language_code
            else:
                logger.warning("Неизвестный тип события для определения языка")
                return 'ru'
            
            logger.info(f"Код языка из Telegram: {lang_code}")
            
            # Поддерживаемые языки
            supported_languages = ['ru', 'en']
            
            if lang_code and lang_code[:2] in supported_languages:
                detected_lang = lang_code[:2]
                logger.info(f"Поддерживаемый язык определен: {detected_lang}")
                return detected_lang
            else:
                logger.info("Неподдерживаемый или отсутствующий язык, используем по умолчанию: ru")
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
            logger.debug("Попытка автоматического определения часового пояса пользователя из данных Telegram.")

            # 1. Проверяем наличие timezone (строковый идентификатор)
            if hasattr(user_data, 'timezone') and user_data.timezone:
                logger.debug(f"Часовой пояс (timezone) из Telegram: {user_data.timezone}")
                import pytz
                try:
                    pytz.timezone(user_data.timezone) # Пробуем создать объект пояса для валидации
                    logger.info(f"Автоматически определён валидный часовой пояс: {user_data.timezone}")
                    return user_data.timezone
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Невалидный идентификатор часового пояса из Telegram: {user_data.timezone}. Используется UTC.")
                    return 'UTC'

            # 2. Если timezone нет, проверяем utc_offset (в секундах)
            elif hasattr(user_data, 'utc_offset') and user_data.utc_offset is not None:
                utc_offset = user_data.utc_offset
                logger.debug(f"UTC offset из Telegram: {utc_offset} секунд")

                # Преобразуем offset в строку часового пояса UTC+/-N
                total_hours = utc_offset // 3600
                if utc_offset % 3600 != 0:
                     logger.info("UTC offset не кратен часу, округляется.")
                if total_hours == 0:
                    logger.info("Автоматически определён часовой пояс: UTC")
                    return 'UTC'
                elif total_hours > 0:
                    tz_name = f'UTC+{total_hours}'
                    logger.info(f"Автоматически определён часовой пояс: {tz_name}")
                    return tz_name
                else:
                    # total_hours уже отрицательный
                    tz_name = f'UTC{total_hours}' # Например, UTC-5
                    logger.info(f"Автоматически определён часовой пояс: {tz_name}")
                    return tz_name
            else:
                logger.debug("Информация о часовом поясе недоступна в данных пользователя Telegram.")
                return 'UTC'

        except Exception as e:
            logger.error(f"Ошибка при попытке автоматического определения часового пояса: {e}")
            return 'UTC'
