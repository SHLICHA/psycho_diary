"""
Handlers для работы с дневником
"""

import asyncio
import logging
import pytz

from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import date, timedelta

from messages import get_message, get_button_text
from diary.models import CombinedDiaryEntry, DiaryEntry, DailyAnalysis, TherapyTask, PsychoAnalysis
from diary.services import daily_state_service
from bot.states.diary_states import DiaryStates
from bot.keyboards import (
    get_cancel_keyboard,
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
from bot.utils.validation_utils import validate_incoming_message, validate_text_entry
from bot.utils.state_manager import state_manager
from bot.utils.message_utils import safe_edit_message_text, edit_or_send_message
from bot.utils.callback_utils import safe_answer_callback
from bot.services.task_service import task_service
from bot.services.diary_service import diary_service, update_daily_state, get_entry_date
from bot.services.psycho_analysis_service import psycho_analysis_service
from bot.services.yandex_speechkit import yandex_speechkit_service
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt
from users.models import User

router = Router()
logger = logging.getLogger(__name__)

# ==================== ОСНОВНЫЕ HANDLERS ДНЕВНИКА ====================

@router.callback_query(F.data == "new_entry")
async def new_entry(callback: CallbackQuery, state: FSMContext, language: str):
    """Создание новой записи - предложение ввести текст или голосовое сообщение"""
    logger.debug(f"Запрос на создание новой записи от пользователя {callback.from_user.id}")
    try:
        await state_manager.set_state(state, DiaryStates.waiting_for_text_entry)
        entry_msg = get_message('ask_entry', language)
        await safe_edit_message_text(
            message=callback.message,
            text=entry_msg,
            reply_markup=get_cancel_keyboard(language)
        )
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при предложении создания записи: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.message(DiaryStates.waiting_for_text_entry, F.content_type.in_({ContentType.TEXT, ContentType.VOICE}))
async def process_any_entry(message: Message, state: FSMContext, user, language: str):
    status_msg = None
    try:
        is_valid, error_code = validate_incoming_message(message)
        if not is_valid:
            await message.answer(get_message(error_code, language))
            return
        entry_text = ""
        voice_file_id = None
        duration = 0
        if message.content_type == ContentType.VOICE:
            voice = message.voice
            duration = voice.duration
            voice_file_id = voice.file_id
        entry_datetime = message.date
        status_msg = await message.answer(get_message('processing', language))
        if message.content_type == ContentType.VOICE:
            file = await message.bot.get_file(voice_file_id)
            voice_bytes = (await message.bot.download_file(file.file_path)).read()
            rec_result = await yandex_speechkit_service.recognize_voice(voice_bytes, language, 'oggopus')
            if not rec_result['success']:
                await status_msg.edit_text(f"{get_message('error_processing', language)}: {rec_result.get('message', 'Unknown')}")
                return
            punct_result = await deepseek_api_service.punctuate_and_format_text(rec_result['result'], language)
            entry_text = punct_result.get('result') or rec_result['result']
        else:
            entry_text = message.text
        diary_entry = await diary_service.create_text_entry(
            user=user,
            text=entry_text,
            language=language,
            entry_datetime=entry_datetime
        ) if message.content_type == ContentType.TEXT else await diary_service.create_voice_entry(
            user=user,
            voice_file_id=voice_file_id,
            duration=duration,
            recognized_text=entry_text,
            language=language,
            entry_datetime=entry_datetime
        )
        entry_date = await diary_entry.aentry_date()
        combined_entry, _ = await diary_service.get_or_update_daily_state_with_entries(user, diary_entry)
        all_entries_text = await diary_service.get_combined_entry_text(user, entry_date)
        ai_state_data = combined_entry.ai_state_data if combined_entry else ""
        base_user_profile = await user.aget_profile_data() # Получаем базовые данные
        extended_user_context = {
            "first_name": base_user_profile.get('first_name', 'Пользователь'),
            "awareness_level": base_user_profile.get('awareness_level', 1),
            "is_premium": base_user_profile.get('is_premium', False),
            "entries_count": base_user_profile.get('entries_count', 0), 
            # Добавляем новые поля из модели User
            "personality_traits": user.personality_traits, # Это словарь {trait: weight}
            "life_facts": user.life_facts, # Это список строк
            "hobbies": user.hobbies, # Это список строк
            "core_values": user.core_values, # Это список строк
            "triggers": user.triggers, # Это список строк
            "strengths": user.strengths, # Это список строк
            "areas_for_growth": user.areas_for_growth, # Это список строк
        }

        prompt = get_prompt(
            key='incremental_day_analysis',
            language=language,
            all_entries_combined=all_entries_text,
            new_entry_text=entry_text,
            ai_state_data=ai_state_data,
            # Передаем данные из расширенного контекста
            first_name=extended_user_context["first_name"],
            awareness_level=extended_user_context["awareness_level"],
            is_premium=extended_user_context["is_premium"],
            # Передаем новые данные (если промпт обновлен)
            user_personality_traits=extended_user_context["personality_traits"],
            user_life_facts=extended_user_context["life_facts"],
            user_hobbies=extended_user_context["hobbies"],
            user_core_values=extended_user_context["core_values"],
            user_triggers=extended_user_context["triggers"],
            user_strengths=extended_user_context["strengths"],
            user_areas_for_growth=extended_user_context["areas_for_growth"],
            entries_count=extended_user_context["entries_count"],
        )
        analysis_result = await deepseek_api_service.send_prompt_and_parse(prompt, language)
        await _process_analysis_result(
            entry=diary_entry,
            analysis_result=analysis_result,
            status_msg=status_msg,
            language=language,
            state=state,
            user=user
        )
    except Exception as e:
        logger.error(f"Ошибка в process_any_entry: {e}", exc_info=True)
        if status_msg:
            try:
                await safe_edit_message_text(status_msg, get_message('error_processing', language))
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке: {edit_error}")
        await state_manager.clear_state(state)

@router.message(DiaryStates.asking_clarifying_questions)
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
        clarification_text = message.text.strip()
        if not clarification_text:
            await message.answer(get_message('invalid_input', language))
            return
        answers_list = [ans.strip() for ans in clarification_text.split("\n") if ans.strip()]
        clarification_answers_dict = {}
        for i, q in enumerate(clarification_questions):
            clarification_answers_dict[q] = answers_list[i] if i < len(answers_list) else "[Ответ не получен]"
        diary_entry.clarification_answers = clarification_answers_dict
        await sync_to_async(diary_entry.save)(update_fields=['clarification_answers'])
        entry_date = await diary_entry.aentry_date()
        user_profile = await user.aget_profile_data()
        first_name = user_profile.get('first_name', 'Пользователь')
        awareness_level = user_profile['awareness_level']
        logger.debug(f'Профиль пользователя: {user_profile}')
        combined_entry = await daily_state_service.get_daily_state(user, entry_date)
        ai_state_data = combined_entry.ai_state_data if combined_entry else ""
        prompt = get_prompt(
            key='clarification_analysis',
            language=language,
            original_text=diary_entry.text,
            clarification_questions="\n".join(clarification_questions),
            clarification_answers="\n".join([f"{q}: {a}" for q, a in clarification_answers_dict.items()]),
            first_name=first_name,
            awareness_level=awareness_level,
        )
        status_message = await message.answer(get_message('processing', language))
        analysis_result = await deepseek_api_service.send_prompt_and_parse(prompt, language)
        await _process_analysis_result(
            entry=diary_entry,
            analysis_result=analysis_result,
            status_msg=status_message,
            language=language,
            state=state,
            user=user
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке уточнений: {e}", exc_info=True)
        if status_message:
            await status_message.edit_text(get_message('error_processing', language))
        await state_manager.clear_state(state)

@router.message(DiaryStates.waiting_for_text_entry)
async def handle_invalid_entry_type(message: Message, language: str):
    """Обработка недопустимого типа сообщения"""
    try:
        invalid_msg = get_message('invalid_input', language)
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=invalid_msg,
            message_to_edit=None
        )
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

        # 1. Получаем CombinedDiaryEntry
        try:
            combined_entry = await CombinedDiaryEntry.objects.select_related('daily_analysis').aget(user=user, date=target_date)
        except CombinedDiaryEntry.DoesNotExist:
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            # Показываем день или возвращаем в архив
            # await select_day(callback, user, language) # Или другая навигация
            return

        # 2. Проверяем, есть ли DailyAnalysis
        if not hasattr(combined_entry, 'daily_analysis'):
            no_analysis_msg = get_message('no_full_analysis_yet', language) # Новое сообщение
            # --- Изменено: добавлена кнопка пересчета ---
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
            # ---
            await safe_edit_message_text(message=callback.message, text=no_analysis_msg, reply_markup=back_keyboard)
            await safe_answer_callback(callback, "")
            return

        daily_analysis = combined_entry.daily_analysis

        # 3. Формируем сообщение с полным анализом, разбивая его на секции
        analysis_header = get_message('full_day_analysis_header', language, date=target_date_str)
        analysis_msg = f"🔬 <b>{analysis_header}</b>\n"
        analysis_msg += "═" * 25 + "\n" # Визуальный разделитель

        # === Общий текстовый анализ ===
        if daily_analysis.overall_analysis_text and daily_analysis.overall_analysis_text.strip():
             analysis_msg += f"🧠 <b>Общий анализ дня:</b>\n{daily_analysis.overall_analysis_text}\n\n"
        else:
             analysis_msg += f"🧠 <b>Общий анализ дня:</b>\n(Общий текстовый анализ отсутствует или не был сгенерирован ИИ.)\n\n"

        # === Тренд настроения и средняя оценка ===
        mood_section = "📈 <b>Настроение и оценки</b>\n"
        mood_trend_display = dict(DailyAnalysis._meta.get_field('mood_trend').choices).get(daily_analysis.mood_trend, daily_analysis.mood_trend)
        mood_section += f"  📊 Тренд настроения: {mood_trend_display}\n"
        
        if combined_entry.average_mood_score and combined_entry.average_mood_score > 0:
             # Добавим визуализацию средней оценки
             avg_score = combined_entry.average_mood_score
             stars_full = "⭐" * int(avg_score // 2) # 1 звезда = 2 балла
             stars_half = "☆" if avg_score % 2 >= 1 else ""
             stars_empty = "☆" * (5 - len(stars_full) - len(stars_half))
             stars_display = stars_full + stars_half + stars_empty
             mood_section += f"  🌟 Средняя оценка: {avg_score:.1f}/10 {stars_display}\n"
        
        analysis_msg += mood_section + "\n"

        # === Ключевые темы ===
        if daily_analysis.key_themes:
            analysis_msg += "🏷 <b>Ключевые темы дня:</b>\n"
            for i, theme in enumerate(daily_analysis.key_themes, 1):
                significance = theme.get('significance', 0)
                # Визуализация значимости в процентах
                significance_percent = f"{significance:.0%}"
                analysis_msg += f"  {i}. <b>{theme['theme']}</b> ({theme.get('mentions', 1)} упоминаний) - Значимость: {significance_percent}\n"
            analysis_msg += "\n"

        # === Эмоциональные паттерны ===
        if daily_analysis.emotional_patterns:
            analysis_msg += "🎭 <b>Эмоциональные паттерны:</b>\n"
            for i, pattern in enumerate(daily_analysis.emotional_patterns, 1):
                analysis_msg += f"  {i}. <b>{pattern['emotion']}</b> (частота: {pattern.get('frequency', 1)})\n"
                analysis_msg += f"     Контекст: {pattern.get('context', 'Контекст не указан')}\n"
            analysis_msg += "\n"

        # === Инсайты ===
        if daily_analysis.insights:
            analysis_msg += "💡 <b>Инсайты:</b>\n"
            for i, insight in enumerate(daily_analysis.insights, 1):
                significance = insight.get('significance', 0)
                category = insight.get('category', 'other')
                significance_percent = f"{significance:.0%}"
                analysis_msg += f"  {i}. <b>{insight['text']}</b>\n"
                analysis_msg += f"     Категория: {category}, Значимость: {significance_percent}\n"
            analysis_msg += "\n"

        # === Рекомендации ===
        if daily_analysis.recommendations:
            analysis_msg += "🎯 <b>Персональные рекомендации:</b>\n"
            for i, rec in enumerate(daily_analysis.recommendations, 1):
                analysis_msg += f"  {i}. {rec}\n"
            analysis_msg += "\n"

        # Добавляем информацию о том, что это результат ИИ
        analysis_msg += "🤖 <i>Анализ выполнен искусственным интеллектом на основе ваших записей.</i>"

        # --- Формируем клавиатуру ---
        keyboard_buttons = []
        
        # Кнопка пересчета
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_reanalyze_entry', language),
                callback_data=f"reanalyze_day:{year}:{month}:{day}"
            )
        ])
        
        # Кнопка "Назад"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data=f"calendar_select_day:{year}:{month}:{day}"
            )
        ])
        
        analysis_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # 4. Отправляем сообщение
        await safe_edit_message_text(message=callback.message, text=analysis_msg, reply_markup=analysis_keyboard)
        await safe_answer_callback(callback, "")

    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_full_day_analysis: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре полного анализа дня: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

