"""
Сервис для выполнения полного анализа дня (Full Day Analysis).
"""

import logging

from datetime import date, datetime
from typing import Dict, Any, Optional
from asgiref.sync import sync_to_async
from django.db import transaction

from users.models import User
from diary.models import CombinedDiaryEntry, DiaryEntry, PsychoAnalysis, TherapyTask, TaskCompletion, DailyAnalysis
from diary.services.daily_state_service import daily_state_service
from diary.services.smart_prompt_manager import smart_prompt_manager
from bot.services.diary_service import diary_service
from bot.services.deepseek_api import deepseek_api_service
from prompts.get_prompt import get_prompt
from core.profile_field_utils import normalize_compressed_profile_for_prompt

logger = logging.getLogger(__name__)


class FullDayAnalysisService:
    """Сервис для выполнения полного анализа дня."""

    async def perform_full_day_analysis(self, user: User, target_date: date) -> Dict[str, Any]:
        """
        Выполняет полный анализ дня для пользователя на заданную дату.

        Args:
            user: Пользователь.
            target_date: Дата для анализа.

        Returns:
            Dict[str, Any]: Результат операции.
                - success (bool): Успешность операции.
                - message (str): Сообщение о результате.
                - daily_analysis (Optional[DailyAnalysis]): Объект анализа дня, если создан/обновлен.
                - error (Optional[str]): Сообщение об ошибке, если есть.
        """
        logger.debug(f"[FullDayAnalysisService] Начало полного анализа дня для пользователя {user.telegram_id} за {target_date}")
        try:
            combined_entry = await daily_state_service.get_daily_state(user, target_date)
            if not combined_entry:
                logger.warning(f"[FullDayAnalysisService] CombinedDiaryEntry не найден для {user.telegram_id} за {target_date}")
                return {
                    "success": False,
                    "message": "Нет данных для анализа за этот день.",
                    "daily_analysis": None,
                    "error": "no_combined_entry"
                }
            if not combined_entry.text.strip():
                logger.warning(f"[FullDayAnalysisService] CombinedDiaryEntry пуст для {user.telegram_id} за {target_date}")
                return {
                    "success": False,
                    "message": "Нет текста записей для анализа за этот день.",
                    "daily_analysis": None,
                    "error": "empty_combined_entry"
                }
            context = await self._gather_context(user, target_date, combined_entry)
            logger.debug(f"[FullDayAnalysisService] Контекст собран для {user.telegram_id} за {target_date}")

            # Проверяем подписку для выбора промпта
            is_premium_active = await sync_to_async(user.is_premium_active)()
            
            # Проверяем возможность использования LITE v2
            from django.conf import settings
            use_lite_v2 = (
                settings.USE_LITE_V2 and 
                user.compressed_psych_profile and 
                combined_entry.day_context_summary
            )

            if is_premium_active:
                import json
                compressed_profile = normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {})
                compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))
                prompt = get_prompt(
                    key='full_day_analysis',
                    language=user.language,
                    compressed_psych_profile_json=compressed_profile_json,
                    all_entries_combined_text=context['all_entries_combined_text'],
                    entry_analyses=context['entry_analyses'],
                    daily_mood_scores=context['daily_mood_scores'],
                    completed_tasks=context['completed_tasks'],
                )
                logger.debug(f"[FullDayAnalysisService] Используется ПОЛНЫЙ промпт (premium) для {user.telegram_id} за {target_date} (длина: {len(prompt)} символов)")
            elif use_lite_v2:
                # LITE v2: использует compressed_psych_profile + day_context_summary
                import json
                compressed_profile = normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {})
                compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))
                day_context_json = json.dumps(combined_entry.day_context_summary or {}, ensure_ascii=False, separators=(",", ":"))
                
                # Создаём краткую сводку из текста записей (первые 200 символов)
                compressed_entries_summary = context['all_entries_combined_text'][:200] + "..." if len(context['all_entries_combined_text']) > 200 else context['all_entries_combined_text']
                
                prompt = get_prompt(
                    key='full_day_analysis_lite_v2',
                    language=user.language,
                    compressed_psych_profile_json=compressed_profile_json,
                    day_context_summary_json=day_context_json,
                    compressed_entries_summary=compressed_entries_summary,
                    daily_mood_scores=context['daily_mood_scores'],
                )
                logger.debug(f"[FullDayAnalysisService] Используется LITE v2 промпт для {user.telegram_id} за {target_date} (длина: {len(prompt)} символов)")
                
                # Логирование для мониторинга
                logger.info(
                    f"[LiteV2] User {user.telegram_id}: using lite_v2_full_day, "
                    f"compressed={bool(user.compressed_psych_profile)}, "
                    f"day_context={bool(combined_entry.day_context_summary)}, "
                    f"prompt_length={len(prompt)}"
                )
            else:
                # LITE v1: используем compressed_psych_profile вместо старых полей
                import json
                compressed_profile = normalize_compressed_profile_for_prompt(user.compressed_psych_profile or {})
                compressed_profile_json = json.dumps(compressed_profile, ensure_ascii=False, separators=(",", ":"))
                
                prompt = get_prompt(
                    key='full_day_analysis_lite',
                    language=user.language,
                    compressed_psych_profile_json=compressed_profile_json,
                    all_entries_combined_text=context['all_entries_combined_text'],
                    entry_analyses=context['entry_analyses'],
                    daily_mood_scores=context['daily_mood_scores'],
                )
                logger.debug(f"[FullDayAnalysisService] Используется LITE v1 промпт (без подписки) для {user.telegram_id} за {target_date} (длина: {len(prompt)} символов)")
                
                # Логирование для мониторинга
                logger.info(
                    f"[LiteV2] User {user.telegram_id}: fallback to lite_v1, "
                    f"compressed={bool(user.compressed_psych_profile)}, "
                    f"day_context={bool(combined_entry.day_context_summary)}, "
                    f"USE_LITE_V2={settings.USE_LITE_V2}"
                )
            api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
            logger.debug(f"[FullDayAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[FullDayAnalysisService] Ошибка API при полном анализе дня: {error_msg}")
                daily_analysis = await self._create_or_update_daily_analysis_with_error(
                    combined_entry, api_result
                )
                return {
                    "success": False,
                    "message": f"Ошибка при анализе: {error_msg}",
                    "daily_analysis": daily_analysis,
                    "error": error_msg
                }
            parsed_result = api_result.get('result', {})
            logger.debug(f"[FullDayAnalysisService] Распарсенный результат от API: {parsed_result}")
            daily_analysis = await self._create_or_update_daily_analysis(
                combined_entry, parsed_result, api_result
            )
            logger.debug(f"[FullDayAnalysisService] DailyAnalysis (ID: {daily_analysis.id}) создан/обновлен для {user.telegram_id} за {target_date}")
            user_profile_updates = parsed_result.get('user_profile_updates', {})
            if user_profile_updates:
                update_success = await self._update_user_profile(user, user_profile_updates)
                if not update_success:
                    logger.warning(f"[FullDayAnalysisService] Не удалось обновить профиль пользователя {user.telegram_id} после анализа {target_date}.")
            awareness_adjustment = parsed_result.get('awareness_level_adjustment', {})
            if awareness_adjustment and isinstance(awareness_adjustment, dict):
                new_level = awareness_adjustment.get('new_level')
                reasoning = awareness_adjustment.get('reasoning', '')
                if new_level is not None and isinstance(new_level, int) and 1 <= new_level <= 10:
                    old_level = user.awareness_level
                    user.awareness_level = new_level
                    await sync_to_async(user.save)(update_fields=['awareness_level'])
                    logger.debug(f"[FullDayAnalysisService] Уровень осознанности пользователя {user.telegram_id} обновлен с {old_level} до {new_level}. Причина: {reasoning}")
            combined_entry.is_analyzed = True
            await combined_entry.asave(update_fields=['is_analyzed'])
            logger.debug(f"[FullDayAnalysisService] CombinedDiaryEntry (ID: {combined_entry.id}) помечен как проанализированный.")

            # Генерируем day_context_summary из DailyAnalysis
            try:
                from diary.services.day_context_service import day_context_service
                day_context = day_context_service.generate_from_daily_analysis(daily_analysis)
                if day_context:
                    combined_entry.day_context_summary = day_context
                    await combined_entry.asave(update_fields=['day_context_summary'])
                    logger.debug(
                        f"[FullDayAnalysisService] day_context_summary сохранён для CombinedDiaryEntry ID {combined_entry.id}"
                    )
            except Exception as ctx_error:
                logger.warning(
                    f"[FullDayAnalysisService] Ошибка генерации day_context_summary: {ctx_error}"
                )

            try:
                mock_entry = DiaryEntry(
                    user=user,
                    text="Анализ дня завершен",
                    created_at=datetime.now(),
                    language=user.language,
                    word_count=0
                )
                mock_entry.id = 0
                await smart_prompt_manager.on_day_analyzed(user, target_date, daily_analysis, user.language)
                logger.debug(f"[FullDayAnalysisService] Подсказка для следующего дня подготовлена через SmartPromptManager")
            except Exception as prompt_error:
                logger.error(f"[FullDayAnalysisService] Ошибка подготовки подсказки через SmartPromptManager: {prompt_error}")
            return {
                "success": True,
                "message": "Полный анализ дня успешно завершен.",
                "daily_analysis": daily_analysis,
                "error": None
            }
        except Exception as e:
            logger.error(f"[FullDayAnalysisService] Критическая ошибка при полном анализе дня для пользователя {user.telegram_id} за {target_date}: {e}", exc_info=True)
            try:
                combined_entry = await daily_state_service.get_daily_state(user, target_date)
                if combined_entry:
                    daily_analysis = await self._create_or_update_daily_analysis_with_error(
                        combined_entry, {"error": "critical_exception", "message": str(e)}
                    )
                else:
                    daily_analysis = None
            except Exception as inner_e:
                logger.error(f"[FullDayAnalysisService] Не удалось создать запись об ошибке в DailyAnalysis: {inner_e}")
                daily_analysis = None
            return {
                "success": False,
                "message": "Критическая ошибка при анализе дня.",
                "daily_analysis": daily_analysis,
                "error": str(e)
            }

    async def _gather_context(self, user: User, target_date: date, combined_entry: CombinedDiaryEntry) -> Dict[str, Any]:
        """
        Собирает контекст для полного анализа дня.

        Args:
            user: Пользователь.
            target_date: Дата для анализа.
            combined_entry: Объект CombinedDiaryEntry.

        Returns:
            Dict[str, Any]: Словарь с контекстом.
        """
        logger.debug(f"[FullDayAnalysisService] Сбор контекста для {user.telegram_id} за {target_date}")
        all_entries_text = combined_entry.text
        entries = await diary_service.get_user_entries_for_date(user, target_date)
        entry_analyses_data = []
        for entry in entries:
            try:
                analysis = await sync_to_async(lambda: entry.analysis)()
                if analysis:
                    entry_analyses_data.append({
                        "entry_id": entry.id,
                        "entry_text_snippet": entry.text[:200] + "..." if len(entry.text) > 200 else entry.text,
                        "mood_score": analysis.mood_score,
                        "comment": analysis.comment,
                        "recommendation": analysis.recommendation,
                        "user_comment": entry.user_comment
                    })
            except PsychoAnalysis.DoesNotExist:
                entry_analyses_data.append({
                    "entry_id": entry.id,
                    "entry_text_snippet": entry.text[:200] + "..." if len(entry.text) > 200 else entry.text,
                    "mood_score": None,
                    "comment": "Анализ отсутствует",
                    "recommendation": "Анализ отсутствует",
                    "user_comment": entry.user_comment
                })
                logger.debug(f"[FullDayAnalysisService] Анализ для записи {entry.id} отсутствует.")
        daily_mood_scores = combined_entry.daily_mood_scores
        completed_tasks_data = []
        related_tasks = []
        async for task in TherapyTask.objects.filter(user=user, related_entry__in=entries):
            related_tasks.append(task)
        for task in related_tasks:
            if task.status == 'completed':
                try:
                    completion = await sync_to_async(lambda: task.completion)()
                    if completion:
                        completed_tasks_data.append({
                            "task_title": task.title,
                            "task_description": task.description,
                            "completion_text": completion.completion_text,
                            "feelings_text": completion.feelings_text,
                        })
                except TaskCompletion.DoesNotExist:
                    logger.debug(f"[FullDayAnalysisService] Completion для задания {task.id} отсутствует, несмотря на статус 'completed'.")
        context = {
            "all_entries_combined_text": all_entries_text,
            "entry_analyses": entry_analyses_data,
            "daily_mood_scores": daily_mood_scores,
            "completed_tasks": completed_tasks_data,
        }
        logger.debug(f"[FullDayAnalysisService] Контекст собран для {user.telegram_id} за {target_date}")
        return context

    async def _create_or_update_daily_analysis(self, combined_entry: CombinedDiaryEntry, parsed_result: Dict[str, Any], api_result: Dict[str, Any]) -> DailyAnalysis:
        """
        Создает или обновляет объект DailyAnalysis на основе результата анализа.

        Args:
            combined_entry: Объект CombinedDiaryEntry.
            parsed_result: Распарсенный результат от API.

        Returns:
            DailyAnalysis: Созданный или обновленный объект.
        """
        logger.debug(f"[FullDayAnalysisService] Создание/обновление DailyAnalysis для CombinedDiaryEntry ID {combined_entry.id}")

        daily_analysis_data = parsed_result.get('daily_analysis', {})
        if not isinstance(daily_analysis_data, dict):
            logger.warning(f"[FullDayAnalysisService] daily_analysis_data не является словарем: {type(daily_analysis_data)}. Используется пустой словарь.")
            daily_analysis_data = {}
        mood_trend_raw = daily_analysis_data.get('mood_trend', 'stable')
        valid_mood_trends = [t[0] for t in DailyAnalysis._meta.get_field('mood_trend').choices]
        mood_trend = mood_trend_raw if mood_trend_raw in valid_mood_trends else 'stable'
        key_themes = daily_analysis_data.get('key_themes', [])
        emotional_patterns = daily_analysis_data.get('emotional_patterns', [])
        insights = daily_analysis_data.get('insights', [])
        recommendations = daily_analysis_data.get('recommendations', [])
        overall_analysis_text = daily_analysis_data.get('overall_analysis_text', '').strip()
        logger.debug(f"[FullDayAnalysisService] Извлеченный overall_analysis_text (первые 100 символов): '{overall_analysis_text[:100]}...'")
        @sync_to_async
        def _create_or_update_sync():
            with transaction.atomic():
                try:
                    daily_analysis = DailyAnalysis.objects.select_for_update().get(combined_entry=combined_entry)
                    logger.debug(f"[SYNC] Найден существующий DailyAnalysis ID {daily_analysis.id} для CombinedDiaryEntry ID {combined_entry.id}")
                    is_update = True
                except DailyAnalysis.DoesNotExist:
                    daily_analysis = DailyAnalysis(combined_entry=combined_entry)
                    logger.debug(f"[SYNC] Создается новый DailyAnalysis для CombinedDiaryEntry ID {combined_entry.id}")
                    is_update = False
                daily_analysis.mood_trend = mood_trend
                daily_analysis.key_themes = key_themes
                daily_analysis.emotional_patterns = emotional_patterns
                daily_analysis.insights = insights
                daily_analysis.recommendations = recommendations
                daily_analysis.overall_analysis_text = overall_analysis_text
                logger.debug(f"[SYNC] Установлен overall_analysis_text для DailyAnalysis ID {daily_analysis.id}")
                daily_analysis.api_response = api_result
                update_fields = ['mood_trend', 'key_themes', 'emotional_patterns', 'insights', 'recommendations', 'overall_analysis_text', 'api_response']
                if is_update:
                    daily_analysis.save(update_fields=update_fields)
                    logger.debug(f"[SYNC] DailyAnalysis ID {daily_analysis.id} обновлен.")
                else:
                    daily_analysis.save()
                    logger.debug(f"[SYNC] DailyAnalysis ID {daily_analysis.id} создан.")  
            return daily_analysis
        return await _create_or_update_sync()

    async def _create_or_update_daily_analysis_with_error(self, combined_entry: CombinedDiaryEntry, error_data: Dict[str, Any]) -> Optional[DailyAnalysis]:
        """
        Создает или обновляет DailyAnalysis с информацией об ошибке.

        Args:
            combined_entry: Объект CombinedDiaryEntry.
            error_data: Данные об ошибке.

        Returns:
            Optional[DailyAnalysis]: Созданный или обновленный объект, или None.
        """
        try:
            @sync_to_async
            def _create_error_sync():
                with transaction.atomic():
                    try:
                        daily_analysis = DailyAnalysis.objects.select_for_update().get(combined_entry=combined_entry)
                        is_update = True
                    except DailyAnalysis.DoesNotExist:
                        daily_analysis = DailyAnalysis(combined_entry=combined_entry)
                        is_update = False
                    daily_analysis.mood_trend = 'stable'
                    daily_analysis.key_themes = [{"theme": "Ошибка анализа", "mentions": 1, "significance": 0.5}]
                    daily_analysis.emotional_patterns = []
                    daily_analysis.insights = [{"text": f"Ошибка при анализе: {error_data.get('message', 'Неизвестная ошибка')}", "category": "other", "significance": 0.1}]
                    daily_analysis.recommendations = ["Попробуйте перезапустить анализ позже."]
                    if is_update:
                        daily_analysis.save(update_fields=['mood_trend', 'key_themes', 'emotional_patterns', 'insights', 'recommendations'])
                    else:
                        daily_analysis.save()
                return daily_analysis
            return await _create_error_sync()
        except Exception as e:
            logger.error(f"[FullDayAnalysisService] Ошибка при создании DailyAnalysis с ошибкой: {e}")
            return None

    async def _update_user_profile(self, user: User, profile_updates: Dict[str, Any]) -> bool:
        """
        Обновляет поля профиля пользователя на основе данных от ИИ.

        Теперь использует weighted format с автоматическим подсчётом весов и частоты.

        Args:
            user: Объект пользователя.
            profile_updates: Словарь обновлений из ответа ИИ (user_profile_updates).

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.debug(f"[FullDayAnalysisService] Обновление профиля пользователя {user.telegram_id} на основе данных ИИ.")
        logger.debug(f"[FullDayAnalysisService] Полученные обновления: {profile_updates}")

        if not profile_updates or not isinstance(profile_updates, dict):
            logger.debug("[FullDayAnalysisService] Нет данных для обновления профиля пользователя.")
            return True

        # Импортируем утилиты для работы с весами
        from core.profile_field_utils import (
            merge_profile_items,
            update_item_frequency,
            mark_stale_items,
            create_weighted_item,
            convert_to_weighted_format,
            sort_by_weight,
            MAX_ITEMS_PER_FIELD
        )
        from django.utils import timezone

        fields_updated = []
        try:
            # --- Обработка personality_traits ---
            new_traits_data = profile_updates.get('personality_traits')
            if new_traits_data is not None:
                traits_changed = False

                if not isinstance(user.personality_traits, dict):
                    logger.warning("[FullDayAnalysisService] user.personality_traits не является словарём. Переинициализируем.")
                    user.personality_traits = {}
                    traits_changed = True

                if isinstance(new_traits_data, list):
                    # AI прислал список строк — добавляем с весом
                    for trait_name in new_traits_data:
                        if isinstance(trait_name, str) and trait_name.strip():
                            old_weight = user.personality_traits.get(trait_name, 0)
                            # Увеличиваем вес: new_weight = old + 0.5, max 3.0
                            new_weight = min(old_weight + 0.5, 3.0)
                            user.personality_traits[trait_name] = new_weight
                            traits_changed = True
                            logger.debug(f"[FullDayAnalysisService] Черта '{trait_name}': {old_weight} -> {new_weight}")
                elif isinstance(new_traits_data, dict):
                    # AI прислал словарь с весами
                    for trait_name, trait_weight in new_traits_data.items():
                        if isinstance(trait_name, str) and isinstance(trait_weight, (int, float)):
                            old_weight = user.personality_traits.get(trait_name, 0)
                            # Берём max веса
                            user.personality_traits[trait_name] = max(old_weight, trait_weight)
                            traits_changed = True

                if traits_changed:
                    fields_updated.append('personality_traits')

            # --- Обработка list полей с весами ---
            # Используем merge_profile_items для интеллектуального объединения
            list_field_names = ['life_facts', 'hobbies', 'core_values', 'triggers', 'strengths', 'areas_for_growth']
            
            for field_name in list_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue
                if not isinstance(updates_for_field, list):
                    logger.warning(f"[FullDayAnalysisService] Некорректный формат для {field_name}: {type(updates_for_field)}")
                    continue

                current_field = getattr(user, field_name, [])
                if not isinstance(current_field, list):
                    current_field = []

                # Конвертируем в weighted формат если нужно
                if current_field and isinstance(current_field[0], dict):
                    # Уже в weighted формате
                    existing_weighted = current_field
                elif current_field and isinstance(current_field[0], str):
                    # Старый формат — конвертируем
                    existing_weighted = convert_to_weighted_format(current_field)
                else:
                    existing_weighted = []

                # Обрабатываем updates от AI
                new_weighted_items = []
                items_to_remove = []
                
                for item in updates_for_field:
                    if isinstance(item, str) and item.strip():
                        # Строка — создаём элемент с дефолтным весом
                        new_weighted_items.append(create_weighted_item(item.strip(), weight=0.5))
                    elif isinstance(item, dict):
                        if 'remove' in item:
                            # Удаление
                            items_to_remove.append(item['remove'])
                        elif 'value' in item:
                            # Уже в weighted формате от AI
                            new_weighted_items.append({
                                "value": item.get('value', ''),
                                "weight": item.get('weight', 0.5),
                                "frequency": item.get('frequency', 1),
                                "added_at": item.get('added_at'),
                                "last_seen": timezone.now().date().isoformat(),
                                "is_stale": False
                            })

                # Удаляем элементы
                if items_to_remove:
                    existing_weighted = [
                        e for e in existing_weighted 
                        if e.get('value') not in items_to_remove
                    ]

                # Объединяем с новыми элементами (стратегия: max weight)
                if new_weighted_items:
                    existing_weighted = merge_profile_items(
                        existing_weighted, 
                        new_weighted_items, 
                        strategy="max_weight"
                    )
                    
                    # Обновляем frequency для существующих элементов
                    for new_item in new_weighted_items:
                        existing_weighted = update_item_frequency(
                            existing_weighted, 
                            new_item.get('value', '')
                        )

                # Помечаем stale элементы
                existing_weighted = mark_stale_items(existing_weighted)

                # Ограничиваем количество элементов (топ по весу)
                if len(existing_weighted) > MAX_ITEMS_PER_FIELD:
                    existing_weighted = sort_by_weight(existing_weighted, reverse=True)[:MAX_ITEMS_PER_FIELD]

                # Проверяем изменилось ли поле
                current_str = str(current_field)
                new_str = str(existing_weighted)
                
                if current_str != new_str:
                    setattr(user, field_name, existing_weighted)
                    fields_updated.append(field_name)
                    logger.debug(f"[FullDayAnalysisService] Поле {field_name} обновлено с {len(current_field)} до {len(existing_weighted)} элементов")

            # --- Сохранение изменений ---
            if fields_updated:
                logger.debug(f"[FullDayAnalysisService] Обновлены поля профиля: {fields_updated}")
                await sync_to_async(user.save)(update_fields=fields_updated)
                
                # После обновления профиля — обновляем compressed_psych_profile
                try:
                    from diary.services.compressed_profile_service import compressed_profile_service
                    new_compressed = compressed_profile_service.generate_for_user(user)
                    if new_compressed:
                        user.compressed_psych_profile = new_compressed
                        await sync_to_async(user.save)(update_fields=['compressed_psych_profile'])
                        logger.debug(f"[FullDayAnalysisService] compressed_psych_profile обновлён для {user.telegram_id}")
                except Exception as e:
                    logger.warning(f"[FullDayAnalysisService] Не удалось обновить compressed_psych_profile: {e}")
            else:
                logger.debug(f"[FullDayAnalysisService] Нет изменений для сохранения в профиле пользователя {user.telegram_id}.")

            return True
        except Exception as e:
            logger.error(f"[FullDayAnalysisService] Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}", exc_info=True)
            return False

full_day_analysis_service = FullDayAnalysisService()


async def perform_full_day_analysis(user: User, target_date: date) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения полного анализа дня.
    """
    return await full_day_analysis_service.perform_full_day_analysis(user, target_date)


