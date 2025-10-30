"""
Handlers для работы с дневником
"""

import asyncio
import logging

from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import date, timedelta
from django.utils import timezone

from messages import get_message, get_button_text
from diary.models import CombinedDiaryEntry, DiaryEntry, DailyAnalysis, PsychoAnalysis
from diary.services import smart_prompt_manager, daily_state_service
from bot.decorators.token_decorator import requires_tokens
from bot.decorators.analytics_decorator import log_user_activity
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_single_button_keyboard,
    get_confirmation_keyboard,
    format_entry_text_for_editing,
    get_back_keyboard,
    get_task_pagination_keyboard,
    get_smart_calendar_keyboard,
    get_delete_entry_confirmation_keyboard,
    get_calendar_back_keyboard,
    get_entry_page_keyboard
    )
from bot.utils.api_utils import format_api_error_for_analysis
from bot.utils.audio_utils import process_voice_message
from bot.utils.validation_utils import validate_incoming_message, validate_text_entry
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.decorators import async_error_handler
from bot.utils.rate_limiter import rate_limiter
from bot.services import (
    diary_service, 
    psycho_analysis_service,
)
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

# ==================== ОСНОВНЫЕ HANDLERS ДНЕВНИКА ====================

@router.callback_query(F.data == "new_entry")
@log_user_activity('entry_created', metadata_extra={'context': 'Создание записи'})
async def new_entry_simple(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    ПРОСТАЯ ВЕРСИЯ - создание новой записи с умной подсказкой
    Вся сложность спрятана в SmartPromptManager
    """
    try:
        await state_manager.set_state(state, DiaryStates.waiting_for_text_entry)
        prompt_text = await smart_prompt_manager.get_prompt_for_user(user, language)
        await safe_edit_message_text(
            message=callback.message,
            text=prompt_text,
            reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel')
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[NEW_ENTRY_SIMPLE] Ошибка при создании записи для {user.telegram_id}: {e}", exc_info=True)
        try:
            await safe_edit_message_text(
                message=callback.message,
                text=get_message('ask_entry', language),
                reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel')
            )
            await safe_answer_callback(callback, "")
        except Exception as fallback_error:
            logger.error(f"[NEW_ENTRY_SIMPLE] Fallback также failed: {fallback_error}")
            await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(DiaryStates.waiting_for_text_entry, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@async_error_handler('diary_handler')
@log_user_activity('entry_process', metadata_extra={'context': 'Обработка записи'})
async def process_any_entry(message: Message, state: FSMContext, user, language: str):
    status_msg = None
    if await rate_limiter.is_rate_limited(f'user_{user.telegram_id}_entries'):
        await message.answer(get_message('rate_limit', language))
        return
    is_valid, error_code = validate_incoming_message(message)
    if not is_valid:
        await message.answer(get_message(error_code, language))
        return
    rate_limit_key = f"user_{user.telegram_id}_entries"
    is_limited = await rate_limiter.is_rate_limited(rate_limit_key, limit=3, period=60)
    if is_limited:
        await message.answer(get_message('rate_limit', language))
        return
    try:
        entry_text = ""
        entry_datetime = message.date
        status_msg = await message.answer(get_message('processing', language))
        if message.content_type == ContentType.VOICE:
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="New Entry",
                language=language,
                status_msg=status_msg
            )
            if not success:
                await status_msg.edit_text(f"{get_message('error_processing', language)}: {error_message}")
                return
            entry_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            entry_text = message.text
        else:
            logger.warning(f"[New Entry] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            await status_msg.delete()
            return
        result = await diary_service.process_new_entry_logic(
            user=user,
            entry_text=entry_text,
            language=language,
            entry_datetime=entry_datetime
        )
        if not result['success']:
            formatted_message_ai = result.get('formatted_message_ai', '')
            validation_comment_ai = result.get('validation_comment_ai', '')
            if formatted_message_ai:
                 final_message_text = formatted_message_ai
            else:
                 final_message_text = f"❌ <b>Ваша запись не прошла валидацию</b>\n"
                 if validation_comment_ai:
                      final_message_text += f"💬 <i>{validation_comment_ai}</i>\n"
                 else:
                      final_message_text += f"📝 <i>{get_message('entry_not_validated_generic', language)}</i>\n"
                 final_message_text += f"🔍 Пожалуйста, попробуйте снова."
            retry_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text('btn_retry_entry', language), callback_data='new_entry')],
                [InlineKeyboardButton(text=get_button_text('btn_main_menu', language), callback_data='main_menu')]
            ])
            await status_msg.edit_text(final_message_text, reply_markup=retry_keyboard)
            await state_manager.clear_state(state)
            return
        diary_entry = result['entry']
        analysis_obj = result['analysis']
        needs_clarification = result['needs_clarification']
        clarification_questions = result['clarification_questions']
        suggested_task_obj = result['suggested_task']
        streak_bonus_info = result['streak_bonus_info']
        task_info = ""
        reply_markup = get_back_keyboard(language)
        if suggested_task_obj:
            preview = suggested_task_obj.description[:150] + "..." if len(suggested_task_obj.description) > 150 else suggested_task_obj.description
            task_info = get_message(
                'task_assigned',
                language,
                title=suggested_task_obj.title,
                description=preview)
            reply_markup = get_task_pagination_keyboard(suggested_task_obj.id, 0, 1, language)

        final_text = get_message('entry_saved', language, score=analysis_obj.mood_score, mood=get_message(f'mood_{analysis_obj.mood_score}', language), comment=analysis_obj.comment, recommendation=analysis_obj.recommendation) + task_info
        if streak_bonus_info.get("awarded"):
            rewards = streak_bonus_info.get("rewards", [])
            reward_strings = [
                get_message('streak_bonus_earned', language, days=streak, tokens=tokens)
                for streak, tokens in rewards
            ]
            reward_text = " ".join(reward_strings)
            final_text += f"\n{reward_text}"
        back_buttons = None
        if isinstance(reply_markup, InlineKeyboardMarkup):
            if reply_markup.inline_keyboard and len(reply_markup.inline_keyboard) > 0:
                 last_row = reply_markup.inline_keyboard[-1]
                 back_button_found = False
                 for btn in last_row:
                     if btn.callback_data == "main_menu":
                         back_button_found = True
                         break
                 if back_button_found:
                     back_buttons = reply_markup.inline_keyboard.pop()
                     logger.debug(f"[DEBUG] Сохранены кнопки 'Назад': {back_buttons}")
                 else:
                     logger.debug(f"[DEBUG] Кнопки 'Назад' не найдены в последней строке. Тип клавиатуры: {type(reply_markup)}")
        try:
            user_rating_exists = await analysis_obj.user_ratings.filter(user=user).aexists()
        except Exception:
            user_rating_exists = False
            logger.warning(f"PsychoAnalysis для записи {diary_entry.id} не найден при добавлении кнопок оценки в process_any_entry")
        if not user_rating_exists:
            rating_emojis = {1: "😠", 2: "😟", 3: "😐", 4: "🙂", 5: "😄"}
            rating_buttons = []
            for rate_value, emoji in rating_emojis.items():
                rating_buttons.append(
                    InlineKeyboardButton(
                        text=emoji,
                        callback_data=f"rate_analysis:{analysis_obj.id}:{rate_value}"
                    )
                )
            if isinstance(reply_markup, InlineKeyboardMarkup):
                 reply_markup.inline_keyboard.append(rating_buttons)
            else:
                 logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в process_any_entry, не добавляем кнопки оценки.")
        try:
            current_entry = await DiaryEntry.objects.aget(id=diary_entry.id)
            has_user_comment = bool(current_entry.user_comment)
        except DiaryEntry.DoesNotExist:
            has_user_comment = True
            logger.warning(f"Запись {diary_entry.id} не найдена при проверке комментария в process_any_entry")
        if not has_user_comment:
            add_comment_button = InlineKeyboardButton(
                text=get_button_text('btn_add_comment', language),
                callback_data=f"request_add_comment:{diary_entry.id}"
            )
            if isinstance(reply_markup, InlineKeyboardMarkup):
                 reply_markup.inline_keyboard.append([add_comment_button])
            else:
                 logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в process_any_entry, не добавляем кнопку 'Добавить комментарий'.")
        if back_buttons and isinstance(reply_markup, InlineKeyboardMarkup):
            reply_markup.inline_keyboard.append(back_buttons)
            logger.debug(f"[DEBUG] Кнопки 'Назад' восстановлены в конец клавиатуры.")
        await status_msg.edit_text(final_text, reply_markup=reply_markup)
        if needs_clarification and clarification_questions:
            now_utc = timezone.now()
            diary_entry.clarification_questions_asked = clarification_questions
            diary_entry.clarification_asked_at = now_utc
            diary_entry.clarification_reminder_due_at = now_utc + timedelta(minutes=10)
            diary_entry.clarification_force_process_at = now_utc + timedelta(minutes=20)
            await sync_to_async(diary_entry.save)(
                update_fields=[
                    'clarification_questions_asked',
                    'clarification_asked_at',
                    'clarification_reminder_due_at',
                    'clarification_force_process_at'
                ]
            )
            await state_manager.update_state_data(
                state,
                clarifying_entry_id=diary_entry.id,
                clarification_questions=clarification_questions
            )
            await state_manager.set_state(state, DiaryStates.asking_clarifying_questions)
            questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clarification_questions)])
            await status_msg.edit_text(
                f"{get_message('clarification_needed', language)}\n{questions_text}",
                reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel')
            )
            return 
        await state_manager.clear_state(state)
        try:
            asyncio.create_task(smart_prompt_manager.on_entry_saved(user, diary_entry, language))
        except Exception as prompt_error:
            logger.error(f"[process_any_entry] Ошибка запуска генерации подсказки: {prompt_error}")
    except Exception as e:
        logger.error(f"Ошибка обработки записи: {e}")
        if status_msg:
            try:
                await status_msg.edit_text(get_message('error_processing', language))
            except Exception as edit_error:
                logger.error(f"Не удалось отредактировать сообщение об ошибке: {edit_error}")
        await state_manager.clear_state(state)

@router.message(DiaryStates.asking_clarifying_questions, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('entry_process', metadata_extra={'context': 'Обработка записи с вопросами'})
async def process_clarification_answers(message: Message, state: FSMContext, user, language: str):
    status_message = None
    try:
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('clarifying_entry_id')
        clarification_questions = state_data.get('clarification_questions', [])
        if not entry_id:
            logger.error("ID записи не найден в FSM")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        try:
            diary_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        clarification_text = ""
        if message.content_type == ContentType.VOICE:
            status_message = await message.answer(get_message('processing', language))
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Clarification",
                language=language,
                status_msg=status_message
            )
            if not success:
                await status_message.edit_text(f"{get_message('error_processing', language)}: {error_message}")
                await state_manager.clear_state(state)
                return
            clarification_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            clarification_text = message.text.strip()
            if not clarification_text:
                await message.answer(get_message('invalid_input', language))
                return
        else:
            logger.warning(f"[Clarification] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        if status_message is None:
            status_message = await message.answer(get_message('processing', language))
        answers_list = [ans.strip() for ans in clarification_text.split("\n") if ans.strip()]
        clarification_answers_dict = {}
        for i, q in enumerate(clarification_questions):
            clarification_answers_dict[q] = answers_list[i] if i < len(answers_list) else "[Ответ не получен]"
        result = await diary_service.process_clarification_answers_logic(
            user=user,
            diary_entry=diary_entry,
            clarification_answers_dict=clarification_answers_dict,
            language=language
        )
        if result['success']:
            analysis_result_for_handler = {
                'success': True,
                'result': {
                    'mood_score': result['analysis'].mood_score,
                    'comment': result['analysis'].comment,
                    'recommendation': result['analysis'].recommendation,
                    'analysis': result['formatted_message_ai']
                }
            }
            await _process_analysis_result(
                entry=result['entry'],
                analysis_result=analysis_result_for_handler,
                status_msg=status_message,
                language=language,
                state=state,
                user=user,
                processing_time=0.0,
                context='clarification'
            )
        else:
            analysis_result_for_handler = {
                'success': False,
                'error': 'service_error',
                'message': 'Ошибка обработки уточнений'
            }
            await _process_analysis_result(
                entry=diary_entry,
                analysis_result=analysis_result_for_handler,
                status_msg=status_message,
                language=language,
                state=state,
                user=user,
                processing_time=0.0,
                context='clarification'
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке уточнений: {e}", exc_info=True)
        if status_message:
            try:
                await status_message.edit_text(get_message('error_processing', language))
            except Exception as edit_error:
                logger.error(f"Не удалось отредактировать сообщение об ошибке в process_clarification_answers: {edit_error}")
        else:
            await message.answer(get_message('error_processing', language))
        await state_manager.clear_state(state)

@router.callback_query(F.data.startswith("request_add_comment:"))
@log_user_activity('entry_comment', metadata_extra={'context': 'Добавление комментария'})
async def request_add_comment(callback: CallbackQuery, state: FSMContext, user, language: str):
    """
    Запрашивает у пользователя комментарий к записи.
    """
    try:
        entry_id = int(callback.data.split(":")[1])
        try:
            diary_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Пользователь {user.telegram_id} пытается добавить комментарий к несуществующей записи {entry_id}")
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        if diary_entry.user_comment:
            logger.warning(f"Пользователь {user.telegram_id} пытается добавить комментарий к записи {entry_id}, но комментарий уже существует.")
            await safe_answer_callback(callback, get_message('comment_already_added', language), show_alert=True) 
            return
        await state_manager.set_state(state, DiaryStates.waiting_for_user_comment)
        await state_manager.update_state_data(state, comment_entry_id=entry_id)
        prompt_text = get_message('ask_user_comment', language)
        await safe_edit_message_text(
            message=callback.message,
            text=prompt_text,
            reply_markup=get_single_button_keyboard(language, 'main_menu', 'btn_cancel')
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"[request_add_comment] Ошибка при запросе комментария от пользователя {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.message(DiaryStates.waiting_for_user_comment, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
@log_user_activity('entry_process', metadata_extra={'context': 'Обработка записи с комментарием'})
async def process_user_comment(message: Message, state: FSMContext, user, language: str):
    """
    Обрабатывает комментарий пользователя (текст или голос) и отправляет его на анализ ИИ.
    """
    status_message = None
    try:
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('comment_entry_id')
        if not entry_id:
            logger.error(f"[process_user_comment] ID записи не найден в FSM для пользователя {user.telegram_id}")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        try:
            diary_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            logger.error(f"[process_user_comment] Запись {entry_id} не найдена для пользователя {user.telegram_id}")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        if diary_entry.user_comment:
            logger.warning(f"Пользователь {user.telegram_id} пытается добавить комментарий к записи {entry_id}, но комментарий уже существует.")
            await message.answer(get_message('comment_already_added', language))
            await state_manager.clear_state(state)
            return
        user_comment_text = ""
        if message.content_type == ContentType.VOICE:
            status_message = await message.answer(get_message('processing', language))
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="User Comment",
                language=language,
                status_msg=status_message
            )
            if not success:
                await status_message.edit_text(f"{get_message('error_processing', language)}: {error_message}")
                await state_manager.clear_state(state)
                return
            user_comment_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            user_comment_text = message.text.strip()
            if not user_comment_text:
                await message.answer(get_message('invalid_input', language))
                await state_manager.clear_state(state)
                return
        else:
            logger.warning(f"[process_user_comment] Неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            await state_manager.clear_state(state)
            return
        if status_message is None:
            status_message = await message.answer(get_message('processing', language))
        result = await diary_service.process_user_comment_logic(
            user=user,
            diary_entry=diary_entry,
            user_comment_text=user_comment_text,
            language=language
        )
        analysis_result_for_handler = {
            'success': True,
            'result': {
                'mood_score': result['analysis'].mood_score,
                'comment': result['analysis'].comment,
                'recommendation': result['analysis'].recommendation,
                'analysis': result['formatted_message_ai']
            }
        }
        await _process_analysis_result(
            entry=result['entry'],
            analysis_result=analysis_result_for_handler,
            status_msg=status_message,
            language=language,
            state=state, 
            user=user,
            context='comment_analysis'
        )
    except Exception as e:
        logger.error(f"[process_user_comment] Ошибка при обработке комментария пользователя {user.telegram_id}: {e}", exc_info=True)
        if status_message:
            try:
                await status_message.edit_text(get_message('error_processing', language))
            except Exception as edit_error:
                logger.error(f"[process_user_comment] Ошибка при редактировании сообщения об ошибке: {edit_error}")
        else:
            await message.answer(get_message('error_processing', language))
        await state_manager.clear_state(state)

@router.callback_query(F.data.startswith("rate_analysis:"))
@log_user_activity('entry_rate', metadata_extra={'context': 'Выставлени оценки анализа'})
async def rate_analysis(callback: CallbackQuery, user, language: str):
    """
    Обработчик оценки анализа записи.
    """
    try:
        parts = callback.data.split(":")
        if len(parts) != 3:
            logger.warning(f"Некорректный формат callback_data: {callback.data}")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        analysis_id = int(parts[1])
        rating = int(parts[2])
        if not (1 <= rating <= 5):
            logger.warning(f"Некорректная оценка: {rating}")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        try:
            analysis = await PsychoAnalysis.objects.select_related('entry__user').aget(id=analysis_id)
            if analysis.entry.user_id != user.id:
                 logger.warning(f"Пользователь {user.telegram_id} пытается оценить чужой анализ {analysis_id}")
                 await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
                 return
        except PsychoAnalysis.DoesNotExist:
            logger.warning(f"PsychoAnalysis с ID {analysis_id} не найден")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        try:
            from diary.models import AnalysisRating
            from asgiref.sync import sync_to_async
            from django.db import IntegrityError
            @sync_to_async
            def create_rating():
                rating_obj = AnalysisRating.objects.create(user=user, analysis=analysis, rating=rating)
                return rating_obj
            await create_rating()
            logger.debug(f"Пользователь {user.telegram_id} поставил оценку {rating} анализу {analysis_id}")
            current_text = callback.message.text or callback.message.caption or ""
            current_reply_markup = callback.message.reply_markup
            if current_reply_markup and hasattr(current_reply_markup, 'inline_keyboard'):
                 new_inline_keyboard = []
                 for row in current_reply_markup.inline_keyboard:
                     if not any(btn.callback_data and btn.callback_data.startswith("rate_analysis:") for btn in row):
                         new_inline_keyboard.append(row)
                 updated_reply_markup = InlineKeyboardMarkup(inline_keyboard=new_inline_keyboard)
            else:
                 updated_reply_markup = None
            await callback.message.edit_reply_markup(reply_markup=updated_reply_markup)
            await safe_answer_callback(callback, "")
        except IntegrityError:
            logger.warning(f"Пользователь {user.telegram_id} уже поставил оценку анализу {analysis_id}")
            await safe_answer_callback(callback, get_message('rating_already_submitted', language), show_alert=True)
    except ValueError as ve:
        logger.error(f"Ошибка парсинга callback_data: {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при оценке анализа пользователем {user.telegram_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.message(DiaryStates.waiting_for_text_entry)
@log_user_activity('entry_invalide', metadata_extra={'context': 'Невалидная запись'})
async def handle_invalid_entry_type(message: Message, state: FSMContext, language: str):
    """Обработка недопустимого типа сообщения"""
    try:
        invalid_msg = get_message('invalid_input', language)
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=invalid_msg,
            message_to_edit=None
        )
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке недопустимого типа сообщения: {e}")
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=get_message('error_processing', language),
            message_to_edit=None
        )

# ==================== HANDLERS ДЛЯ РЕДАКТИРОВАНИЯ И УДАЛЕНИЯ ИСТОРИИ ЗАПИСЕЙ ==================== 

@router.callback_query(F.data.startswith("calendar_select_day:"))
@log_user_activity('entry_viewed', metadata_extra={'context': 'Просмотр первой записи за день'})
async def select_day(callback: CallbackQuery, user, language: str):
    """Показ первой записи дня с пагинацией"""
    try:
        parts = callback.data.split(":")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        if not entries:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_entries_msg,
                reply_markup=get_calendar_back_keyboard(language, year, month)
            )
            await safe_answer_callback(callback, "")
            return
        sorted_entries = sorted(entries, key=lambda e: e.created_at)
        first_entry = sorted_entries[0]
        await _show_entry_page(callback.message, user, first_entry, sorted_entries, target_date, language)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при открытии дня: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language))

@router.callback_query(F.data.startswith("view_full_day_analysis:"))
@log_user_activity('analysis_viewed', metadata_extra={'context': 'Просмотр анализа дня'})
async def view_full_day_analysis(callback: CallbackQuery, user, language: str):
    """
    Показывает полный анализ дня (DailyAnalysis).
    """
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
             raise ValueError("Некорректный формат callback_data")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        target_date_str = target_date.strftime("%d.%m.%Y")
        try:
            combined_entry = await CombinedDiaryEntry.objects.select_related('daily_analysis').aget(user=user, date=target_date)
        except CombinedDiaryEntry.DoesNotExist:
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        if not hasattr(combined_entry, 'daily_analysis'):
            no_analysis_msg = get_message('no_full_analysis_yet', language)
            reanalyze_button = [
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_reanalyze_entry', language),
                        callback_data=f"reanalyze_day:{year}:{month}:{day}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_button_text('btn_back', language),
                        callback_data=f"calendar_select_day:{year}:{month}:{day}"
                    )
                ]
            ]
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=reanalyze_button)
            await safe_edit_message_text(message=callback.message, text=no_analysis_msg, reply_markup=back_keyboard)
            await safe_answer_callback(callback, "")
            return
        daily_analysis = combined_entry.daily_analysis
        analysis_header = get_message('full_day_analysis_header', language, date=target_date_str)
        analysis_msg = f"🔬 <b>{analysis_header}</b>\n"
        analysis_msg += "═" * 25 + "\n"
        if daily_analysis.overall_analysis_text and daily_analysis.overall_analysis_text.strip():
             analysis_msg += f"🧠 <b>Общий анализ дня:</b>\n{daily_analysis.overall_analysis_text}\n\n"
        else:
             analysis_msg += f"🧠 <b>Общий анализ дня:</b>\n(Общий текстовый анализ отсутствует или не был сгенерирован ИИ.)\n\n"
        mood_section = "📈 <b>Настроение и оценки</b>\n"
        mood_trend_display = dict(DailyAnalysis._meta.get_field('mood_trend').choices).get(daily_analysis.mood_trend, daily_analysis.mood_trend)
        mood_section += f"  📊 Тренд настроения: {mood_trend_display}\n"
        if combined_entry.average_mood_score and combined_entry.average_mood_score > 0:
             avg_score = combined_entry.average_mood_score
             stars_full = "⭐" * int(avg_score // 2)
             stars_half = "☆" if avg_score % 2 >= 1 else ""
             stars_empty = "☆" * (5 - len(stars_full) - len(stars_half))
             stars_display = stars_full + stars_half + stars_empty
             mood_section += f"  🌟 Средняя оценка: {avg_score:.1f}/10 {stars_display}\n"
        analysis_msg += mood_section + "\n"
        if daily_analysis.key_themes:
            analysis_msg += "🏷 <b>Ключевые темы дня:</b>\n"
            for i, theme in enumerate(daily_analysis.key_themes, 1):
                significance = theme.get('significance', 0)
                significance_percent = f"{significance:.0%}"
                analysis_msg += f"  {i}. <b>{theme['theme']}</b> ({theme.get('mentions', 1)} упоминаний) - Значимость: {significance_percent}\n"
            analysis_msg += "\n"
        if daily_analysis.emotional_patterns:
            analysis_msg += "🎭 <b>Эмоциональные паттерны:</b>\n"
            for i, pattern in enumerate(daily_analysis.emotional_patterns, 1):
                analysis_msg += f"  {i}. <b>{pattern['emotion']}</b> (частота: {pattern.get('frequency', 1)})\n"
                analysis_msg += f"     Контекст: {pattern.get('context', 'Контекст не указан')}\n"
            analysis_msg += "\n"
        if daily_analysis.insights:
            analysis_msg += "💡 <b>Инсайты:</b>\n"
            for i, insight in enumerate(daily_analysis.insights, 1):
                significance = insight.get('significance', 0)
                category = insight.get('category', 'other')
                significance_percent = f"{significance:.0%}"
                analysis_msg += f"  {i}. <b>{insight['text']}</b>\n"
                analysis_msg += f"     Категория: {category}, Значимость: {significance_percent}\n"
            analysis_msg += "\n"
        if daily_analysis.recommendations:
            analysis_msg += "🎯 <b>Персональные рекомендации:</b>\n"
            for i, rec in enumerate(daily_analysis.recommendations, 1):
                analysis_msg += f"  {i}. {rec}\n"
            analysis_msg += "\n"
        analysis_msg += "🤖 <i>Анализ выполнен искусственным интеллектом на основе ваших записей.</i>"
        keyboard_buttons = []
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_reanalyze_entry', language),
                callback_data=f"reanalyze_day:{year}:{month}:{day}"
            )
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data=f"calendar_select_day:{year}:{month}:{day}"
            )
        ])  
        analysis_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await safe_edit_message_text(message=callback.message, text=analysis_msg, reply_markup=analysis_keyboard)
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_full_day_analysis: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре полного анализа дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("entry_edit:"))
@log_user_activity('entry_edit', metadata_extra={'context': 'Редактирование конкретной записи'})
async def entry_edit(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование конкретной записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        await state_manager.set_state(state, DiaryStates.waiting_for_entry_edit)
        await state_manager.update_state_data(state, editing_entry_id=entry_id)
        formatted_text = format_entry_text_for_editing(entry.text)
        edit_msg = get_message('ask_entry_edit_with_text', language).format(old_text=formatted_text)
        await callback.message.answer(edit_msg, reply_markup=get_single_button_keyboard(language))
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при редактировании записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("entry_delete_confirm"))
async def entry_delete_confirm(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения удаления конкретной записи"""
    try:
        parts = callback.data.split(":")
        if len(parts) < 2:
            raise ValueError("Некорректный формат callback_data для entry_delete_confirm")
        entry_id = int(parts[1])
        entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
        target_date = await entry.aentry_date()

        confirm_msg = get_message('confirm_delete_entry_prompt', language)
        keyboard = get_delete_entry_confirmation_keyboard(language, entry_id, target_date)
        await safe_edit_message_text(callback.message, confirm_msg, reply_markup=keyboard)
        await safe_answer_callback(callback, "")
    except ValueError as ve:
        logger.error(f"Ошибка парсинга callback_data в entry_delete_confirm: {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except DiaryEntry.DoesNotExist:
        logger.warning(f"Пользователь {user.telegram_id} попытался подтвердить удаление несуществующей записи {entry_id}.")
        await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
        try:
            await callback.message.edit_text(
                text=get_message('entry_not_found', language),
                reply_markup=get_back_keyboard(language)
            )
        except Exception as edit_error:
            logger.debug(f"Не удалось отредактировать сообщение в entry_delete_confirm (запись не найдена): {edit_error}")

    except Exception as e:
        logger.error(f"Неожиданная ошибка при подтверждении удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("entry_prev:"))
async def entry_prev(callback: CallbackQuery, user, language: str):
    """Показ предыдущей записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        current_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        target_date = await current_entry.aentry_date()
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        if not entries:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_entries_msg,
                reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month)
            )
            await safe_answer_callback(callback, "")
            return
        sorted_entries = sorted(entries, key=lambda e: e.created_at)
        try:
            current_index = next(i for i, e in enumerate(sorted_entries) if e.id == entry_id)
        except StopIteration:
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        if current_index > 0:
            prev_entry = sorted_entries[current_index - 1]
            await _show_entry_page(callback.message, user, prev_entry, sorted_entries, target_date, language)
        else:
            await safe_answer_callback(callback, "Это первая запись.", show_alert=True)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при переходе к предыдущей записи: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("entry_next:"))
async def entry_next(callback: CallbackQuery, user, language: str):
    """Показ следующей записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        current_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        target_date = await current_entry.aentry_date()
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        if not entries:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=callback.message,
                text=no_entries_msg,
                reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month)
            )
            await safe_answer_callback(callback, "")
            return
        sorted_entries = sorted(entries, key=lambda e: e.created_at)
        try:
            current_index = next(i for i, e in enumerate(sorted_entries) if e.id == entry_id)
        except StopIteration:
            await safe_answer_callback(callback, get_message('error_generic', language))
            return
        if current_index < len(sorted_entries) - 1:
            next_entry = sorted_entries[current_index + 1]
            await _show_entry_page(callback.message, user, next_entry, sorted_entries, target_date, language)
        else:
            await safe_answer_callback(callback, "Это последняя запись.", show_alert=True)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при переходе к следующей записи: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("reanalyze_day:"))
