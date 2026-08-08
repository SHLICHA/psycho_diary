"""
Handlers для прогресса
"""
import logging

from datetime import date
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, BufferedInputFile

from messages import get_message
from bot.keyboards import (
    get_back_keyboard,
    get_progress_keyboard_without_weekly,
    get_single_button_keyboard,
)
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.mood_chart import generate_mood_chart_image
from bot.decorators.premium_decorator import requires_premium
from diary.services.progress_service import (
    get_latest_weekly_analysis,
    get_detailed_weekly_changes,
    build_progress_screen_view,
    build_weekly_analysis_page_view,
    build_restore_streak_request_view,
    confirm_streak_restoration_use_case,
)

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "progress")
async def show_progress(callback: CallbackQuery, user, language: str):
    """Показ прогресса."""
    logger.debug(f"[show_progress] Запрос от пользователя {user.id}")
    try:
        view = await build_progress_screen_view(user, language)
        success = await safe_edit_message_text(
            message=callback.message,
            text=view['text'],
            reply_markup=view['reply_markup'],
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
        latest = await get_latest_weekly_analysis(user)
        if not latest:
            no_analysis_msg = get_message('weekly_analysis_not_found', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_analysis_msg,
                reply_markup=get_progress_keyboard_without_weekly(language)
            )
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
@requires_premium(alert_message_key='feature_requires_premium')
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
        logger.debug(
            f"[send_mood_chart_week] График отправлен в сообщении ID {sent_message.message_id} "
            f"пользователю {user.telegram_id}"
        )
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


@router.callback_query(F.data == "restore_streak")
async def handle_restore_streak_request(callback: CallbackQuery, user, language: str):
    """Обрабатывает запрос на восстановление серии."""
    logger.debug(f"[handle_restore_streak_request] Запрос от пользователя {user.id}")
    try:
        view = await build_restore_streak_request_view(user, language)
        if view.get('mode') == 'unavailable' or not view.get('available'):
            await show_progress(callback, user, language)
            await callback.answer()
            return
        if not view.get('success'):
            await safe_edit_message_text(
                message=callback.message,
                text=view.get('text') or get_message('error_generic', language),
                reply_markup=view.get('reply_markup') or get_back_keyboard(language),
            )
            await callback.answer()
            return

        await safe_edit_message_text(
            message=callback.message,
            text=view['text'],
            reply_markup=view['reply_markup'],
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"[handle_restore_streak_request] Критическая ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await safe_edit_message_text(
            message=callback.message,
            text=error_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()


@router.callback_query(F.data.startswith("restore_streak_confirm:"))
async def handle_restore_streak_confirm(callback: CallbackQuery, user, language: str):
    """Обрабатывает подтверждение восстановления для конкретной даты."""
    logger.debug(f"[handle_restore_streak_confirm] Callback от пользователя {user.id}: {callback.data}")
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Некорректный формат callback_data для подтверждения восстановления")
        date_str = parts[1]
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            raise ValueError(f"Некорректный формат даты в callback_data: {date_str}")
        use_case = await confirm_streak_restoration_use_case(user, target_date, language)
        if use_case['refresh_progress']:
            await show_progress(callback, user, language)
        if use_case.get('notify_mode') == 'message':
            await callback.message.answer(text=use_case['alert_text'])
            await callback.answer()
            return
        await callback.answer(text=use_case['alert_text'], show_alert=True)
    except (ValueError, Exception) as e:
        logger.error(f"[handle_restore_streak_confirm] Ошибка: {e}", exc_info=True)
        error_msg = get_message('error_generic', language)
        await show_progress(callback, user, language)
        await callback.message.answer(text=error_msg)
        await callback.answer()


async def _show_weekly_analysis_page(message, user, week_start_date: date, language: str):
    """Transport: service payload → edit message."""
    logger.debug(
        f"[_show_weekly_analysis_page] Попытка показа анализа для недели "
        f"{week_start_date} пользователя {user.id}"
    )
    try:
        view = await build_weekly_analysis_page_view(user, week_start_date, language)
        await safe_edit_message_text(
            message=message,
            text=view['text'],
            reply_markup=view['reply_markup'],
        )
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
        details_result = await get_detailed_weekly_changes(user, language)
        if not details_result['success']:
            error_msg = details_result.get('message', get_message('error_generic', language))
            await safe_edit_message_text(
                message=callback.message,
                text=error_msg,
                reply_markup=get_back_keyboard(language)
            )
            await callback.answer()
            return

        details_msg = details_result['message']
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
