# /diary/services/user_profile_service.py
"""
Сервис для работы с профилем пользователя.
Выносит бизнес-логику из хендлеров Telegram.
"""

import logging
import os
import urllib.parse
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Optional
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone as django_timezone

from users.models import User, UserProfileHistory, TokenTransaction, Payment
from users.services.identity_policy_service import IdentityPolicyService
from users.services.email_merge_service import EmailMergeService
from diary.models import (
    DiaryEntry, TherapyTask, TaskCompletion, TaskCompletionAnalysis,
    CombinedDiaryEntry, PsychoAnalysis, TherapyProgress, DailyAnalysis,
    UserActivity
)
from messages import get_message, get_button_text
from bot.services.export_service import generate_user_docx # Импорт для export

logger = logging.getLogger(__name__)

class UserProfileService:
    """Сервис для работы с профилем пользователя."""

    @classmethod
    async def get_user_profile_data(cls, user: User) -> Dict[str, Any]:
        """
        Получает данные для отображения основного профиля пользователя.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Словарь с данными профиля.
        """
        try:
            last_entry_date_str = ""
            try:
                @sync_to_async
                def get_last_entry_date():
                    last_entry = DiaryEntry.objects.filter(user=user).order_by('-created_at').first()
                    if last_entry:
                        return last_entry.entry_date
                    return None
                last_entry_date_obj = await get_last_entry_date()
                if last_entry_date_obj:
                    last_entry_date_str = last_entry_date_obj.strftime('%d.%m.%Y')
            except Exception as e:
                logger.error(f"Не удалось получить дату последней записи из DiaryEntry для пользователя {user.telegram_id}: {e}")
                last_entry_date_str = ""
            hobby_str = cls._format_list_for_display(user.hobbies, user.language or 'ru')
            life_facts_str = cls._format_list_for_display(user.life_facts, user.language or 'ru')
            profile_data = {
                'user_telegram_id': user.telegram_id,
                'username': user.username if user.username else '',
                'first_name': user.first_name if user.first_name else '',
                'last_name': user.last_name if user.last_name else '',
                'notifications_status': '✅' if user.notifications_enabled else '❌',
                'auto_analysis_status': '✅' if user.auto_analysis_enabled else '❌',
                'premium_status': '✅' if user.is_premium else '❌',
                'awareness_level': user.awareness_level,
                'token_balance': user.token_balance,
                'registration_date': user.created_at.strftime('%d.%m.%Y') if user.created_at else '',
                'last_entry': last_entry_date_str,
                'hobbies_for_display': hobby_str,
                'life_facts_for_display': life_facts_str,
            }
            has_psychological_data = bool(
                (user.personality_traits and isinstance(user.personality_traits, dict) and user.personality_traits) or
                (user.life_facts and isinstance(user.life_facts, list) and user.life_facts) or
                user.personality_description
            )
            profile_data['has_psychological_data'] = has_psychological_data
            try:
                @sync_to_async
                def _get_last_profile_history_sync():
                    return UserProfileHistory.objects.filter(user=user).order_by('-created_at').first()
                last_profile_history = await _get_last_profile_history_sync()
                if last_profile_history:
                    profile_data['last_analysis_date'] = last_profile_history.created_at.strftime('%d.%m.%Y')
                else:
                    profile_data['last_analysis_date'] = None
            except Exception as e:
                logger.debug(f"Не удалось получить дату последнего анализа профиля: {e}")
                profile_data['last_analysis_date'] = None
            return profile_data
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при получении данных основного профиля для {user.telegram_id}: {e}", exc_info=True)
            return {
                'user_telegram_id': user.telegram_id,
                'username': user.username if user.username else '',
                'first_name': user.first_name if user.first_name else '',
                'last_name': user.last_name if user.last_name else '',
                'notifications_status': '❌',
                'auto_analysis_status': '❌',
                'premium_status': '❌',
                'awareness_level': user.awareness_level,
                'token_balance': user.token_balance,
                'registration_date': user.created_at.strftime('%d.%m.%Y') if user.created_at else '',
                'last_entry': '',
                'hobbies_for_display': get_message('not_specified', user.language or 'ru'),
                'life_facts_for_display': get_message('not_specified', user.language or 'ru'),
                'has_psychological_data': False,
                'last_analysis_date': None,
            }

    @classmethod
    async def get_user_psychology_profile_data(cls, user: User, language: str) -> Dict[str, Any]:
        """
        Получает данные для отображения психологического профиля.

        Args:
            user: Объект пользователя Django.
            language: Язык пользователя.

        Returns:
            Dict[str, Any]: Словарь с данными психологического профиля.
        """
        MAX_DESC_LENGTH = 3500
        MAX_TOTAL_LENGTH = 3580
        try:
            psychology_data = {
                'title': get_message('psychological_portrait', language=language),
                'description': '',
                'has_description': bool(user.personality_description),
                'available_fields': []
            }
            if user.personality_description:
                desc = user.personality_description.strip()
                if len(desc) > MAX_DESC_LENGTH:
                    desc = desc[:MAX_DESC_LENGTH] + get_message(key='description_shortened', language=language)
                psychology_data['description'] = desc
            else:
                psychology_data['description'] = get_message(key='portrait_not_ready', language=language)
            if user.core_values:
                psychology_data['available_fields'].append({'key': 'core_values', 'btn_text': get_button_text('btn_view_values', language)})
            if user.triggers:
                psychology_data['available_fields'].append({'key': 'triggers', 'btn_text': get_button_text('btn_view_triggers', language)})
            if user.strengths:
                psychology_data['available_fields'].append({'key': 'strengths', 'btn_text': get_button_text('btn_view_strengths', language)})
            if user.areas_for_growth:
                psychology_data['available_fields'].append({'key': 'areas_for_growth', 'btn_text': get_button_text('btn_view_growth', language)})
            if user.personality_insights:
                psychology_data['available_fields'].append({'key': 'personality_insights', 'btn_text': get_button_text('btn_view_insights', language)})
            total_msg_len = len(psychology_data['title']) + len(psychology_data['description'])
            if total_msg_len > MAX_TOTAL_LENGTH:
                 psychology_data['description'] = psychology_data['description'][:MAX_TOTAL_LENGTH - len(psychology_data['title'])] + get_message(key='message_truncated', language=language)
            return psychology_data
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при получении данных психологического профиля для {user.telegram_id}: {e}", exc_info=True)
            return {
                'title': get_message('psychological_portrait', language=language),
                'description': get_message('error_generic', language=language),
                'has_description': False,
                'available_fields': []
            }

    @classmethod
    async def get_user_profile_field(cls, user: User, field_key: str, language: str) -> Dict[str, Any]:
        """
        Получает данные для отображения конкретного поля психологического профиля.

        Args:
            user: Объект пользователя Django.
            field_key: Ключ поля (например, 'core_values', 'personality_traits').
            language: Язык пользователя.

        Returns:
            Dict[str, Any]: Словарь с текстом поля и статусом.
        """
        MAX_MESSAGE_LENGTH = 4000
        valid_profile_fields = {
            'personality_traits', 'life_facts', 'hobbies', 'core_values',
            'triggers', 'strengths', 'areas_for_growth', 'personality_insights',
            'practical_patterns', 'aspirations', 'personality_description'
        }

        if field_key not in valid_profile_fields:
            logger.warning(f"[UserProfileService] Получен запрос на отображение недопустимого поля профиля: {field_key}")
            return {
                'success': False,
                'text': get_message('field_not_found', language),
                'error': 'invalid_field'
            }

        field_value = getattr(user, field_key, None)
        if field_value is None:
            return {
                'success': False,
                'text': get_message('field_not_found', language),
                'error': 'field_not_found'
            }

        field_emojis = {
            'core_values': '🎯',
            'triggers': '⚠️',
            'strengths': '💪',
            'areas_for_growth': '🌱',
            'personality_insights': '💡',
            'personality_description': '📝',
            'personality_traits': '🧠',
            'life_facts': '📋',
            'hobbies': '🎨',
            'practical_patterns': '🔄',
            'aspirations': '🌟',
        }
        emoji = field_emojis.get(field_key, '📋')
        field_display_name = f"{emoji} {get_message(f'field_name_{field_key}', language)}"

        field_text = ""
        success = True
        error = None

        try:
            # Импортируем адаптеры для нового формата
            from core.profile_field_utils import field_to_display_format
            
            if isinstance(field_value, list):
                if field_value:
                    # Используем адаптер для корректного отображения
                    # (работает и со старым форматом ["строка"], и с новым [{"value": ...}])
                    formatted_items = field_to_display_format(field_value, field_key)
                    
                    if formatted_items:
                        item_emoji = "\n🔸"
                        formatted_with_emoji = [f"{item_emoji} {item}" for item in formatted_items]
                        joined_items = "".join(formatted_with_emoji)
                        field_text = f"<b>{field_display_name}</b>{joined_items}"
                        
                        # Проверка на максимальную длину
                        if len(field_text) > MAX_MESSAGE_LENGTH:
                            header = f"<b>{field_display_name}</b>"
                            current_length = len(header)
                            truncated_items = []
                            for item_str in formatted_items:
                                item_with_emoji = f"{item_emoji} {item_str}"
                                if current_length + len(item_with_emoji) <= MAX_MESSAGE_LENGTH:
                                    truncated_items.append(item_with_emoji)
                                    current_length += len(item_with_emoji)
                                else:
                                    trunc_indicator = get_message('profile_field_truncated_indicator', language)
                                    if current_length + len(trunc_indicator) <= MAX_MESSAGE_LENGTH:
                                        truncated_items.append(trunc_indicator)
                                    break
                            field_text = header + "".join(truncated_items)
                    else:
                        field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_list', language)
                else:
                    field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_list', language)
            elif isinstance(field_value, dict):
                if field_key == 'personality_insights':
                    if field_value:
                        dict_lines = []
                        for k, v in field_value.items():
                            line = f"💭<b>{k.capitalize()}</b>:\n{v}"
                            dict_lines.append(line)
                        joined_lines = "\n".join(dict_lines)
                        full_text_candidate = f"<b>{field_display_name}</b>\n{joined_lines}"
                        if len(full_text_candidate) > MAX_MESSAGE_LENGTH:
                            header = f"<b>{field_display_name}</b>\n"
                            current_length = len(header)
                            truncated_lines = []
                            for line_str in dict_lines:
                                separator = "\n" if truncated_lines else ""
                                needed_length = len(separator) + len(line_str)
                                if current_length + needed_length <= MAX_MESSAGE_LENGTH:
                                    truncated_lines.append(line_str)
                                    current_length += needed_length
                                else:
                                    trunc_indicator = get_message('profile_field_truncated_indicator', language)
                                    if current_length + len(trunc_indicator) <= MAX_MESSAGE_LENGTH:
                                        truncated_lines.append(trunc_indicator)
                                    break
                            field_text = header + "\n".join(truncated_lines)
                        else:
                            field_text = full_text_candidate
                    else:
                        field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_dict', language)
                else:
                    if field_value:
                        dict_items = [f"  <b>{k}</b>: {v}" for k, v in field_value.items()]
                        joined_items = "".join(dict_items)
                        full_text_candidate = f"<b>{field_display_name}</b>{joined_items}"
                        if len(full_text_candidate) > MAX_MESSAGE_LENGTH:
                            header = f"<b>{field_display_name}</b>"
                            current_length = len(header)
                            truncated_items = []
                            for item_str in dict_items:
                                if current_length + len(item_str) <= MAX_MESSAGE_LENGTH:
                                    truncated_items.append(item_str)
                                    current_length += len(item_str)
                                else:
                                    trunc_indicator = get_message('profile_field_truncated_indicator', language)
                                    if current_length + len(trunc_indicator) <= MAX_MESSAGE_LENGTH:
                                        truncated_items.append(trunc_indicator)
                                    break
                            field_text = header + "".join(truncated_items)
                        else:
                            field_text = full_text_candidate
                    else:
                        field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_dict', language)
            elif isinstance(field_value, str):
                if field_value.strip():
                    full_text_candidate = f"<b>{field_display_name}</b>{field_value.strip()}"
                    if len(full_text_candidate) > MAX_MESSAGE_LENGTH:
                        header = f"<b>{field_display_name}</b>"
                        max_content_length = MAX_MESSAGE_LENGTH - len(header)
                        truncated_content = field_value.strip()[:max_content_length]
                        trunc_indicator = get_message('profile_field_truncated_indicator', language)
                        if len(header) + len(truncated_content) + len(trunc_indicator) <= MAX_MESSAGE_LENGTH:
                            final_content = truncated_content + trunc_indicator
                        else:
                            final_content = truncated_content
                        field_text = header + final_content
                    else:
                        field_text = full_text_candidate
                else:
                    field_text = f"<b>{field_display_name}</b>" + get_message('profile_field_empty_string', language)
            else:
                full_str = str(field_value)
                full_text_candidate = f"<b>{field_display_name}</b>{full_str}"
                if len(full_text_candidate) > MAX_MESSAGE_LENGTH:
                    header = f"<b>{field_display_name}</b>"
                    max_content_length = MAX_MESSAGE_LENGTH - len(header)
                    truncated_content = full_str[:max_content_length]
                    trunc_indicator = get_message('profile_field_truncated_indicator', language)
                    if len(header) + len(truncated_content) + len(trunc_indicator) <= MAX_MESSAGE_LENGTH:
                        final_content = truncated_content + trunc_indicator
                    else:
                        final_content = truncated_content
                    field_text = header + final_content
                else:
                    field_text = full_text_candidate

        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при форматировании поля {field_key} для {user.telegram_id}: {e}", exc_info=True)
            field_text = f"<b>{field_display_name}</b>" + get_message('error_generic', language=language)
            success = False
            error = 'formatting_error'

        return {
            'success': success,
            'text': field_text,
            'error': error
        }

    @classmethod
    async def get_user_transaction_history(cls, user: User, language: str, limit: int = 10) -> Dict[str, Any]:
        """
        Получает историю транзакций и платежей пользователя.

        Args:
            user: Объект пользователя Django.
            language: Язык пользователя.
            limit: Лимит записей.

        Returns:
            Dict[str, Any]: Результат с историей или ошибкой.
        """
        try:
            @sync_to_async
            def get_combined_history():
                token_txs = list(TokenTransaction.objects.filter(user=user).order_by('-created_at')[:limit])
                payments = list(Payment.objects.filter(user=user).order_by('-created_at')[:limit])
                combined = []
                for tx in token_txs:
                    action = "➕" if tx.amount > 0 else "➖"
                    amount = abs(tx.amount)
                    combined.append({
                        'date': tx.created_at,
                        'text': get_message(
                            'transaction_item_token',
                            language,
                            action=action,
                            amount=amount,
                            type=get_message(f'transaction_type_{tx.transaction_type}', language, default=tx.get_transaction_type_display()),
                            description=tx.description or ''
                        )
                    })
                for p in payments:
                    combined.append({
                        'date': p.created_at,
                        'text': get_message(
                            'transaction_item_payment',
                            language,
                            amount_rub=p.amount_rub,
                            type=get_message(f'payment_type_{p.payment_type}', language, default=p.get_payment_type_display()),
                            status=get_message(f'payment_status_{p.status}', language, default=p.get_status_display())
                        )
                    })
                combined.sort(key=lambda x: x['date'], reverse=True)
                return combined[:limit]

            history = await get_combined_history()
            if not history:
                history_msg = get_message('no_transaction_history', language)
            else:
                history_lines = [item['text'] for item in history]
                history_msg = get_message('transaction_history_title', language) + "\n" + "\n".join(history_lines)

            return {
                'success': True,
                'message': history_msg
            }
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при получении истории транзакций для {user.telegram_id}: {e}", exc_info=True)
            return {
                'success': False,
                'message': get_message('error_generic', language=language),
                'error': str(e)
            }

    @classmethod
    async def update_user_profile_field(cls, user: User, field_name: str, new_value: Any) -> Dict[str, Any]:
        """
        Обновляет конкретное поле профиля с валидацией.

        Args:
            user: Объект пользователя Django.
            field_name: Имя поля (например, 'first_name', 'email', 'hobbies').
            new_value: Новое значение.

        Returns:
            Dict[str, Any]: Результат обновления.
        """
        try:
            valid_fields = {
                'first_name': str,
                'email': str,
                'date_of_birth': date,
                'hobbies': list,
                'life_facts': list,
            }
            if field_name not in valid_fields:
                return {'success': False, 'error': 'invalid_field'}
            expected_type = valid_fields[field_name]
            if not isinstance(new_value, expected_type):
                logger.warning(f"[UserProfileService] Неверный тип для поля {field_name}: ожидается {expected_type}, получено {type(new_value)}")
                if expected_type == date and isinstance(new_value, str):
                    try:
                        new_value = datetime.strptime(new_value, '%d.%m.%Y').date()
                    except ValueError:
                        return {'success': False, 'error': 'invalid_format'}
                elif expected_type == list and isinstance(new_value, str):
                    if field_name in ['hobbies', 'life_facts']:
                        new_value = [item.strip() for item in new_value.split(',') if item.strip()]
                    else:
                        return {'success': False, 'error': 'invalid_format'}
                elif expected_type == str and new_value is not None:
                    new_value = str(new_value)
                else:
                    return {'success': False, 'error': 'invalid_format'}
            if field_name == 'email':
                if new_value:
                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                    import re
                    if not re.match(email_pattern, new_value):
                        return {'success': False, 'error': 'invalid_email_format'}

                    # Единый identity policy для конфликтов email (общий для Telegram/MAX/Web).
                    resolution = await IdentityPolicyService.aresolve_email_claim(new_value, requester_user=user)
                    if resolution.status == 'conflict':
                        if getattr(settings, 'EMAIL_MERGE_CONFIRMATION_ENABLED', False):
                            merge_request = await EmailMergeService.acreate_merge_request(
                                requester_user=user,
                                email=new_value,
                                source_platform='telegram',
                                source_context='profile_edit',
                            )
                            return {
                                'success': False,
                                'error': 'email_confirmation_required',
                                'error_code': 'email_confirmation_required',
                                'confirmation_required': True,
                                'merge_request_id': merge_request.id,
                                'confirmation_token': merge_request.confirmation_token,
                                'target_user_id': merge_request.target_user_id,
                            }
                        return {
                            'success': False,
                            'error': 'email_already_exists',
                            'error_code': 'email_already_exists',
                        }
            elif field_name == 'date_of_birth':
                if new_value and new_value > datetime.now().date():
                    return {'success': False, 'error': 'invalid_date_future'}
            elif field_name in ['hobbies', 'life_facts']:
                new_value = cls._filter_remove_items(new_value)
            setattr(user, field_name, new_value)
            update_fields = [field_name]
            await user.asave(update_fields=update_fields)
            logger.debug(f"[UserProfileService] Поле {field_name} пользователя {user.telegram_id} обновлено.")
            return {'success': True}
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при обновлении поля {field_name} для {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    def _filter_remove_items(cls, items_list):
        """
        Фильтрует список, удаляя элементы вида {"remove": ...}.
        """
        if not items_list:
            return []
        return [item for item in items_list if not (isinstance(item, dict) and 'remove' in item)]

    @classmethod
    def _format_list_for_display(cls, items_list, language: str = 'ru', max_length: int = 150):
        """
        Форматирует список для компактного отображения в inline-экранах.

        Args:
            items_list: Список элементов.
            language: Язык для сообщений.
            max_length: Максимальная длина строки.

        Returns:
            str: Отформатированная строка.
        """
        if not isinstance(items_list, list):
            return get_message('not_specified', language)

        filtered_items = cls._filter_remove_items(items_list)
        if not filtered_items:
            return get_message('not_specified', language)

        from core.profile_field_utils import field_to_ai_format

        str_items = field_to_ai_format(filtered_items, 'inline_profile_field')
        if not str_items:
            return get_message('not_specified', language)

        full_str = ', '.join(str_items)
        if len(full_str) > max_length:
            return full_str[:max_length] + '...'
        return full_str

    @classmethod
    async def anonymize_user_account(cls, user: User) -> Dict[str, Any]:
        """
        "Обезличивание" аккаунта пользователя.
        """
        try:
            await TaskCompletionAnalysis.objects.filter(completion__task__user=user).adelete()
            await TaskCompletion.objects.filter(task__user=user).adelete()
            await TherapyTask.objects.filter(user=user).adelete()
            await TherapyProgress.objects.filter(user=user).adelete()
            await DailyAnalysis.objects.filter(combined_entry__user=user).adelete()
            await CombinedDiaryEntry.objects.filter(user=user).adelete()
            await PsychoAnalysis.objects.filter(entry__user=user).adelete()
            await UserActivity.objects.filter(user=user).adelete()
            await DiaryEntry.objects.filter(user=user).adelete()

            user.first_name = ""
            user.last_name = ""
            user.email = ""
            user.username = f"deleted_user_{user.telegram_id}"
            user.timezone = "UTC"
            user.last_entry = None
            user.awareness_level = 1
            user.is_premium = False
            user.last_activity = None
            user.current_calendar_year = 2025
            user.current_calendar_month = 1
            user.notifications_enabled = False
            user.auto_analysis_enabled = False
            user.max_ai_tasks_per_day = 1
            user.personality_description = ''
            user.personality_traits = {}
            user.life_facts = []
            user.hobbies = []
            user.core_values = []
            user.triggers = []
            user.strengths = []
            user.areas_for_growth = []
            user.date_of_birth = None
            user.deleted_at = django_timezone.now()
            user.is_blocked = True
            user.deletion_status = 'anonymized'
            await user.asave()
            logger.info(f"[UserProfileService] Аккаунт пользователя {user.telegram_id} успешно обезличен")
            return {'success': True}
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при обезличивании аккаунта пользователя {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def export_user_data(cls, user: User) -> Dict[str, Any]:
        """
        Экспортирует данные пользователя в .docx.
        """
        try:
            file_path = await generate_user_docx(user)
            return {'success': True, 'file_path': file_path}
        except Exception as e:
            logger.error(f"[UserProfileService] Ошибка при экспорте данных пользователя {user.telegram_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @classmethod
    async def get_referral_link_info(cls, user: User, language: str) -> Dict[str, Any]:
        """
        Получает информацию для отображения реферальной ссылки.
        """
        if not user.referral_link:
            return {
                'success': False,
                'error': 'no_referral_link',
                'message': get_message('no_referral_link_error', language)
            }

        bot_username = os.getenv("TELEGRAM_BOT_USERNAME", settings.BOT_USERNAME) # Используем settings.BOT_USERNAME как fallback
        if not bot_username or bot_username == "your_bot_username":
             logger.warning("TELEGRAM_BOT_USERNAME не установлен. Используется значение по умолчанию.")
        referral_link_url = f"https://t.me/{bot_username}?start={user.referral_link}"
        display_msg = get_message('referral_link_display_text', language)
        share_text_raw = get_message('referral_share_text', language)
        share_text_formatted = share_text_raw.format(url=referral_link_url)
        encoded_text = urllib.parse.quote_plus(share_text_formatted)
        share_url = f"https://t.me/share/url?url={referral_link_url}&text={encoded_text}"
        return {
            'success': True,
            'display_message': display_msg,
            'share_url': share_url,
            'referral_link_url': referral_link_url
        }

async def get_user_profile_data(user: User) -> Dict[str, Any]:
    return await UserProfileService.get_user_profile_data(user)

async def get_user_psychology_profile_data(user: User, language: str) -> Dict[str, Any]:
    return await UserProfileService.get_user_psychology_profile_data(user, language)

async def get_user_profile_field(user: User, field_key: str, language: str) -> Dict[str, Any]:
    return await UserProfileService.get_user_profile_field(user, field_key, language)

async def get_user_transaction_history(user: User, language: str, limit: int = 10) -> Dict[str, Any]:
    return await UserProfileService.get_user_transaction_history(user, language, limit)

async def update_user_profile_field(user: User, field_name: str, new_value: Any) -> Dict[str, Any]:
    return await UserProfileService.update_user_profile_field(user, field_name, new_value)

async def anonymize_user_account(user: User) -> Dict[str, Any]:
    return await UserProfileService.anonymize_user_account(user)

async def export_user_data(user: User) -> Dict[str, Any]:
    return await UserProfileService.export_user_data(user)

async def get_referral_link_info(user: User, language: str) -> Dict[str, Any]:
    return await UserProfileService.get_referral_link_info(user, language)
