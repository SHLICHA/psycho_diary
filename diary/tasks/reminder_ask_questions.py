import asyncio
import logging

from celery import shared_task
from django.utils import timezone
from asgiref.sync import sync_to_async
from aiogram.fsm.context import FSMContext
from django.db import close_old_connections
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from diary.models import DiaryEntry, PsychoAnalysis
from diary.services.daily_state_service import daily_state_service
from users.models import User
from bot.services.deepseek_api import deepseek_api_service
from bot.utils.bot_factory import create_bot_for_task
from bot.utils.message_utils import send_message_to_user
from prompts import get_prompt
from messages import get_message, get_button_text
from bot.utils.state_manager import state_manager
from bot.keyboards import (
    get_skip_clarification_keyboard,
)
from diary.tasks.ai_activity_filter import is_user_active_for_ai_tasks

logger = logging.getLogger(__name__)


def _user_log_id(user: User) -> str:
    parts = [f'id={user.pk}']
    if getattr(user, 'telegram_id', None):
        parts.append(f'tg={user.telegram_id}')
    if getattr(user, 'max_id', None):
        parts.append(f'max={user.max_id}')
    return ' '.join(parts)

@shared_task
def check_clarification_reminders():
    """
    Celery задача для проверки и отправки напоминаний о неотвеченных уточняющих вопросах.
    Использует предвычисленное время clarification_reminder_due_at (в UTC).
    Теперь фильтрует без clarification_answers и проверяет его в Python.
    """
    logger.debug("Запущена задача check_clarification_reminders")
    try:
        now_utc = timezone.now()
        potential_entries_needing_reminder = DiaryEntry.objects.filter(
            clarification_reminder_due_at__lte=now_utc,
            last_reminder_sent_at__isnull=True
        ).select_related('user')

        logger.debug(f"Найдено {potential_entries_needing_reminder.count()} потенциальных записей для напоминания.")

        for entry in potential_entries_needing_reminder:
            if not is_user_active_for_ai_tasks(entry.user):
                continue
            if entry.clarification_answers == {}: 
                logger.debug(
                    "Отправка напоминания для записи %s, пользователь %s, clarification_answers пустой.",
                    entry.id,
                    _user_log_id(entry.user),
                )
                asyncio.run(_send_reminder_async(entry))
            else:
                logger.debug(f"Пропуск напоминания для записи {entry.id}, clarification_answers не пустой: {entry.clarification_answers}")

    except Exception as e:
        logger.error(f"Ошибка в задаче check_clarification_reminders: {e}", exc_info=True)

@shared_task
def force_process_clarifications():
    """
    Celery задача для принудительной обработки записей с неотвеченными уточнениями.
    Использует предвычисленное время clarification_force_process_at (в UTC).
    Теперь фильтрует без clarification_answers и проверяет его в Python.
    """
    logger.debug("Запущена задача force_process_clarifications")
    try:
        now_utc = timezone.now()
        potential_entries_to_force_process = DiaryEntry.objects.filter(
            clarification_force_process_at__lte=now_utc,
            analysis_processed_at__isnull=True
        ).select_related('user')

        logger.debug(f"Найдено {potential_entries_to_force_process.count()} потенциальных записей для принудительной обработки.")

        for entry in potential_entries_to_force_process:
            if not is_user_active_for_ai_tasks(entry.user):
                continue
            if entry.clarification_answers == {}:
                logger.info(
                    "Принудительная обработка для записи %s, пользователь %s, clarification_answers пустой.",
                    entry.id,
                    _user_log_id(entry.user),
                )
                asyncio.run(_force_process_async(entry))
            else:
                logger.debug(f"Пропуск принудительной обработки для записи {entry.id}, clarification_answers не пустой: {entry.clarification_answers}")
    except Exception as e:
        logger.error(f"Ошибка в задаче force_process_clarifications: {e}", exc_info=True)

async def _send_reminder_async(entry: DiaryEntry):
    """
    Асинхронно отправляет напоминание пользователю и обновляет last_reminder_sent_at.
    """
    user = entry.user
    user_ref = _user_log_id(user)
    bot_instance = None
    try:
        bot_instance = await create_bot_for_task()
        ok = await send_message_to_user(
            bot_instance,
            user,
            get_message('reminder_clarification', user.language),
            reply_markup=get_skip_clarification_keyboard(user.language),
        )
        if not ok:
            logger.warning(
                "Напоминание о уточнениях не доставлено пользователю %s для записи %s (нет канала)",
                user_ref,
                entry.id,
            )
            return
        logger.debug(f"Напоминание отправлено пользователю {user_ref} для записи {entry.id}.")
        entry.last_reminder_sent_at = timezone.now()
        await sync_to_async(close_old_connections)()
        await sync_to_async(entry.save)(update_fields=['last_reminder_sent_at'])
    except Exception as e:
        logger.error(
            f"Ошибка при отправке напоминания пользователю {user_ref} для записи {entry.id}: {e}",
            exc_info=True,
        )
    finally:
        if bot_instance:
            try:
                await bot_instance.session.close()
                logger.debug("Сессия бота для напоминания закрыта.")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота напоминания: {close_error}")

