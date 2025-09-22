# /home/shlicha/psycho_diary/diary/services/prompt_generation_service.py
"""
Сервис для генерации персонализированных подсказок для следующей записи пользователя.
"""

import logging
import json
from datetime import date, timedelta
from typing import Optional, Dict, Any
from asgiref.sync import sync_to_async
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder

# Импорты из вашего проекта
from users.models import User
from diary.models import CombinedDiaryEntry, DailyAnalysis, NextEntryPrompt, DiaryEntry
from bot.services.deepseek_api import deepseek_api_service
from prompts import get_prompt

logger = logging.getLogger(__name__)

class PromptGenerationService:
    """Сервис для генерации подсказок."""

    async def _gather_user_profile_context(self, user: User) -> Dict[str, Any]:
        """
        Собирает и подготавливает контекст профиля пользователя для использования в промпте.
        Следует примеру из UserProfileAnalysisService для согласованности.

        Args:
            user: Объект пользователя.

        Returns:
            Dict[str, Any]: Подготовленный словарь данных профиля.
        """
        logger.debug(f"[PromptGenerationService] Сбор контекста профиля для пользователя {user.telegram_id}")

        # Основные поля профиля, сериализованные в строки, как ожидает промпт
        user_profile_data = {
            'username': user.username or f"user_{user.telegram_id}",
            'first_name': user.first_name or user.username or f"Пользователь {user.telegram_id}",
            'awareness_level': user.awareness_level,
            'is_premium': user.is_premium,
            'language': user.language, # Язык теперь передаётся в user_profile
            # --- Сериализация сложных полей в JSON-строки ---
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
            "personality_description": user.personality_description,
        }
        
        logger.debug(f"[PromptGenerationService] Контекст профиля собран для пользователя {user.telegram_id}")
        return user_profile_data

    async def _gather_common_context(self, user: User) -> Dict[str, Any]:
        """
        Собирает общие данные контекста, такие как даты последней и текущей записи.

        Args:
            user: Объект пользователя.

        Returns:
            Dict[str, Any]: Словарь с общими данными контекста.
        """
        logger.debug(f"[PromptGenerationService] Сбор общего контекста для пользователя {user.telegram_id}")

        # --- Получаем дату последней записи пользователя ---
        @sync_to_async
        def _get_last_entry_date_sync():
            try:
                last_entry = DiaryEntry.objects.filter(user=user).latest('created_at')
                return last_entry.created_at.date()
            except DiaryEntry.DoesNotExist:
                return None
        
        last_entry_date = await _get_last_entry_date_sync()
        user_last_entry_date_str = last_entry_date.isoformat() if last_entry_date else "Никогда"
        
        # --- Получаем текущую дату пользователя ---
        current_user_date = user.get_local_datetime().date() # Синхронный метод
        current_user_date_str = current_user_date.isoformat()

        common_context = {
            'user_last_entry_date_str': user_last_entry_date_str,
            'current_user_date_str': current_user_date_str,
        }
        
        logger.debug(f"[PromptGenerationService] Общий контекст собран для пользователя {user.telegram_id}")
        return common_context

    async def generate_and_save_next_entry_prompt_for_first_entry(
        self, 
        user: User, 
        target_date: date,
        previous_daily_analysis: Optional[DailyAnalysis]
    ) -> bool:
        """
        Генерирует подсказку для ПЕРВОЙ записи в target_date, 
        основанную на анализе предыдущего дня (previous_daily_analysis).

        Args:
            user: Пользователь.
            target_date: Дата, для которой генерируется подсказка (следующий день после анализа).
            previous_daily_analysis: Объект DailyAnalysis предыдущего дня.

        Returns:
            bool: True, если подсказка успешно сгенерирована и сохранена, иначе False.
        """
        logger.info(f"[PromptGenerationService] Генерация подсказки для ПЕРВОЙ записи пользователя {user.telegram_id} на {target_date}")
        try:
            # --- 1. Сбор контекста пользователя ---
            user_profile_context = await self._gather_user_profile_context(user)
            common_context = await self._gather_common_context(user)

            # --- 2. Контекст анализа предыдущего дня (сплющенный) ---
            # Вместо вложенного словаря создаём плоские ключи
            flattened_previous_analysis_context = {
                'prev_mood_trend': 'N/A',
                'prev_key_themes_json': '[]',
                'prev_emotional_patterns_json': '[]',
                'prev_insights_json': '[]',
                'prev_recommendations_json': '[]',
                'prev_overall_analysis_text': '',
            }
            if previous_daily_analysis:
                # Сериализуем сложные поля в JSON-строки
                flattened_previous_analysis_context.update({
                    'prev_mood_trend': previous_daily_analysis.mood_trend or 'stable',
                    'prev_key_themes_json': json.dumps(previous_daily_analysis.key_themes or [], cls=DjangoJSONEncoder, ensure_ascii=False),
                    'prev_emotional_patterns_json': json.dumps(previous_daily_analysis.emotional_patterns or [], cls=DjangoJSONEncoder, ensure_ascii=False),
                    'prev_insights_json': json.dumps(previous_daily_analysis.insights or [], cls=DjangoJSONEncoder, ensure_ascii=False),
                    'prev_recommendations_json': json.dumps(previous_daily_analysis.recommendations or [], cls=DjangoJSONEncoder, ensure_ascii=False),
                    'prev_overall_analysis_text': previous_daily_analysis.overall_analysis_text or "",
                })

            # --- 3. Формируем ПЛОСКИЙ полный контекст для промпта ---
            # Распаковываем все словари, включая сплющенный анализ
            context_for_prompt = {
                'user_profile': user_profile_context,
                **common_context,
                **flattened_previous_analysis_context, # <-- Плоские ключи
                # Для "следующей записи в тот же день" эти поля будут иметь значения
                'current_combined_text': "", 
                'entry_count': 0,
            }
            
            logger.debug(f"[PromptGenerationService] Контекст для первой записи сформирован для пользователя {user.telegram_id}")

            # --- 4. Генерация подсказки через ИИ ---
            prompt_language = user.language 
            
            prompt_text = await self._generate_prompt_via_ai(context_for_prompt, prompt_language, is_first_entry=True)
            
            # ... (остальная логика метода без изменений: фолбэк, сохранение) ...
            if not prompt_text or not prompt_text.strip():
                logger.warning(f"[PromptGenerationService] Подсказка ИИ для первой записи на {target_date} пустая. Используется фолбэк.")
                prompt_text = await self._generate_fallback_prompt_for_first_entry(context_for_prompt) # Передаем плоский контекст
                
            logger.debug(f"[PromptGenerationService] Сгенерированная подсказка (первый вход, ИИ/фолбэк): {prompt_text[:100]}...")
            
            if prompt_text and prompt_text.strip():
                @sync_to_async
                def _save_prompt_to_model():
                    with transaction.atomic():
                        obj, created = NextEntryPrompt.objects.update_or_create(
                            user=user,
                            target_date=target_date,
                            defaults={
                                'prompt_text': prompt_text.strip(),
                                'is_used': False
                            }
                        )
                        if created:
                            logger.info(f"[PromptGenerationService] Подсказка для первой записи на {target_date} СОЗДАНА в NextEntryPrompt для пользователя {user.telegram_id}")
                        else:
                            logger.info(f"[PromptGenerationService] Подсказка для первой записи на {target_date} ОБНОВЛЕНА в NextEntryPrompt для пользователя {user.telegram_id}")
                await _save_prompt_to_model()
                return True
            else:
                logger.error(f"[PromptGenerationService] Не удалось сгенерировать текст подсказки для первой записи на {target_date} для пользователя {user.telegram_id}")
                return False

        except Exception as e:
            logger.error(f"[PromptGenerationService] Ошибка при генерации/сохранении подсказки для первой записи на {target_date} для пользователя {user.telegram_id}: {e}", exc_info=True)
            return False

    async def generate_and_save_next_entry_prompt_for_subsequent_entry(
        self,
        user: User,
        target_date: date,
        combined_entry: CombinedDiaryEntry
    ) -> bool:
        """
        Генерирует подсказку для СЛЕДУЮЩЕЙ (после только что добавленной) записи в тот же день.

        Args:
            user: Пользователь.
            target_date: Дата, для которой генерируется подсказка (текущий день).
            combined_entry: Объект CombinedDiaryEntry, уже содержащий текст новой записи.

        Returns:
            bool: True, если подсказка успешно сгенерирована и сохранена, иначе False.
        """
        logger.info(f"[PromptGenerationService] Генерация подсказки для СЛЕДУЮЩЕЙ записи пользователя {user.telegram_id} на {target_date}")
        try:
            # --- 1. Сбор контекста пользователя ---
            user_profile_context = await self._gather_user_profile_context(user)
            common_context = await self._gather_common_context(user)

            # --- 2. Контекст анализа предыдущего дня (сплющенный и ПУСТОЙ для этого случая) ---
            # Передаем пустые/дефолтные значения для всех ключей анализа
            flattened_previous_analysis_context = {
                'prev_mood_trend': 'N/A',
                'prev_key_themes_json': '[]',
                'prev_emotional_patterns_json': '[]',
                'prev_insights_json': '[]',
                'prev_recommendations_json': '[]',
                'prev_overall_analysis_text': '',
            }

            # --- 3. Формируем ПЛОСКИЙ полный контекст для промпта ---
            prompt_language = user.language
            
            context_for_prompt = {
                'user_profile': user_profile_context,
                **common_context,
                **flattened_previous_analysis_context, # <-- Плоские ключи с дефолтами
                'current_combined_text': combined_entry.text[:2000] if combined_entry.text else "Пока нет записей.",
                'entry_count': combined_entry.entry_count,
            }
            
            logger.debug(f"[PromptGenerationService] Контекст для последующей записи сформирован для пользователя {user.telegram_id}")

            # --- 4. Генерация подсказки через ИИ ---
            prompt_text = await self._generate_prompt_via_ai(context_for_prompt, prompt_language, is_first_entry=False)
            
            # ... (остальная логика метода без изменений: фолбэк, сохранение) ...
            if not prompt_text or not prompt_text.strip():
                logger.warning(f"[PromptGenerationService] Подсказка ИИ для последующей записи на {target_date} пустая. Используется фолбэк.")
                # ВАЖНО: Передаем плоский контекст и в фолбэк
                prompt_text = await self._generate_fallback_prompt_for_subsequent_entry(context_for_prompt)
                
            logger.debug(f"[PromptGenerationService] Сгенерированная подсказка (последующий вход, ИИ/фолбэк): {prompt_text[:100]}...")
            
            if prompt_text and prompt_text.strip():
                @sync_to_async
                def _save_prompt_to_model():
                    with transaction.atomic():
                        obj, created = NextEntryPrompt.objects.update_or_create(
                            user=user,
                            target_date=target_date,
                            defaults={
                                'prompt_text': prompt_text.strip(),
                                'is_used': False
                            }
                        )
                        if created:
                            logger.info(f"[PromptGenerationService] Подсказка для последующей записи на {target_date} СОЗДАНА в NextEntryPrompt для пользователя {user.telegram_id}")
                        else:
                            logger.info(f"[PromptGenerationService] Подсказка для последующей записи на {target_date} ОБНОВЛЕНА в NextEntryPrompt для пользователя {user.telegram_id}")
                await _save_prompt_to_model()
                return True
            else:
                logger.error(f"[PromptGenerationService] Не удалось сгенерировать текст подсказки для последующей записи на {target_date} для пользователя {user.telegram_id}")
                return False

        except Exception as e:
            logger.error(f"[PromptGenerationService] Ошибка при генерации/сохранении подсказки для последующей записи на {target_date} для пользователя {user.telegram_id}: {e}", exc_info=True)
            return False

    # --- МЕТОДЫ ДЛЯ ГЕНЕРАЦИИ ЧЕРЕЗ ИИ ---

    async def _generate_prompt_via_ai(self, context: dict, language: str, is_first_entry: bool) -> str:
        """
        Универсальный метод для генерации текста подсказки через ИИ.
        Ожидает, что ИИ вернет JSON с полем 'prompt_text'.

        Args:
            context (dict): Полный контекст для генерации промпта.
            language (str): Язык для генерации промпта и вызова API.
            is_first_entry (bool): Флаг, указывающий, является ли это первой записью следующего дня.

        Returns:
            str: Сгенерированный текст подсказки или пустая строка при ошибке.
        """
        
        try:
            # 1. Формируем промпт для ИИ
            # Передаем key, language и context.
            # get_prompt ожидает language как позиционный аргумент.
            prompt_text = get_prompt(
                key='next_entry_prompt_generation',
                language=language, # <-- Явно переданный язык
                **context # <-- Распаковываем весь подготовленный контекст
            )
            logger.debug(f"[PromptGenerationService] [AI] Промпт сформирован (длина: {len(prompt_text)} символов, первая запись: {is_first_entry})")

            # 2. Вызываем DeepSeek API через существующий сервис
            api_result = await deepseek_api_service.send_prompt_and_parse(
                prompt=prompt_text,
                language=language # <-- Явно переданный язык
            )
            logger.debug(f"[PromptGenerationService] [AI] Ответ API от DeepSeek: success={api_result.get('success')}")

            # 3. Обрабатываем результат
            if not api_result.get('success'):
                error_msg = api_result.get('error', 'Неизвестная ошибка API')
                logger.error(f"[PromptGenerationService] [AI] Ошибка API при генерации подсказки (первая запись: {is_first_entry}): {error_msg}")
                return ""

            # 4. Извлекаем текст подсказки из JSON-ответа
            result_data = api_result.get('result', {})
            if isinstance(result_data, dict) and 'prompt_text' in result_data:
                generated_text = result_data['prompt_text']
                logger.info(f"[PromptGenerationService] [AI] Подсказка успешно сгенерирована ИИ (первая запись: {is_first_entry}).")
                return generated_text.strip()
            else:
                logger.warning("[PromptGenerationService] [AI] Ответ от ИИ не содержит ожидаемого поля 'prompt_text' или не является словарем.")
                raw_text = api_result.get('raw_response', '').strip()
                if raw_text:
                    logger.info("[PromptGenerationService] [AI] Использован raw_response как фолбэк.")
                    return raw_text
                return ""

        except Exception as e:
            logger.error(f"[PromptGenerationService] [AI] Критическая ошибка при генерации подсказки через ИИ (первая запись: {is_first_entry}): {e}", exc_info=True)
            return ""


    # --- МЕТОДЫ-ЗАГЛУШКИ (Фолбэки) С УЧЕТОМ ПЛОСКОГО КОНТЕКСТА ---

    async def _generate_fallback_prompt_for_first_entry(self, context: dict) -> str:
        """
        (ФОЛБЭК) Генерирует текст подсказки для первой записи следующего дня локально.
        Теперь работает с плоским контекстом.
        """
        logger.warning("[PromptGenerationService] [Fallback] Используется локальная генерация подсказки для первой записи.")
        user_profile = context.get('user_profile', {})
        first_name = user_profile.get('first_name', 'Пользователь')
        
        # Работаем с плоским ключом
        try:
            key_themes_str = context.get('prev_key_themes_json', '[]')
            key_themes = json.loads(key_themes_str) if key_themes_str else []
        except (json.JSONDecodeError, TypeError):
            key_themes = []
        
        if key_themes and isinstance(key_themes, list) and len(key_themes) > 0:
            first_theme = key_themes[0]
            theme_text = ""
            if isinstance(first_theme, dict):
                theme_text = first_theme.get('theme') or first_theme.get('text', '')
            elif isinstance(first_theme, str):
                theme_text = first_theme

            if theme_text:
                return f"📝 <b>Привет, {first_name}!</b>\n\n💬 <i>Вчера ты упоминал '{theme_text}'. Как продвигается эта тема?</i>"
        
        return f"📝 <b>Привет, {first_name}!</b>\n\n💬 <i>Расскажи, как прошёл твой день?</i>"


    async def _generate_fallback_prompt_for_subsequent_entry(self, context: dict) -> str:
        """
        (ФОЛБЭК) Генерирует текст подсказки для следующей записи в тот же день локально.
        Теперь работает с плоским контекстом.
        """
        logger.warning("[PromptGenerationService] [Fallback] Используется локальная генерация подсказки для последующей записи.")
        user_profile = context.get('user_profile', {})
        first_name = user_profile.get('first_name', 'Пользователь')
        entry_count = context.get('entry_count', 0)

        if entry_count == 1:
            return f"📝 <b>Продолжай, {first_name}!</b>\n\n💬 <i>Хочешь добавить что-то ещё к тому, что уже написал?</i>"
        elif entry_count > 1:
             return f"📝 <b>Отлично, {first_name}!</b>\n\n💬 <i>Как развивается та история, которую ты начал описывать?</i>"
        else:
            return f"📝 <b>Привет, {first_name}!</b>\n\n💬 <i>Расскажи, как у тебя дела?</i>"

# Глобальный экземпляр сервиса
prompt_generation_service = PromptGenerationService()

# Удобные асинхронные функции
async def generate_and_save_next_entry_prompt_for_first_entry(
    user: User, 
    target_date: date, 
    previous_daily_analysis: Optional[DailyAnalysis]
) -> bool:
    return await prompt_generation_service.generate_and_save_next_entry_prompt_for_first_entry(user, target_date, previous_daily_analysis)

async def generate_and_save_next_entry_prompt_for_subsequent_entry(
    user: User,
    target_date: date,
    combined_entry: CombinedDiaryEntry
) -> bool:
    return await prompt_generation_service.generate_and_save_next_entry_prompt_for_subsequent_entry(user, target_date, combined_entry)
