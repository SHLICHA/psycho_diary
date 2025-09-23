"""
Handlers для прогресса
"""
import logging
from datetime import date, timedelta
from django.db.models.functions import TruncDate
from aiogram import F, Router
from aiogram.types import CallbackQuery
from asgiref.sync import sync_to_async

from diary.models import WeeklyAnalysis, DiaryEntry, TaskCompletion
from messages import get_message
from bot.keyboards import get_back_keyboard, get_weekly_navigation_keyboard, get_progress_keyboard_without_weekly, get_progress_keyboard_with_weekly
from bot.utils.message_utils import safe_edit_message_text

logger = logging.getLogger(__name__)
router = Router()

async def _has_weekly_analyses(user) -> bool:
    """Проверяет, есть ли у пользователя хотя бы один недельный анализ."""
    try:
        @sync_to_async
        def _check_sync():
            return WeeklyAnalysis.objects.filter(user=user).exists()
        return await _check_sync()
    except Exception as e:
        logger.error(f"Ошибка при проверке наличия недельных анализов для пользователя {user.id}: {e}")
        return False

async def _get_user_statistics(user) -> dict:
    """
    Получает или вычисляет актуальную статистику пользователя.
    """
    logger.debug(f"[_get_user_statistics] Получение статистики для пользователя {user.id}")
    stats = {
        'entries_count': 0,
        'tasks_completed': 0,
        'streak_days': 0,
    }
    try:
        @sync_to_async
        def _count_entries():
            return DiaryEntry.objects.filter(user=user).count()
        stats['entries_count'] = await _count_entries()
        logger.debug(f"[_get_user_statistics] Записей: {stats['entries_count']}")
        @sync_to_async
        def _count_tasks():
            return TaskCompletion.objects.filter(task__user=user).count()
        stats['tasks_completed'] = await _count_tasks()
        logger.debug(f"[_get_user_statistics] Заданий выполнено: {stats['tasks_completed']}")
        @sync_to_async
        def _count_active_days():

            result = DiaryEntry.objects.filter(user=user).annotate(
                entry_date=TruncDate('created_at')
            ).values('entry_date').distinct().count()
            return result
        stats['streak_days'] = await _count_active_days()
        logger.debug(f"[_get_user_statistics] Дней с записями (упр. серия): {stats['streak_days']}")
    except Exception as e:
        logger.error(f"[_get_user_statistics] Ошибка при подсчете статистики для пользователя {user.id}: {e}")
    return stats

async def _get_latest_weekly_analysis(user):
    """Получает последний недельный анализ пользователя."""
    try:
        @sync_to_async
        def _get_sync():
            return WeeklyAnalysis.objects.filter(user=user).order_by('-week_start_date').first()
        return await _get_sync()
    except Exception as e:
        logger.error(f"Ошибка при получении последнего недельного анализа для пользователя {user.id}: {e}")
        return None