async def _force_process_async(entry: DiaryEntry):
    """
    Асинхронно запускает принудительную обработку записи с пустыми ответами
    и отправляет финальное сообщение пользователю (TG и/или MAX).
    """
    user = entry.user
    user_ref = _user_log_id(user)
    bot_instance = None
    try:
        await sync_to_async(close_old_connections)()
        user_profile = await user.aget_profile_data()
        combined_entry = await daily_state_service.get_daily_state(user, await entry.aentry_date())
        ai_state_data = combined_entry.ai_state_data if combined_entry else ""
        clarification_questions = entry.clarification_questions_asked
        clarification_answers_dict = {q: "[Ответ не получен]" for q in clarification_questions}
        prompt = get_prompt(
            key='clarification_analysis',
            language=user.language,
            original_text=entry.text,
            clarification_questions="\n".join(clarification_questions),
            clarification_answers="\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]),
            ai_state_data=ai_state_data,
            user_profile=user_profile
        )
        analysis_result = await deepseek_api_service.send_prompt_and_parse(prompt, user.language)
        entry.clarification_answers = clarification_answers_dict
        await sync_to_async(close_old_connections)()
        await sync_to_async(entry.save)(update_fields=[
            'clarification_answers',
            'clarification_reminder_due_at',
            'clarification_force_process_at'
        ])
        entry.analysis_processed_at = timezone.now()
        await sync_to_async(close_old_connections)()
        await sync_to_async(entry.save)(update_fields=['analysis_processed_at'])
        logger.debug(
            "[reminder_ask_questions] analysis_processed_at установлен для записи %s перед принудительной обработкой.",
            entry.id,
        )
        bot_instance = await create_bot_for_task()
        # Фоновая задача: сразу финальный результат в доступные каналы (без TG-only status_msg).
        await _process_analysis_result(
            entry=entry,
            analysis_result=analysis_result,
            status_msg=None,
            language=user.language,
            state=None,
            user=user,
            processing_time=0.0,
            context='clarification',
            bot=bot_instance,
        )
        logger.info(
            "Принудительная обработка записи %s завершена, сообщение отправлено пользователю %s.",
            entry.id,
            user_ref,
        )
    except Exception as e:
        logger.error(
            "Ошибка при принудительной обработке записи %s или отправке сообщения пользователю %s: %s",
            entry.id,
            user_ref,
            e,
            exc_info=True,
        )
        if bot_instance:
            try:
                ok = await send_message_to_user(
                    bot_instance,
                    user,
                    get_message('error_processing', user.language),
                )
                if not ok:
                    logger.warning(
                        "Не удалось отправить сообщение об ошибке пользователю %s (нет канала)",
                        user_ref,
                    )
            except Exception as msg_error:
                logger.error(
                    "Ошибка при отправке сообщения об ошибке пользователю %s: %s",
                    user_ref,
                    msg_error,
                )
    finally:
        if bot_instance:
            try:
                await bot_instance.session.close()
                logger.debug("Сессия бота для принудительной обработки закрыта.")
            except Exception as close_error:
                logger.error(f"Ошибка при закрытии сессии бота принудительной обработки: {close_error}")

