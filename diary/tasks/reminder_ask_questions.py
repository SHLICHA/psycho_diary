import asyncio
import logging

from datetime import timedelta
from aiogram.enums import ParseMode
from celery import shared_task
from django.utils import timezone
from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext

from core.settings import TELEGRAM_BOT_TOKEN
from core.constants import TASK_TYPES
from diary.models import DiaryEntry
from users.models import User
from bot.services.diary_service import diary_service
from bot.services.psycho_analysis_service import psycho_analysis_service
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt
from messages import get_message
from bot.utils.state_manager import state_manager
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_skip_clarification_keyboard,
    get_back_keyboard,
    get_task_pagination_keyboard
)

logger = logging.getLogger(__name__)

@shared_task
def check_clarification_reminders():
    """
    Celery задача для проверки и отправки напоминаний о неотвеченных уточняющих вопросах.
    Использует предвычисленное время clarification_reminder_due_at (в UTC).
    Теперь фильтрует без clarification_answers и проверяет его в Python.
    """
    logger.info("Запущена задача check_clarification_reminders")
    try:
        now_utc = timezone.now()
        # Убираем clarification_answers={} из фильтра
        potential_entries_needing_reminder = DiaryEntry.objects.filter(
            clarification_reminder_due_at__lte=now_utc,
            last_reminder_sent_at__isnull=True
        ).select_related('user')

        logger.debug(f"Найдено {potential_entries_needing_reminder.count()} потенциальных записей для напоминания.")

        for entry in potential_entries_needing_reminder:
            # Проверяем clarification_answers в Python после загрузки
            # from_db_value уже вызвана, и clarification_answers - это Python dict/list
            if entry.clarification_answers == {}: # или == dict(), если default=dict
                logger.debug(f"Отправка напоминания для записи {entry.id}, пользователь {entry.user.telegram_id}, clarification_answers пустой.")
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
        # Убираем clarification_answers={} из фильтра
        potential_entries_to_force_process = DiaryEntry.objects.filter(
            clarification_force_process_at__lte=now_utc,
            analysis_processed_at__isnull=True
        ).select_related('user')

        logger.debug(f"Найдено {potential_entries_to_force_process.count()} потенциальных записей для принудительной обработки.")

        for entry in potential_entries_to_force_process:
            # Проверяем clarification_answers в Python после загрузки
            if entry.clarification_answers == {}: # или == dict(), если default=dict
                logger.info(f"Принудительная обработка для записи {entry.id}, пользователь {entry.user.telegram_id}, clarification_answers пустой.")
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
    bot_instance = None
    try:
        bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        await bot_instance.send_message(
            chat_id=user.telegram_id,
            text=get_message('reminder_clarification', user.language),
            reply_markup=get_skip_clarification_keyboard(user.language)
        )
        logger.debug(f"Напоминание отправлено пользователю {user.telegram_id} для записи {entry.id}.")
        entry.last_reminder_sent_at = timezone.now()
        await sync_to_async(entry.save)(update_fields=['last_reminder_sent_at'])
    except TelegramForbiddenError as e:
        logger.warning(f"Бот заблокирован пользователем {user.telegram_id}. Напоминание не отправлено. Ошибка: {e}")
        user.is_blocked = True
        await sync_to_async(user.save)(update_fields=['is_blocked'])
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user.telegram_id} для записи {entry.id}: {e}", exc_info=True)
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
    и отправляет финальное сообщение пользователю.
    """
    user = entry.user
    bot_instance = None
    status_message_sent = None
    try:
        user_profile = await user.aget_profile_data()
        first_name = user_profile.get('first_name', 'Пользователь')
        awareness_level = user_profile['awareness_level']
        clarification_questions = entry.clarification_questions_asked
        clarification_answers_dict = {q: "[Ответ не получен]" for q in clarification_questions}
        prompt = get_prompt(
            key='clarification_analysis',
            language=user.language,
            original_text=entry.text,
            clarification_questions="\n".join(clarification_questions),
            clarification_answers="\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]),
            first_name=first_name,
            awareness_level=awareness_level,
        )
        analysis_result = await deepseek_api_service.send_prompt_and_parse(prompt, user.language)
        entry.clarification_answers = clarification_answers_dict
        await sync_to_async(entry.save)(update_fields=[
            'clarification_answers',
            'clarification_reminder_due_at', 
            'clarification_force_process_at'
        ])
        entry.analysis_processed_at = timezone.now()
        await sync_to_async(entry.save)(update_fields=['analysis_processed_at'])
        bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        status_message_sent = await bot_instance.send_message(
            chat_id=user.telegram_id,
            text=get_message('processing', user.language)
        )
        await _process_analysis_result(
            entry=entry,
            analysis_result=analysis_result,
            status_msg=status_message_sent,
            language=user.language,
            state=None,
            user=user
        )
        logger.info(f"Принудительная обработка записи {entry.id} завершена, сообщение отправлено пользователю {user.telegram_id}.")
    except TelegramForbiddenError as e:
        logger.warning(f"Бот заблокирован пользователем {user.telegram_id}. Не удалось отправить сообщение после принудительной обработки. Ошибка: {e}")
        if entry.analysis_processed_at is None:
            entry.analysis_processed_at = timezone.now()
            await sync_to_async(entry.save)(update_fields=['analysis_processed_at'])
        user.is_blocked = True
        await sync_to_async(user.save)(update_fields=['is_blocked'])
    except Exception as e:
        logger.error(f"Ошибка при принудительной обработке записи {entry.id} или отправке сообщения: {e}", exc_info=True)
        if entry.analysis_processed_at is None:
            entry.analysis_processed_at = timezone.now()
            await sync_to_async(entry.save)(update_fields=['analysis_processed_at'])
        if bot_instance:
            try:
                await bot_instance.send_message(
                    chat_id=user.telegram_id,
                    text=get_message('error_processing', user.language)
                )
            except TelegramForbiddenError:
                logger.warning(f"Бот заблокирован пользователем {user.telegram_id}. Не удалось отправить сообщение об ошибке.")
                user.is_blocked = True
                await sync_to_async(user.save)(update_fields=['is_blocked'])
            except Exception as msg_error:
                logger.error(f"Ошибка при отправке сообщения об ошибке пользователю {user.telegram_id}: {msg_error}")
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
    user: User
):
    """Обрабатывает результат анализа."""
    try:
        result_data = {}
        if not analysis_result or not analysis_result.get('success'):
            from bot.utils.api_utils import format_api_error_for_analysis
            comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, False)
            mood_score = 5
        else:
            result_data = analysis_result.get('result', {})
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')
            suggested_task = result_data.get('suggested_task')
            needs_clarification = result_data.get('needs_clarification', False)
            clarification_questions = result_data.get('clarification_questions', [])
            if needs_clarification and clarification_questions:
                 logger.warning(f"ИИ вернул needs_clarification=True в clarification_analysis для записи {entry.id}. Это неожиданно.")
        await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {})
        )
        from diary.services import daily_state_service
        combined_entry = await daily_state_service.get_daily_state(user, entry.entry_date)
        if combined_entry and 'updated_ai_state_data' in result_data:
            new_state = result_data['updated_ai_state_data']
        else:
            new_state = analysis_text
        await daily_state_service.update_daily_state(
            combined_entry=combined_entry,
            new_ai_state_data=new_state,
            latest_mood_score=mood_score
        )
        task_info = ""
        reply_markup = get_back_keyboard(language)
        if suggested_task and isinstance(suggested_task, dict):
            @sync_to_async
            def check_ai_tasks_limit_sync():
                from diary.models import TherapyTask
                today = entry.entry_date
                count = TherapyTask.objects.filter(
                    user=user,
                    related_entry__created_at__date=today
                ).count()
                return count < user.max_ai_tasks_per_day
            limit_not_exceeded = await check_ai_tasks_limit_sync()
            if limit_not_exceeded:
                try:
                    task = await _create_task_from_suggested_data(user, suggested_task, entry.entry_date, entry)
                    if task:
                        preview = task.description[:150] + "..." if len(task.description) > 150 else task.description
                        task_info = get_message(
                            key='new_ai_task',
                            language=language,
                            title=task.title,
                            preview=preview
                        )
                        reply_markup = get_task_pagination_keyboard(task.id, 0, 1, language)
                except Exception as task_creation_error:
                    logger.error(f"Ошибка при создании задания от ИИ для пользователя {user.telegram_id}: {task_creation_error}")
            else:
                logger.debug(f"Задание от ИИ для пользователя {user.telegram_id} не создано: превышен дневной лимит ({user.max_ai_tasks_per_day}).")
        final_text = get_message('entry_saved', language, score=mood_score, mood=get_message(f'mood_{mood_score}', language), comment=comment, recommendation=recommendation) + task_info
        await status_msg.edit_text(final_text, reply_markup=reply_markup)
        if state:
            await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка в _process_analysis_result (в задаче): {e}", exc_info=True)
        if status_msg:
            try:
                from bot.utils.message_utils import safe_edit_message_text
                await safe_edit_message_text(status_msg, get_message('error_processing', language))
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке в _process_analysis_result (в задаче): {edit_error}")
        raise

async def _create_task_from_suggested_data(user, task_data, entry_date, related_entry):
    """Создаёт задание из данных ИИ."""
    
    valid_types = [t[0] for t in TASK_TYPES]
    task_type = task_data.get('type', 'daily')
    if task_type not in valid_types:
        task_type = 'daily'
    priority_map = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    priority = priority_map.get(task_data.get('priority', 'medium').lower(), 2)
    from bot.services import task_service
    return await task_service.assign_task(
        user=user,
        title=task_data.get('title', 'Задание от ИИ'),
        description=task_data.get('description', 'Выполните задание.'),
        task_type=task_type,
        priority=priority,
        related_entry=related_entry
    )