@requires_tokens(cost=1)
async def reanalyze_day(callback: CallbackQuery, user, language: str):
    """Запускает пересчёт (полный анализ) дня."""
    try:
        await callback.answer(get_message('day_analysis_confirmed', language), show_alert=False)
        logger.debug(f"[reanalyze_day] Callback подтвержден для пользователя {user.telegram_id}")
        parts = callback.data.split(":")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        combined_entry = await diary_service.prepare_combined_entry_for_analysis(user, target_date)
        if not combined_entry:
            logger.warning(f"[reanalyze_day] Нет записей для {user.telegram_id} за {target_date}, анализ невозможен.")
            await callback.message.answer(get_message('no_entries_for_analysis', language))
            return
        processing_msg = get_message('processing', language) + " " + get_message('task_effect_analysis_started', language)
        status_message = await callback.message.answer(processing_msg)
        logger.debug(f"[reanalyze_day] Сообщение о начале обработки отправлено пользователю {user.telegram_id}")
        asyncio.create_task(_run_full_analysis_and_notify(
            user=user,
            target_date=target_date,
            chat_id=callback.message.chat.id,
            status_message_id=status_message.message_id,
            language=language,
            year=year,
            month=month,
            day=day,
            bot_instance=callback.bot
        ))
        logger.debug(f"[reanalyze_day] Фоновая задача анализа запущена для пользователя {user.telegram_id}")

    except ValueError as ve:
        logger.error(f"[reanalyze_day] Ошибка парсинга даты из callback_ {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"[reanalyze_day] Критическая ошибка при запуске пересчёта анализа дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
        
@router.message(DiaryStates.waiting_for_entry_edit, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def process_entry_edit(message: Message, state: FSMContext, user, language: str):
    """Обработка отредактированного текста записи или голосового сообщения."""  
    try:
        new_text = ""
        if message.content_type == ContentType.VOICE:
            processing_voice_msg = await message.answer(get_message('processing', language))
            success, recognized_text, error_message = await process_voice_message(
                message=message,
                context_name="Entry Edit",
                language=language,
                status_msg=processing_voice_msg
            )
            try:
                await processing_voice_msg.delete()
            except Exception as delete_error:
                logger.warning(f"[Entry Edit] Не удалось удалить сообщение статуса обработки голоса: {delete_error}")

            if not success:
                await message.answer(f"{get_message('error_processing', language)}: {error_message}")
                await state_manager.clear_state(state)
                return
            new_text = recognized_text
        elif message.content_type == ContentType.TEXT:
            new_text = message.text
        else:
            logger.warning(f"[Entry Edit] Получен неподдерживаемый тип контента: {message.content_type}")
            await message.answer(get_message('invalid_input', language))
            return
        is_valid, error_code = validate_text_entry(new_text)
        if not is_valid:
            error_msg = get_message(error_code, language)
            await message.answer(error_msg)
            logger.warning(f"Валидация отредактированного текста не пройдена: {error_code}")
            return
        state_data = await state_manager.get_state_data(state)
        entry_id = state_data.get('editing_entry_id')
        if not entry_id:
            logger.error("Не найден ID редактируемой записи в состоянии")
            await message.answer(get_message('error_generic', language))
            await state_manager.clear_state(state)
            return
        success = await diary_service.update_entry_text(entry_id, user, new_text)
        if not success:
            logger.error(f"Сервис не смог обновить запись {entry_id}")
            await message.answer(get_message('error_processing', language))
            await state_manager.clear_state(state)
            return
        try:
            entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена при попытке получить дату для навигации.")
        state_data = await state_manager.get_state_data(state)
        target_date_iso = state_data.get('editing_entry_target_date')
        target_date = date.fromisoformat(target_date_iso) if target_date_iso else await entry.aentry_date()
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        if entries:
            sorted_entries = sorted(entries, key=lambda e: e.created_at)
            await _show_entry_page(message, user, entry, sorted_entries, target_date, language)
        else:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=message,
                text=no_entries_msg,
                reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month)
            )
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке отредактированного текста записи: {e}", exc_info=True)
        await message.answer(get_message('error_processing', language))
        try:
            await state_manager.clear_state(state)
        except:
            pass