@router.callback_query(F.data.startswith("entry_edit:"))
async def entry_edit(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование конкретной записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        await state_manager.set_state(state, DiaryStates.waiting_for_entry_edit)
        await state_manager.update_state_data(state, editing_entry_id=entry_id)
        formatted_text = format_entry_text_for_editing(entry.text)
        edit_msg = get_message('ask_entry_edit_with_text', language).format(old_text=formatted_text)
        await callback.message.answer(edit_msg, reply_markup=get_cancel_keyboard(language))
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при редактировании записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

@router.callback_query(F.data.startswith("entry_delete_confirm:"))
async def entry_delete_confirm(callback: CallbackQuery, user, language: str):
    """Запрос подтверждения удаления конкретной записи"""
    try:
        entry_id = int(callback.data.split(":")[1])
        entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        target_date = entry.entry_date
        confirm_msg = get_message('confirm_delete_entry_prompt', language)
        keyboard = get_delete_entry_confirmation_keyboard(entry_id, target_date, language)
        await safe_edit_message_text(callback.message, confirm_msg, reply_markup=keyboard)
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language))

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
async def reanalyze_day(callback: CallbackQuery, user, language: str):
    """
    Запускает пересчёт (полный анализ) дня.
    """
    try:
        # 1. НЕМЕДЛЕННО подтверждаем callback, чтобы избежать "query is too old"
        await callback.answer(get_message('day_analysis_confirmed', language), show_alert=False) 
        logger.info(f"[reanalyze_day] Callback подтвержден для пользователя {user.telegram_id}")

        # 2. Парсим дату
        parts = callback.data.split(":")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        target_date = date(year, month, day)
        
        # 3. Получаем CombinedDiaryEntry (если его нет, логика внутри diary_service должна это обработать)
        try:
            combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=target_date)
        except CombinedDiaryEntry.DoesNotExist:
            # Пытаемся создать/найти записи и CombinedDiaryEntry
            entries = await diary_service.get_user_entries_for_date(user, target_date)
            if not entries:
                no_entries_msg = get_message('archive_empty', language)
                # РЕШЕНИЕ: Отправляем новое сообщение вместо редактирования
                await callback.message.answer(no_entries_msg, reply_markup=get_calendar_back_keyboard(language, year, month))
                # await safe_edit_message_text(...) - убираем
                return # callback.answer уже был
            
            # Создаем CombinedDiaryEntry если его не было
            combined_entry = await diary_service.create_daily_state_from_entry(entries[0])
            combined_text = await diary_service.get_combined_entry_text(user, target_date, entries_list=entries)
            combined_entry.text = combined_text
            combined_entry.entry_count = len(entries)
            await combined_entry.asave(update_fields=['text', 'entry_count'])
            logger.info(f"[reanalyze_day] Создан CombinedDiaryEntry ID {combined_entry.id} для пересчёта.")

        # 4. Проверка, если анализ уже выполнен
        # if combined_entry.is_analyzed and not callback.data.endswith(":force"): # Опционально
        #     already_analyzed_msg = get_message('analysis_already_done', language)
        #     await callback.message.answer(already_analyzed_msg) # Отправляем новое сообщение
        #     # await safe_answer_callback(callback, already_analyzed_msg, show_alert=True) - не нужно, callback уже подтвержден
        #     # Показываем день
        #     entries = await diary_service.get_user_entries_for_date(user, target_date)
        #     if entries:
        #         sorted_entries = sorted(entries, key=lambda e: e.created_at)
        #         await _show_entry_page(callback.message, user, sorted_entries[0], sorted_entries, target_date, language)
        #     return

        # 5. Показываем пользователю сообщение о начале процесса В НОВОМ СООБЩЕНИИ
        processing_msg = get_message('processing', language) + "\n\n" + get_message('task_effect_analysis_started', language)
        # ВСЕГДА отправляем новое сообщение, не редактируем старое
        status_message = await callback.message.answer(processing_msg)
        logger.info(f"[reanalyze_day] Сообщение о начале обработки отправлено пользователю {user.telegram_id}")

        # 6. ЗАПУСКАЕМ АНАЛИЗ В ФОНОВОЙ ЗАДАЧЕ
        # Передаем status_message.message_id, чтобы фоновая задача могла его отредактировать
        asyncio.create_task(
            _run_full_analysis_and_notify(
                user=user,
                target_date=target_date,
                chat_id=callback.message.chat.id,
                status_message_id=status_message.message_id, # ID сообщения "Обработка..."
                language=language,
                year=year,
                month=month,
                day=day
            )
        )
        logger.info(f"[reanalyze_day] Фоновая задача анализа запущена для пользователя {user.telegram_id}")

    except Exception as e:
        logger.error(f"[reanalyze_day] Критическая ошибка при запуске пересчёта анализа дня: {e}", exc_info=True)
        # Даже если произошла ошибка, callback уже подтвержден, поэтому отправляем новое сообщение
        try:
            await callback.message.answer(get_message('error_generic', language))
        except Exception as send_error:
             logger.error(f"[reanalyze_day] Не удалось отправить сообщение об ошибке: {send_error}")

