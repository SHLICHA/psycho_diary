# /diary/services/user_service.py
"""
Сервис для работы с пользователями: регистрация, обновление, рефералы.
"""

import logging
import pytz
import re
from typing import Optional, Tuple

from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db import transaction

from users.models import User, TokenTransaction
from messages import get_message # Может понадобиться для логов или сообщений об ошибках

logger = logging.getLogger(__name__)

# Паттерн для парсинга реферальной ссылки
REFERRAL_PATTERN = re.compile(r'^start\s+ref_(\d+)_([a-zA-Z0-9_-]+)$')

class UserService:
    """Сервис для управления пользователями."""

    @classmethod
    async def get_or_create_user_from_event(
        cls,
        event, # Импортировать точный тип из aiogram, если нужно
        referrer_user: Optional[User] = None
    ) -> Tuple[Optional[User], bool, bool]:
        """
        Получение или создание пользователя на основе события Telegram.
        Обрабатывает обновление данных, автоматическую разблокировку и установку реферера.

        Args:
            event: Событие Telegram (Message или CallbackQuery).
            referrer_user: Пользователь-реферер (если есть).

        Returns:
            Tuple[Optional[User], bool, bool]: Кортеж (пользователь, создан_ли_новый, установлен_ли_реферер).
        """
        is_new_user = False
        was_invited_set = False
        user = None

        try:
            # --- Определение данных из события ---
            if hasattr(event, 'from_user'):
                from_user = event.from_user
                telegram_id = from_user.id
                username = from_user.username or f"user_{telegram_id}"
                first_name = from_user.first_name or ""
                last_name = from_user.last_name or ""
                user_data = from_user # Для определения часового пояса
                logger.debug(f"[UserService] Данные пользователя из события: {username} ({telegram_id})")
            else:
                logger.warning("[UserService] Событие не содержит from_user.")
                return None, is_new_user, was_invited_set

            # --- Попытка получить существующего пользователя ---
            try:
                # Используем select_related для invited_by, чтобы избежать дополнительных запросов
                user = await User.objects.select_related('invited_by').aget(telegram_id=telegram_id)
                logger.debug(f"[UserService] Найден существующий пользователь: {user.telegram_id}")

                # --- Обновление данных пользователя ---
                updated_fields = []
                if user.username != username:
                    user.username = username
                    updated_fields.append('username')
                # Обновляем имя, если оно было стандартным или изменилось
                is_standard_first_name = user.first_name == "" or user.first_name.startswith(f"Пользователь {user.telegram_id}")
                if (user.first_name != first_name) and (user.first_name == event.from_user.first_name or is_standard_first_name):
                    user.first_name = first_name
                    updated_fields.append('first_name')
                if user.last_name != last_name:
                    user.last_name = last_name
                    updated_fields.append('last_name')

                # --- Автоматическая разблокировка ---
                if user.is_blocked:
                    user.is_blocked = False
                    updated_fields.append('is_blocked')
                    logger.debug(f"[UserService] Пользователь {user.telegram_id} разблокирован.")

                # --- Установка invited_by для существующего пользователя ---
                # Устанавливаем только если он еще не установлен и передан referrer_user
                # и это не тот же самый пользователь (защита от самореференса внутри логики создания/обновления)
                if user.invited_by is None and referrer_user is not None:
                    if user.telegram_id != referrer_user.telegram_id:
                        user.invited_by = referrer_user
                        updated_fields.append('invited_by')
                        was_invited_set = True
                        logger.info(f"[UserService] Пользователь {user.telegram_id} (уже существовал) отмечен как приглашённый пользователем {referrer_user.telegram_id}.")
                    else:
                        logger.warning(f"[UserService] Попытка самореференса для пользователя {user.telegram_id}.")

                # --- Сохранение обновлений ---
                if updated_fields:
                    await user.asave(update_fields=updated_fields)
                    logger.debug(f"[UserService] Пользователь {user.telegram_id} обновлён. Поля: {updated_fields}")

                return user, is_new_user, was_invited_set

            except User.DoesNotExist:
                logger.debug("[UserService] Пользователь не найден, создаём нового.")
                # --- Создание нового пользователя ---
                language = cls._detect_language_from_event(event)
                logger.debug(f"[UserService] Определён язык при регистрации: {language}")
                detected_timezone = cls._detect_timezone_from_user_data(user_data)
                timezone_to_set = detected_timezone if detected_timezone and detected_timezone != 'UTC' else 'UTC'
                logger.debug(f"[UserService] Определён/установлен часовой пояс при регистрации: {timezone_to_set}")

                # --- Создание пользователя в транзакции ---
                @sync_to_async
                def _create_user_atomic():
                    with transaction.atomic():
                        user = User.objects.create(
                            telegram_id=telegram_id,
                            username=username,
                            first_name=first_name,
                            last_name=last_name,
                            language=language,
                            timezone=timezone_to_set,
                            invited_by=referrer_user # Устанавливаем при создании
                        )
                        # --- Начисление приветственных токенов ---
                        welcome_tokens = 15
                        user.token_balance += welcome_tokens
                        user.save(update_fields=['token_balance']) # Используем sync save внутри транзакции
                        logger.info(f"[UserService] Новый пользователь создан: {user.username} ({user.telegram_id}) с языком {language} и часовым поясом {timezone_to_set}. Начислено {welcome_tokens} приветственных токенов.")
                        # --- Создание транзакции ---
                        TokenTransaction.objects.create( # Используем sync create внутри транзакции
                            user=user,
                            amount=welcome_tokens,
                            transaction_type='bonus',
                            description='Приветственные токены при регистрации'
                        )
                        logger.debug(f"[UserService] Создана транзакция начисления приветственных токенов для пользователя {user.telegram_id}")
                    return user

                user = await _create_user_atomic()
                is_new_user = True
                if referrer_user:
                    was_invited_set = True
                    logger.info(f"[UserService] Новый пользователь {user.telegram_id} создан и отмечен как приглашённый пользователем {referrer_user.telegram_id}.")

                return user, is_new_user, was_invited_set

        except Exception as e:
            logger.error(f"[UserService] Ошибка при создании/загрузке пользователя: {e}", exc_info=True)
            return None, is_new_user, was_invited_set

    @classmethod
    async def award_referral_bonus(cls, referrer_user: User, referred_user: User) -> bool:
        """
        Начисляет бонусные токены рефереру за приглашение нового пользователя.

        Args:
            referrer_user: Пользователь-реферер.
            referred_user: Приглашённый пользователь.

        Returns:
            bool: True, если бонус успешно начислен, иначе False.
        """
        try:
            bonus_tokens = 15
            # --- Атомарное обновление баланса и создание транзакции ---
            @sync_to_async
            def _award_bonus_atomic():
                with transaction.atomic():
                    # Обновляем баланс
                    referrer_user.token_balance += bonus_tokens
                    referrer_user.save(update_fields=['token_balance'])
                    logger.info(f"[UserService] Пользователю {referrer_user.telegram_id} начислено {bonus_tokens} токенов за приглашение {referred_user.telegram_id}.")
                    # Создаём транзакцию
                    TokenTransaction.objects.create(
                        user=referrer_user,
                        amount=bonus_tokens,
                        transaction_type='bonus',
                        description=f'Бонус за приглашение пользователя {referred_user.telegram_id}'
                    )
                    logger.debug(f"[UserService] Создана транзакция начисления реферального бонуса для пользователя {referrer_user.telegram_id}")
                return True
            await _award_bonus_atomic()
            return True
        except Exception as e:
            logger.error(f"[UserService] Ошибка при начислении реферального бонуса пользователю {referrer_user.telegram_id} за приглашение {referred_user.telegram_id}: {e}", exc_info=True)
            return False

    @classmethod
    def _detect_language_from_event(cls, event) -> str:
        """Определение языка пользователя из события Telegram."""
        try:
            lang_code = None
            if hasattr(event, 'from_user') and event.from_user:
                lang_code = event.from_user.language_code
            supported_languages = ['ru', 'en']
            if lang_code and lang_code[:2] in supported_languages:
                detected_lang = lang_code[:2]
                return detected_lang
            else:
                return 'ru'
        except Exception as e:
            logger.error(f"[UserService] Ошибка при определении языка: {e}")
            return 'ru'

    @classmethod
    def _detect_timezone_from_user_data(cls, user_data) -> str:
        """Попытка определения часового пояса пользователя из данных Telegram."""
        try:
            if hasattr(user_data, 'timezone') and user_data.timezone:
                try:
                    pytz.timezone(user_data.timezone)
                    return user_data.timezone
                except pytz.UnknownTimeZoneError:
                    logger.warning(f"[UserService] Невалидный идентификатор часового пояса из Telegram: {user_data.timezone}. Используется UTC.")
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
            logger.error(f"[UserService] Ошибка при попытке автоматического определения часового пояса: {e}")
            return 'UTC'

# --- Удобные функции для импорта ---
async def get_or_create_user_from_event(event, referrer_user: Optional[User] = None) -> Tuple[Optional[User], bool, bool]:
    """Удобная функция для получения или создания пользователя."""
    return await UserService.get_or_create_user_from_event(event, referrer_user)

async def award_referral_bonus(referrer_user: User, referred_user: User) -> bool:
    """Удобная функция для начисления реферального бонуса."""
    return await UserService.award_referral_bonus(referrer_user, referred_user)
