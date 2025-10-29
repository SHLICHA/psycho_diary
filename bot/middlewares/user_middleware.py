# /home/shlicha/psycho_diary/bot/middlewares/user_middleware.py
"""
Middleware для регистрации пользователей и контроля доступа (онбординг)
"""
import logging
import re

from typing import Any, Awaitable, Callable, Dict, Set, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from messages import get_message
from bot.keyboards.onboarding_keyboards import get_start_onboarding_keyboard
from bot.utils.callback_utils import safe_answer_callback
# ИМПОРТИРУЕМ НОВЫЙ СЕРВИС
from diary.services.user_service import get_or_create_user_from_event, award_referral_bonus
# ИМПОРТИРУЕМ User, если он нужен для типизации или других целей
from users.models import User, TokenTransaction # TokenTransaction убираем, если он больше не используется напрямую в мидлваре

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
        user_obj: Optional[User] = None
        was_reactivated = False
        referrer_user: Optional[User] = None

        if isinstance(event, (Message, CallbackQuery)):
            telegram_id = event.from_user.id if hasattr(event, 'from_user') else None

            was_blocked_before = False
            if telegram_id:
                try:
                    # Проверяем, был ли пользователь заблокирован до взаимодействия
                    existing_user = await User.objects.select_related('invited_by').aget(telegram_id=telegram_id)
                    was_blocked_before = existing_user.is_blocked
                    logger.debug(f"[Middleware] Пользователь {telegram_id} был заблокирован до: {was_blocked_before}")
                except User.DoesNotExist:
                    was_blocked_before = False

            # --- ОБРАБОТКА РЕФЕРАЛЬНОЙ ССЫЛКИ ---
            referrer_telegram_id = None
            if isinstance(event, Message) and event.text and event.text.startswith('/start'):
                logger.debug(f"[Middleware] Получена команда /start: '{event.text}'")
                match = REFERRAL_PATTERN.match(event.text[1:]) # Убираем '/'
                if match:
                    logger.debug(f"[Middleware] Успешное совпадение паттерна для: '{event.text[1:]}'")
                    referrer_telegram_id = int(match.group(1))
                    if referrer_telegram_id == telegram_id:
                        logger.warning(f"[Middleware] Пользователь {telegram_id} попытался пригласить сам себя.")
                        referrer_telegram_id = None
                    else:
                        logger.debug(f"[Middleware] Пользователь {telegram_id} пришёл по реферальной ссылке от {referrer_telegram_id}")

            if referrer_telegram_id:
                try:
                    referrer_user = await User.objects.aget(telegram_id=referrer_telegram_id)
                    logger.debug(f"[Middleware] Найден пригласивший пользователь: {referrer_user.telegram_id}")
                except User.DoesNotExist:
                    logger.warning(f"[Middleware] Пользователь-пригласитель с telegram_id {referrer_telegram_id} не найден.")
                    referrer_user = None
            # --- КОНЕЦ ОБРАБОТКИ РЕФЕРАЛЬНОЙ ССЫЛКИ ---

            # --- ВЫЗОВ СЕРВИСА ДЛЯ ПОЛУЧЕНИЯ/СОЗДАНИЯ ПОЛЬЗОВАТЕЛЯ ---
            user_obj, was_created_new, was_invited_set = await get_or_create_user_from_event(event, referrer_user)
            # --- /ВЫЗОВ СЕРВИСА ---

            # --- НАЧИСЛЕНИЕ РЕФЕРАЛЬНОГО БОНУСА (если нужно) ---
            if was_created_new and was_invited_set and referrer_user:
                # Вызов сервиса для начисления бонуса
                bonus_awarded = await award_referral_bonus(referrer_user, user_obj)
                if bonus_awarded:
                    logger.info(f"[Middleware] Реферальный бонус успешно начислен пользователю {referrer_user.telegram_id} за приглашение {user_obj.telegram_id}.")
                else:
                    logger.error(f"[Middleware] Ошибка при начислении реферального бонуса пользователю {referrer_user.telegram_id} за приглашение {user_obj.telegram_id}.")
            # --- /НАЧИСЛЕНИЕ РЕФЕРАЛЬНОГО БОНУСА ---

            # --- ПРОВЕРЯЕМ, БЫЛ ЛИ РАЗБЛОКИРОВАН ---
            if user_obj and was_blocked_before and not user_obj.is_blocked:
                was_reactivated = True
                logger.info(f"[Middleware] Пользователь {user_obj.telegram_id} автоматически разблокирован через взаимодействие с ботом.")
            else:
                logger.debug(f"[Middleware] Пользователь {user_obj.telegram_id if user_obj else 'N/A'} разблокирован: {False if not user_obj else not user_obj.is_blocked}, был заблокирован: {was_blocked_before}")
            # --- КОНЕЦ ПРОВЕРКИ ---

            if user_obj:
                data['user'] = user_obj
                if not getattr(user_obj, 'has_agreed_to_terms', False):
                    is_allowed = await self._is_action_allowed_during_onboarding(event)
                    if not is_allowed:
                        logger.info(f"[Middleware] Пользователь {user_obj.telegram_id} еще не дал согласие. Действие заблокировано.")
                        await self._handle_blocked_action(event, data)
                        return
            else:
                logger.warning("[Middleware] Пользователь не был создан/загружен")
                
        # --- ПЕРЕДАЁМ ФЛАГ В DATA ---
        data['was_blocked_and_reactivated'] = was_reactivated
        logger.debug(f"[Middleware] Установлен флаг was_blocked_and_reactivated: {was_reactivated}")
        # --- КОНЕЦ ---
                
        result = await handler(event, data)
        return result
        
    # --- УБРАНО: async def _get_or_create_user(self, ...) ---
    # --- УБРАНО: async def _is_action_allowed_during_onboarding(self, ...) ---
    # --- УБРАНО: async def _handle_blocked_action(self, ...) ---
    # --- УБРАНО: def _detect_language(self, ...) ---
    # --- УБРАНО: def _detect_timezone_from_user_data(self, ...) ---
    
    # ОСТАВЛЯЕМ ТЕ МЕТОДЫ, КОТОРЫЕ НЕ БЫЛИ ПЕРЕНЕСЕНЫ В СЕРВИС (ЛОГИКА ONBOARDING/ДОСТУПА)
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
        logger.debug("[Middleware] Действие не разрешено без согласия.")
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
            logger.error("[Middleware] Невозможно обработать заблокированное действие: пользователь не найден в data.")
            return
        blocked_message = get_message('onboarding_required', language)
        try:
            if isinstance(event, Message):
                bot = data.get('bot') 
                if bot:
                    keyboard = get_start_onboarding_keyboard(language)
                    await bot.send_message(chat_id=event.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("[Middleware] Бот не найден в data для отправки сообщения о блокировке.")
            elif isinstance(event, CallbackQuery):
                await safe_answer_callback(event, get_message('access_denied', language), show_alert=True)
                bot = data.get('bot')
                if bot:
                    keyboard = get_start_onboarding_keyboard(language)
                    await bot.send_message(chat_id=event.message.chat.id, text=blocked_message, reply_markup=keyboard)
                else:
                    logger.warning("[Middleware] Бот не найден в data для отправки сообщения о блокировке через callback.")
        except Exception as e:
            logger.error(f"[Middleware] Ошибка при обработке заблокированного действия для пользователя {user.telegram_id}: {e}")
