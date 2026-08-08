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
                if current_limit > 0:
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

    @classmethod
    async def build_task_settings_view(cls, user: User, language: str) -> Dict[str, Any]:
        """Экран настроек лимита заданий."""
        from bot.keyboards import get_task_settings_keyboard

        info_result = await cls.get_task_limit_info(user)
        if not info_result.get('success'):
            return {
                'success': False,
                'mode': 'error',
                'error': info_result.get('error'),
                'text': get_message('error_generic', language=language),
            }
        return {
            'success': True,
            'mode': 'task_settings',
            'text': get_message('task_settings_menu', language=language).format(
                max_tasks=info_result['current_limit']
            ),
            'reply_markup': get_task_settings_keyboard(user, language),
            'current_limit': info_result['current_limit'],
        }

    @classmethod
    async def build_task_limit_update_view(
        cls,
        user: User,
        language: str,
        increment: int,
    ) -> Dict[str, Any]:
        """Обновляет лимит и собирает alert/screen payload."""
        from bot.keyboards import get_task_settings_keyboard

        result = await cls.update_task_limit(user, increment=increment)
        if not result.get('success'):
            if result.get('error') == 'limit_exceeded':
                alert_message = get_message(
                    'awareness_level_insufficient_for_tasks_current',
                    language=language,
                    current_level=result['current_level'],
                    current_max_tasks=result['current_max_tasks'],
                )
                screen = await cls.build_task_settings_view(user, language)
                return {
                    'success': False,
                    'mode': 'limit_exceeded',
                    'alert_text': alert_message,
                    'show_alert': True,
                    'text': screen.get('text'),
                    'reply_markup': screen.get('reply_markup'),
                    'refresh_screen': screen.get('success', False),
                }
            return {
                'success': False,
                'mode': 'error',
                'error': result.get('error'),
                'alert_text': get_message('error_generic', language=language),
                'show_alert': False,
                'refresh_screen': False,
            }

        action = result.get('action')
        if action == 'increased':
            alert_text = get_message('tasks_limit_increased', language=language).format(
                new_limit=result['new_limit']
            )
        elif action == 'max_reached':
            alert_text = get_message('tasks_limit_max_reached', language=language)
        elif action == 'decreased':
            alert_text = get_message('tasks_limit_decreased', language=language).format(
                new_limit=result['new_limit']
            )
        elif action == 'min_reached':
            alert_text = get_message('tasks_limit_min_reached', language=language)
        else:
            alert_text = get_message('tasks_limit_increased', language=language).format(
                new_limit=result['new_limit']
            )

        return {
            'success': True,
            'mode': action or 'updated',
            'alert_text': alert_text,
            'show_alert': False,
            'text': get_message('task_settings_menu', language=language).format(
                max_tasks=result['new_limit']
            ),
            'reply_markup': get_task_settings_keyboard(user, language),
            'refresh_screen': True,
            'new_limit': result['new_limit'],
        }

    @classmethod
    def build_city_timezone_lookup_view(
        cls,
        lookup_result: Dict[str, Any],
        language: str,
        city_name: str = '',
    ) -> Dict[str, Any]:
        """Нормализует результат поиска города в transport payload."""
        from bot.keyboards import (
            get_city_timezone_confirmation_keyboard,
            get_multiple_city_timezones_keyboard,
            get_single_button_keyboard,
        )

        normalized = (city_name or '').strip()
        if normalized.lower() in {'назад', 'back', '/start', '/menu'}:
            return {
                'success': True,
                'mode': 'cancel',
                'clear_state': True,
                'text': get_message('settings_menu', language=language),
            }

        if not normalized:
            return {
                'success': False,
                'mode': 'empty_city',
                'text': get_message(key='please_enter_city', language=language),
                'clear_state': False,
            }

        if not lookup_result.get('success'):
            error_msg = lookup_result.get('error') or get_message('timezone_error', language)
            return {
                'success': False,
                'mode': 'lookup_failed',
                'text': f'❌ {error_msg}',
                'retry_text': get_message(key='please_enter_city', language=language),
                'reply_markup': get_single_button_keyboard(language, 'settings', 'btn_back'),
                'clear_state': False,
            }

        source = lookup_result.get('source')
        if source in ('cache', 'api_single'):
            timezone_data = lookup_result['timezone_data']
            return {
                'success': True,
                'mode': 'confirm_single',
                'text': get_message(
                    key='timezone_found',
                    language=language,
                    city_name=timezone_data['city'],
                    country=timezone_data['country'],
                    timezone=timezone_data['timezone'],
                ),
                'reply_markup': get_city_timezone_confirmation_keyboard(language, timezone_data),
                'fsm_state': 'waiting_for_timezone_confirmation',
                'fsm_payload': {'timezone_data': timezone_data},
                'clear_state': False,
            }

        if source == 'api_multiple':
            options = lookup_result.get('multiple_options') or []
            return {
                'success': True,
                'mode': 'select_multiple',
                'text': get_message(key='multiple_cities_found', language=language),
                'reply_markup': get_multiple_city_timezones_keyboard(language, options),
                'clear_state': False,
            }

        return {
            'success': False,
            'mode': 'unexpected_source',
            'text': get_message(key='selection_failed', language=language),
            'retry_text': get_message(key='enter_city', language=language),
            'reply_markup': get_single_button_keyboard(language, 'settings', 'btn_back'),
            'clear_state': False,
        }

    @classmethod
    async def set_timezone_and_resolve_next_step(
        cls,
        user: User,
        new_timezone_str: str,
        language: str,
        is_onboarding: bool,
    ) -> Dict[str, Any]:
        """
        Валидирует/ставит TZ и решает следующий шаг:
        onboarding_first_entry | main_menu | error.
        """
        result = await cls.update_user_timezone(user, new_timezone_str)
        if not result.get('success'):
            error = result.get('error')
            if error == 'unknown_timezone':
                return {
                    'success': False,
                    'mode': 'unknown_timezone',
                    'alert_text': get_message('error_unknown_timezone', language),
                    'show_alert': True,
                }
            return {
                'success': False,
                'mode': 'error',
                'alert_text': get_message('error_generic', language),
                'show_alert': True,
                'error': error,
            }

        if is_onboarding:
            return {
                'success': True,
                'mode': 'onboarding_first_entry',
                'next': 'onboarding_first_entry',
                'text': get_message('onboarding_prompt_first_entry', language),
                'reply_markup': None,
                'set_state': 'waiting_for_first_entry',
                'clear_state': False,
                'alert_text': '',
                'show_alert': False,
                'new_timezone': result['new_timezone'],
            }

        from diary.services.main_menu_service import build_main_menu_data

        menu_data = await build_main_menu_data(user=user, language=language)
        return {
            'success': True,
            'mode': 'main_menu',
            'next': 'main_menu',
            'text': menu_data['message_text'],
            'reply_markup': menu_data['keyboard'],
            'clear_state': True,
            'alert_text': get_message(
                'timezone_changed', language, timezone=result['new_timezone']
            ),
            'show_alert': False,
            'new_timezone': result['new_timezone'],
        }


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

async def build_task_settings_view(user: User, language: str) -> Dict[str, Any]:
    return await SettingsService.build_task_settings_view(user, language)

async def build_task_limit_update_view(
    user: User, language: str, increment: int
) -> Dict[str, Any]:
    return await SettingsService.build_task_limit_update_view(user, language, increment)

def build_city_timezone_lookup_view(
    lookup_result: Dict[str, Any], language: str, city_name: str = ''
) -> Dict[str, Any]:
    return SettingsService.build_city_timezone_lookup_view(
        lookup_result, language, city_name=city_name
    )

async def set_timezone_and_resolve_next_step(
    user: User,
    new_timezone_str: str,
    language: str,
    is_onboarding: bool,
) -> Dict[str, Any]:
    return await SettingsService.set_timezone_and_resolve_next_step(
        user, new_timezone_str, language, is_onboarding
    )
