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
    """
    logger.info("Запущена задача check_clarification_reminders")
    try:
        now_utc = timezone.now() # Текущее время UTC

        # Находим записи, время напоминания для которых уже наступило (по UTC), и напоминание еще не отправлялось
        entries_needing_reminder = DiaryEntry.objects.filter(
            clarification_reminder_due_at__lte=now_utc, # Время напоминания наступило (по UTC)
            clarification_answers={}, # Ответов пока нет
            last_reminder_sent_at__isnull=True # Напоминание еще не отправлялось
        ).select_related('user')

        logger.info(f"Найдено {entries_needing_reminder.count()} записей, требующих напоминания.")

        for entry in entries_needing_reminder:
            logger.info(f"Отправка напоминания для записи {entry.id}, пользователь {entry.user.telegram_id}")
            asyncio.run(_send_reminder_async(entry))
    except Exception as e:
        logger.error(f"Ошибка в задаче check_clarification_reminders: {e}", exc_info=True)


@shared_task
def force_process_clarifications():
    """
    Celery задача для принудительной обработки записей с неотвеченными уточнениями.
    Использует предвычисленное время clarification_force_process_at (в UTC).
    """
    logger.info("Запущена задача force_process_clarifications")
    try:
        now_utc = timezone.now() # Текущее время UTC

        # Находим записи, время принудительной обработки для которых уже наступило (по UTC), и она еще не выполнена
        entries_to_force_process = DiaryEntry.objects.filter(
            clarification_force_process_at__lte=now_utc, # Время принудительной обработки наступило (по UTC)
            clarification_answers={}, # Ответов пока нет
            analysis_processed_at__isnull=True # Принудительная обработка еще не выполнялась
        ).select_related('user')

        logger.info(f"Найдено {entries_to_force_process.count()} записей, требующих принудительной обработки.")

        for entry in entries_to_force_process:
            logger.info(f"Принудительная обработка для записи {entry.id}, пользователь {entry.user.telegram_id}")
            asyncio.run(_force_process_async(entry))
    except Exception as e:
        logger.error(f"Ошибка в задаче force_process_clarifications: {e}", exc_info=True)

async def _send_reminder_async(entry: DiaryEntry):
    """
    Асинхронно отправляет напоминание пользователю и обновляет last_reminder_sent_at.
    """
    user = entry.user
    bot_instance = None
    try:
        # Создаем новый экземпляр бота
        bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML) # Используем токен из настроек

        # Отправляем напоминание
        await bot_instance.send_message(
            chat_id=user.telegram_id,
            text=get_message('reminder_clarification', user.language),
            reply_markup=get_skip_clarification_keyboard(user.language) # Добавляем клавиатуру
        )
        logger.info(f"Напоминание отправлено пользователю {user.telegram_id} для записи {entry.id}.")

        # Обновляем поле last_reminder_sent_at
        entry.last_reminder_sent_at = timezone.now()
        await sync_to_async(entry.save)(update_fields=['last_reminder_sent_at'])

    except TelegramForbiddenError as e:
        # Бот заблокирован пользователем
        logger.warning(f"Бот заблокирован пользователем {user.telegram_id}. Напоминание не отправлено. Ошибка: {e}")
        # Не обновляем last_reminder_sent_at, чтобы не пытаться отправлять снова
        # Можно отметить в профиле пользователя, что бот заблокирован
        user.is_blocked = True
        await sync_to_async(user.save)(update_fields=['is_blocked'])
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user.telegram_id} для записи {entry.id}: {e}", exc_info=True)
    finally:
        # Закрываем сессию бота, если она была создана
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
        # Подготовка данных для промпта clarification_analysis
        user_profile = await user.aget_profile_data()
        first_name = user_profile.get('first_name', 'Пользователь')
        awareness_level = user_profile['awareness_level']

        # Формируем "пустые" ответы
        clarification_questions = entry.clarification_questions_asked
        clarification_answers_dict = {q: "[Ответ не получен]" for q in clarification_questions}

        logger.debug(f'Профиль пользователя для принудительной обработки: {user_profile}')

        prompt = get_prompt(
            key='clarification_analysis',
            language=user.language, # Используем язык пользователя
            original_text=entry.text,
            clarification_questions="\n".join(clarification_questions),
            clarification_answers="\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]),
            first_name=first_name,
            awareness_level=awareness_level,
        )

        # Отправляем промпт к ИИ
        analysis_result = await deepseek_api_service.send_prompt_and_parse(prompt, user.language)

        # --- ИЗМЕНЕНИЕ: Обновляем clarification_answers и сбрасываем поля уточнений ---
        entry.clarification_answers = clarification_answers_dict
        await sync_to_async(entry.save)(update_fields=[
            'clarification_answers',
            'clarification_reminder_due_at', # Сбрасываем, так как анализ запускается
            'clarification_force_process_at' # Сбрасываем, так как анализ запускается
        ])
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        # Обновляем analysis_processed_at, чтобы избежать повторной принудительной обработки
        entry.analysis_processed_at = timezone.now()
        await sync_to_async(entry.save)(update_fields=['analysis_processed_at'])

        # --- ИЗМЕНЕНИЕ: Создаём бота и отправляем статусное сообщение ---
        bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
        status_message_sent = await bot_instance.send_message(
            chat_id=user.telegram_id,
            text=get_message('processing', user.language) # Отправляем "Обрабатываю..."
        )
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        # --- ИЗМЕНЕНИЕ: Вызываем ОРИГИНАЛЬНУЮ (или АДАПТИРОВАННУЮ) функцию с state=None ---
        # Импортируем из diary.py, если нет циклической зависимости
        # from bot.handlers.diary import _process_analysis_result
        # Или используем адаптированную копию из этого же файла
        await _process_analysis_result(
            entry=entry,
            analysis_result=analysis_result,
            status_msg=status_message_sent,
            language=user.language,
            # state=None, # <-- ПЕРЕДАЁМ state=None
            state=None, # ВАЖНО: передаём None, так как это фоновая задача
            user=user
        )
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        logger.info(f"Принудительная обработка записи {entry.id} завершена, сообщение отправлено пользователю {user.telegram_id}.")

    except TelegramForbiddenError as e:
        # Бот заблокирован пользователем
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

# --- АДАПТИРОВАННАЯ КОПИЯ _process_analysis_result ---
# Копируем функцию из diary.py (второй файл) и адаптируем
# УБЕДИТЕСЬ, ЧТО ЭТА КОПИЯ ИДЕНТИЧНА ОРИГИНАЛУ В diary.py, КРОМЕ ПРОВЕРКИ if state:
# Особенно проверьте строку: if state: await state_manager.clear_state(state)

# (Вставьте сюда точную копию функции _process_analysis_result из diary.py, файл 2)
# Но убедитесь, что строка внутри неё выглядит так:
# if state: # <-- Это важно
#     await state_manager.clear_state(state)
# Или, если в оригинале diary.py она уже такая, то копируем *её* точь-в-точь.

# Предположим, в diary.py (файл 2) строка 775-780 (примерный диапазон):
#         await status_msg.edit_text(final_text, reply_markup=reply_markup)
#         await state_manager.clear_state(state) # <-- Вот ЭТА строка
# Нам нужно убедиться, что в копии в *этом* файле (reminder_ask_questions.py) она тоже такая.
# Если в копии в reminder_ask_questions.py было просто:
#         await status_msg.edit_text(final_text, reply_markup=reply_markup)
#         await state_manager.clear_state(state) # <-- Это вызовет ошибку, если state = None
# Тогда нужно изменить на:
#         await status_msg.edit_text(final_text, reply_markup=reply_markup)
#         if state: # <-- Добавляем проверку
#             await state_manager.clear_state(state) # <-- Выполняем только если state не None

# Итак, адаптируем копию:
async def _process_analysis_result(
    entry: DiaryEntry,
    analysis_result: dict,
    status_msg,
    language: str,
    state: FSMContext, # Может быть None
    user: User
):
    """Обрабатывает результат анализа."""
    try:
        result_data = {}
        if not analysis_result or not analysis_result.get('success'):
            from bot.utils.api_utils import format_api_error_for_analysis # Импорт внутри функции
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
            # --- КРИТИЧЕСКИЙ МОМЕНТ ---
            # Эта ветка НЕ должна сработать в clarification_analysis, если ИИ всё сделал правильно.
            # Но на всякий случай, добавим логирование.
            if needs_clarification and clarification_questions:
                 logger.warning(f"ИИ вернул needs_clarification=True в clarification_analysis для записи {entry.id}. Это неожиданно.")
                 # В оригинальной функции тут был return.
                 # В контексте принудительной обработки, возможно, лучше не возвращать,
                 # а обработать как обычный результат, чтобы не оставлять запись в состоянии ожидания.
                 # Однако, если ИИ снова запросил уточнения, это странно после "clarification_analysis".
                 # Пока оставим return, как в оригинале, но с логированием.
                 # Лучше бы ИИ не возвращал этого в clarification_analysis.
                 # Если вы хотите, чтобы оно игнорировалось, уберите return.
                 # return # <-- Закомментировано, чтобы не прерывать обработку в задаче, если ИИ ошибся

        await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {})
        )

        # Обновление CombinedDiaryEntry
        # Импорт внутри функции, чтобы избежать циклических зависимостей при запуске Celery
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

        # Обработка задания
        task_info = ""
        reply_markup = get_back_keyboard(language)
        if suggested_task and isinstance(suggested_task, dict):
            @sync_to_async
            def check_ai_tasks_limit_sync():
                from diary.models import TherapyTask # Импорт внутри sync_to_async
                today = entry.entry_date
                count = TherapyTask.objects.filter(
                    user=user,
                    related_entry__created_at__date=today
                ).count()
                return count < user.max_ai_tasks_per_day

            limit_not_exceeded = await check_ai_tasks_limit_sync()
            if limit_not_exceeded:
                try:
                    # Импорт внутри async функции
                    from bot.services import task_service
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

        # --- КРИТИЧЕСКАЯ СТРОКА: Проверка state перед очисткой ---
        if state: # <-- ЭТА ПРОВЕРКА ВАЖНА
            await state_manager.clear_state(state)
        # --- КОНЕЦ КРИТИЧЕСКОЙ СТРОКИ ---

    except Exception as e:
        logger.error(f"Ошибка в _process_analysis_result (в задаче): {e}", exc_info=True)
        if status_msg:
            try:
                # Импорт внутри функции
                from bot.utils.message_utils import safe_edit_message_text
                await safe_edit_message_text(status_msg, get_message('error_processing', language))
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке в _process_analysis_result (в задаче): {edit_error}")
                # В фоновой задаче state_manager.clear_state не нужен, если state == None
                # Но если state был бы валидным, его очистка тут не помешала бы.
                # if state: await state_manager.clear_state(state) # <-- Не нужно, если state всегда None в задаче
        raise # Переподнимаем ошибку, если это критично для задачи

# --- КОПИЯ _create_task_from_suggested_data (если нужна в этом файле) ---
# Копируем и адаптируем, если оригинальная функция не импортируется из-за зависимостей
async def _create_task_from_suggested_data(user, task_data, entry_date, related_entry):
    """Создаёт задание из данных ИИ."""
    # Импорт внутри async функции
    from core.constants import TASK_TYPES
    valid_types = [t[0] for t in TASK_TYPES]
    task_type = task_data.get('type', 'daily')
    if task_type not in valid_types:
        task_type = 'daily'
    priority_map = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    priority = priority_map.get(task_data.get('priority', 'medium').lower(), 2)
    # Импорт внутри async функции
    from bot.services import task_service
    return await task_service.assign_task(
        user=user,
        title=task_data.get('title', 'Задание от ИИ'),
        description=task_data.get('description', 'Выполните задание.'),
        task_type=task_type,
        priority=priority,
        related_entry=related_entry
    )