async def build_full_day_reanalysis_notification(
    user: User,
    target_date: date,
    language: str,
) -> Dict[str, Any]:
    """
    Use-case: выполнить полный анализ дня и собрать payload уведомления (без send).

    Returns:
        {
          success: bool,
          text: str,
          reply_markup: Optional[InlineKeyboardMarkup],
          error: Optional[str],
        }
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from messages import get_message

    try:
        analysis_result = await perform_full_day_analysis(user, target_date)
        year, month, day = target_date.year, target_date.month, target_date.day

        if analysis_result.get("success"):
            daily_analysis = analysis_result.get("daily_analysis")
            text = get_message("analysis_recalculated", language)
            if daily_analysis and getattr(daily_analysis, "overall_analysis_text", None):
                text += f"\n\n{daily_analysis.overall_analysis_text[:200]}..."
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔬 Просмотреть анализ",
                            callback_data=f"view_full_day_analysis:{year}:{month}:{day}",
                        )
                    ]
                ]
            )
            return {
                "success": True,
                "text": text,
                "reply_markup": reply_markup,
                "error": None,
            }

        error_msg = analysis_result.get("message") or ""
        return {
            "success": False,
            "text": f"{get_message('error_processing', language)}: {error_msg}",
            "reply_markup": None,
            "error": error_msg or "full_day_analysis_failed",
        }
    except Exception as exc:
        logger.error(
            f"[build_full_day_reanalysis_notification] Ошибка для {user.telegram_id}, "
            f"{target_date}: {exc}",
            exc_info=True,
        )
        return {
            "success": False,
            "text": get_message("error_processing", language),
            "reply_markup": None,
            "error": str(exc),
        }
