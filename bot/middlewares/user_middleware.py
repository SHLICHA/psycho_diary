# /home/shlicha/psycho_diary/bot/middlewares/user_middleware.py
"""
Middleware для регистрации пользователей и контроля доступа (онбординг)
"""
import logging
import re

from typing import Any, Awaitable, Callable, Dict, Set, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

# ИМПОРТИРУЕМ НОВЫЙ СЕРВИС
from diary.services.user_service import get_or_create_user_from_event, award_referral_bonus
# ИМПОРТИРУЕМ User, если он нужен для типизации или других целей
from users.models import User, TokenTransaction # TokenTransaction убираем, если он больше не используется напрямую в мидлваре
from messages import get_message
from bot.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)

ALLOWED_DURING_ONBOARDING_PREFIXES: Set[str] = {
    "start",
}

REFERRAL_PATTERN = re.compile(r'^start\s+ref_(\d+)_([a-zA-Z0-9_-]+)$')
REFERRAL_PAYLOAD_LEGACY_PATTERN = re.compile(r'^ref_(\d+)_([a-zA-Z0-9_-]+)$')


async def resolve_referrer_user_from_start(start_text: str, current_telegram_id: Optional[int]) -> Optional[User]:
    """Resolve referrer from /start payload with support for legacy and new referral formats."""
    if not start_text:
        return None

    normalized = start_text.strip()
    if normalized.startswith('/'):
        normalized = normalized[1:]

    if not normalized.startswith('start'):
        return None

    parts = normalized.split(maxsplit=1)
    if len(parts) < 2:
        return None

    payload = parts[1].strip()
    if not payload:
        return None

    legacy_match = REFERRAL_PAYLOAD_LEGACY_PATTERN.match(payload)
    if legacy_match:
        referrer_telegram_id = int(legacy_match.group(1))
        if current_telegram_id and referrer_telegram_id == current_telegram_id:
            logger.warning(f"[Middleware] Пользователь {current_telegram_id} попытался пригласить сам себя.")
            return None
        try:
            return await User.objects.aget(telegram_id=referrer_telegram_id)
        except User.DoesNotExist:
            logger.warning(f"[Middleware] Пользователь-пригласитель с telegram_id {referrer_telegram_id} не найден.")
            return None

    # Новый формат: payload совпадает с user.referral_link (например, ref_u_xxx).
    try:
        referrer = await User.objects.aget(referral_link=payload)
    except User.DoesNotExist:
        return None

    if current_telegram_id and referrer.telegram_id and referrer.telegram_id == current_telegram_id:
        logger.warning(f"[Middleware] Пользователь {current_telegram_id} попытался пригласить сам себя.")
        return None

    return referrer

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
            if isinstance(event, Message) and event.text and event.text.startswith('/start'):
                logger.debug(f"[Middleware] Получена команда /start: '{event.text}'")
                referrer_user = await resolve_referrer_user_from_start(event.text, telegram_id)
                if referrer_user:
                    logger.debug(f"[Middleware] Найден пригласивший пользователь: {referrer_user.id}")
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
            else:
                logger.warning("[Middleware] Пользователь не был создан/загружен")
        # --- ПЕРЕДАЁМ ФЛАГ В DATA ---
        data['was_blocked_and_reactivated'] = was_reactivated
        logger.debug(f"[Middleware] Установлен флаг was_blocked_and_reactivated: {was_reactivated}")
        # --- КОНЕЦ ---
                
        result = await handler(event, data)
        return result
    
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
