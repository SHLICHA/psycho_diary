"""
Сервис для выполнения еженедельного анализа пользователя.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Any, Optional

from asgiref.sync import sync_to_async
from django.db import transaction

from users.models import User
from diary.models import (
    CombinedDiaryEntry, TherapyTask, TaskCompletion,
    WeeklyAnalysis
)
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from core.profile_field_utils import field_to_ai_format

logger = logging.getLogger(__name__)


class WeeklyAnalysisService:
    """Сервис для выполнения еженедельного анализа."""

    async def perform_weekly_analysis(self, user: User) -> Dict[str, Any]:
        """
        Выполняет полный цикл еженедельного анализа для пользователя.
        Определяет неделю, собирает данные, вызывает ИИ, сохраняет результат.

        Args:
            user: Пользователь.

        Returns:
            Dict[str, Any]: Результат операции.
                - success (bool): Успешность операции.
                - message (str): Сообщение о результате.
                - weekly_analysis (Optional[WeeklyAnalysis]): Объект анализа недели, если создан.
                - error (Optional[str]): Сообщение об ошибке, если есть.
        """
        logger.debug(f"[WeeklyAnalysisService] Начало еженедельного анализа для пользователя {user.telegram_id}")

        try:
            today_user_tz = user.get_local_datetime().date()
            logger.debug(f"[WeeklyAnalysisService] Сегодня по часовому поясу пользователя: {today_user_tz}")
            last_sunday = today_user_tz - timedelta(days=today_user_tz.weekday() + 1)
            week_start_date = last_sunday - timedelta(days=6)
            logger.debug(f"[WeeklyAnalysisService] Анализируем неделю с {week_start_date} по {last_sunday}")
            existing_analysis = await self._get_weekly_analysis_for_week(user, week_start_date)
            if existing_analysis:
                logger.debug(f"[WeeklyAnalysisService] Анализ для недели {week_start_date} уже существует (ID: {existing_analysis.id}). Пропускаем.")
                return {
                    "success": True,
                    "message": "Анализ для этой недели уже существует.",
                    "weekly_analysis": existing_analysis,
                    "error": None
                }
            context = await self._gather_weekly_context(user, week_start_date, last_sunday)
            if not context.get('has_data'):
                 logger.warning(f"[WeeklyAnalysisService] Нет данных для анализа недели {week_start_date} у пользователя {user.telegram_id}")
                 return {
                    "success": False,
                    "message": "Недостаточно данных для анализа недели.",
                    "weekly_analysis": None,
                    "error": "no_data"
                }
            logger.debug(f"[WeeklyAnalysisService] Контекст собран для недели {week_start_date}")
            prompt = get_prompt(
                key='weekly_analysis',
                language=user.language,
                user_profile=context['user_profile'],
                daily_analyses=context['daily_analyses'],
                previous_weekly_analysis=context['previous_weekly_analysis'],
                week_statistics=context['week_statistics']
            )
            logger.debug(f"[WeeklyAnalysisService] Промпт сформирован для {user.telegram_id} за неделю {week_start_date} (длина: {len(prompt)} символов)")
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt,
                language=user.language,
                timeout_per_attempt=120
            )
            logger.debug(f"[WeeklyAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")

            # Обработать результат API
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[WeeklyAnalysisService] Ошибка API при недельном анализе: {error_msg}")

                # Создаем WeeklyAnalysis с информацией об ошибке
                weekly_analysis = await self._create_or_update_weekly_analysis(
                    user=user,
                    week_start_date=week_start_date,
                    parsed_result={},
                    api_result=api_result,
                    context=context
                )
                return {
                    "success": False,
                    "message": f"Ошибка при анализе недели: {error_msg}",
                    "weekly_analysis": weekly_analysis,
                    "error": error_msg
                }
            parsed_result = api_result.get('result', {})
            logger.debug(f"[WeeklyAnalysisService] Распарсенный результат от API: {parsed_result}")

            weekly_analysis = await self._create_or_update_weekly_analysis(
                user=user,
                week_start_date=week_start_date,
                parsed_result=parsed_result,
                api_result=api_result,
                context=context
            )
            logger.debug(f"[WeeklyAnalysisService] WeeklyAnalysis (ID: {weekly_analysis.id}) создан для {user.telegram_id} за неделю {week_start_date}")
            return {
                "success": True,
                "message": "Еженедельный анализ успешно завершен.",
                "weekly_analysis": weekly_analysis,
                "error": None
            }

        except Exception as e:
            logger.error(f"[WeeklyAnalysisService] Критическая ошибка при еженедельном анализе для пользователя {user.telegram_id}: {e}", exc_info=True)
            try:
                 context = {
                    'user_profile': {
                        'username': user.username or f"user_{user.telegram_id}",
                        'first_name': user.first_name or "",
                        'awareness_level': user.awareness_level,
                    },
                    'daily_analyses': [],
                    'previous_weekly_analysis': None,
                    'week_statistics': {}
                 }
                 weekly_analysis = await self._create_or_update_weekly_analysis(
                    user=user,
                    week_start_date=week_start_date if 'week_start_date' in locals() else date.today(),
                    parsed_result={},
                    api_result={"error": "critical_exception", "message": str(e)},
                    context=context
                 )
            except Exception as inner_e:
                 logger.error(f"[WeeklyAnalysisService] Не удалось создать запись об ошибке в WeeklyAnalysis: {inner_e}")
                 weekly_analysis = None

            return {
                "success": False,
                "message": "Критическая ошибка при анализе недели.",
                "weekly_analysis": weekly_analysis,
                "error": str(e)
            }

    async def _gather_weekly_context(
        self, 
        user: User, 
        week_start_date: date, 
        week_end_date: date
    ) -> Dict[str, Any]:
        """
        Собирает контекст для еженедельного анализа.

        Args:
            user: Пользователь.
            week_start_date: Дата начала недели (понедельник).
            week_end_date: Дата конца недели (воскресенье).

        Returns:
            Dict[str, Any]: Словарь с контекстом.
        """
        logger.debug(f"[WeeklyAnalysisService] Сбор контекста для недели {week_start_date} - {week_end_date} пользователя {user.telegram_id}")

        context = {
            'has_data': False,
            'user_profile': {},
            'daily_analyses': [],
            'previous_weekly_analysis': None,
            'week_statistics': {}
        }

        # Профиль пользователя — используем адаптеры для AI
        extended_user_profile = {
            'username': user.username or f"user_{user.telegram_id}",
            'first_name': user.first_name or "",
            'awareness_level': user.awareness_level,
            'date_of_birth': user.date_of_birth,
            # Адаптеры возвращают простой формат для AI
            "personality_traits": field_to_ai_format(user.personality_traits, 'personality_traits') if user.personality_traits else [],
            "life_facts": field_to_ai_format(user.life_facts, 'life_facts') if user.life_facts else [],
            "hobbies": field_to_ai_format(user.hobbies, 'hobbies') if user.hobbies else [],
            "core_values": field_to_ai_format(user.core_values, 'core_values') if user.core_values else [],
            "triggers": field_to_ai_format(user.triggers, 'triggers') if user.triggers else [],
            "strengths": field_to_ai_format(user.strengths, 'strengths') if user.strengths else [],
            "areas_for_growth": field_to_ai_format(user.areas_for_growth, 'areas_for_growth') if user.areas_for_growth else [],
        }
        context['user_profile'] = extended_user_profile

        # DailyAnalysis за неделю
        daily_analyses_data = []
        current_date = week_start_date
        total_entries = 0
        total_mood_scores = []
        tasks_assigned = 0
        tasks_completed = 0
        unique_themes = set()
        unique_emotions = set()
        total_word_count = 0

        while current_date <= week_end_date:
            logger.debug(f"[WeeklyAnalysisService] Обрабатываем дату: {current_date}")
            try:
                # Получение CombinedDiaryEntry
                @sync_to_async
                def _get_combined_entry_sync():
                    try:
                        return CombinedDiaryEntry.objects.select_related('daily_analysis').get(
                            user=user, date=current_date
                        )
                    except CombinedDiaryEntry.DoesNotExist:
                        return None

                combined_entry = await _get_combined_entry_sync()

                if combined_entry:
                    logger.debug(f"[WeeklyAnalysisService] Найден CombinedDiaryEntry ID {combined_entry.id} за {current_date}")
                    total_entries += combined_entry.entry_count
                    total_word_count += len(combined_entry.text.split()) if combined_entry.text else 0
                    if isinstance(combined_entry.daily_mood_scores, list):
                        total_mood_scores.extend(combined_entry.daily_mood_scores)
                    else:
                        logger.warning(f"[WeeklyAnalysisService] daily_mood_scores для {current_date} не является списком: {type(combined_entry.daily_mood_scores)}")

                    # --- Получение и обработка DailyAnalysis ---
                    if hasattr(combined_entry, 'daily_analysis') and combined_entry.daily_analysis:
                        da = combined_entry.daily_analysis
                        logger.debug(f"[WeeklyAnalysisService] Найден DailyAnalysis ID {da.id} для CombinedDiaryEntry ID {combined_entry.id}")

                        # Сбор данных для daily_analyses_data
                        da_data = {
                            "date": combined_entry.date.isoformat(),
                            "mood_trend": getattr(da, 'mood_trend', 'unknown'),
                            "key_themes": list(da.key_themes) if isinstance(da.key_themes, (list, tuple)) else [],
                            "emotional_patterns": list(da.emotional_patterns) if isinstance(da.emotional_patterns, (list, tuple)) else [],
                            "insights": list(da.insights) if isinstance(da.insights, (list, tuple)) else [],
                            "overall_analysis_text": getattr(da, 'overall_analysis_text', ''),
                            "average_mood_score": getattr(combined_entry, 'average_mood_score', 0.0)
                        }
                        daily_analyses_data.append(da_data)
                        logger.debug(f"[WeeklyAnalysisService] Данные DailyAnalysis за {current_date} добавлены.")

                        # Сбор уникальных тем (key_themes)
                        key_themes_raw = getattr(da, 'key_themes', [])
                        if isinstance(key_themes_raw, list):
                            for theme_item in key_themes_raw:
                                try:
                                    hash(theme_item)
                                    if isinstance(theme_item, str):
                                        unique_themes.add(theme_item[:50])
                                except TypeError:
                                    if isinstance(theme_item, dict):
                                        theme_text = theme_item.get('theme') or theme_item.get('text')
                                        if isinstance(theme_text, str):
                                            unique_themes.add(theme_text[:50])
                                    else:
                                        logger.debug(f"[WeeklyAnalysisService] Неподходящий тип элемента в key_themes: {type(theme_item)}. Пропущен.")
                        else:
                            logger.warning(f"[WeeklyAnalysisService] key_themes для {current_date} не является списком: {type(key_themes_raw)}")

                        # Сбор уникальных эмоций (emotional_patterns)
                        emotional_patterns_raw = getattr(da, 'emotional_patterns', [])
                        if isinstance(emotional_patterns_raw, list):
                            for pattern_item in emotional_patterns_raw:
                                try:
                                    hash(pattern_item)
                                    if isinstance(pattern_item, str):
                                        unique_emotions.add(pattern_item)
                                except TypeError:
                                    if isinstance(pattern_item, dict):
                                        emotion_text = pattern_item.get('emotion')
                                        if isinstance(emotion_text, str):
                                            unique_emotions.add(emotion_text)
                                    else:
                                        logger.debug(f"[WeeklyAnalysisService] Неподходящий тип элемента в emotional_patterns: {type(pattern_item)}. Пропущен.")
                        else:
                            logger.warning(f"[WeeklyAnalysisService] emotional_patterns для {current_date} не является списком: {type(emotional_patterns_raw)}")

                    else:
                        logger.debug(f"[WeeklyAnalysisService] DailyAnalysis для CombinedDiaryEntry ID {combined_entry.id} за {current_date} не найден.")

                else:
                    logger.debug(f"[WeeklyAnalysisService] CombinedDiaryEntry за {current_date} не найден.")

                # --- Счетчики задач ---
                @sync_to_async
                def _get_tasks_sync():
                    return TherapyTask.objects.filter(user=user, assigned_at__date=current_date).count()

                @sync_to_async
                def _get_completed_tasks_sync():
                    return TaskCompletion.objects.filter(
                        task__user=user, created_at__date=current_date
                    ).count()

                day_tasks_count = await _get_tasks_sync()
                day_completed_tasks_count = await _get_completed_tasks_sync()

                tasks_assigned += day_tasks_count
                tasks_completed += day_completed_tasks_count
                logger.debug(f"[WeeklyAnalysisService] Задачи за {current_date}: назначено {day_tasks_count}, выполнено {day_completed_tasks_count}")

            except Exception as e:
                logger.error(f"[WeeklyAnalysisService] Критическая ошибка при сборе данных за {current_date}: {e}", exc_info=True)
            
            current_date += timedelta(days=1)

        context['daily_analyses'] = daily_analyses_data
        if daily_analyses_data:
            context['has_data'] = True

        # Предыдущий WeeklyAnalysis
        previous_week_start = week_start_date - timedelta(weeks=1)
        previous_analysis = await self._get_weekly_analysis_for_week(user, previous_week_start)
        if previous_analysis:
            context['previous_weekly_analysis'] = {
                "week_start_date": previous_analysis.week_start_date.isoformat(),
                "summary_text": previous_analysis.summary_text,
            }
        else:
             logger.debug(f"[WeeklyAnalysisService] Предыдущий анализ недели для {user.telegram_id} не найден.")

        # Статистика недели
        streak_days_current = 0
        temp_date = week_end_date
        while temp_date >= week_start_date:
            @sync_to_async
            def _check_entry_for_date_sync(d):
                return CombinedDiaryEntry.objects.filter(user=user, date=d).exists()
            has_entry = await _check_entry_for_date_sync(temp_date)
            if has_entry:
                streak_days_current += 1
            else:
                break
            temp_date -= timedelta(days=1)

        avg_mood_score = sum(total_mood_scores) / len(total_mood_scores) if total_mood_scores else 0.0

        context['week_statistics'] = {
            "total_entries": total_entries,
            "streak_days_current": streak_days_current,
            "avg_mood_score": round(avg_mood_score, 2),
            "tasks_assigned": tasks_assigned,
            "tasks_completed": tasks_completed,
            "unique_themes_count": len(unique_themes),
            "unique_emotions_count": len(unique_emotions),
            "word_count_total": total_word_count
        }

        logger.debug(f"[WeeklyAnalysisService] Контекст собран для недели {week_start_date} - {week_end_date}")
        return context

    async def _get_weekly_analysis_for_week(self, user: User, week_start_date: date) -> Optional[WeeklyAnalysis]:
        """Получает анализ недели для конкретной даты начала недели."""
        try:
            @sync_to_async
            def _get_sync():
                try:
                    return WeeklyAnalysis.objects.get(user=user, week_start_date=week_start_date)
                except WeeklyAnalysis.DoesNotExist:
                    return None
            return await _get_sync()
        except Exception as e:
            logger.error(f"[WeeklyAnalysisService] Ошибка при получении анализа недели {week_start_date} для пользователя {user.telegram_id}: {e}")
            return None

    async def _create_or_update_weekly_analysis(
        self, 
        user: User, 
        week_start_date: date,
        parsed_result: Dict[str, Any], 
        api_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> WeeklyAnalysis:
        """
        Создает объект WeeklyAnalysis на основе результата анализа.

        Args:
            user: Пользователь.
            week_start_date: Дата начала недели.
            parsed_result: Распарсенный результат от API.
            api_result: Полный ответ API.
            context: Контекст, использованный для анализа.

        Returns:
            WeeklyAnalysis: Созданный объект.
        """
        logger.debug(f"[WeeklyAnalysisService] Создание WeeklyAnalysis для пользователя {user.telegram_id}, неделя {week_start_date}")

        # Извлекаем данные из результата ИИ
        summary_text = parsed_result.get('summary_text', 'Анализ недели завершен.')
        
        progress_insights = parsed_result.get('progress_insights', {})
        if not isinstance(progress_insights, dict):
            logger.warning("[WeeklyAnalysisService] progress_insights не является словарем.")
            progress_insights = {}

        awareness_level_adjustment = parsed_result.get('awareness_level_adjustment', {})
        consolidated_user_profile_to_save = {}
        if isinstance(awareness_level_adjustment, dict) and awareness_level_adjustment:
            new_level = awareness_level_adjustment.get('new_level')
            if new_level is not None:
                 consolidated_user_profile_to_save['awareness_level'] = new_level
        
        statistics = parsed_result.get('statistics', context.get('week_statistics', {}))
        if not isinstance(statistics, dict):
            logger.warning("[WeeklyAnalysisService] statistics не является словарем.")
            statistics = context.get('week_statistics', {})

        comparison_with_previous = parsed_result.get('comparison_with_previous', {})
        if not isinstance(comparison_with_previous, dict):
            logger.warning("[WeeklyAnalysisService] comparison_with_previous не является словарем.")
            comparison_with_previous = {}

        @sync_to_async
        def _create_sync():
            with transaction.atomic():
                 weekly_analysis = WeeklyAnalysis(
                    user=user,
                    week_start_date=week_start_date,
                    summary_text=summary_text,
                    progress_insights=progress_insights,
                    consolidated_user_profile=consolidated_user_profile_to_save, 
                    statistics=statistics,
                    comparison_with_previous=comparison_with_previous,
                    api_response=api_result
                 )
                 weekly_analysis.save()
                 logger.debug(f"[SYNC] WeeklyAnalysis ID {weekly_analysis.id} создан.")
                 
                 # ─── Генерируем full_psych_profile ───────────────────
                 try:
                     from diary.services.full_profile_service import full_profile_service
                     full_profile = full_profile_service.generate_for_user(user)
                     user.full_psych_profile = full_profile
                     user.save(update_fields=['full_psych_profile'])
                     logger.debug(f"[SYNC] full_psych_profile обновлён для пользователя {user.telegram_id}")
                 except Exception as e:
                     logger.warning(f"[SYNC] Ошибка генерации full_psych_profile: {e}")
                 
                 return weekly_analysis
        return await _create_sync()


weekly_analysis_service = WeeklyAnalysisService()


async def perform_weekly_analysis(user: User) -> Dict[str, Any]:
    """Удобная асинхронная функция для выполнения еженедельного анализа."""
    return await weekly_analysis_service.perform_weekly_analysis(user)
