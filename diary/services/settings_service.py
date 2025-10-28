"""
Сервис для работы с настройками пользователя.
Выносит бизнес-логику из хендлеров Telegram.
"""

import logging
import pytz
from typing import Dict, Any, Optional

from asgiref.sync import sync_to_async
from django.db import transaction

from users.models import User, CityTimezone
from messages import get_message
from bot.services.deepseek_api import deepseek_api_service

logger = logging.getLogger(__name__)

class SettingsService:
    """Сервис для работы с настройками пользователя."""

    @classmethod
    async def update_user_language(cls, user: User, new_language: str) -> Dict[str, Any]:
        """
        Обновляет язык пользователя.

        Args:
            user: Объект пользователя Django.
            new_language: Новый код языка ('ru', 'en').

        Returns:
            Dict[str, Any]: Результат обновления.
        """
        supported_languages = ['ru', 'en']
        if new_language not in supported_languages:
            logger.warning(f"[SettingsService] Неподдерживаемый язык: {new_language}")
            return {'success': False, 'error': 'unsupported_language'}

        try:
            user.language = new_language
            await user.asave(update_fields=['language'])
            logger.debug(f"[SettingsService] Язык пользователя {user.telegram_id} обновлён на {new_language}")
            return {'success': True, 'new_language': new_language}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при обновлении языка для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def toggle_user_notifications(cls, user: User) -> Dict[str, Any]:
        """
        Переключает состояние уведомлений пользователя.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Результат переключения.
        """
        try:
            new_state = not user.notifications_enabled
            user.notifications_enabled = new_state
            await user.asave(update_fields=['notifications_enabled'])
            logger.debug(f"[SettingsService] Уведомления пользователя {user.telegram_id} {'включены' if new_state else 'отключены'}")
            status_message_key = 'notifications_enabled' if new_state else 'notifications_disabled'
            return {'success': True, 'new_state': new_state, 'status_message_key': status_message_key}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при переключении уведомлений для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def toggle_user_auto_analysis(cls, user: User) -> Dict[str, Any]:
        """
        Переключает состояние автоанализа пользователя.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Результат переключения.
        """
        try:
            new_state = not user.auto_analysis_enabled
            user.auto_analysis_enabled = new_state
            await user.asave(update_fields=['auto_analysis_enabled'])
            logger.debug(f"[SettingsService] Автоанализ пользователя {user.telegram_id} {'включён' if new_state else 'отключён'}")
            status_message_key = 'status_enabled' if new_state else 'status_disabled'
            return {'success': True, 'new_state': new_state, 'status_message_key': status_message_key}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при переключении автоанализа для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def get_task_limit_info(cls, user: User) -> Dict[str, Any]:
        """
        Получает информацию о лимите заданий.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Информация о лимите.
        """
        try:
            awareness_level = user.awareness_level
            max_allowed = 5
            if awareness_level < 8:
                max_allowed = 1
            elif awareness_level == 8:
                max_allowed = 2
            elif awareness_level == 9:
                max_allowed = 3
            current_limit = user.max_ai_tasks_per_day
            return {
                'success': True,
                'current_limit': current_limit,
                'max_allowed': max_allowed,
                'awareness_level': awareness_level
            }
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при получении информации о лимите заданий для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def update_task_limit(cls, user: User, increment: int) -> Dict[str, Any]:
        """
        Обновляет лимит заданий пользователя (увеличивает или уменьшает).

        Args:
            user: Объект пользователя Django.
            increment: +1 или -1.

        Returns:
            Dict[str, Any]: Результат обновления.
        """
        try:
            info_result = await cls.get_task_limit_info(user)
            if not info_result['success']:
                return info_result

            current_limit = info_result['current_limit']
            max_allowed = info_result['max_allowed']

            new_limit_proposed = current_limit + increment

            if increment > 0:
                if new_limit_proposed > max_allowed:
                    return {
                        'success': False,
                        'error': 'limit_exceeded',
                        'current_level': info_result['awareness_level'],
                        'current_max_tasks': max_allowed
                    }
                if current_limit < max_allowed:
                    user.max_ai_tasks_per_day += 1
                    await user.asave(update_fields=['max_ai_tasks_per_day'])
                    logger.debug(f"[SettingsService] Лимит заданий пользователя {user.telegram_id} увеличен до {user.max_ai_tasks_per_day}")
                    return {'success': True, 'new_limit': user.max_ai_tasks_per_day, 'action': 'increased'}
                else:
                    return {'success': True, 'new_limit': current_limit, 'action': 'max_reached'}
            elif increment < 0:
                if current_limit > 1:
                    user.max_ai_tasks_per_day -= 1
                    await user.asave(update_fields=['max_ai_tasks_per_day'])
                    logger.debug(f"[SettingsService] Лимит заданий пользователя {user.telegram_id} уменьшен до {user.max_ai_tasks_per_day}")
                    return {'success': True, 'new_limit': user.max_ai_tasks_per_day, 'action': 'decreased'}
                else:
                    return {'success': True, 'new_limit': current_limit, 'action': 'min_reached'}
            else:
                return {'success': True, 'new_limit': current_limit, 'action': 'no_change'}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при обновлении лимита заданий для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def update_user_timezone(cls, user: User, new_timezone_str: str) -> Dict[str, Any]:
        """
        Обновляет часовой пояс пользователя.

        Args:
            user: Объект пользователя Django.
            new_timezone_str: Новый часовой пояс (строка, например, 'Europe/Moscow').

        Returns:
            Dict[str, Any]: Результат обновления.
        """
        try:
            pytz.timezone(new_timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"[SettingsService] Неизвестный часовой пояс: {new_timezone_str}")
            return {'success': False, 'error': 'unknown_timezone'}

        try:
            tz_obj = pytz.timezone(new_timezone_str)
            canonical_tz_name = str(tz_obj)
            user.timezone = canonical_tz_name
            await user.asave(update_fields=['timezone'])
            logger.debug(f"[SettingsService] Часовой пояс пользователя {user.telegram_id} обновлён на {canonical_tz_name}")
            return {'success': True, 'new_timezone': canonical_tz_name}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при обновлении часового пояса для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def get_timezone_info(cls, user: User) -> Dict[str, Any]:
        """
        Получает информацию о текущем часовом поясе пользователя.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Информация о часовом поясе.
        """
        try:
            return {'success': True, 'current_timezone': user.timezone}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при получении информации о часовом поясе для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def process_city_timezone_lookup(cls, city_name: str, language: str) -> Dict[str, Any]:
        """
        Выполняет поиск часового пояса по названию города.

        Args:
            city_name: Название города.
            language: Язык пользователя.

        Returns:
            Dict[str, Any]: Результат поиска.
        """
        try:
            try:
                city_tz_obj = await CityTimezone.objects.aget(city_name__iexact=city_name)
                return {
                    'success': True,
                    'timezone_data': {
                        'timezone': city_tz_obj.timezone,
                        'city': city_tz_obj.city_name,
                        'country': city_tz_obj.country
                    },
                    'source': 'cache'
                }
            except CityTimezone.DoesNotExist:
                pass
            result = await deepseek_api_service.detect_timezone_by_city(city_name, language)
            if not result['success']:
                error_msg = result.get('message', get_message('timezone_error', language))
                logger.warning(f"[SettingsService] Ошибка API при поиске часового пояса для '{city_name}': {error_msg}")
                return {'success': False, 'error': error_msg, 'api_error': result.get('error')}
            api_result = result['result']
            if not api_result.get('success', False):
                error_msg = api_result.get('error', get_message('city_not_found', language))
                logger.debug(f"[SettingsService] API вернул ошибку для '{city_name}': {error_msg}")
                return {'success': False, 'error': error_msg, 'api_error': api_result.get('error')}
            if api_result.get('multiple', False):
                options = api_result.get('options', [])
                if options:
                    return {
                        'success': True,
                        'multiple_options': options,
                        'source': 'api_multiple'
                    }
                else:
                    logger.warning(f"[SettingsService] API сообщил о нескольких вариантах для '{city_name}', но список пуст.")
                    return {'success': False, 'error': get_message('selection_failed', language)}
            timezone_str = api_result.get('timezone')
            city = api_result.get('city', city_name)
            country = api_result.get('country', 'Неизвестно')

            if not timezone_str:
                logger.warning(f"[SettingsService] API не вернул часовой пояс для '{city_name}'.")
                return {'success': False, 'error': get_message('timezone_detection_failed', language)}
            try:
                pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"[SettingsService] API вернул неверный часовой пояс: {timezone_str}")
                return {'success': False, 'error': get_message('invalid_timezone', language)}
            return {
                'success': True,
                'timezone_data': {
                    'timezone': timezone_str,
                    'city': city,
                    'country': country
                },
                'source': 'api_single'
            }
        except Exception as e:
            logger.error(f"[SettingsService] Неожиданная ошибка при поиске часового пояса для '{city_name}': {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def confirm_timezone_by_city(cls, user: User, timezone_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Подтверждает и устанавливает часовой пояс, найденный по городу.
        Также сохраняет город в кэш (CityTimezone), если его там не было.

        Args:
            user: Объект пользователя Django.
            timezone_data: Словарь с ключами 'timezone', 'city', 'country'.

        Returns:
            Dict[str, Any]: Результат подтверждения.
        """
        try:
            new_timezone_str = timezone_data['timezone']
            city = timezone_data.get('city', '')
            country = timezone_data.get('country', '')
            try:
                pytz.timezone(new_timezone_str)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"[SettingsService] Подтверждение: неверный часовой пояс: {new_timezone_str}")
                return {'success': False, 'error': 'invalid_timezone'}
            user.timezone = new_timezone_str
            await user.asave(update_fields=['timezone'])
            if city and country:
                @sync_to_async
                def _create_or_update_city_timezone():
                    with transaction.atomic():
                        city_obj, created = CityTimezone.objects.get_or_create(
                            city_name__iexact=city,
                            defaults={
                                'city_name': city,
                                'timezone': new_timezone_str,
                                'country': country
                            }
                        )
                        if not created and city_obj.timezone != new_timezone_str:
                            logger.debug(f"[SettingsService] Обновление часового пояса для существующего города '{city}' в кэше.")
                            city_obj.timezone = new_timezone_str
                            city_obj.country = country
                            city_obj.save(update_fields=['timezone', 'country'])
                await _create_or_update_city_timezone()

            logger.debug(f"[SettingsService] Часовой пояс пользователя {user.telegram_id} подтверждён и обновлён на {new_timezone_str} через город {city}.")
            return {'success': True, 'new_timezone': new_timezone_str}
        except Exception as e:
            logger.error(f"[SettingsService] Ошибка при подтверждении часового пояса по городу для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

async def update_user_language(user: User, new_language: str) -> Dict[str, Any]:
    return await SettingsService.update_user_language(user, new_language)

async def toggle_user_notifications(user: User) -> Dict[str, Any]:
    return await SettingsService.toggle_user_notifications(user)

async def toggle_user_auto_analysis(user: User) -> Dict[str, Any]:
    return await SettingsService.toggle_user_auto_analysis(user)

async def get_task_limit_info(user: User) -> Dict[str, Any]:
    return await SettingsService.get_task_limit_info(user)

async def update_task_limit(user: User, increment: int) -> Dict[str, Any]:
    return await SettingsService.update_task_limit(user, increment)

async def update_user_timezone(user: User, new_timezone_str: str) -> Dict[str, Any]:
    return await SettingsService.update_user_timezone(user, new_timezone_str)

async def get_timezone_info(user: User) -> Dict[str, Any]:
    return await SettingsService.get_timezone_info(user)

async def process_city_timezone_lookup(city_name: str, language: str) -> Dict[str, Any]:
    return await SettingsService.process_city_timezone_lookup(city_name, language)

async def confirm_timezone_by_city(user: User, timezone_data: Dict[str, str]) -> Dict[str, Any]:
    return await SettingsService.confirm_timezone_by_city(user, timezone_data)
