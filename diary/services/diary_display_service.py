# /diary/services/diary_display_service.py
"""
Сервис для отображения записей дневника.
Отвечает за:
- Создание клавиатур (rating, comment buttons)
- Форматирование данных для отображения (mood stars, analysis sections)
- Пагинацию записей
- Подготовку контента для показа пользователю

Универсальный сервис: работает и для бота, и для API.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import date

from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from django.db import IntegrityError

from diary.models import DiaryEntry, PsychoAnalysis, CombinedDiaryEntry, DailyAnalysis, AnalysisRating
from users.models import User
from messages import get_message, get_button_text

logger = logging.getLogger(__name__)


class DiaryDisplayService:
    """Сервис для отображения записей дневника."""

    async def build_rating_keyboard(
        self, analysis: PsychoAnalysis, user: User, language: str
    ) -> Tuple[bool, List[List[InlineKeyboardButton]]]:
        """
        Создает клавиатуру с рейтингом для анализа.

        Args:
            analysis: Объект PsychoAnalysis.
            user: Пользователь.
            language: Язык интерфейса.

        Returns:
            Tuple[bool, List[List[InlineKeyboardButton]]]:
                - has_rating: True если рейтинг уже существует
                - rating_buttons: Список кнопок рейтинга (пустой если has_rating=True)
        """
        try:
            user_rating_exists = await analysis.user_ratings.filter(user=user).aexists()
            if user_rating_exists:
                return True, []
        except Exception:
            logger.warning(f"PsychoAnalysis для записи {analysis.entry_id} не найден при создании клавиатуры рейтинга")
            return False, []

        rating_emojis = {1: "😠", 2: "😟", 3: "😐", 4: "🙂", 5: "😄"}
        rating_buttons = []
        for rate_value, emoji in rating_emojis.items():
            rating_buttons.append(
                InlineKeyboardButton(
                    text=emoji,
                    callback_data=f"rate_analysis:{analysis.id}:{rate_value}"
                )
            )

        return False, [rating_buttons]

    async def build_add_comment_button(
        self, entry: DiaryEntry, language: str
    ) -> Optional[List[InlineKeyboardButton]]:
        """
        Создает кнопку 'Добавить комментарий' если комментарий еще не добавлен.

        Args:
            entry: Объект DiaryEntry.
            language: Язык интерфейса.

        Returns:
            Optional[List[InlineKeyboardButton]]: Кнопка комментария или None.
        """
        try:
            current_entry = await DiaryEntry.objects.aget(id=entry.id)
            has_user_comment = bool(current_entry.user_comment)
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry.id} не найдена при проверке комментария")
            return None

        if has_user_comment:
            return None

        return [
            InlineKeyboardButton(
                text=get_button_text('btn_add_comment', language),
                callback_data=f"request_add_comment:{entry.id}"
            )
        ]

    async def submit_rating(
        self, analysis_id: int, user: User, rating: int
    ) -> Dict[str, Any]:
        """
        Добавляет рейтинг к анализу.

        Args:
            analysis_id: ID анализа.
            user: Пользователь.
            rating: Оценка (1-5).

        Returns:
            Dict[str, Any]: Результат операции.
        """
        try:
            analysis = await PsychoAnalysis.objects.select_related('entry__user').aget(id=analysis_id)
            if analysis.entry.user_id != user.id:
                logger.warning(f"Пользователь {user.telegram_id} пытается оценить чужой анализ {analysis_id}")
                return {'success': False, 'error': 'forbidden'}
        except PsychoAnalysis.DoesNotExist:
            logger.warning(f"PsychoAnalysis с ID {analysis_id} не найден")
            return {'success': False, 'error': 'not_found'}

        try:
            @sync_to_async
            def create_rating_sync():
                rating_obj = AnalysisRating.objects.create(user=user, analysis=analysis, rating=rating)
                return rating_obj

            await create_rating_sync()
            logger.debug(f"Пользователь {user.telegram_id} поставил оценку {rating} анализу {analysis_id}")
            return {'success': True, 'rating': rating}

        except IntegrityError:
            logger.warning(f"Пользователь {user.telegram_id} уже поставил оценку анализу {analysis_id}")
            return {'success': False, 'error': 'already_rated'}

    async def remove_rating_buttons_from_keyboard(
        self, keyboard: InlineKeyboardMarkup
    ) -> InlineKeyboardMarkup:
        """
        Удаляет кнопки рейтинга из клавиатуры после оценки.

        Args:
            keyboard: Исходная клавиатура.

        Returns:
            InlineKeyboardMarkup: Обновленная клавиатура без кнопок рейтинга.
        """
        if not keyboard or not hasattr(keyboard, 'inline_keyboard'):
            return keyboard

        new_inline_keyboard = []
        for row in keyboard.inline_keyboard:
            if not any(btn.callback_data and btn.callback_data.startswith("rate_analysis:") for btn in row):
                new_inline_keyboard.append(row)

        return InlineKeyboardMarkup(inline_keyboard=new_inline_keyboard)

    async def format_mood_stars(self, score: float) -> str:
        """
        Форматирует оценку настроения в звезды для отображения.

        Args:
            score: Оценка (1-10).

        Returns:
            str: Строка с звездами (например, "⭐⭐⭐☆☆").
        """
        if not score or score <= 0:
            return ""

        stars_full = "⭐" * int(score // 2)
        stars_half = "☆" if score % 2 >= 1 else ""
        stars_empty = "☆" * (5 - len(stars_full) - len(stars_half))
        return stars_full + stars_half + stars_empty

    async def get_entry_with_pagination(
        self, user: User, entry_id: int, direction: str
    ) -> Dict[str, Any]:
        """
        Получает запись с информацией о пагинации.

        Args:
            user: Пользователь.
            entry_id: ID текущей записи.
            direction: 'prev' или 'next'.

        Returns:
            Dict[str, Any]:
                - entry: Следующая/предыдущая запись или None
                - has_entry: True если запись найдена
                - is_first: True если это первая запись
                - is_last: True если это последняя запись
        """
        try:
            current_entry = await DiaryEntry.objects.aget(id=entry_id, user=user)
        except DiaryEntry.DoesNotExist:
            return {'success': False, 'error': 'not_found'}

        target_date = await current_entry.aentry_date()

        from diary.services.diary_service import diary_service
        entries = await diary_service.get_user_entries_for_date(user, target_date)

        if not entries:
            return {'success': False, 'error': 'no_entries'}

        sorted_entries = sorted(entries, key=lambda e: e.created_at)

        try:
            current_index = next(i for i, e in enumerate(sorted_entries) if e.id == entry_id)
        except StopIteration:
            return {'success': False, 'error': 'entry_not_in_list'}

        if direction == 'prev':
            if current_index > 0:
                return {
                    'success': True,
                    'entry': sorted_entries[current_index - 1],
                    'entries': sorted_entries,
                    'target_date': target_date,
                    'is_first': current_index == 1,
                    'is_last': False
                }
            else:
                return {'success': False, 'error': 'first_entry', 'is_first': True}
        else:  # next
            if current_index < len(sorted_entries) - 1:
                return {
                    'success': True,
                    'entry': sorted_entries[current_index + 1],
                    'entries': sorted_entries,
                    'target_date': target_date,
                    'is_first': False,
                    'is_last': current_index == len(sorted_entries) - 2
                }
            else:
                return {'success': False, 'error': 'last_entry', 'is_last': True}

    async def format_entry_for_display(
        self,
        entry: DiaryEntry,
        entries: List[DiaryEntry],
        target_date: date,
        language: str
    ) -> Dict[str, Any]:
        """
        Форматирует запись для отображения с клавиатурой.

        Args:
            entry: Запись для отображения.
            entries: Все записи за день (для пагинации).
            target_date: Целевая дата.
            language: Язык интерфейса.

        Returns:
            Dict[str, Any]:
                - text: Текст сообщения
                - keyboard: Клавиатура
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
            analysis = None

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
                combined_entry = await CombinedDiaryEntry.objects.aget(user=entry.user, date=target_date)
                is_day_analyzed = combined_entry.is_analyzed
            except CombinedDiaryEntry.DoesNotExist:
                pass

            from bot.keyboards import get_entry_page_keyboard
            keyboard = get_entry_page_keyboard(
                entry_id=entry.id,
                current_index=current_index,
                total_entries=total,
                target_date=target_date,
                language=language,
                is_day_analyzed=is_day_analyzed
            )

            return {
                'success': True,
                'text': text,
                'keyboard': keyboard
            }

        except Exception as e:
            logger.error(f"Ошибка при форматировании записи {entry.id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    async def format_full_day_analysis(
        self,
        combined_entry: CombinedDiaryEntry,
        daily_analysis: DailyAnalysis,
        year: int,
        month: int,
        day: int,
        language: str
    ) -> Dict[str, Any]:
        """
        Форматирует полный анализ дня для отображения.

        Args:
            combined_entry: Объединенная запись дня.
            daily_analysis: Анализ дня.
            year: Год.
            month: Месяц.
            day: День.
            language: Язык интерфейса.

        Returns:
            Dict[str, Any]:
                - text: Текст сообщения
                - keyboard: Клавиатура
        """
        target_date_str = combined_entry.date.strftime("%d.%m.%Y")

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
            stars_display = await self.format_mood_stars(avg_score)
            mood_section += f"  🌟 Средняя оценка: {avg_score:.1f}/10 {stars_display}\n"

        analysis_msg += mood_section + "\n"

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

        return {
            'success': True,
            'text': analysis_msg,
            'keyboard': analysis_keyboard
        }

    async def build_entry_result_keyboard(
        self,
        entry: DiaryEntry,
        analysis: PsychoAnalysis,
        user: User,
        language: str,
        back_callback: str = "main_menu"
    ) -> InlineKeyboardMarkup:
        """
        Создает полную клавиатуру для результата анализа записи.
        Включает: рейтинг + комментарий + назад.

        Args:
            entry: Запись.
            analysis: Анализ.
            user: Пользователь (передаётся явно, чтобы избежать entry.user в async контексте).
            language: Язык.
            back_callback: Callback для кнопки 'Назад'.

        Returns:
            InlineKeyboardMarkup: Клавиатура.
        """
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[])

        # Кнопки рейтинга
        has_rating, rating_buttons = await self.build_rating_keyboard(analysis, user, language)
        if not has_rating and rating_buttons:
            reply_markup.inline_keyboard.extend(rating_buttons)

        # Кнопка комментария
        comment_button = await self.build_add_comment_button(entry, language)
        if comment_button:
            reply_markup.inline_keyboard.append(comment_button)

        # Кнопка назад
        back_buttons = [
            InlineKeyboardButton(
                text=get_button_text('btn_back', language),
                callback_data=back_callback
            )
        ]
        reply_markup.inline_keyboard.append(back_buttons)

        return reply_markup


diary_display_service = DiaryDisplayService()


async def build_entry_result_keyboard_from_service(
    entry: DiaryEntry,
    analysis: PsychoAnalysis,
    user: User,
    language: str,
    back_callback: str = "main_menu"
) -> InlineKeyboardMarkup:
    """
    Удобная функция для создания клавиатуры.
    """
    return await diary_display_service.build_entry_result_keyboard(
        entry, analysis, user, language, back_callback
    )
