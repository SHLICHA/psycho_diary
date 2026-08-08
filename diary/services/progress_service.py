# /diary/services/progress_service.py
"""
Сервис для работы с прогрессом пользователя.
Выносит бизнес-логику из хендлеров Telegram.
"""

import logging
import pytz
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Dict, Any, List, Optional

from asgiref.sync import sync_to_async
from django.db.models import Q
from django.db.models.functions import TruncDate

from diary.models import WeeklyAnalysis, DiaryEntry, TaskCompletion, TherapyTask, CombinedDiaryEntry
from users.models import User
from messages import get_message
from bot.utils.diary_utils import get_recoverable_gap_info, attempt_restore_streak # Импортируем утилиты, которые тоже содержат бизнес-логику

logger = logging.getLogger(__name__)

class ProgressService:
    """Сервис для работы с прогрессом пользователя."""

    @classmethod
    async def get_user_progress_statistics(cls, user: User) -> Dict[str, Any]:
        """
        Получает или вычисляет актуальную статистику пользователя.

        Args:
            user: Объект пользователя Django.

        Returns:
            Dict[str, Any]: Словарь со статистикой.
        """
        logger.debug(f"[ProgressService] Получение статистики для пользователя {user.id}")
        stats = {
            'entries_count': 0,
            'tasks_completed': 0,
            'tasks_assigned': 0,
            'tasks_completion_percentage': 0.0,
            'streak_days': 0,
            'has_entry_today': False,
            'streak_reset_warning': "",
        }
        try:
            # --- Подсчет записей ---
            @sync_to_async
            def _count_entries():
                return DiaryEntry.objects.filter(user=user, is_recovered_streak=False).count()
            stats['entries_count'] = await _count_entries()

            # --- Подсчет выполненных заданий ---
            @sync_to_async
            def _count_tasks_completed():
                return TaskCompletion.objects.filter(task__user=user).count()
            stats['tasks_completed'] = await _count_tasks_completed()

            # --- Подсчет назначенных заданий ---
            @sync_to_async
            def _count_tasks_assigned():
                return TherapyTask.objects.filter(user=user).count()
            stats['tasks_assigned'] = await _count_tasks_assigned()

            # --- Процент выполнения заданий ---
            if stats['tasks_assigned'] > 0:
                stats['tasks_completion_percentage'] = (stats['tasks_completed'] / stats['tasks_assigned']) * 100.0

            # --- Проверка записи за сегодня ---
            @sync_to_async
            def _check_entry_today():
                user_timezone_str = user.timezone or 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except Exception:
                    logger.warning(f"[ProgressService] Неверный часовой пояс для пользователя {user.id}: {user_timezone_str}. Используем UTC.")
                    user_tz = pytz.UTC
                now_user_tz = datetime.now(user_tz)
                today_user_date = now_user_tz.date()
                start_of_day_user_tz = datetime.combine(today_user_date, dtime.min)
                start_of_day_user_tz = user_tz.localize(start_of_day_user_tz)
                end_of_day_user_tz = datetime.combine(today_user_date, dtime.max)
                end_of_day_user_tz = user_tz.localize(end_of_day_user_tz)
                start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
                end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)
                return DiaryEntry.objects.filter(
                    user=user,
                    created_at__gte=start_of_day_utc,
                    created_at__lte=end_of_day_utc
                ).exists()
            stats['has_entry_today'] = await _check_entry_today()

            # --- Подсчет текущей серии ---
            @sync_to_async
            def _calculate_current_streak():
                user_timezone_str = user.timezone or 'UTC'
                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except Exception:
                    logger.warning(f"[ProgressService] Неверный часовой пояс для пользователя {user.id}: {user_timezone_str}. Используем UTC.")
                    user_tz = pytz.UTC
                entry_dates_qs = DiaryEntry.objects.filter(user=user).annotate(
                    entry_date=TruncDate('created_at', tzinfo=user_tz)
                ).values('entry_date').order_by('-entry_date').distinct()
                entry_dates = [item['entry_date'] for item in entry_dates_qs]
                if not entry_dates:
                    return 0
                today_user_date = datetime.now(user_tz).date()
                streak = 0
                expected_date = today_user_date
                for entry_date in entry_dates:
                    if entry_date == expected_date:
                        streak += 1
                        expected_date -= timedelta(days=1)
                    elif entry_date < expected_date:
                        break
                return streak
            stats['streak_days'] = await _calculate_current_streak()

            # --- Предупреждение о сбросе серии ---
            if not stats['has_entry_today'] and stats['streak_days'] > 0:
                 stats['streak_reset_warning'] = get_message('streak_reset_warning', user.language or 'ru', streak_days=stats['streak_days'])

        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при подсчете статистики для пользователя {user.id}: {e}", exc_info=True)
        return stats

    @classmethod
    async def get_latest_weekly_analysis(cls, user: User) -> Optional[WeeklyAnalysis]:
        """Получает последний недельный анализ пользователя."""
        try:
            @sync_to_async
            def _get_sync():
                return WeeklyAnalysis.objects.filter(user=user).order_by('-week_start_date').first()
            return await _get_sync()
        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при получении последнего недельного анализа для пользователя {user.id}: {e}")
            return None

    @classmethod
    async def get_has_weekly_analyses(cls, user: User) -> bool:
        """Проверяет, есть ли у пользователя хотя бы один недельный анализ."""
        try:
            @sync_to_async
            def _check_sync():
                return WeeklyAnalysis.objects.filter(user=user).exists()
            return await _check_sync()
        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при проверке наличия недельных анализов для пользователя {user.id}: {e}")
            return False

    @classmethod
    async def get_weekly_analysis_for_date(cls, user: User, week_start_date: date) -> Optional[WeeklyAnalysis]:
        """Получает недельный анализ для конкретной даты начала недели."""
        try:
            @sync_to_async
            def _get_sync():
                return WeeklyAnalysis.objects.filter(user=user, week_start_date=week_start_date).first()
            return await _get_sync()
        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при получении недельного анализа за {week_start_date} для пользователя {user.id}: {e}")
            return None

    @classmethod
    async def get_all_weekly_analysis_dates(cls, user: User) -> List[date]:
        """Получает список дат начала недель, для которых есть анализ."""
        try:
            @sync_to_async
            def _get_dates_sync():
                return list(WeeklyAnalysis.objects.filter(user=user).order_by('-week_start_date').values_list('week_start_date', flat=True))
            return await _get_dates_sync()
        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при получении дат недельных анализов для пользователя {user.id}: {e}")
            return []

    @classmethod
    async def get_detailed_weekly_changes(cls, user: User, language: str) -> Dict[str, Any]:
        """Подготавливает данные для отображения подробных изменений из последнего WeeklyAnalysis."""
        latest_analysis = await cls.get_latest_weekly_analysis(user)
        if not latest_analysis:
            return {'success': False, 'message': get_message('weekly_analysis_not_found', language), 'error': 'no_analysis'}

        changes_text = ""
        if latest_analysis.profile_changes_summary:
            changes_summary = latest_analysis.profile_changes_summary
            summary = changes_summary.get('summary', '')
            key_changes = changes_summary.get('key_changes', [])
            stable_traits = changes_summary.get('stable_traits', [])

            parts = []
            if summary:
                parts.append(get_message('changes', language, summary=summary))
            if key_changes:
                changes_list = "\n".join([f"🔸 {change}" for change in key_changes])
                parts.append(get_message('key_changes', language, changes_list=changes_list))
            if stable_traits:
                stable_list = "\n".join([f"🔹 {trait}" for trait in stable_traits])
                parts.append(get_message('stable_traits', language, stable_list=stable_list))

            if parts:
                changes_text = "\n\n".join(parts)
        else:
             changes_text = get_message('no_profile_changes_found', language)

        week_start_date = latest_analysis.week_start_date.strftime("%d.%m.%Y")
        week_end_date = (latest_analysis.week_start_date + timedelta(days=6)).strftime("%d.%m.%Y")
        details_msg = get_message(
            'detailed_progress',
            language,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            changes_text=changes_text)

        return {'success': True, 'message': details_msg, 'error': None}

    @classmethod
    async def check_restore_streak_availability(cls, user: User) -> Dict[str, Any]:
        """Проверяет, доступно ли восстановление серии и возвращает возможные даты."""
        recoverable_dates = await get_recoverable_gap_info(user)
        if recoverable_dates:
            return {'available': True, 'dates': recoverable_dates}
        else:
            return {'available': False, 'dates': []}

    @classmethod
    async def attempt_streak_restoration(cls, user: User, target_date: date, language: str) -> Dict[str, Any]:
        """Пытается восстановить серию за указанную дату."""
        result = await attempt_restore_streak(user, target_date)
        message_key = result['message_key']
        message_kwargs = result.get('message_kwargs', {})
        message_text = get_message(message_key, language, **message_kwargs)
        return {
            'success': result.get('awarded', False), # Предполагаем, что 'awarded' означает успех операции
            'message': message_text,
            'updated_date': result.get('updated_date'),
            'error': result.get('error') # Если в attempt_restore_streak возвращается 'error'
        }

    @classmethod
    async def format_weekly_analysis_for_display(cls, analysis: WeeklyAnalysis, user: User, language: str) -> Dict[str, Any]:
        """Форматирует текст анализа недели для отображения в Telegram."""
        try:
            week_start_date = analysis.week_start_date
            week_end_date = week_start_date + timedelta(days=6)

            title_msg = get_message('weekly_analysis_title', language).format(
                week_start_date=week_start_date.strftime("%d.%m.%Y"),
                week_end_date=week_end_date.strftime("%d.%m.%Y"),
                awareness_level=analysis.consolidated_user_profile.get('awareness_level', user.awareness_level)
                                 if isinstance(analysis.consolidated_user_profile, dict) else user.awareness_level
            )
            summary_part = ""
            if analysis.summary_text:
                summary_part = get_message('weekly_analysis_summary', language).format(
                    summary_text=analysis.summary_text
                )
            stats_part = ""
            stats = analysis.statistics
            if isinstance(stats, dict):
                stats_part = get_message('weekly_analysis_stats', language).format(
                    total_entries=stats.get('total_entries', 'N/A'),
                    streak_days_current=stats.get('streak_days_current', 'N/A'),
                    avg_mood_score=f"{stats.get('avg_mood_score', 0.0):.2f}",
                    tasks_assigned=stats.get('tasks_assigned', 'N/A'),
                    tasks_completed=stats.get('tasks_completed', 'N/A')
                )
            # Собираем финальное сообщение
            final_msg_parts = [part for part in [title_msg.strip(), summary_part.strip(), stats_part.strip()] if part]
            final_msg = "\n\n".join(final_msg_parts) if final_msg_parts else get_message('weekly_analysis_no_data', language)

            return {'success': True, 'formatted_text': final_msg, 'error': None}

        except Exception as e:
            logger.error(f"[ProgressService] Ошибка при форматировании анализа недели {analysis.week_start_date} для отображения: {e}", exc_info=True)
            return {'success': False, 'formatted_text': get_message('error_generic', language), 'error': str(e)}

    @classmethod
    async def build_progress_screen_view(cls, user: User, language: str) -> Dict[str, Any]:
        """Собирает полный payload главного экрана прогресса."""
        from bot.keyboards import (
            get_progress_keyboard_with_weekly,
            get_progress_keyboard_without_weekly,
        )

        user_stats = await cls.get_user_progress_statistics(user)
        latest_weekly_analysis = await cls.get_latest_weekly_analysis(user)

        comparison_text = ""
        if latest_weekly_analysis and latest_weekly_analysis.comparison_with_previous:
            comparison_data = latest_weekly_analysis.comparison_with_previous
            progress_comment = comparison_data.get('progress_comment')
            mood_comparison = comparison_data.get('mood_comparison')
            parts = []
            if progress_comment:
                parts.append(progress_comment)
            if mood_comparison:
                if not progress_comment:
                    parts.insert(0, mood_comparison)
                else:
                    parts.append(f"({mood_comparison})")
            if parts:
                comparison_text = f"\n\n📊 <b>Динамика:</b> {' '.join(parts)}"

        no_analysis_info = ""
        if not latest_weekly_analysis:
            no_analysis_info = get_message('weekly_analysis_not_performed_yet', language)

        progress_msg = get_message(
            'progress_title',
            language,
            awareness_level=user.awareness_level,
            entries_count=user_stats['entries_count'],
            tasks_completed=user_stats['tasks_completed'],
            tasks_assigned=user_stats['tasks_assigned'],
            tasks_completion_percentage=user_stats['tasks_completion_percentage'],
            streak_days=user_stats['streak_days'],
            streak_reset_warning=user_stats['streak_reset_warning'],
        )
        progress_msg += no_analysis_info
        progress_msg += comparison_text

        has_analyses = await cls.get_has_weekly_analyses(user)
        restore_check_result = await cls.check_restore_streak_availability(user)
        show_restore_btn = restore_check_result['available']
        if has_analyses:
            reply_markup = get_progress_keyboard_with_weekly(
                language, show_restore_button=show_restore_btn
            )
        else:
            reply_markup = get_progress_keyboard_without_weekly(
                language, show_restore_button=show_restore_btn
            )

        return {
            'success': True,
            'text': progress_msg,
            'reply_markup': reply_markup,
            'has_analyses': has_analyses,
            'show_restore_button': show_restore_btn,
            'stats': user_stats,
        }

    @classmethod
    async def build_weekly_analysis_page_view(
        cls,
        user: User,
        week_start_date: date,
        language: str,
    ) -> Dict[str, Any]:
        """Payload страницы недельного анализа."""
        from bot.keyboards import (
            get_weekly_navigation_keyboard,
            get_progress_keyboard_without_weekly,
        )

        analysis = await cls.get_weekly_analysis_for_date(user, week_start_date)
        if not analysis:
            return {
                'success': True,
                'mode': 'not_found',
                'text': get_message('weekly_analysis_not_found', language),
                'reply_markup': get_weekly_navigation_keyboard(language, week_start_date),
            }

        format_result = await cls.format_weekly_analysis_for_display(analysis, user, language)
        if not format_result.get('success'):
            return {
                'success': False,
                'mode': 'error',
                'text': get_message('error_generic', language),
                'reply_markup': get_progress_keyboard_without_weekly(language),
                'error': format_result.get('error'),
            }

        return {
            'success': True,
            'mode': 'analysis',
            'text': format_result['formatted_text'],
            'reply_markup': get_weekly_navigation_keyboard(language, week_start_date),
        }

    @classmethod
    async def build_restore_streak_request_view(
        cls,
        user: User,
        language: str,
    ) -> Dict[str, Any]:
        """Payload экрана запроса восстановления streak."""
        from bot.keyboards import get_restore_date_selection_keyboard, get_back_keyboard

        restore_check_result = await cls.check_restore_streak_availability(user)
        if not restore_check_result.get('available'):
            return {
                'success': True,
                'mode': 'unavailable',
                'available': False,
                'dates': [],
            }

        recoverable_dates = restore_check_result.get('dates') or []
        if len(recoverable_dates) not in (1, 2):
            return {
                'success': False,
                'mode': 'error',
                'text': get_message('error_generic', language),
                'reply_markup': get_back_keyboard(language),
                'error': 'unexpected_recoverable_dates_count',
            }

        return {
            'success': True,
            'mode': 'select_date',
            'available': True,
            'dates': recoverable_dates,
            'text': get_message('restore_streak_info', language, tokens_cost=10),
            'reply_markup': get_restore_date_selection_keyboard(language, recoverable_dates),
        }

    @classmethod
    async def confirm_streak_restoration_use_case(
        cls,
        user: User,
        target_date: date,
        language: str,
    ) -> Dict[str, Any]:
        """
        Use case подтверждения восстановления streak за конкретную дату.

        Returns:
            ok, alert_text, refresh_progress, notify_mode ('message' | 'alert')
        """
        restore_check_result = await cls.check_restore_streak_availability(user)
        if (
            not restore_check_result.get('available')
            or target_date not in (restore_check_result.get('dates') or [])
        ):
            return {
                'ok': False,
                'alert_text': get_message('restore_streak_unavailable', language),
                'refresh_progress': True,
                'notify_mode': 'message',
            }

        restoration_result = await cls.attempt_streak_restoration(user, target_date, language)
        return {
            'ok': restoration_result.get('success', False),
            'alert_text': restoration_result['message'],
            'refresh_progress': True,
            'notify_mode': 'alert',
        }

