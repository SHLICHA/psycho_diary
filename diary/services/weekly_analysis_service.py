# /home/shlicha/psycho_diary/diary/services/weekly_analysis_service.py
"""
Сервис для выполнения еженедельного анализа пользователя.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple
import pytz

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from users.models import User
from diary.models import (
    DailyAnalysis, CombinedDiaryEntry, TherapyTask, TaskCompletion,
    WeeklyAnalysis # Новая модель
)
from diary.services.daily_state_service import daily_state_service
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt
from messages import get_message

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
        logger.info(f"[WeeklyAnalysisService] Начало еженедельного анализа для пользователя {user.telegram_id}")

        try:
            # 1. Определяем начало и конец недели (Пн - Вс)
            # Неделя заканчивается в воскресенье, анализ запускается в понедельник
            # Поэтому анализируем неделю, закончившуюся вчера (воскресенье)
            # today_user_tz = (await user.aget_local_datetime()).date() # Асинхронный вариант
            today_user_tz = user.get_local_datetime().date() # Синхронный вариант, так как get_local_datetime синхронный
            logger.debug(f"[WeeklyAnalysisService] Сегодня по часовому поясу пользователя: {today_user_tz}")

            # Определяем воскресенье прошлой недели (конец анализируемой недели)
            last_sunday = today_user_tz - timedelta(days=today_user_tz.weekday() + 1)
            # Определяем понедельник той же недели (начало анализируемой недели)
            week_start_date = last_sunday - timedelta(days=6)
            
            logger.info(f"[WeeklyAnalysisService] Анализируем неделю с {week_start_date} по {last_sunday}")

            # 2. Проверяем, не существует ли уже анализ для этой недели
            existing_analysis = await self._get_weekly_analysis_for_week(user, week_start_date)
            if existing_analysis:
                logger.info(f"[WeeklyAnalysisService] Анализ для недели {week_start_date} уже существует (ID: {existing_analysis.id}). Пропускаем.")
                return {
                    "success": True,
                    "message": "Анализ для этой недели уже существует.",
                    "weekly_analysis": existing_analysis,
                    "error": None
                }

            # 3. Собираем контекст
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

            # 4. Сформировать промпт
            prompt = get_prompt(
                key='weekly_analysis', # Нужно будет добавить в prompts.py
                language=user.language,
                user_profile=context['user_profile'],
                daily_analyses=context['daily_analyses'],
                previous_weekly_analysis=context['previous_weekly_analysis'],
                week_statistics=context['week_statistics']
            )
            logger.debug(f"[WeeklyAnalysisService] Промпт сформирован для {user.telegram_id} за неделю {week_start_date} (длина: {len(prompt)} символов)")

            # 5. Вызвать DeepSeek API
            api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
            logger.debug(f"[WeeklyAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")

            # 6. Обработать результат API
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[WeeklyAnalysisService] Ошибка API при недельном анализе: {error_msg}")
                
                # Создаем WeeklyAnalysis с информацией об ошибке? Пока просто возвращаем ошибку.
                return {
                    "success": False,
                    "message": f"Ошибка при анализе недели: {error_msg}",
                    "weekly_analysis": None,
                    "error": error_msg
                }

            # 7. Парсинг результата и сохранение
            parsed_result = api_result.get('result', {})
            logger.debug(f"[WeeklyAnalysisService] Распарсенный результат от API: {parsed_result}")
            
            # 8. Создать/сохранить WeeklyAnalysis
            weekly_analysis = await self._create_or_update_weekly_analysis(
                user=user,
                week_start_date=week_start_date,
                parsed_result=parsed_result,
                api_result=api_result,
                context=context # Передаем для consolidated_user_profile
            )
            logger.info(f"[WeeklyAnalysisService] WeeklyAnalysis (ID: {weekly_analysis.id}) создан для {user.telegram_id} за неделю {week_start_date}")
            
            # 9. Обновить поля User на основе user_profile_updates из результата ИИ
            user_profile_updates = parsed_result.get('user_profile_updates', {})
            if user_profile_updates:
                update_success = await self._update_user_profile(user, user_profile_updates)
                if not update_success:
                    logger.warning(f"[WeeklyAnalysisService] Не удалось обновить профиль пользователя {user.telegram_id} после анализа недели {week_start_date}.")
                # Даже если обновление профиля не удалось, основной анализ считаем успешным
            
            # 10. (Опционально) Обновить awareness_level
            awareness_adjustment = parsed_result.get('awareness_level_adjustment', {})
            if awareness_adjustment and isinstance(awareness_adjustment, dict):
                new_level = awareness_adjustment.get('new_level')
                reasoning = awareness_adjustment.get('reasoning', '')
                if new_level is not None and isinstance(new_level, int) and 1 <= new_level <= 10:
                    old_level = user.awareness_level
                    user.awareness_level = new_level
                    await sync_to_async(user.save)(update_fields=['awareness_level'])
                    logger.info(f"[WeeklyAnalysisService] Уровень осознанности пользователя {user.telegram_id} обновлен с {old_level} до {new_level}. Причина: {reasoning}")

            return {
                "success": True,
                "message": "Еженедельный анализ успешно завершен.",
                "weekly_analysis": weekly_analysis,
                "error": None
            }

        except Exception as e:
            logger.error(f"[WeeklyAnalysisService] Критическая ошибка при еженедельном анализе для пользователя {user.telegram_id}: {e}", exc_info=True)
            
            # Попытка создать запись об ошибке в WeeklyAnalysis?
            # Пока просто возвращаем ошибку
            return {
                "success": False,
                "message": "Критическая ошибка при анализе недели.",
                "weekly_analysis": None,
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

        # --- 1. Профиль пользователя ---
        # Передаем расширенный профиль, как в full_day_analysis_service
        extended_user_profile = {
            'username': user.username or f"user_{user.telegram_id}",
            'first_name': user.first_name or "",
            'awareness_level': user.awareness_level,
            'is_premium': user.is_premium,
            "personality_traits": user.personality_traits,
            "life_facts": user.life_facts,
            "hobbies": user.hobbies,
            "core_values": user.core_values,
            "triggers": user.triggers,
            "strengths": user.strengths,
            "areas_for_growth": user.areas_for_growth,
            # Не передаем telegram_id и другие чувствительные данные
        }
        context['user_profile'] = extended_user_profile

        # --- 2. DailyAnalysis за неделю ---
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
             try:
                 # combined_entry = await daily_state_service.get_daily_state(user, current_date)
                 # Асинхронный вариант может быть медленнее из-за множества запросов
                 # Лучше один запрос с фильтрацией
                 @sync_to_async
                 def _get_combined_entries_sync():
                     return list(CombinedDiaryEntry.objects.filter(
                         user=user, date=current_date
                     ).select_related('daily_analysis'))
                 
                 combined_entries = await _get_combined_entries_sync()
                 
                 if combined_entries:
                     combined_entry = combined_entries[0]
                     total_entries += combined_entry.entry_count
                     total_word_count += len(combined_entry.text.split())
                     total_mood_scores.extend(combined_entry.daily_mood_scores)

                     if hasattr(combined_entry, 'daily_analysis'):
                         da = combined_entry.daily_analysis
                         da_data = {
                             "date": combined_entry.date.isoformat(),
                             "mood_trend": da.mood_trend,
                             "key_themes": da.key_themes,
                             "emotional_patterns": da.emotional_patterns,
                             "insights": da.insights,
                             "overall_analysis_text": da.overall_analysis_text,
                             "average_mood_score": combined_entry.average_mood_score
                         }
                         daily_analyses_data.append(da_data)

                         # Собираем уникальные темы и эмоции
                         for theme_dict in da.key_themes:
                             if isinstance(theme_dict, dict) and 'theme' in theme_dict:
                                 unique_themes.add(theme_dict['theme'])
                             elif isinstance(theme_dict, dict) and 'text' in theme_dict: # Альтернативный ключ
                                 unique_themes.add(theme_dict['text'][:50]) # Берем часть текста
                         
                         for pattern_dict in da.emotional_patterns:
                             if isinstance(pattern_dict, dict) and 'emotion' in pattern_dict:
                                 unique_emotions.add(pattern_dict['emotion'])
                             elif isinstance(pattern_dict, str):
                                 unique_emotions.add(pattern_dict)

                 # Считаем задачи за день
                 @sync_to_async
                 def _get_tasks_sync():
                     return list(TherapyTask.objects.filter(
                         user=user, assigned_at__date=current_date
                     ))
                 
                 @sync_to_async
                 def _get_completed_tasks_sync():
                     return list(TaskCompletion.objects.filter(
                         task__user=user, created_at__date=current_date
                     ))
                 
                 day_tasks = await _get_tasks_sync()
                 day_completed_tasks = await _get_completed_tasks_sync()
                 
                 tasks_assigned += len(day_tasks)
                 tasks_completed += len(day_completed_tasks)

             except Exception as e:
                 logger.error(f"[WeeklyAnalysisService] Ошибка при сборе данных за {current_date}: {e}")
             current_date += timedelta(days=1)

        context['daily_analyses'] = daily_analyses_data
        if daily_analyses_data:
            context['has_data'] = True

        # --- 3. Предыдущий WeeklyAnalysis ---
        # Определяем начало предыдущей недели
        previous_week_start = week_start_date - timedelta(weeks=1)
        previous_analysis = await self._get_weekly_analysis_for_week(user, previous_week_start)
        if previous_analysis:
            # Передаем только нужные поля или весь объект?
            # Для простоты передадим основные поля как словарь
            context['previous_weekly_analysis'] = {
                "week_start_date": previous_analysis.week_start_date.isoformat(),
                "summary_text": previous_analysis.summary_text,
                # Можно добавить другие поля, если они нужны в промпте
                # "progress_insights": previous_analysis.progress_insights,
                # "consolidated_user_profile": previous_analysis.consolidated_user_profile,
            }
        else:
             logger.debug(f"[WeeklyAnalysisService] Предыдущий анализ недели для {user.telegram_id} не найден.")

        # --- 4. Статистика недели ---
        # Рассчитываем серию дней подряд (простая оценка)
        # Для точности лучше хранить это в User или отдельно, но для MVP сделаем тут
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
                break # Серия прервана
            temp_date -= timedelta(days=1)

        # Получаем общий streak_days_total из User или оцениваем (упрощенно)
        # streak_days_total = user.??? # Нет такого поля. Можно добавить в User позже.
        # Пока используем streak_days_current как приближение или добавим в User позже.
        
        avg_mood_score = sum(total_mood_scores) / len(total_mood_scores) if total_mood_scores else 0.0

        context['week_statistics'] = {
            "total_entries": total_entries,
            "streak_days_current": streak_days_current,
            # "streak_days_total": streak_days_total, # Пока нет
            "avg_mood_score": round(avg_mood_score, 2),
            "tasks_assigned": tasks_assigned,
            "tasks_completed": tasks_completed,
            "unique_themes_count": len(unique_themes),
            "unique_emotions_count": len(unique_emotions),
            "word_count_total": total_word_count
        }
        
        # Попробуем обновить streak_days_total в User (если нужно)
        # Это можно сделать отдельно или здесь. Пока оставим комментарий.
        # if streak_days_current > (user.streak_days_total if hasattr(user, 'streak_days_total') else 0):
        #     user.streak_days_total = streak_days_current
        #     await user.asave(update_fields=['streak_days_total']) # Если добавим поле

        logger.debug(f"[WeeklyAnalysisService] Контекст собран для недели {week_start_date} - {week_end_date}")
        return context

    async def _get_weekly_analysis_for_week(self, user: User, week_start_date: date) -> Optional[WeeklyAnalysis]:
        """Получает анализ недели для конкретной даты начала недели."""
        try:
            # return await WeeklyAnalysis.objects.aget(user=user, week_start_date=week_start_date)
            # Синхронный вариант для совместимости
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
        context: Dict[str, Any] # Для consolidated_user_profile
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

        # Извлекаем данные
        summary_text = parsed_result.get('summary_text', 'Анализ недели завершен.')
        
        progress_insights = parsed_result.get('progress_insights', {})
        if not isinstance(progress_insights, dict):
            logger.warning("[WeeklyAnalysisService] progress_insights не является словарем.")
            progress_insights = {}

        # consolidated_user_profile из контекста или из результата?
        # Лучше взять обновленный профиль из результата ИИ и смержить с текущим
        # Но для простоты возьмем из контекста и обновим поля из user_profile_updates позже
        # Или возьмем из результата ИИ напрямую, если он содержит полный профиль
        # В промпте мы просим обновить весь профиль, значит ИИ должен вернуть обновленный
        consolidated_user_profile_from_ai = parsed_result.get('user_profile_updates', {})
        # Но это только обновления. Нужно применить их к текущему профилю.
        # Лучше взять текущий профиль и применить обновления.
        current_profile = context.get('user_profile', {})
        consolidated_user_profile = current_profile.copy() # База
        
        # Применяем обновления от ИИ
        for key, value in consolidated_user_profile_from_ai.items():
            if key in ['personality_traits', 'life_facts', 'hobbies', 'core_values', 'triggers', 'strengths', 'areas_for_growth']:
                if key == 'personality_traits' and isinstance(value, dict):
                    consolidated_user_profile[key] = value
                elif isinstance(value, list):
                    # Логика добавления/удаления для списков
                    current_list = consolidated_user_profile.get(key, [])
                    if not isinstance(current_list, list):
                        current_list = []
                    new_set = set(item for item in current_list if isinstance(item, str))
                    items_to_add = set()
                    items_to_remove = set()
                    for item in value:
                        if isinstance(item, str):
                            items_to_add.add(item)
                        elif isinstance(item, dict) and 'remove' in item:
                            item_to_remove = item['remove']
                            if isinstance(item_to_remove, str):
                                items_to_remove.add(item_to_remove)
                    new_set = new_set - items_to_remove
                    new_set.update(items_to_add)
                    consolidated_user_profile[key] = list(new_set)
                # awareness_level_adjustment обрабатывается отдельно
            elif key == 'awareness_level_adjustment':
                # Уже обработано
                pass
            else:
                # Другие поля, если есть
                consolidated_user_profile[key] = value

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
                    consolidated_user_profile=consolidated_user_profile,
                    statistics=statistics,
                    comparison_with_previous=comparison_with_previous,
                    api_response=api_result
                 )
                 weekly_analysis.save()
                 logger.info(f"[SYNC] WeeklyAnalysis ID {weekly_analysis.id} создан.")
                 return weekly_analysis
        return await _create_sync()

    async def _update_user_profile(self, user: User, profile_updates: Dict[str, Any]) -> bool:
        """
        Обновляет поля профиля пользователя на основе данных от ИИ.
        Логика взята из FullDayAnalysisService, но адаптирована под недельный анализ.

        Args:
            user: Объект пользователя.
            profile_updates: Словарь обновлений из ответа ИИ (user_profile_updates).

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"[WeeklyAnalysisService] Обновление профиля пользователя {user.telegram_id} на основе данных ИИ (недельный анализ).")
        logger.debug(f"[WeeklyAnalysisService] Полученные обновления: {profile_updates}")

        if not profile_updates or not isinstance(profile_updates, dict):
            logger.info("[WeeklyAnalysisService] Нет данных для обновления профиля пользователя (недельный).")
            return True # Не ошибка, просто нет данных

        fields_updated = []

        try:
            # --- Обработка personality_traits (словарь {trait: weight}) ---
            new_traits_dict = profile_updates.get('personality_traits')
            if new_traits_dict is not None and isinstance(new_traits_dict, dict):
                # Убедимся, что текущее значение - словарь
                if not isinstance(user.personality_traits, dict):
                    logger.warning("[WeeklyAnalysisService] user.personality_traits не является словарем. Переинициализируем.")
                    user.personality_traits = {}
                
                # Обновляем словарь traits
                for trait, weight in new_traits_dict.items():
                    if isinstance(trait, str) and isinstance(weight, (int, float)):
                        user.personality_traits[trait] = weight
                        logger.debug(f"[WeeklyAnalysisService] Обновлен/добавлен personality_trait '{trait}': {weight}")
                    else:
                       logger.warning(f"[WeeklyAnalysisService] Некорректный элемент в personality_traits: {trait}: {weight}")
                
                fields_updated.append('personality_traits')
            elif new_traits_dict is not None:
                 logger.warning(f"[WeeklyAnalysisService] Некорректный формат для personality_traits: {type(new_traits_dict)}. Ожидается словарь.")

            # --- Обработка списков (life_facts, hobbies, core_values, triggers, strengths, areas_for_growth) ---
            list_field_names = ['life_facts', 'hobbies', 'core_values', 'triggers', 'strengths', 'areas_for_growth']
            for field_name in list_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue # Поле не передано, пропускаем

                if not isinstance(updates_for_field, list):
                    logger.warning(f"[WeeklyAnalysisService] Некорректный формат для {field_name}: {type(updates_for_field)}. Ожидается список.")
                    continue

                # Получаем текущее значение поля у пользователя
                current_user_list = getattr(user, field_name, [])
                if not isinstance(current_user_list, list):
                    logger.warning(f"[WeeklyAnalysisService] Текущее значение {field_name} у пользователя не является списком. Перезаписываем.")
                    current_user_list = []
                
                current_user_set = set(item for item in current_user_list if isinstance(item, str))
                items_to_add = set()
                items_to_remove = set()

                for item in updates_for_field:
                    if isinstance(item, str):
                        items_to_add.add(item)
                    elif isinstance(item, dict) and 'remove' in item:
                        item_to_remove = item['remove']
                        if isinstance(item_to_remove, str):
                            items_to_remove.add(item_to_remove)
                        else:
                            logger.warning(f"[WeeklyAnalysisService] Некорректный формат 'remove' в {field_name}: {item_to_remove}")
                    else:
                        logger.warning(f"[WeeklyAnalysisService] Некорректный элемент в {field_name}: {item}")

                # Удаляем
                if items_to_remove:
                    new_set = current_user_set - items_to_remove
                    if len(new_set) != len(current_user_set):
                        current_user_set = new_set
                        logger.debug(f"[WeeklyAnalysisService] Удалены из {field_name}: {items_to_remove}")
                
                # Добавляем (избегая дубликатов)
                if items_to_add:
                    actually_added = items_to_add - current_user_set
                    if actually_added:
                        current_user_set.update(actually_added)
                        logger.debug(f"[WeeklyAnalysisService] Добавлены в {field_name}: {actually_added}")
                
                # Сохраняем обратно в поле пользователя, если было изменение
                final_list = list(current_user_set)
                if set(final_list) != set(current_user_list):
                    setattr(user, field_name, final_list)
                    fields_updated.append(field_name)

            # --- Сохранение изменений ---
            if fields_updated:
                logger.info(f"[WeeklyAnalysisService] Обновлены поля профиля пользователя {user.telegram_id}: {fields_updated}")
                await sync_to_async(user.save)(update_fields=fields_updated)
                logger.debug(f"[WeeklyAnalysisService] Изменения профиля пользователя {user.telegram_id} сохранены.")
            else:
                logger.debug(f"[WeeklyAnalysisService] Нет изменений для сохранения в профиле пользователя {user.telegram_id}.")

            return True

        except Exception as e:
            logger.error(f"[WeeklyAnalysisService] Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}", exc_info=True)
            return False


# Глобальный экземпляр сервиса
weekly_analysis_service = WeeklyAnalysisService()


# Удобные функции
async def perform_weekly_analysis(user: User) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения еженедельного анализа.
    """
    return await weekly_analysis_service.perform_weekly_analysis(user)
