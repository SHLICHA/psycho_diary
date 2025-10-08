"""
Handlers для прогресса
"""
import logging
import pytz

from datetime import date, datetime, timedelta
from datetime import time as dtime
from django.db.models.functions import TruncDate
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InputFile, BufferedInputFile
from asgiref.sync import sync_to_async

from diary.models import WeeklyAnalysis, DiaryEntry, TaskCompletion, TherapyTask
from messages import get_message
from bot.keyboards import (
    get_back_keyboard,
    get_weekly_navigation_keyboard,
    get_progress_keyboard_without_weekly,
    get_progress_keyboard_with_weekly,
    get_single_button_keyboard
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.mood_chart import generate_mood_chart_image

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
        'tasks_assigned': 0,
        'tasks_completion_percentage': 0.0,
        'streak_days': 0,
        'has_entry_today': False,
        'streak_reset_warning': "",
    }
    try:
        @sync_to_async
        def _count_entries():
            return DiaryEntry.objects.filter(user=user).count()
        stats['entries_count'] = await _count_entries()
        @sync_to_async
        def _count_tasks_completed():
            return TaskCompletion.objects.filter(task__user=user).count()
        stats['tasks_completed'] = await _count_tasks_completed()
        @sync_to_async
        def _count_tasks_assigned():
            return TherapyTask.objects.filter(user=user).count()
        stats['tasks_assigned'] = await _count_tasks_assigned()
        if stats['tasks_assigned'] > 0:
            stats['tasks_completion_percentage'] = (stats['tasks_completed'] / stats['tasks_assigned']) * 100.0
        @sync_to_async
        def _check_entry_today():
            
            from datetime import time as dtime
            user_timezone_str = user.timezone or 'UTC'
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except Exception:
                logger.warning(f"Неверный часовой пояс для пользователя {user.id}: {user_timezone_str}. Используем UTC.")
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
        @sync_to_async
        def _calculate_current_streak():
            from datetime import datetime
            import pytz
            from django.db.models.functions import TruncDate
            from django.db.models import Q
            user_timezone_str = user.timezone or 'UTC'
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except Exception:
                logger.warning(f"Неверный часовой пояс для пользователя {user.id}: {user_timezone_str}. Используем UTC.")
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
        if not stats['has_entry_today'] and stats['streak_days'] > 0:
             stats['streak_reset_warning'] = get_message('streak_reset_warning', user.language or 'ru', streak_days=stats['streak_days'])
    except Exception as e:
        logger.error(f"[_get_user_statistics] Ошибка при подсчете статистики для пользователя {user.id}: {e}", exc_info=True)
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
    logger.debug(f"[show_progress] Запрос от пользователя {user.id}")
    try:
        awareness_level_current = user.awareness_level
        user_stats = await _get_user_statistics(user)
        total_entries = user_stats['entries_count']
        tasks_completed = user_stats['tasks_completed']
        tasks_assigned = user_stats['tasks_assigned']
        tasks_completion_percentage = user_stats['tasks_completion_percentage']
        streak_days = user_stats['streak_days']
        streak_reset_warning = user_stats['streak_reset_warning']

        # --- НОВОЕ: Получение последнего WeeklyAnalysis ---
        latest_weekly_analysis = await _get_latest_weekly_analysis(user)

        # --- Формирование текста сравнения с предыдущей неделей (если есть) ---
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

        # --- Формирование информационного сообщения, если WeeklyAnalysis ещё не проводилось ---
        no_analysis_info = ""
        if not latest_weekly_analysis:
             no_analysis_info = get_message('weekly_analysis_not_performed_yet', language)

        progress_msg = get_message('progress_title', language,
                                   awareness_level=awareness_level_current,
                                   entries_count=total_entries,
                                   tasks_completed=tasks_completed,
                                   tasks_assigned=tasks_assigned,
                                   tasks_completion_percentage=tasks_completion_percentage,
                                   streak_days=streak_days,
                                   streak_reset_warning=streak_reset_warning)

        # Добавляем информационное сообщение, если анализов нет
        progress_msg += no_analysis_info
        # Добавляем текст сравнения (если есть)
        progress_msg += comparison_text
        # УБРАНО: отображение profile_changes_summary в основном сообщении

        has_analyses = await _has_weekly_analyses(user)
        # --- ОБНОВЛЯЕМ КЛАВИАТУРУ: добавляем кнопку "Подробный прогресс" ---
        if has_analyses:
             # Предположим, у нас есть новая клавиатура, которая включает кнопку "Подробный прогресс"
             reply_markup = get_progress_keyboard_with_weekly(language) # Новая функция в keyboards
        else:
             reply_markup = get_progress_keyboard_without_weekly(language)

        success = await safe_edit_message_text(
            message=callback.message,
            text=progress_msg,
            reply_markup=reply_markup
        )
        if success:
            logger.debug(f"[show_progress] Сообщение успешно обновлено для пользователя {user.id}")
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
    logger.debug(f"[show_weekly_progress_list] Запрос от пользователя {user.id}")
    try:
        latest = await _get_latest_weekly_analysis(user)
        if not latest:
            no_analysis_msg = get_message('weekly_analysis_not_found', language)
            success = await safe_edit_message_text(
                message=callback.message,
                text=no_analysis_msg,
                reply_markup=get_progress_keyboard_without_weekly(language)
            )
            if success:
                logger.debug(f"[show_weekly_progress_list] Сообщение 'нет анализа' отправлено.")
            await callback.answer()
            return
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
    logger.debug(f"[navigate_weekly_analysis] Callback от пользователя {user.id}: {callback.data}")
    try:
        parts = callback.data.split(":")
        if len(parts) != 2:
            raise ValueError("Некорректный формат callback_data для навигации")
        week_start_iso = parts[1]
        week_start_date = date.fromisoformat(week_start_iso)
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

