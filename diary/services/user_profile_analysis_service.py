# /home/shlicha/psycho_diary/diary/services/user_profile_analysis_service.py
"""
Сервис для выполнения глубокого анализа и обновления психологического профиля пользователя.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
import json

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder

from users.models import User, UserProfileHistory
from diary.models import WeeklyAnalysis, TaskCompletionAnalysis
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt

logger = logging.getLogger(__name__)

class UserProfileAnalysisService:
    """Сервис для анализа и обновления психологического профиля пользователя."""

    async def perform_user_profile_analysis(self, user: User) -> Dict[str, Any]:
        """
        Выполняет полный цикл анализа профиля пользователя.
        Собирает данные, вызывает ИИ, сохраняет результат и историю.

        Args:
            user: Пользователь.

        Returns:
            Dict[str, Any]: Результат операции.
                - success (bool): Успешность операции.
                - message (str): Сообщение о результате.
                - error (Optional[str]): Сообщение об ошибке, если есть.
        """
        logger.info(f"[UserProfileAnalysisService] Начало анализа профиля для пользователя {user.telegram_id}")

        try:
            # 1. Создаем "слепок" текущего профиля ДО обновления
            await self._create_profile_snapshot(user)
            logger.debug(f"[UserProfileAnalysisService] Слепок профиля создан для пользователя {user.telegram_id}")

            # 2. Собираем контекст
            context = await self._gather_user_context(user)
            if not context.get('has_data'):
                 logger.warning(f"[UserProfileAnalysisService] Недостаточно данных для анализа профиля пользователя {user.telegram_id}")
                 return {
                    "success": False,
                    "message": "Недостаточно данных для анализа профиля.",
                    "error": "no_data"
                }
            logger.debug(f"[UserProfileAnalysisService] Контекст собран для пользователя {user.telegram_id}")

            # 3. Сформировать промпт
            prompt = get_prompt(
                key='user_profile_analysis', # Нужно будет добавить в prompts.py
                language=user.language,
                user_profile=context['user_profile'],
                recent_weekly_analyses=context['recent_weekly_analyses'],
                selected_task_completion_analyses=context['selected_task_completion_analyses'],
                # historical_profile_snapshots=context['historical_profile_snapshots'] # Пока не используем
            )
            logger.debug(f"[UserProfileAnalysisService] Промпт сформирован для {user.telegram_id} (длина: {len(prompt)} символов)")

            # 4. Вызвать DeepSeek API
            # Увеличиваем таймаут, так как это может быть объемный запрос/ответ
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt, 
                language=user.language,
                timeout_per_attempt=150 # 2.5 минуты на попытку
            )
            logger.debug(f"[UserProfileAnalysisService] Ответ API от DeepSeek: success={api_result.get('success')}")

            # 5. Обработать результат API
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[UserProfileAnalysisService] Ошибка API при анализе профиля: {error_msg}")
                return {
                    "success": False,
                    "message": f"Ошибка при анализе профиля: {error_msg}",
                    "error": error_msg
                }

            # 6. Парсинг результата
            parsed_result = api_result.get('result', {})
            logger.debug(f"[UserProfileAnalysisService] Распарсенный результат от API: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else type(parsed_result)}")
            
            # 7. Обновить поля User на основе результата ИИ
            update_success = await self._update_user_profile_from_analysis(user, parsed_result)
            if not update_success:
                 logger.error(f"[UserProfileAnalysisService] Не удалось обновить профиль пользователя {user.telegram_id} после анализа.")
                 return {
                    "success": False,
                    "message": "Ошибка при обновлении профиля пользователя.",
                    "error": "update_failed"
                }
            
            logger.info(f"[UserProfileAnalysisService] Профиль пользователя {user.telegram_id} успешно обновлен.")
            return {
                "success": True,
                "message": "Профиль пользователя успешно обновлен.",
                "error": None
            }

        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Критическая ошибка при анализе профиля для пользователя {user.telegram_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Критическая ошибка при анализе профиля.",
                "error": str(e)
            }

    async def _create_profile_snapshot(self, user: User) -> Optional[UserProfileHistory]:
        """
        Создает снимок текущего состояния профиля пользователя и сохраняет его в истории.
        Выполняется ДО обновления профиля.
        """
        logger.debug(f"[UserProfileAnalysisService] Создание слепка профиля для пользователя {user.telegram_id}")
        try:
            @sync_to_async
            def _create_snapshot_sync():
                with transaction.atomic():
                    snapshot = UserProfileHistory(
                        user=user,
                        awareness_level=user.awareness_level,
                        personality_traits=user.personality_traits,
                        life_facts=user.life_facts,
                        hobbies=user.hobbies,
                        core_values=user.core_values,
                        triggers=user.triggers,
                        strengths=user.strengths,
                        areas_for_growth=user.areas_for_growth,
                        personality_insights=user.personality_insights,
                        habits=user.habits,
                        skills=user.skills,
                        aspirations=user.aspirations,
                        personality_description=user.personality_description,
                    )
                    snapshot.save()
                    logger.info(f"[SYNC] Слепок профиля ID {snapshot.id} создан для пользователя {user.telegram_id}")
                    return snapshot
            return await _create_snapshot_sync()
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при создании слепка профиля для пользователя {user.telegram_id}: {e}")
            return None

    async def _gather_user_context(self, user: User) -> Dict[str, Any]:
        """
        Собирает контекст для анализа профиля пользователя.

        Args:
            user: Пользователь.

        Returns:
            Dict[str, Any]: Словарь с контекстом.
        """
        logger.debug(f"[UserProfileAnalysisService] Сбор контекста для пользователя {user.telegram_id}")

        context = {
            'has_data': False,
            'user_profile': {},
            'recent_weekly_analyses': [],
            'selected_task_completion_analyses': [],
            # 'historical_profile_snapshots': [] # Пока не используем
        }

        # --- 1. Профиль пользователя (полный) ---
        # Передаем полный актуальный профиль, включая новое текстовое описание
        user_profile_data = {
            'username': user.username or f"user_{user.telegram_id}",
            'first_name': user.first_name or "",
            'awareness_level': user.awareness_level,
            'is_premium': user.is_premium,
            # --- Сериализация сложных полей ---
            # ИИ получит их как строки и сможет их десериализовать
            "personality_traits": json.dumps(user.personality_traits, cls=DjangoJSONEncoder, ensure_ascii=False),
            "life_facts": json.dumps(user.life_facts, cls=DjangoJSONEncoder, ensure_ascii=False),
            "hobbies": json.dumps(user.hobbies, cls=DjangoJSONEncoder, ensure_ascii=False),
            "core_values": json.dumps(user.core_values, cls=DjangoJSONEncoder, ensure_ascii=False),
            "triggers": json.dumps(user.triggers, cls=DjangoJSONEncoder, ensure_ascii=False),
            "strengths": json.dumps(user.strengths, cls=DjangoJSONEncoder, ensure_ascii=False),
            "areas_for_growth": json.dumps(user.areas_for_growth, cls=DjangoJSONEncoder, ensure_ascii=False),
            "personality_insights": json.dumps(user.personality_insights, cls=DjangoJSONEncoder, ensure_ascii=False),
            "habits": json.dumps(user.habits, cls=DjangoJSONEncoder, ensure_ascii=False),
            "skills": json.dumps(user.skills, cls=DjangoJSONEncoder, ensure_ascii=False),
            "aspirations": json.dumps(user.aspirations, cls=DjangoJSONEncoder, ensure_ascii=False),
            "personality_description": user.personality_description, # Текстовое поле оставляем как есть
        }
        context['user_profile'] = user_profile_data

        # --- 2. Последние WeeklyAnalysis (например, последние 4 недели) ---
        recent_weekly_analyses_data = []
        try:
            # Определяем дату 4 недели назад
            four_weeks_ago = datetime.now().date() - timedelta(weeks=4)
            
            @sync_to_async
            def _get_recent_weekly_analyses_sync():
                return list(WeeklyAnalysis.objects.filter(
                    user=user, week_start_date__gte=four_weeks_ago
                ).order_by('-week_start_date'))
            
            recent_weekly_analyses = await _get_recent_weekly_analyses_sync()
            
            for wa in recent_weekly_analyses:
                wa_data = {
                    "week_start_date": wa.week_start_date.isoformat(),
                    "summary_text": wa.summary_text,
                    "progress_insights": wa.progress_insights,
                    # "consolidated_user_profile": wa.consolidated_user_profile, # Может быть большим, пропускаем
                    "statistics": wa.statistics,
                    "comparison_with_previous": wa.comparison_with_previous,
                    # "overall_analysis_text": wa.api_response.get('result', {}).get('overall_analysis_text', ''), # Из API, если нужно
                }
                recent_weekly_analyses_data.append(wa_data)
                
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при сборе WeeklyAnalysis для пользователя {user.telegram_id}: {e}")

        context['recent_weekly_analyses'] = recent_weekly_analyses_data
        if recent_weekly_analyses_data:
            context['has_data'] = True

        # --- 3. Выбранные TaskCompletionAnalysis (например, последние 5 с наибольшим impact) ---
        selected_task_analyses_data = []
        try:
            # ИСПРАВЛЕНИЕ: Используем sync_to_async для ORM-запроса внутри асинхронной функции
            @sync_to_async
            def _get_selected_task_analyses_sync():
                # Получаем TaskCompletionAnalysis с mood_impact_score по модулю > 0, сортируем по impact и берем топ 5
                # Используем select_related для оптимизации
                return list(TaskCompletionAnalysis.objects.select_related(
                    'completion', 'completion__task'
                ).filter(
                    completion__task__user=user
                ).exclude(
                    mood_impact_score=0
                ).order_by('-mood_impact_score')[:5]) # Топ 5 по абсолютному значению impact
            
            selected_task_analyses = await _get_selected_task_analyses_sync()
            
            for tca in selected_task_analyses:
                tca_data = {
                    "completion_date": tca.completion.created_at.date().isoformat() if tca.completion and tca.completion.created_at else None,
                    "effect_description": tca.effect_description,
                    "mood_impact_score": tca.mood_impact_score,
                    "comment": tca.comment,
                    "recommendation": tca.recommendation,
                    # Ограничиваем длину подробного анализа
                    "detailed_analysis": (tca.detailed_analysis[:500] + "...") if tca.detailed_analysis and len(tca.detailed_analysis) > 500 else (tca.detailed_analysis or ""),
                }
                selected_task_analyses_data.append(tca_data)
                
        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при сборе TaskCompletionAnalysis для пользователя {user.telegram_id}: {e}")

        context['selected_task_completion_analyses'] = selected_task_analyses_data
        # has_data уже может быть True от WeeklyAnalysis

        # --- 4. Исторические снимки профиля (опционально, для продвинутого анализа) ---
        # Пока не реализуем, чтобы не перегружать запрос.
        # context['historical_profile_snapshots'] = []

        logger.debug(f"[UserProfileAnalysisService] Контекст собран для пользователя {user.telegram_id}. WeeklyAnalyses: {len(recent_weekly_analyses_data)}, TaskAnalyses: {len(selected_task_analyses_data)}")
        return context

    async def _update_user_profile_from_analysis(self, user: User, parsed_result: Dict[str, Any]) -> bool:
        """
        Обновляет поля профиля пользователя на основе результата анализа ИИ.

        Args:
            user: Объект пользователя.
            parsed_result: Словарь обновлений из ответа ИИ.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"[UserProfileAnalysisService] Обновление профиля пользователя {user.telegram_id} на основе данных ИИ.")
        logger.debug(f"[UserProfileAnalysisService] Полученные обновления: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else type(parsed_result)}")

        if not parsed_result or not isinstance(parsed_result, dict):
            logger.info("[UserProfileAnalysisService] Нет данных для обновления профиля пользователя.")
            return True # Не ошибка, просто нет данных

        fields_updated = []
        updates_to_apply = {}

        try:
            # --- Обработка всех полей профиля из результата ИИ ---
            # Предполагаем, что ИИ возвращает структуру, аналогичную модели User
            profile_updates = parsed_result
            
            # Список полей, которые мы ожидаем обновлять
            list_and_dict_field_names = [
                'personality_traits', 'life_facts', 'hobbies', 'core_values', 
                'triggers', 'strengths', 'areas_for_growth', 
                'personality_insights', 'habits', 'skills', 'aspirations'
            ]
            
            for field_name in list_and_dict_field_names:
                updates_for_field = profile_updates.get(field_name)
                if updates_for_field is None:
                    continue # Поле не передано, пропускаем

                if isinstance(updates_for_field, (dict, list)):
                    # Для dict/list просто присваиваем новое значение целиком
                    # Это соответствует логике "перезаписать слепок"
                    updates_to_apply[field_name] = updates_for_field
                    fields_updated.append(field_name)
                    logger.debug(f"[UserProfileAnalysisService] Подготовлено обновление для поля '{field_name}'")
                else:
                    logger.warning(f"[UserProfileAnalysisService] Некорректный формат для поля '{field_name}': {type(updates_for_field)}. Ожидается dict или list.")

            # --- Обработка текстового описания личности ---
            new_personality_description = profile_updates.get('personality_description')
            if isinstance(new_personality_description, str):
                updates_to_apply['personality_description'] = new_personality_description
                fields_updated.append('personality_description')
                logger.debug("[UserProfileAnalysisService] Подготовлено обновление для поля 'personality_description'")
            elif new_personality_description is not None:
                 logger.warning(f"[UserProfileAnalysisService] Некорректный формат для поля 'personality_description': {type(new_personality_description)}. Ожидается str.")

            # --- Обработка уровня осознанности (опционально, если ИИ его предложит) ---
            # new_awareness_level = profile_updates.get('awareness_level')
            # if isinstance(new_awareness_level, int) and 1 <= new_awareness_level <= 10:
            #     updates_to_apply['awareness_level'] = new_awareness_level
            #     fields_updated.append('awareness_level')
            #     logger.debug(f"[UserProfileAnalysisService] Подготовлено обновление для поля 'awareness_level' до {new_awareness_level}")
            # elif new_awareness_level is not None:
            #      logger.warning(f"[UserProfileAnalysisService] Некорректное значение для поля 'awareness_level': {new_awareness_level}. Ожидается int 1-10.")

            # --- Сохранение изменений ---
            if fields_updated:
                logger.info(f"[UserProfileAnalysisService] Обновлены поля профиля пользователя {user.telegram_id}: {fields_updated}")
                
                @sync_to_async
                def _save_updates_sync():
                    with transaction.atomic():
                        for field, value in updates_to_apply.items():
                            setattr(user, field, value)
                        user.save(update_fields=fields_updated)
                    logger.debug(f"[SYNC] Изменения профиля пользователя {user.telegram_id} сохранены.")
                
                await _save_updates_sync()
                return True
            else:
                logger.debug(f"[UserProfileAnalysisService] Нет изменений для сохранения в профиле пользователя {user.telegram_id}.")
                return True

        except Exception as e:
            logger.error(f"[UserProfileAnalysisService] Ошибка при обновлении профиля пользователя {user.telegram_id}: {e}", exc_info=True)
            return False

# Глобальный экземпляр сервиса
user_profile_analysis_service = UserProfileAnalysisService()

# Удобная функция
async def perform_user_profile_analysis(user: User) -> Dict[str, Any]:
    """
    Удобная асинхронная функция для выполнения анализа профиля пользователя.
    """
    return await user_profile_analysis_service.perform_user_profile_analysis(user)