async def _process_analysis_result(
    entry: DiaryEntry,
    analysis_result: dict,
    status_msg,
    language: str,
    state: FSMContext,
    user: User,
    processing_time: float = 0.0,
    context: str = 'new_entry',
    bot=None,
):
    """Обрабатывает результат анализа (копия из diary.py или обновлённая версия)."""
    from bot.utils.api_utils import format_api_error_for_analysis
    from diary.services import daily_state_service
    from bot.services.psycho_analysis_service import psycho_analysis_service
    from bot.keyboards import get_back_keyboard
    from bot.utils.message_utils import safe_edit_message_text

    try:
        result_data = {}
        if not analysis_result or not analysis_result.get('success'):
            comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, is_final=(context in ['clarification', 'comment_analysis']))
            mood_score = 5
        else:
            result_data = analysis_result.get('result', {})
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')
        await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {}),
            processing_time=processing_time # <-- Передаём processing_time
        )

        # --- Обновление CombinedDiaryEntry (только для clarification и comment_analysis) ---
        if context in ['clarification', 'comment_analysis']:
            combined_entry = await daily_state_service.get_daily_state(user, await entry.aentry_date())
            if combined_entry and 'updated_ai_state_data' in result_data:
                new_state = result_data['updated_ai_state_data']
            else:
                new_state = analysis_text # Резервный вариант
            await daily_state_service.update_daily_state(
                combined_entry=combined_entry,
                new_ai_state_data=new_state,
                latest_mood_score=mood_score
            )
            logger.debug(f"[_process_analysis_result in tasks] Обновлен CombinedDiaryEntry для {context} записи {entry.id}")
        final_text = get_message('entry_saved', language, score=mood_score, mood=get_message(f'mood_{mood_score}', language), comment=comment, recommendation=recommendation)

        reply_markup = get_back_keyboard(language)
        try:
            current_analysis = await PsychoAnalysis.objects.aget(entry=entry)
            user_rating_exists = await current_analysis.user_ratings.filter(user=user).aexists()
        except PsychoAnalysis.DoesNotExist:
            user_rating_exists = False
            logger.warning(f"PsychoAnalysis для записи {entry.id} не найден при добавлении кнопок оценки в _process_analysis_result (tasks)")

        if not user_rating_exists:
            rating_emojis = {1: "😠", 2: "😟", 3: "😐", 4: "🙂", 5: "😄"}
            rating_buttons = []
            for rate_value, emoji in rating_emojis.items():
                rating_buttons.append(
                    InlineKeyboardButton(
                        text=emoji,
                        callback_data=f"rate_analysis:{current_analysis.id}:{rate_value}"
                    )
                )
            if isinstance(reply_markup, InlineKeyboardMarkup):
                 reply_markup.inline_keyboard.append(rating_buttons)
            else:
                 logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в _process_analysis_result (tasks), не добавляем кнопки оценки.")
        if context != 'comment_analysis': 
            try:
                current_entry = await DiaryEntry.objects.aget(id=entry.id)
                has_user_comment = bool(current_entry.user_comment)
            except DiaryEntry.DoesNotExist:
                has_user_comment = True
                logger.warning(f"Запись {entry.id} не найдена при проверке комментария в _process_analysis_result (tasks)")

            if not has_user_comment:
                add_comment_button = InlineKeyboardButton(
                    text=get_button_text('btn_add_comment', language),
                    callback_data=f"request_add_comment:{entry.id}"
                )
                if isinstance(reply_markup, InlineKeyboardMarkup):
                     reply_markup.inline_keyboard.append([add_comment_button])
                else:
                     logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в _process_analysis_result (tasks), не добавляем кнопку 'Добавить комментарий'.")
        back_buttons = [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
        reply_markup.inline_keyboard.append(back_buttons)
        if status_msg is not None:
            await status_msg.edit_text(final_text, reply_markup=reply_markup)
        elif bot is not None:
            ok = await send_message_to_user(
                bot,
                user,
                final_text,
                reply_markup=reply_markup,
            )
            if not ok:
                logger.warning(
                    "Не удалось доставить результат анализа пользователю %s для записи %s (нет канала)",
                    _user_log_id(user),
                    entry.id,
                )
        else:
            logger.error(
                "Нет status_msg и bot для доставки результата анализа пользователю %s, запись %s",
                _user_log_id(user),
                entry.id,
            )
        if state and context in ['clarification', 'comment_analysis']:
            try:
                 await state_manager.clear_state(state)
                 logger.debug(f"Состояние FSM очищено в _process_analysis_result (tasks) для контекста {context}")
            except Exception as state_error:
                logger.error(f"Не удалось очистить состояние в _process_analysis_result (tasks) после {context}: {state_error}")
    except Exception as e:
        logger.error(f"Ошибка в _process_analysis_result (в задаче tasks): {e}", exc_info=True)
        error_text = get_message('error_processing', language)
        if status_msg:
            try:
                await safe_edit_message_text(status_msg, error_text)
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке в _process_analysis_result (в задаче tasks): {edit_error}")
        elif bot is not None:
            try:
                await send_message_to_user(bot, user, error_text)
            except Exception as send_error:
                logger.warning(
                    "Не удалось отправить сообщение об ошибке пользователю %s: %s",
                    _user_log_id(user),
                    send_error,
                )
        if state:
            try:
                await state_manager.clear_state(state)
            except Exception as state_error:
                logger.error(f"Не удалось очистить состояние в _process_analysis_result (в задаче tasks) после ошибки: {state_error}")