# Удобные функции для импорта в хендлеры
async def get_user_progress_statistics(user: User) -> Dict[str, Any]:
    return await ProgressService.get_user_progress_statistics(user)

async def get_latest_weekly_analysis(user: User) -> Optional[WeeklyAnalysis]:
    return await ProgressService.get_latest_weekly_analysis(user)

async def get_has_weekly_analyses(user: User) -> bool:
    return await ProgressService.get_has_weekly_analyses(user)

async def get_weekly_analysis_for_date(user: User, week_start_date: date) -> Optional[WeeklyAnalysis]:
    return await ProgressService.get_weekly_analysis_for_date(user, week_start_date)

async def get_all_weekly_analysis_dates(user: User) -> List[date]:
    return await ProgressService.get_all_weekly_analysis_dates(user)

async def get_detailed_weekly_changes(user: User, language: str) -> Dict[str, Any]:
    return await ProgressService.get_detailed_weekly_changes(user, language)

async def check_restore_streak_availability(user: User) -> Dict[str, Any]:
    return await ProgressService.check_restore_streak_availability(user)

async def attempt_streak_restoration(user: User, target_date: date, language: str) -> Dict[str, Any]:
    return await ProgressService.attempt_streak_restoration(user, target_date, language)

async def format_weekly_analysis_for_display(analysis: WeeklyAnalysis, user: User, language: str) -> Dict[str, Any]:
    return await ProgressService.format_weekly_analysis_for_display(analysis, user, language)

async def build_progress_screen_view(user: User, language: str) -> Dict[str, Any]:
    return await ProgressService.build_progress_screen_view(user, language)

async def build_weekly_analysis_page_view(
    user: User,
    week_start_date: date,
    language: str,
) -> Dict[str, Any]:
    return await ProgressService.build_weekly_analysis_page_view(user, week_start_date, language)

async def build_restore_streak_request_view(user: User, language: str) -> Dict[str, Any]:
    return await ProgressService.build_restore_streak_request_view(user, language)

async def confirm_streak_restoration_use_case(
    user: User,
    target_date: date,
    language: str,
) -> Dict[str, Any]:
    return await ProgressService.confirm_streak_restoration_use_case(user, target_date, language)