@router.callback_query(F.data.startswith("delete_entry:"))
async def delete_selected_entry(callback: CallbackQuery, user, language: str):
    """Удаление записей за день, в зависимости от callback_data."""
    try:
        parts = callback.data.split(":")
        if len(parts) == 4:
            year = int(parts[1])
            month = int(parts[2])
            day = int(parts[3])
            target_date = date(year, month, day)
            confirm_msg = get_message('confirm_delete_entire_day_prompt', language).format(date=target_date.strftime('%d.%m.%Y')) 
            confirm_keyboard = get_confirmation_keyboard(
                language=language,
                confirm_text_key='btn_confirm_delete_day',
                cancel_text_key='btn_cancel',
                confirm_callback_data=f"confirm_delete_entire_day:{target_date.isoformat()}",
                cancel_callback_data=f"calendar_select_day:{year}:{month}:{day}"
)
            await safe_edit_message_text(
                message=callback.message,
                text=confirm_msg,
                reply_markup=confirm_keyboard
            )
            await safe_answer_callback(callback, "")
        else:
            raise ValueError(f"Неподдерживаемый формат callback_data: {callback.data}")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки callback_data для удаления: {callback.data} - {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Неожиданная ошибка в delete_selected_entry: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
        
@router.message(DiaryStates.waiting_for_entry_edit)
async def process_entry_edit(message: Message, state: FSMContext, user, language: str):
    """Обработка отредактированного текста записи."""  
    target_date_for_navigation = None
    try:
        new_text = message.text
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
            target_date_for_navigation = await get_entry_date(entry)
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена при попытке получить дату для навигации.")
        state_data = await state_manager.get_state_data(state)
        target_date_iso = state_data.get('editing_entry_target_date')
        target_date = date.fromisoformat(target_date_iso) if target_date_iso else entry.entry_date
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
            target_date = entry.entry_date
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
        target_date_iso = parts[2]
        target_date = date.fromisoformat(target_date_iso)
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
        await safe_answer_callback(callback, "")

    except DiaryEntry.DoesNotExist:
        logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
        await safe_answer_callback(callback, get_message('entry_not_found', language), show_alert=True)
        try:
            target_date = date.fromisoformat(parts[2])
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
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления записи {entry_id}: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
        try:
            if 'target_date' in locals():
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
        except Exception:
            pass

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
        target_date_iso = parts[2]
        target_date = date.fromisoformat(target_date_iso)
        cancel_msg = get_message('entry_delete_cancelled', language)
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
        await safe_answer_callback(callback, "")
    except Exception as e:
        logger.error(f"Ошибка при отмене удаления записи {entry_id}: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

# ==================== HANDLERS ДЛЯ ПРОСМОТРА ИНСАЙТОВ И КЛЮЧЕВЫХ МОМЕНТОВ ==================== 

@router.callback_query(F.data.startswith("view_day_insights:"))
async def view_day_insights(callback: CallbackQuery, user, language: str):
    """Просмотр инсайтов за день."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            raise ValueError("Некорректный формат callback_data для view_day_insights")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        target_date = date(year, month, day)
        target_date_str = target_date.strftime("%d.%m.%Y")
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        entry_ids = [entry.id for entry in entries]
        back_button = [[InlineKeyboardButton(text=get_button_text('btn_back', language), callback_data=f"calendar_select_day:{year}:{month}:{day}")]]
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=back_button)
        if not entry_ids:
             no_data_msg = get_message('no_insights_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_data_msg, reply_markup=back_keyboard)
             await safe_answer_callback(callback, "")
             return
        insights = await diary_service.get_insights_for_entries(entry_ids)
        if not insights:
             no_insights_msg = get_message('no_insights_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_insights_msg, reply_markup=back_keyboard)
        else:
             insights_header = get_message('header_insights', language, date=target_date_str)
             insights_msg = f"<b>{insights_header}</b>\n"
             for i, insight in enumerate(insights, 1):
                 category_display = getattr(insight, 'get_category_display', lambda: insight.category)()
                 insights_msg += f"<b>{i}. {insight.text}</b>\n"
                 insights_msg += f"   🏷 {category_display}\n"
                 insights_msg += f"   ⭐ {insight.weight}\n"
                 insights_msg += f"   🕒 {insight.last_mentioned.strftime('%d.%m.%Y %H:%M')}\n"
             await safe_edit_message_text(message=callback.message, text=insights_msg, reply_markup=back_keyboard)
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_day_insights: {e}")
        error_msg = get_message('error_loading_insights', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре инсайтов за день: {e}", exc_info=True)
        error_msg = get_message('error_loading_insights', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)

@router.callback_query(F.data.startswith("view_day_keypoints:"))
async def view_day_keypoints(callback: CallbackQuery, user, language: str):
    """Просмотр ключевых моментов за день."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            raise ValueError("Некорректный формат callback_data для view_day_keypoints")
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        target_date = date(year, month, day)
        target_date_str = target_date.strftime("%d.%m.%Y")
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        entry_ids = [entry.id for entry in entries]
        back_button = [[InlineKeyboardButton(text=get_button_text('btn_back', language), callback_data=f"calendar_select_day:{year}:{month}:{day}")]]
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=back_button)
        if not entry_ids:
             no_data_msg = get_message('no_key_points_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_data_msg, reply_markup=back_keyboard)
             await safe_answer_callback(callback, "")
             return
        keypoints = await diary_service.get_keypoints_for_entries(entry_ids)
        if not keypoints:
             no_keypoints_msg = get_message('no_key_points_for_day', language, date=target_date_str)
             await safe_edit_message_text(message=callback.message, text=no_keypoints_msg, reply_markup=back_keyboard)
        else:
             keypoints_header = get_message('header_key_points', language, date=target_date_str)
             keypoints_msg = f"<b>{keypoints_header}</b>\n"
             keypoints_by_type = {}
             for kp in keypoints:
                 kp_type = getattr(kp, 'get_type_display', lambda: kp.type)()
                 if kp_type not in keypoints_by_type:
                     keypoints_by_type[kp_type] = []
                 keypoints_by_type[kp_type].append(kp)
             for kp_type, kp_list in keypoints_by_type.items():
                 keypoints_msg += f"<b>{kp_type}:</b>\n"
                 for i, kp in enumerate(kp_list, 1):
                     kp_text_display = (kp.text[:50] + "...") if len(kp.text) > 50 else kp.text
                     keypoints_msg += f"  {i}. {kp_text_display} ({kp.confidence:.2f})\n"
                 keypoints_msg += "\n"
             await safe_edit_message_text(message=callback.message, text=keypoints_msg, reply_markup=back_keyboard)
        await safe_answer_callback(callback, "")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка обработки даты в view_day_keypoints: {e}")
        error_msg = get_message('error_loading_key_points', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при просмотре ключевых моментов за день: {e}", exc_info=True)
        error_msg = get_message('error_loading_key_points', language)
        await safe_answer_callback(callback, error_msg, show_alert=True)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

# TODO Сообщения для en
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
        if not analysis_result or not analysis_result.get('success'):
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
                entry.clarification_questions_asked = clarification_questions
                await sync_to_async(lambda: entry.save(update_fields=['clarification_questions_asked']))()
                await state_manager.update_state_data(
                    state,
                    clarifying_entry_id=entry.id,
                    clarification_questions=clarification_questions
                )
                await state_manager.set_state(state, DiaryStates.asking_clarifying_questions)
                questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clarification_questions)])
                await status_msg.edit_text(
                    f"{get_message('clarification_needed', language)}\n{questions_text}",
                    reply_markup=get_cancel_keyboard(language)
                )
                return
        await psycho_analysis_service.create_or_update_analysis(
            entry=entry,
            mood_score=mood_score,
            comment=comment,
            recommendation=recommendation,
            analysis_text=analysis_text,
            api_response=analysis_result.get('api_response', {})
        )
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
                        task_info = f"\n📌 <b>Новое задание от ИИ:</b>\n<b>{task.title}</b>\n{preview}"
                        reply_markup = get_task_pagination_keyboard(task.id, 0, 1, language)
                    else:
                         logger.debug(f"Задание от ИИ не было создано для пользователя {user.telegram_id} (возможно, превышен общий лимит активных заданий).")
                except Exception as task_creation_error:
                    logger.error(f"Ошибка при создании задания от ИИ для пользователя {user.telegram_id}: {task_creation_error}")
            else:
                logger.debug(f"Задание от ИИ для пользователя {user.telegram_id} не создано: превышен дневной лимит ({user.max_ai_tasks_per_day}).")
        final_text = get_message('entry_saved', language, score=mood_score, mood=get_message(f'mood_{mood_score}', language), comment=comment, recommendation=recommendation) + task_info
        await status_msg.edit_text(final_text, reply_markup=reply_markup)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка в _process_analysis_result: {e}", exc_info=True)
        if status_msg:
            try:
                await safe_edit_message_text(status_msg, get_message('error_processing', language))
            except Exception as edit_error:
                logger.warning(f"Не удалось отредактировать сообщение об ошибке в _process_analysis_result: {edit_error}")
                await state_manager.clear_state(state)
        raise

