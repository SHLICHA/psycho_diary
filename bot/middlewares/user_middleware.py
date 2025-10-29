# /home/shlicha/psycho_diary/bot/middlewares/user_middleware.py
"""
Middleware для регистрации пользователей и контроля доступа (онбординг)
"""
import logging
import re

from typing import Any, Awaitable, Callable, Dict, Set, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from asgiref.sync import sync_to_async

# ИМПОРТИРУЕМ НОВЫЙ СЕРВИС
from diary.services.user_service import get_or_create_user_from_event, award_referral_bonus
# ИМПОРТИРУЕМ User, если он нужен для типизации или других целей
from users.models import User, TokenTransaction # TokenTransaction убираем, если он больше не используется напрямую в мидлваре
from messages import get_message
from bot.keyboards import get_main_menu_keyboard
from bot.keyboards.onboarding_keyboards import get_next_after_welcome_keyboard, get_next_after_info_keyboard
from bot.handlers.settings import onboarding_start_timezone_setup

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
                # --- НОВАЯ ЛОГИКА: ПРОВЕРКА ОНБОРДИНГА ---
                # Проверяем, завершён ли онбординг
                if not user_obj.is_onboarding_completed:
                    # Если не завершён, проверяем, является ли событие продвижением онбординга
                    is_onboarding_event = await self._is_onboarding_event(event, user_obj)
                    if is_onboarding_event:
                        # Это событие продвигает онбординг, даем обработать хендлеру
                        logger.debug(f"[Middleware] Событие {event} является событием онбординга для {user_obj.telegram_id}, передаем дальше.")
                    else:
                        # Это событие не продвигает онбординг, направляем к текущему шагу
                        logger.info(f"[Middleware] Пользователь {user_obj.telegram_id} не завершил онбординг. Текущий шаг: {user_obj.onboarding_step}. Направляем к следующему шагу.")
                        language = data.get('language', 'ru')
                        await self._redirect_to_onboarding_step(event, data, user_obj, language)
                        # ВАЖНО: Возвращаемся ДО выполнения основного handler
                        return
                # --- /НОВАЯ ЛОГИКА ---
            else:
                logger.warning("[Middleware] Пользователь не был создан/загружен")
                
        # --- ПЕРЕДАЁМ ФЛАГ В DATA ---
        data['was_blocked_and_reactivated'] = was_reactivated
        logger.debug(f"[Middleware] Установлен флаг was_blocked_and_reactivated: {was_reactivated}")
        # --- КОНЕЦ ---
                
        result = await handler(event, data)
        return result

    async def _is_onboarding_event(self, event: TelegramObject, user: User) -> bool:
        """
        Проверяет, является ли событие продвижением онбординга.
        """
        if isinstance(event, CallbackQuery):
            callback_data = event.data
            if callback_data:
                # Проверяем, соответствует ли callback_data шагу, который ожидает пользователь
                current_step = user.onboarding_step
                expected_callbacks = {
                    'start': {'onboarding_info_next'},
                    'welcome_shown': {'onboarding_ready_for_entry'},
                    'first_entry_created': {'onboarding_start_timezone_setup'}, # Предполагаем, что это callback_data для вызова хендлера из middleware
                    # 'info_shown' не ожидает callback, а ожидает Message
                }
                expected = expected_callbacks.get(current_step)
                if expected and callback_data in expected:
                    logger.debug(f"[Middleware] Callback {callback_data} соответствует текущему шагу {current_step} для {user.telegram_id}.")
                    return True
                # Проверяем, может быть, это callback, связанный с установкой пояса (из settings)
                # Эти callback'и могут иметь разный формат, можно проверить начало
                if current_step == 'first_entry_created' and callback_data.startswith(('set_timezone:', 'select_timezone:', 'confirm_timezone:', 'onboarding_start_timezone_setup')):
                    logger.debug(f"[Middleware] Callback {callback_data} (установка пояса) соответствует текущему шагу {current_step} для {user.telegram_id}.")
                    return True
        elif isinstance(event, Message):
            # Проверяем, ожидает ли текущий шаг ввода сообщения
            if user.onboarding_step == 'info_shown':
                 logger.debug(f"[Middleware] Сообщение соответствует текущему шагу {user.onboarding_step} для {user.telegram_id}.")
                 return True
        return False

    async def _redirect_to_onboarding_step(self, event: TelegramObject, data: Dict[str, Any], user: User, language: str):
        """
        Направляет пользователя к следующему шагу онбординга на основе onboarding_step.
        """
        bot = data.get('bot')
        if not bot:
            logger.error("[Middleware] Бот не найден в data для _redirect_to_onboarding_step.")
            return

        step = user.onboarding_step
        chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id

        try:
            if step == 'start':
                # Middleware показывает приветствие ТОЛЬКО если пользователь пришёл сюда не после нажатия "Далее" из приветствия
                # (например, после перезапуска бота, если не было перехода к welcome_shown)
                # Но если онбординг только начался и middleware вызывается первый раз, она покажет приветствие.
                # Это нормально для первого входа.
                welcome_text = get_message('onboarding_welcome_extended_first_entry', language)
                keyboard = get_next_after_welcome_keyboard(language)
                await bot.send_message(chat_id=chat_id, text=welcome_text, reply_markup=keyboard)
            elif step == 'welcome_shown':
                # Middleware показывает инструкцию если пользователь пришёл сюда не после нажатия "Готов ввести запись"
                # Это может happen, если пользователь, например, нажал /start после просмотра приветствия, но до нажатия "Готов ввести запись"
                info_text = get_message('onboarding_project_info', language)
                keyboard = get_next_after_info_keyboard(language)
                await bot.send_message(chat_id=chat_id, text=info_text, reply_markup=keyboard)
            elif step == 'info_shown':
                # Middleware показывает просьбу ввести запись если пользователь пришёл сюда не после ввода сообщения
                # Это может happen, если пользователь, например, нажал /start после просмотра инструкции, но до ввода текста
                prompt_text = get_message('onboarding_prompt_first_entry', language)
                await bot.send_message(chat_id=chat_id, text=prompt_text) # <-- Без клавиатуры
            elif step == 'first_entry_created':
                # Направляем на установку часового пояса (через новый хендлер)
                
                
                fake_callback = CallbackQuery(
                    id="fake_id_onboarding_2",
                    from_user=event.from_user,
                    chat_instance="fake_instance_onboarding_2",
                    data="onboarding_start_timezone_setup",
                    message=event.message if isinstance(event, CallbackQuery) else None
                )
                state = data.get('state')
                if state:
                    await onboarding_start_timezone_setup(fake_callback, state, user, language)
                else:
                    logger.error(f"[Middleware] FSMContext не найден для пользователя {user.telegram_id} при перенаправлении на установку часового пояса (из onboarding).")
                    await bot.send_message(chat_id=chat_id, text=get_message('error_generic', language))
            elif step == 'completed':
                # Логическая ошибка: если completed, middleware не должна сюда попасть
                logger.warning(f"[Middleware] Пользователь {user.telegram_id} имеет onboarding_step 'completed', но is_onboarding_completed = False.")
                # Пытаемся исправить
                user.is_onboarding_completed = True
                await sync_to_async(user.save)(update_fields=['is_onboarding_completed'])
                # Показываем главное меню
                
                main_menu_text = get_message('main_menu', language)
                main_menu_keyboard = await get_main_menu_keyboard(language)
                await bot.send_message(chat_id=chat_id, text=main_menu_text, reply_markup=main_menu_keyboard)
            else:
                logger.error(f"[Middleware] Неизвестный onboarding_step: {step} для пользователя {user.telegram_id}")
                await bot.send_message(chat_id=chat_id, text=get_message('error_generic', language))

        except Exception as e:
            logger.error(f"[Middleware] Ошибка при перенаправлении пользователя {user.telegram_id} на шаг онбординга: {e}", exc_info=True)
            try:
                await bot.send_message(chat_id=chat_id, text=get_message('error_generic', language))
            except Exception as send_error:
                logger.error(f"[Middleware] Ошибка при отправке сообщения об ошибке пользователю {user.telegram_id}: {send_error}")

    
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