@router.callback_query(F.data == "show_mood_chart_week")
async def send_mood_chart_week(callback: CallbackQuery, user, language: str, bot: Bot):
    """Отправляет изображение с графиком настроения за последние 7 дней."""
    try:
        chart_image_buffer = await generate_mood_chart_image(user, days=14)
        chart_input_file = BufferedInputFile(chart_image_buffer.getvalue(), filename='mood_chart.png')
        dismiss_kb = get_single_button_keyboard(
            language=language,
            button_callback_data="delete_current_chart",
            button_text="btn_remove"
        )

        sent_message = await callback.message.answer_photo(
            photo=chart_input_file,
            caption=get_message('mood_chart_caption', language, days=14),
            reply_markup=dismiss_kb
        )
        await callback.answer()
        logger.debug(f"[send_mood_chart_week] График отправлен в сообщении ID {sent_message.message_id} пользователю {user.telegram_id}")
    except Exception as e:
        logger.error(f"[send_mood_chart_week] Ошибка генерации/отправки графика: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language), show_alert=True)


@router.callback_query(F.data == "delete_current_chart")
async def delete_chart_message(callback: CallbackQuery, bot: Bot):
    """Удаляет текущее сообщение (предположительно, с графиком)."""
    try:
        message_to_delete = callback.message
        await bot.delete_message(chat_id=message_to_delete.chat.id, message_id=message_to_delete.message_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"[delete_chart_message] Ошибка при удалении сообщения: {e}", exc_info=True)

async def _show_weekly_analysis_page(message, user, week_start_date: date, language: str):
    """Вспомогательная функция для отображения анализа конкретной недели."""
    logger.debug(f"[_show_weekly_analysis_page] Попытка показа анализа для недели {week_start_date} пользователя {user.id}")
    try:
        week_end_date = week_start_date + timedelta(days=6)
        logger.debug(f"[_show_weekly_analysis_page] Конец недели: {week_end_date}")
        @sync_to_async
        def get_analysis_sync():
            try:
                return WeeklyAnalysis.objects.get(user=user, week_start_date=week_start_date)
            except WeeklyAnalysis.DoesNotExist:
                logger.debug(f"[_show_weekly_analysis_page] Анализ для недели {week_start_date} не найден.")
                return None
        analysis = await get_analysis_sync()
        if not analysis:
            no_data_msg = get_message('weekly_analysis_not_found', language)
            logger.debug(f"[_show_weekly_analysis_page] Анализ не найден, отправляем сообщение.")
            await safe_edit_message_text(
                message=message,
                text=no_data_msg,
                reply_markup=get_weekly_navigation_keyboard(language, week_start_date)
            )
            return
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
        success = await safe_edit_message_text(
            message=message,
            text=final_msg,
            reply_markup=get_weekly_navigation_keyboard(language, week_start_date)
        )
        if success:
            logger.debug(f"[_show_weekly_analysis_page] Сообщение анализа успешно обновлено.")
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

@router.callback_query(F.data == "weekly_details")
async def show_detailed_progress(callback: CallbackQuery, user, language: str):
    """Показывает подробности изменений профиля из последнего WeeklyAnalysis."""
    logger.debug(f"[show_detailed_progress] Запрос от пользователя {user.id}")
    try:
        latest_weekly_analysis = await _get_latest_weekly_analysis(user)

        if not latest_weekly_analysis:
            no_data_msg = get_message('weekly_analysis_not_found', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_data_msg,
                reply_markup=get_back_keyboard(language)
            )
            await callback.answer()
            return
        changes_text = ""
        if latest_weekly_analysis.profile_changes_summary:
            changes_summary = latest_weekly_analysis.profile_changes_summary
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
        week_start_date = latest_weekly_analysis.week_start_date.strftime("%d.%m.%Y")
        week_end_date = (latest_weekly_analysis.week_start_date + timedelta(days=6)).strftime("%d.%m.%Y")
        details_msg = get_message(
            'detailed_progress',
            language,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            changes_text=changes_text)
        await safe_edit_message_text(
            message=callback.message,
            text=details_msg,
            reply_markup=get_single_button_keyboard(language, 'progress', 'btn_back')
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"[show_detailed_progress] Критическая ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=callback.message,
            text=error_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