async def _create_task_from_suggested_data(user, task_data, entry_date, related_entry):
    """Создаёт задание из данных ИИ."""
    from core.constants import TASK_TYPES
    valid_types = [t[0] for t in TASK_TYPES]
    task_type = task_data.get('type', 'daily')
    if task_type not in valid_types:
        task_type = 'daily'
    priority_map = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    priority = priority_map.get(task_data.get('priority', 'medium').lower(), 2)
    return await task_service.assign_task(
        user=user,
        title=task_data.get('title', 'Задание от ИИ'),
        description=task_data.get('description', 'Выполните задание.'),
        task_type=task_type,
        priority=priority,
        related_entry=related_entry
    )
             
async def _show_entry_page(message, user, entry, entries, target_date, language):
    """
    Отображает текущую запись с клавиатурой пагинации.
    Использует edit_or_send_message для надежного обновления.
    Логика клавиатуры вынесена в отдельную функцию.
    """
    try:
        current_index = entries.index(entry)
        total = len(entries)
        text = f"<b>Запись {current_index + 1}/{total}</b>\n{entry.text}"
        try:
            analysis = await PsychoAnalysis.objects.aget(entry=entry)
            text += f"\n📊 <b>Анализ:</b>\n{analysis.comment}"
        except PsychoAnalysis.DoesNotExist:
            pass
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

        # --- Отправляем/редактируем сообщение ---
        await edit_or_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text=text,
            reply_markup=keyboard,
            message_to_edit=message
        )
    except Exception as e:
        logger.error(f"Ошибка при отображении страницы записи: {e}")
        try:
            await message.answer(get_message('error_generic', language))
        except:
            pass

