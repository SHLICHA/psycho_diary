"""
Middleware для регистрации пользователей и контроля доступа (онбординг)
"""
import logging
import re

from typing import Any, Awaitable, Callable, Dict, Set
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from messages import get_message
from bot.keyboards.onboarding_keyboards import get_start_onboarding_keyboard
from bot.utils.callback_utils import safe_answer_callback
from users.models import User, TokenTransaction

logger = logging.getLogger(__name__)

ALLOWED_DURING_ONBOARDING_PREFIXES: Set[str] = {
    "start",
    "onboarding_",
}

REFERRAL_PATTERN = re.compile(r'^start\s+ref_(\d+)_([a-zA-Z0-9_-]+)$')
    
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
        was_reactivated = False
        referrer_user = None

        if isinstance(event, (Message, CallbackQuery)):
            if isinstance(event, Message):
                telegram_id = event.from_user.id
            elif isinstance(event, CallbackQuery):
                telegram_id = event.from_user.id
            else:
                telegram_id = None

            was_blocked_before = False
            if telegram_id:
                try:
                    # --- ИСПРАВЛЕНО: select_related для invited_by ---
                    existing_user = await User.objects.select_related('invited_by').aget(telegram_id=telegram_id)
                    was_blocked_before = existing_user.is_blocked
                    logger.debug(f"[Middleware] Пользователь {telegram_id} был заблокирован до: {was_blocked_before}")
                except User.DoesNotExist:
                    was_blocked_before = False

            referrer_telegram_id = None
            if isinstance(event, Message) and event.text and event.text.startswith('/start'):
                logger.debug(f"[Middleware] Получена команда /start: '{event.text}'")
                match = REFERRAL_PATTERN.match(event.text[1:])
                if match:
                    logger.debug(f"[Middleware] Успешное совпадение паттерна для: '{event.text[1:]}'")
                    referrer_telegram_id = int(match.group(1))
                else:
                    logger.debug(f"[Middleware] Паттерн НЕ СОВПАЛ для: '{event.text[1:]}'")
                if match:
                    referrer_telegram_id = int(match.group(1))
                    if referrer_telegram_id == telegram_id:
                         logger.warning(f"Пользователь {telegram_id} попытался пригласить сам себя.")
                         referrer_telegram_id = None
                    else:
                        logger.debug(f"Пользователь {telegram_id} пришёл по реферальной ссылке от {referrer_telegram_id}")

            if referrer_telegram_id:
                try:
                    referrer_user = await User.objects.aget(telegram_id=referrer_telegram_id)
                    logger.debug(f"Найден пригласивший пользователь: {referrer_user.telegram_id}")
                except User.DoesNotExist:
                    logger.warning(f"Пользователь-пригласитель с telegram_id {referrer_telegram_id} не найден.")
                    referrer_user = None
            # --- КОНЕЦ НОВОГО ---

            user_obj, was_created_new, was_invited_set = await self._get_or_create_user(event, referrer_user)

            # --- НОВОЕ: Обработка начисления токенов за реферала ---
            # Начисляем бонус только если пользователь *новый* и ему *установили* invited_by
            if was_created_new and was_invited_set and referrer_user:
                bonus_tokens = 15
                referrer_user.token_balance += bonus_tokens
                await referrer_user.asave(update_fields=['token_balance'])
                logger.info(f"Пользователю {referrer_user.telegram_id} начислено {bonus_tokens} токенов за приглашение {user_obj.telegram_id}.")

                # Создаём транзакцию
                await TokenTransaction.objects.acreate(
                    user=referrer_user,
                    amount=bonus_tokens,
                    transaction_type='bonus',
                    description=f'Бонус за приглашение пользователя {user_obj.telegram_id}'
                )
                logger.debug(f"Создана транзакция начисления реферального бонуса для пользователя {referrer_user.telegram_id}")
            # --- КОНЕЦ НОВОГО ---

            # --- ПРОВЕРЯЕМ, БЫЛ ЛИ РАЗБЛОКИРОВАН ---
            if user_obj and was_blocked_before and not user_obj.is_blocked:
                was_reactivated = True
                logger.info(f"Пользователь {user_obj.telegram_id} автоматически разблокирован через взаимодействие с ботом.")
            else:
                logger.debug(f"[Middleware] Пользователь {user_obj.telegram_id if user_obj else 'N/A'} разблокирован: {False if not user_obj else not user_obj.is_blocked}, был заблокирован: {was_blocked_before}")
            # --- КОНЕЦ ПРОВЕРКИ ---

            if user_obj:
                data['user'] = user_obj
                if not getattr(user_obj, 'has_agreed_to_terms', False):
                    is_allowed = await self._is_action_allowed_during_onboarding(event)
                    if not is_allowed:
                        logger.info(f"Пользователь {user_obj.telegram_id} еще не дал согласие. Действие заблокировано.")
                        await self._handle_blocked_action(event, data)
                        return
            else:
                logger.warning("Пользователь не был создан/загружен")
                
        # --- ПЕРЕДАЁМ ФЛАГ В DATA ---
        data['was_blocked_and_reactivated'] = was_reactivated
        logger.debug(f"[Middleware] Установлен флаг was_blocked_and_reactivated: {was_reactivated}")
        # --- КОНЕЦ ---
                
        result = await handler(event, data)
        return result
        
    async def _get_or_create_user(self, event: TelegramObject, referrer_user=None) -> tuple[User, bool, bool]:
        """Получение или создание пользователя. Возвращает кортеж (User, is_new_user, was_invited_set)."""
        is_new_user = False
        was_invited_set = False
        try:
            if isinstance(event, Message):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user
                logger.debug(f"[Событие] Сообщения от пользователя: {username} ({telegram_id})")
            elif isinstance(event, CallbackQuery):
                telegram_id = event.from_user.id
                username = event.from_user.username or f"user_{telegram_id}"
                first_name = event.from_user.first_name or ""
                last_name = event.from_user.last_name or ""
                user_data = event.from_user
                logger.debug(f"[Событие] Callback от пользователя: {username} ({telegram_id})")
            else:
                logger.warning("Неизвестный тип события для определения пользователя")
                return None, is_new_user, was_invited_set

            try:
                # --- ИСПРАВЛЕНО: select_related для invited_by ---
                user = await User.objects.select_related('invited_by').aget(telegram_id=telegram_id)
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                updated_fields = []
                if user.username != username:
                    user.username = username
                    updated_fields.append('username')
                is_standard_first_name = user.first_name == "" or user.first_name.startswith(f"Пользователь {user.telegram_id}")
                if (user.first_name != first_name) and (user.first_name == event.from_user.first_name or is_standard_first_name):
                    user.first_name = first_name
                    updated_fields.append('first_name')
                if user.last_name != last_name:
                    user.last_name = last_name
                    updated_fields.append('last_name')
                # --- НОВОЕ: Автоматическая разблокировка при взаимодействии ---
                if user.is_blocked:
                    user.is_blocked = False
                    updated_fields.append('is_blocked')
                    logger.debug(f"Пользователь {user.telegram_id} разблокирован в _get_or_create_user.")
                # --- КОНЕЦ НОВОГО ---
                # --- ИСПРАВЛЕНО: Проверка и установка invited_by для существующего пользователя ---
                # Так как мы использовали select_related, 'invited_by' будет загружен как объект или None.
                # Однако, если invited_by был None в БД, а referrer_user передан, мы его устанавливаем.
                # Если он был не None (т.е. уже был установлен ранее), мы его не меняем.
                if user.invited_by is None and referrer_user is not None:
                    if user.telegram_id != referrer_user.telegram_id: # Убедимся, что это разные пользователи
                        user.invited_by = referrer_user
                        updated_fields.append('invited_by')
                        was_invited_set = True
                        logger.info(f"Пользователь {user.telegram_id} (уже существовал) отмечен как приглашённый пользователем {referrer_user.telegram_id}.")
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                if updated_fields:
                    await user.asave(update_fields=updated_fields)
                return user, is_new_user, was_invited_set # False, потому что пользователь уже существовал
            except User.DoesNotExist:
                logger.debug("Пользователь не найден, создаем нового")
                language = self._detect_language(event)
                logger.debug(f"Определен язык при регистрации: {language}")
                detected_timezone = self._detect_timezone_from_user_data(user_data)
                timezone_to_set = detected_timezone if detected_timezone and detected_timezone != 'UTC' else 'UTC'
                logger.debug(f"Определен/установлен часовой пояс при регистрации: {timezone_to_set}")
                user = await User.objects.acreate(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language=language,
                    timezone=timezone_to_set,
                    # --- ИСПРАВЛЕНО: Устанавливаем invited_by при создании, если он передан ---
                    invited_by=referrer_user
                    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                )
                is_new_user = True
                # Если referrer был передан и успешно установлен при создании
                if referrer_user:
                     was_invited_set = True
                     logger.info(f"Новый пользователь {user.telegram_id} создан и отмечен как приглашённый пользователем {referrer_user.telegram_id}.")

                welcome_tokens = 15
                user.token_balance += welcome_tokens
                await user.asave(update_fields=['token_balance'])
                logger.info(f"Новый пользователь создан: {user.username} ({user.telegram_id}) с языком {language} и часовым поясом {timezone_to_set} (по умолчанию). Начислено {welcome_tokens} приветственных токенов.")
                await TokenTransaction.objects.acreate(
                    user=user,
                    amount=welcome_tokens,
                    transaction_type='bonus',
                    description='Приветственные токены при регистрации'
                )
                logger.debug(f"Создана транзакция начисления приветственных токенов для пользователя {user.telegram_id}")
                return user, is_new_user, was_invited_set # True, потому что пользователь был создан
        except Exception as e:
            logger.error(f"Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None, is_new_user, was_invited_set
    
    def _detect_language(self, event: TelegramObject) -> str:
        """Определение языка пользователя (без изменений)"""
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
                return 'ru'
        except Exception as e:
            logger.error(f"Ошибка при определении языка: {e}")
            return 'ru'

    def _detect_timezone_from_user_data(self, user_data) -> str:
        """Попытка определения часового пояса пользователя из данных Telegram. (без изменений)"""
        try:
            if hasattr(user_data, 'timezone') and user_data.timezone:
                import pytz
                try:
                    pytz.timezone(user_data.timezone)
                    return user_data.timezone
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"Невалидный идентификатор часового пояса из Telegram: {user_data.timezone}. Используется UTC.")
                    return 'UTC'
            elif hasattr(user_data, 'utc_offset') and user_data.utc_offset is not None:
                utc_offset = user_data.utc_offset
                total_hours = utc_offset // 3600
                if total_hours == 0:
                    return 'UTC'
                elif total_hours > 0:
                    tz_name = f'UTC+{total_hours}'
                    return tz_name
                else:
                    tz_name = f'UTC{total_hours}'
                    return tz_name
            else:
                return 'UTC'
        except Exception as e:
            logger.error(f"Ошибка при попытке автоматического определения часового пояса: {e}")
            return 'UTC'

    async def _is_action_allowed_during_onboarding(self, event: TelegramObject) -> bool:
        """
        Проверяет, разрешено ли действие пользователю без согласия.
        """
        if isinstance(event, Message) and event.text and event.text.startswith('/'):
            command = event.text[1:].split()[0]
            if command == "start":
                return True
        if isinstance(event, CallbackQuery):
            callback_data = event.data
            if callback_data:
                if any(callback_data.startswith(prefix) for prefix in ALLOWED_DURING_ONBOARDING_PREFIXES):
                    return True
        logger.debug("Действие не разрешено без согласия.")
        return False

    async def _handle_blocked_action(self, event: TelegramObject, data: Dict[str, Any]):
        """
        Обрабатывает ситуацию, когда действие пользователя заблокировано из-за отсутствия согласия.
        """
        user = data.get('user')
        language = data.get('language', 'ru')
        if user and not language:
            language = user.language or 'ru'
        if not user:
            logger.error("Невозможно обработать заблокированное действие: пользователь не найден в data.")
            return
        blocked_message = get_message('onboarding_required', language)
        try:
            if isinstance(event, Message):
                bot = data.get('bot') 
                if bot:
                    keyboard = get_start_onboarding_keyboard(language)
                    await bot.send_message(chat_id=event.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("Бот не найден в data для отправки сообщения о блокировке.")
            elif isinstance(event, CallbackQuery):
                await safe_answer_callback(event, get_message('access_denied', language), show_alert=True)
                bot = data.get('bot')
                if bot:
                    keyboard = get_start_onboarding_keyboard(language)
                    await bot.send_message(chat_id=event.message.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("Бот не найден в data для отправки сообщения о блокировке через callback.")
        except Exception as e:
            logger.error(f"Ошибка при обработке заблокированного действия для пользователя {user.telegram_id}: {e}")