@router.callback_query(F.data == "progress")
async def show_progress(callback: CallbackQuery, user, language: str):
    """Показ прогресса."""
    logger.info(f"[show_progress] Запрос от пользователя {user.id}")
    try:
        awareness_level_current = user.awareness_level
        logger.debug(f"[show_progress] Текущий уровень осознанности: {awareness_level_current}")
        user_stats = await _get_user_statistics(user)
        total_entries = user_stats['entries_count']
        tasks_completed = user_stats['tasks_completed']
        streak_days = user_stats['streak_days']
        logger.debug(f"[show_progress] Статистика: записи={total_entries}, задания={tasks_completed}, серия={streak_days}")
        progress_msg = get_message('progress_title', language).format(
            awareness_level=awareness_level_current,
            entries_count=total_entries,
            tasks_completed=tasks_completed,
            streak_days=streak_days
        )
        logger.debug(f"[show_progress] Сообщение сформировано: {progress_msg[:50]}...")
        has_analyses = await _has_weekly_analyses(user)
        reply_markup = get_progress_keyboard_with_weekly(language) if has_analyses else get_progress_keyboard_without_weekly(language)
        logger.debug(f"[show_progress] Клавиатура: {'с аналитикой' if has_analyses else 'без аналитики'}")
        success = await safe_edit_message_text(
            message=callback.message,
            text=progress_msg,
            reply_markup=reply_markup
        )
        if success:
            logger.info(f"[show_progress] Сообщение успешно обновлено для пользователя {user.id}")
        else:
            logger.warning(f"[show_progress] Не удалось обновить сообщение для пользователя {user.id}")

        await callback.answer()

    except Exception as e:
        logger.error(f"[show_progress] Критическая ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=callback.message,
            text=error_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()

@router.callback_query(F.data == "weekly_progress_list")
async def show_weekly_progress_list(callback: CallbackQuery, user, language: str):
    """Показывает последний недельный анализ."""
    logger.info(f"[show_weekly_progress_list] Запрос от пользователя {user.id}")
    try:
        latest = await _get_latest_weekly_analysis(user)
        if not latest:
            no_analysis_msg = get_message('weekly_analysis_not_found', language)
            logger.info(f"[show_weekly_progress_list] Нет анализов для пользователя {user.id}")
            success = await safe_edit_message_text(
                message=callback.message,
                text=no_analysis_msg,
                reply_markup=get_progress_keyboard_without_weekly(language)
            )
            if success:
                logger.debug(f"[show_weekly_progress_list] Сообщение 'нет анализа' отправлено.")
            await callback.answer()
            return
        logger.debug(f"[show_weekly_progress_list] Найден анализ ID {latest.id}, показываем.")
        await _show_weekly_analysis_page(callback.message, user, latest.week_start_date, language)
        await callback.answer()    
    except Exception as e:
        logger.error(f"[show_weekly_progress_list] Критическая ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=callback.message,
            text=error_msg,
            reply_markup=get_progress_keyboard_without_weekly(language)
        )
        await callback.answer()


@router.callback_query(F.data.startswith("weekly_nav:"))
async def navigate_weekly_analysis(callback: CallbackQuery, user, language: str):
    """Навигация между недельными анализами."""
    logger.info(f"[navigate_weekly_analysis] Callback от пользователя {user.id}: {callback.data}")
    try:
        parts = callback.data.split(":")
        if len(parts) != 2:
            raise ValueError("Некорректный формат callback_data для навигации")
        week_start_iso = parts[1]
        week_start_date = date.fromisoformat(week_start_iso)
        logger.debug(f"[navigate_weekly_analysis] Навигация к неделе: {week_start_date}")
        await _show_weekly_analysis_page(callback.message, user, week_start_date, language)
        await callback.answer()
    except (ValueError, Exception) as e:
        logger.error(f"[navigate_weekly_analysis] Ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=callback.message,
            text=error_msg,
            reply_markup=get_progress_keyboard_without_weekly(language)
        )
        await callback.answer()


async def _show_weekly_analysis_page(message, user, week_start_date: date, language: str):
    """Вспомогательная функция для отображения анализа конкретной недели."""
    logger.debug(f"[_show_weekly_analysis_page] Попытка показа анализа для недели {week_start_date} пользователя {user.id}")
    try:
        week_end_date = week_start_date + timedelta(days=6)
        logger.debug(f"[_show_weekly_analysis_page] Конец недели: {week_end_date}")
        
        @sync_to_async
        def get_analysis_sync():
            try:
                logger.debug(f"[_show_weekly_analysis_page] Поиск анализа для user_id={user.id}, week_start_date={week_start_date}")
                return WeeklyAnalysis.objects.get(user=user, week_start_date=week_start_date)
            except WeeklyAnalysis.DoesNotExist:
                logger.debug(f"[_show_weekly_analysis_page] Анализ для недели {week_start_date} не найден.")
                return None
        analysis = await get_analysis_sync()
        if not analysis:
            no_data_msg = get_message('weekly_analysis_not_found', language)
            logger.info(f"[_show_weekly_analysis_page] Анализ не найден, отправляем сообщение.")
            await safe_edit_message_text(
                message=message,
                text=no_data_msg,
                reply_markup=get_weekly_navigation_keyboard(language, week_start_date)
            )
            return
        logger.debug(f"[_show_weekly_analysis_page] Формируем сообщение для анализа ID {analysis.id}")
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
        final_msg_parts = [part for part in [title_msg.strip(), summary_part.strip(), stats_part.strip()] if part]
        final_msg = "\n\n".join(final_msg_parts) if final_msg_parts else get_message('weekly_analysis_no_data', language)
        logger.debug(f"[_show_weekly_analysis_page] Финальное сообщение сформировано ({len(final_msg)} символов).")
        success = await safe_edit_message_text(
            message=message,
            text=final_msg,
            reply_markup=get_weekly_navigation_keyboard(language, week_start_date)
        )
        if success:
            logger.info(f"[_show_weekly_analysis_page] Сообщение анализа успешно обновлено.")
        else:
            logger.warning(f"[_show_weekly_analysis_page] Не удалось обновить сообщение анализа.")
    except Exception as e:
        logger.error(f"[_show_weekly_analysis_page] Критическая ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=message,
            text=error_msg,
            reply_markup=get_progress_keyboard_without_weekly(language)
        )