async def _run_full_analysis_and_notify(
    user: User, 
    target_date: date, 
    chat_id: int, 
    status_message_id: int, # Теперь это ID сообщения статуса
    language: str,
    year: int,
    month: int,
    day: int
):
    """
    Фоновая задача для выполнения полного анализа и уведомления пользователя.
    """
    from diary.services.full_day_analysis_service import full_day_analysis_service # Импорт внутри
    
    try:
        logger.info(f"[_run_full_analysis_and_notify] Начало фоновой задачи анализа дня {target_date} для пользователя {user.telegram_id}")
        
        # 1. Выполняем длительный анализ
        analysis_result = await full_day_analysis_service.perform_full_day_analysis(user, target_date)
        
        # 2. Получаем бота
        from bot.main import bot as global_bot 
        
        if not global_bot:
            raise RuntimeError("Глобальный экземпляр бота не найден")
            
        if analysis_result["success"]:
            success_msg = analysis_result["message"]
            logger.info(f"[_run_full_analysis_and_notify] Анализ дня {target_date} для {user.telegram_id} успешен: {success_msg}")
            
            # --- ВАШ ВАРИАНТ: Отредактировать сообщение "Обработка..." на результат ---
            # Сначала получим данные для отображения
            daily_analysis = analysis_result.get("daily_analysis")
            analysis_summary_text = get_message('analysis_recalculated', language) # Используем существующее сообщение
            
            if daily_analysis:
                # Можно сделать более подробное резюме
                mood_trend_display = dict(DailyAnalysis._meta.get_field('mood_trend').choices).get(daily_analysis.mood_trend, daily_analysis.mood_trend)
                analysis_summary_text += f"\n\n📊 Тренд настроения: {mood_trend_display}"
                if daily_analysis.key_themes:
                    themes_text = ", ".join([t['theme'] for t in daily_analysis.key_themes[:3]]) # Первые 3 темы
                    analysis_summary_text += f"\n🏷 Ключевые темы: {themes_text}"
                # ... добавить другие поля при необходимости ...
            
            # --- Отредактируем сообщение "Обработка..." ---
            try:
                await global_bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=analysis_summary_text,
                    # Можно добавить кнопку "Просмотреть анализ"
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔬 Просмотреть анализ",
                            callback_data=f"view_full_day_analysis:{year}:{month}:{day}"
                        )
                    ]])
                )
                logger.debug(f"[_run_full_analysis_and_notify] Сообщение обработки отредактировано для пользователя {user.telegram_id}")
            except Exception as edit_error:
                logger.warning(f"[_run_full_analysis_and_notify] Не удалось отредактировать сообщение обработки: {edit_error}. Отправляем новое.")
                # Если не удалось отредактировать, отправляем новое сообщение
                await global_bot.send_message(chat_id=chat_id, text=analysis_summary_text)
            
            # --- Альтернатива: Всегда отправлять новое сообщение ---
            # await global_bot.send_message(chat_id=chat_id, text=analysis_summary_text)

        else:
            error_msg = analysis_result["message"]
            logger.error(f"[_run_full_analysis_and_notify] Ошибка анализа дня {target_date} для {user.telegram_id}: {error_msg}")
            
            # --- Отредактируем сообщение "Обработка..." на сообщение об ошибке ---
            try:
                await global_bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"{get_message('error_processing', language)}: {error_msg}"
                )
                logger.debug(f"[_run_full_analysis_and_notify] Сообщение об ошибке отправлено пользователю {user.telegram_id}")
            except Exception as edit_error:
                logger.warning(f"[_run_full_analysis_and_notify] Не удалось отредактировать сообщение об ошибке: {edit_error}. Отправляем новое.")
                # Если не удалось отредактировать, отправляем новое сообщение
                await global_bot.send_message(
                    chat_id=chat_id, 
                    text=f"{get_message('error_processing', language)}: {error_msg}"
                )

    except Exception as e:
        logger.error(f"[_run_full_analysis_and_notify] Критическая ошибка в фоновой задаче для пользователя {user.telegram_id}: {e}", exc_info=True)
        try:
            from bot.main import bot as global_bot
            if global_bot:
                # Отправляем сообщение об ошибке в фоновой задаче
                await global_bot.send_message(
                    chat_id=chat_id, 
                    text=get_message('error_generic', language)
                )
        except Exception as send_error:
             logger.error(f"[_run_full_analysis_and_notify] Не удалось отправить сообщение об ошибке в фоновой задаче: {send_error}")

