# diary/services/full_day_analysis_service.py
"""
Сервис для выполнения полного анализа дня (Full Day Analysis).
"""

import logging
import json
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from asgiref.sync import sync_to_async
from django.db import transaction

from users.models import User
from diary.models import CombinedDiaryEntry, DiaryEntry, PsychoAnalysis, TherapyTask, TaskCompletion, DailyAnalysis
from diary.services.daily_state_service import daily_state_service
from diary.services.prompt_generation_service import prompt_generation_service
from bot.services.diary_service import diary_service
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt

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
        logger.info(f"[FullDayAnalysisService] Начало полного анализа дня для пользователя {user.telegram_id} за {target_date}")

        try:
            # 1. Получить или создать CombinedDiaryEntry
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

            # 2. Собрать контекст
            context = await self._gather_context(user, target_date, combined_entry)
            logger.debug(f"[FullDayAnalysisService] Контекст собран для {user.telegram_id} за {target_date}")

            # 3. Сформировать промпт
            prompt = get_prompt(
                key='full_day_analysis',
                language=user.language,
                user_profile=context['user_profile'], # Передаем словарь
                all_entries_combined_text=context['all_entries_combined_text'], # Передаем строку
                entry_analyses=context['entry_analyses'], # Передаем список словарей
                daily_mood_scores=context['daily_mood_scores'], # Передаем список
                completed_tasks=context['completed_tasks'], # Передаем список словарей
                #current_user_data=context['current_user_data'] # Передаем словарь
            )
            logger.debug(f"[FullDayAnalysisService] Промпт сформирован для {user.telegram_id} за {target_date} (длина: {len(prompt)} символов)")

            # 4. Вызвать DeepSeek API
            api_result = await deepseek_api_service.send_prompt_and_parse(prompt, language=user.language)
            logger.debug(f"[FullDayAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")

            # 5. Обработать результат API
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[FullDayAnalysisService] Ошибка API при полном анализе дня: {error_msg}")
                
                # Создаем/обновляем DailyAnalysis с информацией об ошибке
                # Передаем только api_result, так как parsed_result отсутствует
                daily_analysis = await self._create_or_update_daily_analysis_with_error(
                    combined_entry, api_result # Передаем api_result напрямую или извлекаем ошибку
                )
                # Если _create_or_update_daily_analysis_with_error не использует api_result,
                # можно передать словарь с ошибкой, как было раньше:
                # daily_analysis = await self._create_or_update_daily_analysis_with_error(
                #     combined_entry, {"error": error_msg, "raw_api_response": api_result}
                # )

                return {
                    "success": False,
                    "message": f"Ошибка при анализе: {error_msg}",
                    "daily_analysis": daily_analysis,
                    "error": error_msg
                }

            # 6. Парсинг результата
            parsed_result = api_result.get('result', {})
            logger.debug(f"[FullDayAnalysisService] Распарсенный результат от API: {parsed_result}")
            
            # 7. Создать/обновить DailyAnalysis
            daily_analysis = await self._create_or_update_daily_analysis(
                combined_entry, parsed_result, api_result # Передаем api_result
            )
            logger.info(f"[FullDayAnalysisService] DailyAnalysis (ID: {daily_analysis.id}) создан/обновлен для {user.telegram_id} за {target_date}")
            
            # 8. Обновить поля User на основе user_profile_updates
            user_profile_updates = parsed_result.get('user_profile_updates', {})
            if user_profile_updates:
                update_success = await self._update_user_profile(user, user_profile_updates)
                if not update_success:
                    logger.warning(f"[FullDayAnalysisService] Не удалось обновить профиль пользователя {user.telegram_id} после анализа {target_date}.")
                # Даже если обновление профиля не удалось, основной анализ считаем успешным
            
            # 9. (Опционально) Обновить awareness_level
            awareness_adjustment = parsed_result.get('awareness_level_adjustment', {})
            if awareness_adjustment and isinstance(awareness_adjustment, dict):
                new_level = awareness_adjustment.get('new_level')
                reasoning = awareness_adjustment.get('reasoning', '')
                if new_level is not None and isinstance(new_level, int) and 1 <= new_level <= 10:
                    old_level = user.awareness_level
                    user.awareness_level = new_level
                    await sync_to_async(user.save)(update_fields=['awareness_level'])
                    logger.info(f"[FullDayAnalysisService] Уровень осознанности пользователя {user.telegram_id} обновлен с {old_level} до {new_level}. Причина: {reasoning}")

            # 10. Отметить CombinedDiaryEntry как проанализированный
            combined_entry.is_analyzed = True
            await combined_entry.asave(update_fields=['is_analyzed'])
            logger.debug(f"[FullDayAnalysisService] CombinedDiaryEntry (ID: {combined_entry.id}) помечен как проанализированный.")
            # --- Генерация подсказки для ПЕРВОЙ записи СЛЕДУЮЩЕГО дня ---
            try:
                # Используем daily_analysis, который был создан/обновлен выше
                # daily_analysis_obj = await sync_to_async(lambda: daily_analysis)() # <-- Старая, неправильная строка
                
                # Определяем дату для следующей записи (следующий день)
                next_day = target_date + timedelta(days=1)
                
                # Асинхронно вызываем сервис генерации подсказки
                # Передаем daily_analysis напрямую, так как он уже существует
                prompt_gen_success = await prompt_generation_service.generate_and_save_next_entry_prompt_for_first_entry(
                    user=user,
                    target_date=next_day,
                    previous_daily_analysis=daily_analysis # <-- Передаем правильный объект
                )
                if prompt_gen_success:
                    logger.info(f"[FullDayAnalysisService] Подсказка для первой записи {next_day} успешно поставлена в очередь/сгенерирована.")
                else:
                    logger.warning(f"[FullDayAnalysisService] Не удалось поставить в очередь/сгенерировать подсказку для первой записи {next_day}.")
            except Exception as prompt_integration_error:
                logger.error(f"[FullDayAnalysisService] Ошибка интеграции с PromptGenerationService для первой записи: {prompt_integration_error}", exc_info=True)
 
            return {
                "success": True,
                "message": "Полный анализ дня успешно завершен.",
                "daily_analysis": daily_analysis, # daily_analysis уже определен выше
                "error": None
            }

        except Exception as e:
            logger.error(f"[FullDayAnalysisService] Критическая ошибка при полном анализе дня для пользователя {user.telegram_id} за {target_date}: {e}", exc_info=True)
            
            # Попытка создать запись об ошибке в DailyAnalysis
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

        # --- 2. Все записи за день (уже в combined_entry.text) ---
        all_entries_text = combined_entry.text

        # --- 3. Аналитики отдельных записей ---
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
                    })
            except PsychoAnalysis.DoesNotExist:
                # Если анализа нет, пропускаем или добавляем заглушку
                entry_analyses_data.append({
                    "entry_id": entry.id,
                    "entry_text_snippet": entry.text[:200] + "..." if len(entry.text) > 200 else entry.text,
                    "mood_score": None,
                    "comment": "Анализ отсутствует",
                    "recommendation": "Анализ отсутствует",
                })
                logger.debug(f"[FullDayAnalysisService] Анализ для записи {entry.id} отсутствует.")

        # --- 4. Оценки настроения за день ---
        daily_mood_scores = combined_entry.daily_mood_scores

        # --- 5. Выполненные задания за день ---
        completed_tasks_data = []
        # Получаем задания, связанные с записями этого дня
        related_tasks = []
        async for task in TherapyTask.objects.filter(user=user, related_entry__in=entries):
            related_tasks.append(task)
        
        # Также можно искать задания, завершенные в этот день, независимо от связи
        # Но для простоты ограничимся связанными
        
        for task in related_tasks:
            if task.status == 'completed': # или hasattr(task, 'completion')
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
                    # Можно добавить заглушку или пропустить

        # --- 6. Текущие данные профиля пользователя ---

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

        context = {
            "user_profile": extended_user_profile, # <-- Передаем расширенный профиль
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
        
        # Извлекаем и валидируем данные
        mood_trend_raw = daily_analysis_data.get('mood_trend', 'stable')
        valid_mood_trends = [t[0] for t in DailyAnalysis._meta.get_field('mood_trend').choices]
        mood_trend = mood_trend_raw if mood_trend_raw in valid_mood_trends else 'stable'

        key_themes = daily_analysis_data.get('key_themes', [])
        emotional_patterns = daily_analysis_data.get('emotional_patterns', [])
        insights = daily_analysis_data.get('insights', [])
        recommendations = daily_analysis_data.get('recommendations', [])
        # === ИЗМЕНЕНО: Более явное извлечение и логирование ===
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
                    logger.info(f"[SYNC] DailyAnalysis ID {daily_analysis.id} обновлен.")
                else:
                    daily_analysis.save()
                    logger.info(f"[SYNC] DailyAnalysis ID {daily_analysis.id} создан.")
                    
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

                    # Заполняем поля заглушками или информацией об ошибке
                    daily_analysis.mood_trend = 'stable' # или 'unknown'
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

        Args:
            user: Объект пользователя.
            profile_updates: Словарь обновлений из ответа ИИ (user_profile_updates).

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"[FullDayAnalysisService] Обновление профиля пользователя {user.telegram_id} на основе данных ИИ.")
        logger.debug(f"[FullDayAnalysisService] Полученные обновления: {profile_updates}")

        if not profile_updates or not isinstance(profile_updates, dict):
            logger.info("[FullDayAnalysisService] Нет данных для обновления профиля пользователя.")
            return True # Не ошибка, просто нет данных

        fields_updated = []

        try:
            # --- Обработка personality_traits (словарь {trait: weight}) ---
            # Ожидаем список строк от ИИ, например: ["trait1", "trait2"]
            # Мы будем добавлять их как ключи в словарь с начальным весом 1.0 или увеличивать существующий вес.
            new_traits_list = profile_updates.get('personality_traits')
            if new_traits_list and isinstance(new_traits_list, list):
                # Убедимся, что текущее значение - словарь
                if not isinstance(user.personality_traits, dict):
                    logger.warning("[FullDayAnalysisService] user.personality_traits не является словарем. Переинициализируем.")
                    user.personality_traits = {}
                    fields_updated.append('personality_traits')

                traits_changed = False
                initial_weight = 1.0
                increment_value = 1.0

                for trait in new_traits_list:
                    if isinstance(trait, str):
                        if trait in user.personality_traits:
                            # Увеличиваем вес существующей черты
                            old_weight = user.personality_traits[trait]
                            user.personality_traits[trait] = old_weight + increment_value
                            logger.debug(f"[FullDayAnalysisService] Увеличен вес personality_trait '{trait}': {old_weight} -> {user.personality_traits[trait]}")
                        else:
                            # Добавляем новую черту с начальным весом
                            user.personality_traits[trait] = initial_weight
                            logger.debug(f"[FullDayAnalysisService] Добавлен новый personality_trait '{trait}' с весом {initial_weight}")
                        traits_changed = True
                    else:
                        logger.warning(f"[FullDayAnalysisService] Некорректный элемент в personality_traits: {trait} (тип: {type(trait)})")

                if traits_changed:
                    fields_updated.append('personality_traits')
            elif new_traits_list is not None:
                 logger.warning(f"[FullDayAnalysisService] Некорректный формат для personality_traits: {type(new_traits_list)}. Ожидается список строк.")

            # --- Обработка списков (life_facts, hobbies, core_values, triggers, strengths, areas_for_growth) ---
            list_field_names = ['life_facts', 'hobbies', 'core_values', 'triggers', 'strengths', 'areas_for_growth']
            for field_name in list_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue # Поле не передано, пропускаем

                if not isinstance(updates_for_field, list):
                    logger.warning(f"[FullDayAnalysisService] Некорректный формат для {field_name}: {type(updates_for_field)}. Ожидается список.")
                    continue

                # Получаем текущее значение поля у пользователя
                current_user_list = getattr(user, field_name, [])
                if not isinstance(current_user_list, list):
                    logger.warning(f"[FullDayAnalysisService] Текущее значение {field_name} у пользователя не является списком. Перезаписываем.")
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
                            logger.warning(f"[FullDayAnalysisService] Некорректный формат 'remove' в {field_name}: {item_to_remove}")
                    else:
                        logger.warning(f"[FullDayAnalysisService] Некорректный элемент в {field_name}: {item}")

                # Удаляем
                if items_to_remove:
                    new_set = current_user_set - items_to_remove
                    if len(new_set) != len(current_user_set):
                        current_user_set = new_set
                        logger.debug(f"[FullDayAnalysisService] Удалены из {field_name}: {items_to_remove}")
                
                # Добавляем (избегая дубликатов)
                if items_to_add:
                    actually_added = items_to_add - current_user_set
                    if actually_added:
                        current_user_set.update(actually_added)
                        logger.debug(f"[FullDayAnalysisService] Добавлены в {field_name}: {actually_added}")
                
                # Сохраняем обратно в поле пользователя, если было изменение
                final_list = list(current_user_set)
                if set(final_list) != set(current_user_list):
                    setattr(user, field_name, final_list)
                    fields_updated.append(field_name)

            # --- Сохранение изменений ---
            if fields_updated:
                logger.info(f"[FullDayAnalysisService] Обновлены поля профиля пользователя {user.telegram_id}: {fields_updated}")
                await sync_to_async(user.save)(update_fields=fields_updated)
                logger.debug(f"[FullDayAnalysisService] Изменения профиля пользователя {user.telegram_id} сохранены.")
            else:
                logger.debug(f"[FullDayAnalysisService] Нет изменений для сохранения в профиле пользователя {user.telegram_id}.")

            return True

        except Exception as e:
            logger.error(f"[FullDayAnalysisService] Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}", exc_info=True)
            return False


# Глобальный экземпляр сервиса
full_day_analysis_service = FullDayAnalysisService()


# Удобные функции
async def perform_full_day_analysis(user: User, target_date: date) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения полного анализа дня.
    """
    return await full_day_analysis_service.perform_full_day_analysis(user, target_date)
