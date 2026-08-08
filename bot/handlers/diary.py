"""Diary handlers (transport-only)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext
from datetime import date

from messages import get_message
from diary.services import smart_prompt_manager
from diary.services.diary_display_service import diary_display_service
from bot.decorators.token_decorator import requires_tokens
from bot.decorators.analytics_decorator import log_user_activity
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_single_button_keyboard,
    format_entry_text_for_editing,
)
from bot.utils.audio_utils import process_voice_message
from bot.utils.validation_utils import validate_incoming_message, validate_text_entry
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.decorators import async_error_handler
from bot.presenters.diary_presenter import (
    build_new_entry_outcome_view,
    build_entry_saved_view,
    build_delete_entire_day_confirm_view,
)
from bot.services.diary_service import diary_service
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from users.models import User

router = Router()
logger = logging.getLogger(__name__)

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
    is_valid, error_code = validate_incoming_message(message)
    if not is_valid:
        await message.answer(get_message(error_code, language))
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
        response = await diary_service.process_new_entry_use_case(
            user=user,
            entry_text=entry_text,
            language=language,
            entry_datetime=entry_datetime
        )
        outcome_view = await build_new_entry_outcome_view(response, user, language)
        await status_msg.edit_text(
            outcome_view['text'],
            reply_markup=outcome_view['reply_markup'],
        )
        if outcome_view['fsm_action'] == 'clarification':
            await state_manager.update_state_data(
                state,
                clarifying_entry_id=outcome_view['clarifying_entry_id'],
                clarification_questions=outcome_view['clarification_questions'],
            )
            await state_manager.set_state(state, DiaryStates.asking_clarifying_questions)
            return
        await state_manager.clear_state(state)
        if outcome_view.get('should_trigger_prompt'):
            try:
                asyncio.create_task(
                    smart_prompt_manager.on_entry_saved(user, outcome_view['entry'], language)
                )
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
        diary_entry = await diary_service.get_user_entry_by_id(user, entry_id)
        if not diary_entry:
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
        clarification_answers_dict = diary_service.build_clarification_answers_map(
            clarification_questions=clarification_questions,
            clarification_text=clarification_text,
        )
        response = await diary_service.process_clarification_answers_use_case(
            user=user,
            diary_entry=diary_entry,
            clarification_answers_dict=clarification_answers_dict,
            language=language
        )
        if not response.success:
            await status_message.edit_text(
                response.message or get_message('error_processing', language)
            )
            await state_manager.clear_state(state)
            return
        result = response.data or {}
        view = await build_entry_saved_view(
            entry=result['entry'],
            analysis=result.get('analysis'),
            user=user,
            language=language,
        )
        await status_message.edit_text(view['text'], reply_markup=view['reply_markup'])
        if view.get('should_clear_state', True):
            await state_manager.clear_state(state)
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
        use_case_result = await diary_service.start_add_comment_use_case(user, entry_id)
        if use_case_result['mode'] == 'not_found':
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        if use_case_result['mode'] == 'already_added':
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
        diary_entry = await diary_service.get_user_entry_by_id(user, entry_id)
        if not diary_entry:
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
        response = await diary_service.process_user_comment_use_case(
            user=user,
            diary_entry=diary_entry,
            user_comment_text=user_comment_text,
            language=language
        )
        if not response.success:
            raise RuntimeError(response.message or 'Ошибка обработки комментария')
        result = response.data or {}
        view = await build_entry_saved_view(
            entry=result['entry'],
            analysis=result.get('analysis'),
            user=user,
            language=language,
        )
        await status_message.edit_text(view['text'], reply_markup=view['reply_markup'])
        if view.get('should_clear_state', True):
            await state_manager.clear_state(state)
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

        result = await diary_display_service.submit_analysis_rating_use_case(analysis_id, user, rating)

        if result['success']:
            logger.debug(
                f"[diary.rate_analysis] user_id={user.id} analysis_id={analysis_id} rating={rating}"
            )
            updated_keyboard = await diary_display_service.remove_rating_buttons_from_keyboard(
                callback.message.reply_markup
            )
            await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
            await safe_answer_callback(callback, "")
        elif result['error'] == 'already_rated':
            await safe_answer_callback(callback, get_message('rating_already_submitted', language), show_alert=True)
        else:
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

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


@router.callback_query(F.data.startswith("calendar_select_day:"))
@log_user_activity('entry_viewed', metadata_extra={'context': 'Просмотр первой записи за день'})
async def select_day(callback: CallbackQuery, user, language: str):
    """Показ первой записи дня с пагинацией"""
    try:
        parts = callback.data.split(":")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        day_view = await diary_display_service.build_day_first_entry_view(user, target_date, language)
        if not day_view.get('success'):
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        if day_view['mode'] == 'empty':
            await safe_edit_message_text(
                message=callback.message,
                text=day_view['text'],
                reply_markup=day_view['keyboard']
            )
            await safe_answer_callback(callback, "")
            return
        await _show_entry_page(
            callback.message,
            user,
            day_view['entry'],
            day_view['entries'],
            day_view['target_date'],
            language,
        )
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

        result = await diary_display_service.build_full_day_analysis_view(
            user=user,
            target_date=target_date,
            language=language,
        )

        if result['success']:
            await safe_edit_message_text(message=callback.message, text=result['text'], reply_markup=result['keyboard'])
        else:
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

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
        entry = await diary_service.get_user_entry_by_id(user, entry_id)
        if not entry:
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
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
        view = await diary_display_service.build_entry_delete_confirmation_view(
            user=user,
            entry_id=entry_id,
            language=language,
        )
        if not view.get('success'):
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        if view.get('mode') == 'not_found':
            logger.warning(f"Пользователь {user.telegram_id} попытался подтвердить удаление несуществующей записи {entry_id}.")
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            try:
                await callback.message.edit_text(
                    text=view['text'],
                    reply_markup=view['keyboard']
                )
            except Exception as edit_error:
                logger.debug(f"Не удалось отредактировать сообщение в entry_delete_confirm (запись не найдена): {edit_error}")
            return

        await safe_edit_message_text(callback.message, view['text'], reply_markup=view['keyboard'])
        await safe_answer_callback(callback, "")
    except ValueError as ve:
        logger.error(f"Ошибка парсинга callback_data в entry_delete_confirm: {callback.data} - {ve}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Неожиданная ошибка при подтверждении удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("entry_prev:"))
async def entry_prev(callback: CallbackQuery, user, language: str):
    """Показ предыдущей записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        result = await diary_display_service.get_entry_with_pagination(user, entry_id, 'prev')

        if result['success']:
            await _show_entry_page(callback.message, user, result['entry'], result['entries'], result['target_date'], language)
            await safe_answer_callback(callback, "")
        elif result['error'] == 'first_entry':
            await safe_answer_callback(callback, "Это первая запись.", show_alert=True)
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))

    except Exception as e:
        logger.error(f"Ошибка при переходе к предыдущей записи: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("entry_next:"))
async def entry_next(callback: CallbackQuery, user, language: str):
    """Показ следующей записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        result = await diary_display_service.get_entry_with_pagination(user, entry_id, 'next')

        if result['success']:
            await _show_entry_page(callback.message, user, result['entry'], result['entries'], result['target_date'], language)
            await safe_answer_callback(callback, "")
        elif result['error'] == 'last_entry':
            await safe_answer_callback(callback, "Это последняя запись.", show_alert=True)
        else:
            await safe_answer_callback(callback, get_message('error_generic', language))

    except Exception as e:
        logger.error(f"Ошибка при переходе к следующей записи: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("reanalyze_day:"))
@requires_tokens(cost=1)
async def reanalyze_day(callback: CallbackQuery, user, language: str):
    """Запускает пересчёт (полный анализ) дня."""
    try:
        parts = callback.data.split(":")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        use_case_result = await diary_service.start_full_day_reanalysis_use_case(
            user, target_date, language
        )
        await callback.answer(use_case_result.get('confirm_alert', ''), show_alert=False)
        if use_case_result['mode'] == 'no_entries':
            await callback.message.answer(use_case_result['text'])
            return
        status_message = await callback.message.answer(use_case_result['status_text'])
        asyncio.create_task(_run_full_analysis_and_notify(
            user=user,
            target_date=target_date,
            chat_id=callback.message.chat.id,
            status_message_id=status_message.message_id,
            language=language,
            bot_instance=callback.bot
        ))
        logger.debug(
            f"[diary.reanalyze_day] started user_id={user.id} date={target_date}"
        )

    except ValueError as ve:
        logger.error(f"[diary.reanalyze_day] bad callback date {callback.data}: {ve}")
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
        state_data = await state_manager.get_state_data(state)
        target_date_iso = state_data.get('editing_entry_target_date')
        response = await diary_service.process_entry_edit_use_case(
            user=user,
            entry_id=entry_id,
            new_text=new_text,
            language=language,
            target_date_iso=target_date_iso,
        )
        if not response.success:
            await message.answer(response.message or get_message('error_processing', language))
            await state_manager.clear_state(state)
            return
        day_view = (response.data or {}).get('day_view', {})
        if day_view.get('mode') == 'entries':
            await _show_entry_page(
                message,
                user,
                day_view['entry'],
                day_view['entries'],
                day_view['target_date'],
                language,
            )
        else:
            no_entries_msg = get_message('archive_empty', language)
            await safe_edit_message_text(
                message=message,
                text=no_entries_msg,
                reply_markup=day_view['keyboard']
            )
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке отредактированного текста записи: {e}", exc_info=True)
        await message.answer(get_message('error_processing', language))
        try:
            await state_manager.clear_state(state)
        except Exception as clear_error:
            logger.debug(f"[process_entry_edit] clear_state failed: {clear_error}")

@router.callback_query(F.data.startswith("request_delete_specific_entry:"))
async def request_delete_specific_entry(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения удаления конкретной записи."""
    try:
        entry_id = int(callback.data.split(":")[1])
        view = await diary_display_service.build_entry_delete_confirmation_view(
            user=user,
            entry_id=entry_id,
            language=language,
        )
        if not view.get('success'):
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return
        if view.get('mode') == 'not_found':
            await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
            return
        await safe_edit_message_text(message=callback.message, text=view['text'], reply_markup=view['keyboard'])
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
        confirm_view = build_delete_entire_day_confirm_view(target_date, language)
        await safe_edit_message_text(
            message=callback.message,
            text=confirm_view['text'],
            reply_markup=confirm_view['keyboard']
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
        response = await diary_service.process_delete_specific_entry_use_case(
            user=user,
            entry_id=entry_id,
            language=language,
            target_date_iso=target_date_iso,
        )
        if not response.success:
            await safe_answer_callback(callback, response.message or get_message('error_generic', language), show_alert=True)
            return
        payload = response.data or {}
        await safe_answer_callback(callback, text=payload.get('alert_message', get_message('error_processing', language)), show_alert=True)
        day_view = payload.get('day_view', {})
        if day_view.get('mode') == 'entries':
            await _show_entry_page(
                callback.message,
                user,
                day_view['entry'],
                day_view['entries'],
                day_view['target_date'],
                language,
            )
        else:
            await safe_edit_message_text(
                message=callback.message,
                text=day_view['text'],
                reply_markup=day_view['keyboard']
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
        delete_result = await diary_service.delete_entire_day_use_case(user, target_date, language)
        if delete_result['success']:
            await safe_answer_callback(callback, delete_result['alert_message'], show_alert=True)
            archive_view = delete_result['archive_view']
            try:
                await edit_or_send_message(
                    bot=callback.bot,
                    chat_id=callback.message.chat.id,
                    text=archive_view['text'],
                    reply_markup=archive_view['keyboard'],
                    message_to_edit=callback.message
                )
            except Exception as nav_error:
                logger.error(f"Ошибка при возврате в календарь: {nav_error}", exc_info=True)
                try:
                    await callback.message.answer(
                        text=archive_view['text'],
                        reply_markup=archive_view['keyboard'],
                    )
                except Exception as fallback_error:
                    logger.error(f"Фолбэк ошибка при отправке календаря: {fallback_error}")
                    await callback.message.answer(
                        archive_view['text'],
                        reply_markup=archive_view['keyboard'],
                    )
        else:
            await safe_answer_callback(callback, delete_result['alert_message'], show_alert=True)
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
        _entry_id = int(parts[1])
        if len(parts) < 3:
            raise ValueError("Некорректный формат callback_data: отсутствует дата")
        target_date_iso = parts[2] 
        response = await diary_service.process_cancel_delete_specific_entry_use_case(
            user=user,
            language=language,
            target_date_iso=target_date_iso,
        )
        if not response.success:
            await safe_answer_callback(callback, response.message or get_message('error_generic', language), show_alert=True)
            return
        day_view = (response.data or {}).get('day_view', {})
        if day_view.get('mode') == 'entries':
            await _show_entry_page(
                callback.message,
                user,
                day_view['entry'],
                day_view['entries'],
                day_view['target_date'],
                language,
            )
        else:
            await safe_edit_message_text(
                message=callback.message,
                text=day_view['text'],
                reply_markup=day_view['keyboard']
            )
    except (ValueError, IndexError) as e:
        logger.error(f"Некорректный формат даты в callback_data для отмены удаления записи: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
         logger.error(f"Ошибка при отмене удаления записи: {e}", exc_info=True)
         await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

async def _show_entry_page(message, user, entry, entries, target_date, language):
    """
    Отображает текущую запись с клавиатурой пагинации.
    Использует edit_or_send_message для надежного обновления.
    Логика форматирования вынесена в diary_display_service.
    """
    try:
        result = await diary_display_service.format_entry_for_display(entry, entries, target_date, language)

        if result['success']:
            await edit_or_send_message(
                bot=message.bot,
                chat_id=message.chat.id,
                text=result['text'],
                reply_markup=result['keyboard'],
                message_to_edit=message
            )
        else:
            logger.error(f"Ошибка при форматировании записи: {result.get('error')}")
            try:
                await message.answer(get_message('error_generic', language))
            except Exception as send_error:
                logger.debug(f"[_show_entry_page] failed to send format error: {send_error}")

    except Exception as e:
        logger.error(f"Ошибка при отображении страницы записи: {e}", exc_info=True)
        try:
            await message.answer(get_message('error_generic', language))
        except Exception as send_error:
            logger.debug(f"[_show_entry_page] failed to send generic error: {send_error}")

async def _run_full_analysis_and_notify(
    user: User,
    target_date: date,
    chat_id: int,
    status_message_id: int,
    language: str,
    bot_instance
):
    """Transport: use-case анализа дня → edit/send уведомления."""
    from diary.services.full_day_analysis_service import build_full_day_reanalysis_notification
    try:
        notification = await build_full_day_reanalysis_notification(
            user=user,
            target_date=target_date,
            language=language,
        )
        text = notification.get("text") or get_message("error_processing", language)
        reply_markup = notification.get("reply_markup")
        try:
            await bot_instance.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as edit_error:
            logger.warning(
                f"[diary.full_day_notify] edit failed user_id={user.id}: {edit_error}; sending new"
            )
            await bot_instance.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
    except Exception as e:
        logger.error(
            f"[diary.full_day_notify] failed user_id={user.id} date={target_date}: {e}",
            exc_info=True,
        )
        try:
            await bot_instance.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=get_message('error_processing', language)
            )
        except Exception as edit_error:
            logger.error(
                f"[_run_full_analysis_and_notify] Критическая ошибка при отправке сообщения об ошибке: {edit_error}"
            )
            await bot_instance.send_message(
                chat_id=chat_id,
                text=get_message('error_processing', language)
            )