@router.callback_query(F.data.startswith("request_delete_specific_entry:"))
async def request_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения удаления конкретной записи."""
    try:
        entry_id = int(callback.data.split(":")[1])
        try:
            entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            target_date = await entry.aentry_date()
        except DiaryEntry.DoesNotExist:
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        confirm_msg = get_message('confirm_delete_entry_prompt', language)
        confirm_keyboard = get_delete_entry_confirmation_keyboard(entry_id, target_date, language)
        await safe_edit_message_text(message=callback.message, text=confirm_msg, reply_markup=confirm_keyboard)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при запросе подтверждения удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("delete_entire_day:"))
async def request_delete_entire_day(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения на удаление всех записей за день."""
    try:
        date_str = callback.data.split(":", 1)[1]
        parts = date_str.split("-")
        if len(parts) != 3:
            raise ValueError("Некорректный формат даты")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        target_date = date(year, month, day)
        confirm_msg = get_message('confirm_delete_entire_day_prompt', language).format(date=target_date.strftime('%d.%m.%Y'))
        confirm_buttons = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_confirm_delete_day', language),
                    callback_data=f"confirm_delete_entire_day:{target_date.isoformat()}"
                ),
                InlineKeyboardButton(
                    text=get_button_text('btn_cancel', language),
                    callback_data="archive"
                )
            ]
        ]
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=confirm_buttons)
        await safe_edit_message_text(
            message=callback.message,
            text=confirm_msg,
            reply_markup=confirm_keyboard
        )
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data для удаления дня: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при запросе подтверждения удаления дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_delete_specific_entry:"))
async def confirm_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Подтверждение удаления конкретной записи."""
    try:
        parts = callback.data.split(":")
        entry_id = int(parts[1])
        if len(parts) < 3:
            raise ValueError("Некорректный формат callback_data: отсутствует дата")
        target_date_iso = parts[2] 
        try:
            target_date = date.fromisoformat(target_date_iso) 
        except ValueError as ve:
            logger.error(f"Некорректный формат даты ISO в callback_data '{target_date_iso}': {ve}")
            raise ValueError(f"Некорректный формат даты: {target_date_iso}")
        success = await diary_service.delete_entry_and_update_combined(entry_id, user)
        if success:
            alert_msg = get_message('entry_deleted_success', language)
            await safe_answer_callback(callback, text=alert_msg, show_alert=True)
            entries = await diary_service.get_user_entries_for_date(user, target_date) 
            if entries:
                sorted_entries = sorted(entries, key=lambda e: e.created_at)
                await _show_entry_page(callback.message, user, sorted_entries[0], sorted_entries, target_date, language) 
            else:
                no_entries_msg = get_message('archive_empty', language)
                await safe_edit_message_text(
                    message=callback.message,
                    text=no_entries_msg,
                    reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month) 
                )
        else:
             error_alert_msg = get_message('error_processing', language)
             await safe_answer_callback(callback, text=error_alert_msg, show_alert=True)
             entries = await diary_service.get_user_entries_for_date(user, target_date) 
             if entries:
                 sorted_entries = sorted(entries, key=lambda e: e.created_at)
                 await _show_entry_page(callback.message, user, sorted_entries[0], sorted_entries, target_date, language) 
             else:
                 no_entries_msg = get_message('archive_empty', language)
                 await safe_edit_message_text(
                     message=callback.message,
                     text=no_entries_msg,
                     reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month) 
                 )
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data для удаления записи: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("confirm_delete_entire_day:"))
async def confirm_delete_entire_day(callback: CallbackQuery, user, language: str):
    """Подтверждение и выполнение удаления всех записей за день."""
    try:
        date_str = callback.data.split(":", 1)[1]
        target_date = date.fromisoformat(date_str)
        success = await diary_service.delete_all_entries_for_day(user, target_date)
        if success:
            success_msg = get_message('day_deleted_success', language)
            await safe_answer_callback(callback, success_msg, show_alert=True)
            try:
                calendar_keyboard = await get_smart_calendar_keyboard(user, language)
                calendar_msg = get_message('archive_menu', language)
                await edit_or_send_message(
                    bot=callback.bot,
                    chat_id=callback.message.chat.id,
                    text=calendar_msg,
                    reply_markup=calendar_keyboard,
                    message_to_edit=callback.message
                )
            except Exception as nav_error:
                logger.error(f"Ошибка при возврате в календарь: {nav_error}", exc_info=True)
                try:
                    calendar_keyboard = await get_smart_calendar_keyboard(user, language)
                    await callback.message.answer(text=calendar_msg, reply_markup=calendar_keyboard)
                except Exception as fallback_error:
                    logger.error(f"Фолбэк ошибка при отправке календаря: {fallback_error}")
                    await callback.message.answer(get_message('archive_menu', language), reply_markup=await get_smart_calendar_keyboard(user, language))
        else:
            error_msg = get_message('error_processing', language)
            await safe_answer_callback(callback, error_msg, show_alert=True)
            logger.warning(f"Не удалось удалить записи за {target_date}.")
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("cancel_delete_specific_entry:"))
async def cancel_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Отмена удаления конкретной записи."""
    try:
        parts = callback.data.split(":")
        entry_id = int(parts[1])
        if len(parts) < 3:
            raise ValueError("Некорректный формат callback_data: отсутствует дата")
        target_date_iso = parts[2] 
        try:
            target_date = date.fromisoformat(target_date_iso) 
        except ValueError as ve:
            logger.error(f"Некорректный формат даты ISO в callback_data '{target_date_iso}': {ve}")
            raise ValueError(f"Некорректный формат даты: {target_date_iso}")
        entries = await diary_service.get_user_entries_for_date(user, target_date) 
        if entries:
            sorted_entries = sorted(entries, key=lambda e: e.created_at)
            await _show_entry_page(callback.message, user, sorted_entries[0], sorted_entries, target_date, language) 
        else:
             no_entries_msg = get_message('archive_empty', language)
             await safe_edit_message_text(
                 message=callback.message,
                 text=no_entries_msg,
                 reply_markup=get_calendar_back_keyboard(language, target_date.year, target_date.month) 
             )
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data для отмены удаления записи: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
         logger.error(f"Ошибка при отмене удаления записи {entry_id}: {e}", exc_info=True)
         await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def _process_analysis_result(
    entry: DiaryEntry,
    analysis_result: dict,
    status_msg,
    language: str,
    state: FSMContext,
    user: User,
    processing_time: float = 0.0,
    context: str = 'new_entry'
):
    """Обрабатывает результат анализа для уточнений и комментариев."""
    try:
        result_data = {}
        if not analysis_result or not analysis_result.get('success'):
            comment, recommendation, analysis_text, _ = format_api_error_for_analysis(analysis_result, language, context in ['clarification', 'comment_analysis'])
            mood_score = 5
        else:
            result_data = analysis_result.get('result', {})
            mood_score = result_data.get('mood_score', 5)
            comment = result_data.get('comment', 'Анализ записан')
            recommendation = result_data.get('recommendation', 'Продолжайте вести дневник')
            analysis_text = result_data.get('analysis', 'Текст проанализирован.')
        finalize_now = (context in ['clarification', 'comment_analysis'])
        await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {}),
            processing_time=processing_time,
            finalize_processing=finalize_now
        )
        if context in ['clarification', 'comment_analysis']:
            combined_entry = await daily_state_service.get_daily_state(user, await entry.aentry_date())
            if combined_entry and 'updated_ai_state_data' in result_data:
                new_state = result_data['updated_ai_state_data']
            else:
                new_state = analysis_text
            await daily_state_service.update_daily_state(
                combined_entry=combined_entry,
                new_ai_state_data=new_state,
                latest_mood_score=mood_score
            )
            logger.debug(f"[_process_analysis_result] Обновлен CombinedDiaryEntry для {context} записи {entry.id}")
        final_text = get_message('entry_saved', language, score=mood_score, mood=get_message(f'mood_{mood_score}', language), comment=comment, recommendation=recommendation)
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[])
        try:
            current_analysis = await PsychoAnalysis.objects.aget(entry=entry)
            user_rating_exists = await current_analysis.user_ratings.filter(user=user).aexists()
        except PsychoAnalysis.DoesNotExist:
            user_rating_exists = False
            logger.warning(f"PsychoAnalysis для записи {entry.id} не найден при добавлении кнопок оценки в _process_analysis_result")
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
                 logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в _process_analysis_result, не добавляем кнопки оценки.")
        if context != 'comment_analysis':
            try:
                current_entry = await DiaryEntry.objects.aget(id=entry.id)
                has_user_comment = bool(current_entry.user_comment)
            except DiaryEntry.DoesNotExist:
                has_user_comment = True
                logger.warning(f"Запись {entry.id} не найдена при проверке комментария в _process_analysis_result")
            if not has_user_comment:
                add_comment_button = InlineKeyboardButton(
                    text=get_button_text('btn_add_comment', language),
                    callback_data=f"request_add_comment:{entry.id}"
                )
                if isinstance(reply_markup, InlineKeyboardMarkup):
                     reply_markup.inline_keyboard.append([add_comment_button])
                else:
                     logger.warning(f"reply_markup не является InlineKeyboardMarkup: {type(reply_markup)} в _process_analysis_result, не добавляем кнопку 'Добавить комментарий'.")
        back_buttons = [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data="main_menu"
            )
        ]
        reply_markup.inline_keyboard.append(back_buttons)
        await status_msg.edit_text(final_text, reply_markup=reply_markup)
        if context in ['clarification', 'comment_analysis']:
            await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка в _process_analysis_result: {e}", exc_info=True)
        if status_msg:
            try:
                await safe_edit_message_text(status_msg, get_message('error_processing', language))
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке в _process_analysis_result: {edit_error}")
        if context in ['clarification', 'comment_analysis']:
            try:
                await state_manager.clear_state(state)
            except Exception as state_error:
                logger.error(f"Не удалось очистить состояние в _process_analysis_result после ошибки: {state_error}")

