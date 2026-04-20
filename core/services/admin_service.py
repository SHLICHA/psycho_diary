# /core/services/admin_service.py
"""
Сервис для административных операций.
Универсальный сервис: работает и для бота, и для API.

Отвечает за:
- Проверку прав администратора
- Рассылку сообщений
- Сбор статистики системы
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import timedelta
from collections import Counter

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from django.db.models import Count

from users.models import User, Payment
from diary.models import DiaryEntry, AnalysisRating

logger = logging.getLogger(__name__)


class AdminService:
    """Сервис для административных операций."""

    @staticmethod
    def _get_users_for_broadcast_sync(is_important: bool = False) -> List[Tuple[int, str]]:
        """Синхронная выборка пользователей для thread-sensitive вызова из async-кода."""
        base_filter = {
            'is_blocked': False,
            'deletion_status': 'active',
            'deleted_at__isnull': True,
        }

        if not is_important:
            base_filter['notifications_enabled'] = True

        return list(
            User.objects.filter(**base_filter).values_list('telegram_id', 'language')
        )

    @staticmethod
    def _get_admin_stats_sync() -> Dict[str, Any]:
        """Собирает статистику синхронно, чтобы использовать один DB connection в тестах и async-вызовах."""
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        stats: Dict[str, Any] = {}

        active_in_system_users = User.objects.filter(deletion_status='active', is_superuser=False)
        active_users_query = active_in_system_users.filter(is_blocked=False)

        stats['total_users'] = active_in_system_users.count()
        stats['active_users'] = active_users_query.count()
        stats['active_users_last_7_days'] = active_users_query.filter(last_activity__gte=seven_days_ago).count()
        stats['blocked_users'] = active_in_system_users.filter(is_blocked=True).count()

        premium_users = 0
        for user in active_users_query.iterator():
            if user.is_premium_active():
                premium_users += 1

        stats['premium_users'] = premium_users
        stats['users_with_tokens'] = active_users_query.filter(token_balance__gt=0).count()
        stats['users_with_auto_analysis_enabled'] = active_users_query.filter(auto_analysis_enabled=True).count()
        stats['users_completed_onboarding'] = active_users_query.filter(is_onboarding_completed=True).count()

        active_user_ids = list(active_users_query.values_list('id', flat=True))
        entry_query = DiaryEntry.objects.filter(user_id__in=active_user_ids)
        stats['users_with_entries'] = entry_query.values('user_id').distinct().count()

        timezone_counts = Counter(active_users_query.values_list('timezone', flat=True))
        stats['top_timezones'] = timezone_counts.most_common(10)

        all_ratings = AnalysisRating.objects.all()
        stats['total_ratings'] = all_ratings.count()

        rating_counts = all_ratings.values('rating').annotate(count=Count('rating')).order_by('rating')
        distribution = {i: 0 for i in range(1, 6)}
        for item in rating_counts:
            distribution[item['rating']] = item['count']
        stats['rating_distribution'] = distribution

        successful_payments = Payment.objects.filter(status='succeeded')
        stats['subscriptions_30_count'] = successful_payments.filter(payment_type='subscription_month').count()
        stats['subscriptions_year_count'] = successful_payments.filter(payment_type='subscription_year').count()
        stats['tokens_10_count'] = successful_payments.filter(payment_type='tokens_10').count()
        stats['tokens_50_count'] = successful_payments.filter(payment_type='tokens_50').count()
        stats['tokens_100_count'] = successful_payments.filter(payment_type='tokens_100').count()
        stats['tokens_200_count'] = successful_payments.filter(payment_type='tokens_200').count()
        stats['tokens_500_count'] = successful_payments.filter(payment_type='tokens_500').count()
        stats['custom_tokens_count'] = successful_payments.filter(payment_type='tokens_custom').count()

        stats['total_entries'] = entry_query.count()
        stats['real_entries'] = entry_query.filter(is_recovered_streak=False).count()
        stats['recovered_entries'] = entry_query.filter(is_recovered_streak=True).count()

        return stats

    @staticmethod
    def is_developer(telegram_id: int) -> bool:
        """
        Единая проверка: является ли пользователь разработчиком.
        Используется во всех сервисах и хендлерах.

        Args:
            telegram_id: Telegram ID пользователя.

        Returns:
            bool: True если разработчик.
        """
        dev_chat_id_str = settings.DEVELOPER_CHAT_ID
        if not dev_chat_id_str:
            return False
        try:
            dev_chat_id = int(dev_chat_id_str)
            return telegram_id == dev_chat_id
        except (ValueError, TypeError):
            return False

    def is_admin(self, telegram_id: int) -> bool:
        """
        Проверяет, является ли пользователь администратором.
        Алиас для is_developer — для обратной совместимости.

        Args:
            telegram_id: Telegram ID пользователя.

        Returns:
            bool: True если администратор.
        """
        return self.is_developer(telegram_id)

    async def get_users_for_broadcast(self, is_important: bool = False) -> List[Tuple[int, str]]:
        """
        Получает список пользователей для рассылки.

        Args:
            is_important: True для важной рассылки (всем активным), False для обычной (только с уведомлениями).

        Returns:
            List[Tuple[int, str]]: Список кортежей (telegram_id, language).
        """
        users = await sync_to_async(
            self._get_users_for_broadcast_sync,
            thread_sensitive=True,
        )(
            is_important
        )
        return users

    async def send_broadcast_message(
        self,
        bot,
        users: List[Tuple[int, str]],
        message_text: str,
        is_important: bool = False
    ) -> Dict[str, int]:
        """
        Отправляет массовую рассылку.

        Args:
            bot: Экземпляр бота для отправки.
            users: Список пользователей (telegram_id, language).
            message_text: Текст сообщения.
            is_important: Важная рассылка или нет.

        Returns:
            Dict[str, int]: {'success': N, 'failed': N}
        """
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from messages import get_message, get_button_text

        success = 0
        failed = 0

        for user_id, user_lang in users:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=get_button_text('btn_main_menu', user_lang),
                        callback_data="main_menu"
                    )]
                ])

                prefix = "🔴 " if is_important else "🔵 "
                broadcast_prefix = get_message('broadcast_prefix', user_lang)

                await bot.send_message(
                    chat_id=user_id,
                    text=f"{prefix}{broadcast_prefix}\n\n{message_text}",
                    reply_markup=kb
                )
                success += 1

            except Exception as e:
                if "bot was blocked" in str(e).lower():
                    await User.mark_blocked(user_id)
                failed += 1

        return {'success': success, 'failed': failed}

    async def get_admin_stats(self) -> Dict[str, Any]:
        """
        Получает полную статистику системы.

        Returns:
            Dict[str, Any]: Словарь со статистикой.
        """
        return await sync_to_async(self._get_admin_stats_sync, thread_sensitive=True)()


admin_service = AdminService()
