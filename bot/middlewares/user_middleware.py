# /home/shlicha/psycho_diary/bot/middlewares/user_middleware.py
"""
Middleware для регистрации пользователей и контроля доступа (онбординг)
"""
import logging
from typing import Any, Awaitable, Callable, Dict, Set
from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.enums import ContentType
# Импортируем FSMContext для потенциального использования в будущем, если понадобится
# from aiogram.fsm.context import FSMContext 

from messages import get_message
from bot.keyboards.onboarding_keyboards import get_start_onboarding_keyboard
from users.models import User
# Импортируем состояния онбординга (создадим их позже)
# from bot.states.onboarding_states import OnboardingStates

logger = logging.getLogger(__name__)

# Определим список команд и коллбэков, которые разрешены без согласия
# Это позволит пользователю взаимодействовать с онбордингом
ALLOWED_DURING_ONBOARDING_PREFIXES: Set[str] = {
    "start",
    "onboarding_",
}

class UserMiddleware(BaseMiddleware):
    """
    Middleware для автоматической регистрации пользователей и контроля доступа на основе согласия.
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_obj = None
        if isinstance(event, (Message, CallbackQuery)):
            user_obj = await self._get_or_create_user(event)
            if user_obj:
                data['user'] = user_obj
                
                # --- НОВАЯ ЛОГИКА КОНТРОЛЯ ДОСТУПА ---
                # Проверяем, дал ли пользователь согласие
                if not getattr(user_obj, 'has_agreed_to_terms', False):
                    # Если согласие не дано, проверяем, разрешено ли действие
                    is_allowed = await self._is_action_allowed_during_onboarding(event)
                    if not is_allowed:
                        # Если действие не разрешено, перенаправляем на онбординг или показываем сообщение
                        logger.info(f"Пользователь {user_obj.telegram_id} еще не дал согласие. Действие заблокировано.")
                        await self._handle_blocked_action(event, data)
                        return # Прерываем обработку
                        
                # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
            else:
                logger.warning("Пользователь не был создан/загружен")
                
        result = await handler(event, data)
        return result
        
    async def _get_or_create_user(self, event: TelegramObject) -> User:
        """Получение или создание пользователя (без изменений)"""
        # ... (существующий код метода _get_or_create_user без изменений) ...
        # Для краткости не повторяю, предполагается, что он остается как есть
        # ВАЖНО: Убедиться, что поле has_agreed_to_terms корректно загружается
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
                # ВАЖНО: Убедиться, что поле has_agreed_to_terms загружается
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
                    timezone=timezone_to_set,
                    # has_agreed_to_terms по умолчанию False
                )
                logger.info(f"Новый пользователь создан: {user.username} ({user.telegram_id}) с языком {language} и часовым поясом {timezone_to_set} (по умолчанию)")
                return user
        except Exception as e:
            logger.error(f"Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None
    
    def _detect_language(self, event: TelegramObject) -> str:
        """Определение языка пользователя (без изменений)"""
        # ... (существующий код метода _detect_language без изменений) ...
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
        """Попытка определения часового пояса пользователя из данных Telegram. (без изменений)"""
        # ... (существующий код метода _detect_timezone_from_user_data без изменений) ...
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

    async def _is_action_allowed_during_onboarding(self, event: TelegramObject) -> bool:
        """
        Проверяет, разрешено ли действие пользователю без согласия.
        """
        # 1. Проверка команды /start
        if isinstance(event, Message) and event.text and event.text.startswith('/'):
            command = event.text[1:].split()[0] # Получаем часть после '/'
            # if command in ALLOWED_DURING_ONBOARDING: # Старый способ
            if command == "start": # Разрешаем только /start
                logger.debug(f"Команда '{command}' разрешена без согласия.")
                return True
                
        # 2. Проверка callback_data (для кнопок)
        if isinstance(event, CallbackQuery):
            callback_data = event.data
            if callback_data:
                # Проверим, начинается ли callback_data с префиксов, связанных с онбордингом
                # if any(callback_data.startswith(prefix) for prefix in onboarding_prefixes): # Старый способ
                if any(callback_data.startswith(prefix) for prefix in ALLOWED_DURING_ONBOARDING_PREFIXES):
                    logger.debug(f"Callback '{callback_data}' разрешен без согласия.")
                    return True
                # Также разрешим /start через callback (если кнопка "Начать" ведет на это)
                # if callback_data == "start": # Уже покрыто префиксом
                #     return True
                    
        # 3. Если ничего не подошло, действие запрещено
        logger.debug("Действие не разрешено без согласия.")
        return False

    async def _handle_blocked_action(self, event: TelegramObject, data: Dict[str, Any]):
        """
        Обрабатывает ситуацию, когда действие пользователя заблокировано из-за отсутствия согласия.
        """
        from messages import get_message
        from bot.keyboards.onboarding_keyboards import get_start_onboarding_keyboard # Убедимся, что импортирован
        
        # Получаем объект пользователя и язык из data
        user = data.get('user')
        language = data.get('language', 'ru') # Предполагаем, что язык уже определен в data или получаем его из user
        if user and not language:
            language = user.language or 'ru'
        
        if not user:
            logger.error("Невозможно обработать заблокированное действие: пользователь не найден в data.")
            return

        blocked_message = get_message('onboarding_required', language) # Новое сообщение в messages.py
        
        try:
            if isinstance(event, Message):
                # Отправляем сообщение в чат
                bot = data.get('bot') 
                if bot:
                    keyboard = get_start_onboarding_keyboard(language) # Создадим эту клавиатуру позже
                    await bot.send_message(chat_id=event.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("Бот не найден в data для отправки сообщения о блокировке.")
                    
            elif isinstance(event, CallbackQuery):
                # Редактируем сообщение или отправляем новое
                from bot.utils.callback_utils import safe_answer_callback
                # from bot.utils.message_utils import safe_edit_message_text # Не всегда уместно редактировать
                
                # Сначала отвечаем на callback, чтобы он не "завис"
                await safe_answer_callback(event, get_message('access_denied', language), show_alert=True) # Новое сообщение
                
                # Затем отправляем новое сообщение с предложением начать онбординг
                bot = data.get('bot')
                if bot:
                    keyboard = get_start_onboarding_keyboard(language)
                    # Отправляем в тот же чат, откуда пришел callback
                    await bot.send_message(chat_id=event.message.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("Бот не найден в data для отправки сообщения о блокировке через callback.")
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке заблокированного действия для пользователя {user.telegram_id}: {e}")