async def _show_entry_page(message, user, entry, entries, target_date, language):
    """
    Отображает текущую запись с клавиатурой пагинации.
    Использует edit_or_send_message для надежного обновления.
    Логика клавиатуры вынесена в отдельную функцию.
    """
    try:
        current_index = entries.index(entry)
        total = len(entries)
        try:
            entry_datetime_str = await entry.alocalized_created_at() 
            
        except Exception as tz_error:
            logger.error(f"Ошибка при получении локализованного времени записи {entry.id}: {tz_error}")
            entry_datetime_str = entry.created_at.strftime('%d.%m.%Y %H:%M UTC')
        mood_score_display = "Н/Д"
        analysis_comment = ""
        analysis_recommendation = ""
        try:
            analysis = await PsychoAnalysis.objects.aget(entry=entry)
            mood_score_display = str(analysis.mood_score)
            if analysis.comment:
                analysis_comment = analysis.comment
            if analysis.recommendation:
                analysis_recommendation = analysis.recommendation
        except PsychoAnalysis.DoesNotExist:
            pass
        header = f"📅 <b>{entry_datetime_str}</b>\n"
        entry_content = get_message('entry_header', language, 
                                current_index=current_index + 1, 
                                total=total, 
                                entry_text=entry.text)
        analysis_section = ""
        if analysis_comment:
            analysis_section = get_message('analysis_section', language, 
                                        analysis_comment=analysis_comment)
        if analysis_recommendation:
            analysis_section += get_message('recommendation_section', language, 
                                        analysis_recommendation=analysis_recommendation)
        footer = get_message('entry_footer', language, 
                    mood_score_display=mood_score_display)
        text = header + entry_content + analysis_section + footer
        is_day_analyzed = False
        try:
            combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_date)
            is_day_analyzed = combined_entry.is_analyzed
        except CombinedDiaryEntry.DoesNotExist:
            pass
        keyboard = get_entry_page_keyboard(
            entry_id=entry.id,
            current_index=current_index,
            total_entries=total,
            target_date=target_date,
            language=language,
            is_day_analyzed=is_day_analyzed
        )
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=text,
            reply_markup=keyboard,
            message_to_edit=message
        )
    except Exception as e:
        logger.error(f"Ошибка при отображении страницы записи: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_generic', language))
        except:
            pass

async def _run_full_analysis_and_notify(
    user: User,
    target_date: date,
    chat_id: int,
    status_message_id: int,
    language: str,
    year: int,
    month: int,
    day: int,
    bot_instance
):
    """Фоновая задача для выполнения полного анализа и уведомления пользователя."""
    from diary.services.full_day_analysis_service import perform_full_day_analysis
    try:
        logger.debug(f"[_run_full_analysis_and_notify] Начало фоновой задачи анализа дня {target_date} для пользователя {user.telegram_id}")
        analysis_result = await perform_full_day_analysis(user, target_date)
        if analysis_result["success"]:
            success_msg = analysis_result["message"]
            logger.debug(f"[_run_full_analysis_and_notify] Анализ дня {target_date} для {user.telegram_id} успешен: {success_msg}")
            daily_analysis = analysis_result.get("daily_analysis")
            analysis_summary_text = get_message('analysis_recalculated', language)
            if daily_analysis and daily_analysis.overall_analysis_text:
                 analysis_summary_text += f"\n\n{daily_analysis.overall_analysis_text[:200]}..."
            try:
                await bot_instance.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=analysis_summary_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="🔬 Просмотреть анализ",
                            callback_data=f"view_full_day_analysis:{year}:{month}:{day}"
                        )]
                    ])
                )
                logger.debug(f"[_run_full_analysis_and_notify] Сообщение обработки отредактировано для пользователя {user.telegram_id}")
            except Exception as edit_error:
                logger.warning(f"[_run_full_analysis_and_notify] Не удалось отредактировать сообщение обработки: {edit_error}. Отправляем новое.")
                await bot_instance.send_message(
                    chat_id=chat_id,
                    text=analysis_summary_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="🔬 Просмотреть анализ",
                            callback_data=f"view_full_day_analysis:{year}:{month}:{day}"
                        )]
                    ])
                )
        else:
            error_msg = analysis_result["message"]
            logger.error(f"[_run_full_analysis_and_notify] Ошибка анализа дня {target_date} для {user.telegram_id}: {error_msg}")
            try:
                await bot_instance.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"{get_message('error_processing', language)}: {error_msg}"
                )
                logger.debug(f"[_run_full_analysis_and_notify] Сообщение об ошибке отправлено пользователю {user.telegram_id}")
            except Exception as edit_error:
                logger.warning(f"[_run_full_analysis_and_notify] Не удалось отредактировать сообщение об ошибке: {edit_error}. Отправляем новое.")
                await bot_instance.send_message(
                    chat_id=chat_id,
                    text=f"{get_message('error_processing', language)}: {error_msg}"
                )
    except Exception as e:
        logger.error(f"[_run_full_analysis_and_notify] Критическая ошибка при анализе/уведомлении: {e}", exc_info=True)
        try:
            await bot_instance.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=get_message('error_processing', language)
            )
        except Exception as edit_error:
            logger.error(f"[_run_full_analysis_and_notify] Критическая ошибка при отправке сообщения об ошибке: {edit_error}")
            await bot_instance.send_message(
                chat_id=chat_id,
                text=get_message('error_processing', language)
            )