"""
ПЕРЕПИСАННЫЙ SmartPromptManager - ИСПРАВЛЕННЫЙ И УПРОЩЕННЫЙ
"""

import logging
from datetime import date, timedelta
from typing import Optional
from asgiref.sync import sync_to_async

from bot.services.deepseek_api import deepseek_api_service
from diary.models import NextEntryPrompt, DiaryEntry, CombinedDiaryEntry, DailyAnalysis
from users.models import User
from messages import get_message
from prompts.get_prompt import get_prompt

logger = logging.getLogger(__name__)

class SmartPromptManager:
    """
    ИСПРАВЛЕННЫЙ менеджер подсказок с четкой логикой:
    1. При создании записи: показываем подсказку для СЕГОДНЯ
    2. После сохранения записи: готовим подсказку для СЛЕДУЮЩЕЙ записи (сегодня или завтра)
    3. После анализа дня: готовим подсказку для ЗАВТРАШНЕГО дня
    """
    async def get_prompt_for_user(self, user: User, language: str = 'ru') -> str:
        """Показываем подсказку при создании новой записи"""
        logger.debug(f"[SmartPrompt] Получение подсказки для пользователя {user.telegram_id}")
        try:
            prompt = await self._get_prompt_for_date(user, date.today())
            if prompt:
                logger.debug(f"[SmartPrompt] Найдена подсказка для сегодня для {user.telegram_id}")
                return prompt
            logger.debug(f"[SmartPrompt] Используем базовую подсказку для {user.telegram_id}")
            return get_message('ask_entry', language)
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка получения подсказки: {e}")
            return get_message('ask_entry', language)
    async def on_entry_saved(self, user: User, entry: DiaryEntry, language: str = 'ru'):
        """После сохранения реальной записи - готовим подсказку через AI"""
        if entry.id == 0:
            return
        logger.debug(f"[SmartPrompt] Обработка сохраненной записи {entry.id} для {user.telegram_id}")
        
        try:
            entry_date = await entry.aentry_date()
            today = date.today()
            if entry_date == today:
                await self._generate_ai_prompt_today(user, entry, language)
            else:
                await self._generate_ai_prompt_tomorrow(user, language)
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка обработки сохраненной записи: {e}")

    async def on_day_analyzed(self, user: User, analyzed_date: date, daily_analysis: DailyAnalysis, language: str = 'ru'):
        """После анализа дня - готовим подсказку для ЗАВТРА через AI"""
        logger.deb(f"[SmartPrompt] Генерация подсказки после анализа дня {analyzed_date}")
        try:
            tomorrow = analyzed_date + timedelta(days=1)
            prompt_text = await self._generate_ai_prompt_from_analysis(user, daily_analysis, language)
            
            if prompt_text:
                await self._save_prompt(user, tomorrow, prompt_text, force_overwrite=True)
                logger.debug(f"[SmartPrompt] AI-подсказка на завтра создана после анализа дня")
            else:
                await self._prepare_first_prompt_tomorrow(user, language) 
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка генерации подсказки после анализа: {e}")

    async def _generate_ai_prompt_today(self, user: User, entry: DiaryEntry, language: str):
        """Генерирует AI-подсказку для следующей записи сегодня"""
        try:
            entry_date = await entry.aentry_date()
            today = date.today()
            logger.debug(f"[SmartPrompt-DATE] Дата записи: {entry_date}, Сегодня: {today}")
            entries_today = await self._get_entries_for_date(user, entry_date)
            days_since_last = await self._get_days_since_last_entry(user)
            analysis_context = ""
            if len(entries_today) == 1:
                analysis_context = f"Пользователь только что сделал первую запись сегодня: '{entry.text[:100]}...'"
            else:
                analysis_context = f"У пользователя уже {len(entries_today)} записей сегодня. Последняя: '{entry.text[:100]}...'"
            prompt_text = await self._call_ai_prompt_generation(
                user, analysis_context, days_since_last, language
            )
            if prompt_text:
                await self._save_prompt(user, today, prompt_text)
                logger.debug(f"[SmartPrompt] AI-подсказка на сегодня создана")
            else:
                await self._prepare_next_prompt_today(user, entry, language)
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка AI-генерации подсказки на сегодня: {e}")
            await self._prepare_next_prompt_today(user, entry, language)

    async def _generate_ai_prompt_tomorrow(self, user: User, language: str):
        """Генерирует AI-подсказку для завтра"""
        try:
            tomorrow = date.today() + timedelta(days=1)
            days_since_last = await self._get_days_since_last_entry(user)

            today_analysis = await self._get_todays_analysis(user)
            if today_analysis:
                prompt_text = await self._generate_ai_prompt_from_analysis(user, today_analysis, language)
            else:
                analysis_context = "Нет анализа сегодняшнего дня. Используй общую подсказку."
                prompt_text = await self._call_ai_prompt_generation(
                    user, analysis_context, days_since_last, language
                )
            if prompt_text:
                await self._save_prompt(user, tomorrow, prompt_text)
            else:
                await self._prepare_first_prompt_tomorrow(user, language)
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка AI-генерации подсказки на завтра: {e}")
            await self._prepare_first_prompt_tomorrow(user, language)

    async def _generate_ai_prompt_from_analysis(self, user: User, daily_analysis: DailyAnalysis, language: str) -> Optional[str]:
        """Генерирует подсказку на основе анализа дня через AI"""
        try:
            days_since_last = await self._get_days_since_last_entry(user)
            analysis_context = "Анализ предыдущего дня: "
            if hasattr(daily_analysis, 'key_themes') and daily_analysis.key_themes:
                theme = daily_analysis.key_themes[0].get('theme', 'день') if isinstance(daily_analysis.key_themes[0], dict) else str(daily_analysis.key_themes[0])
                analysis_context += f"Ключевая тема: '{theme}'. "
            if hasattr(daily_analysis, 'mood_trend'):
                analysis_context += f"Тренд настроения: {daily_analysis.mood_trend}. "
            return await self._call_ai_prompt_generation(
                user, analysis_context, days_since_last, language
            )
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка генерации подсказки из анализа: {e}")
            return None

    async def _call_ai_prompt_generation(self, user: User, analysis_context: str, days_since_last: int, language: str) -> Optional[str]:
        """Вызывает AI для генерации подсказки"""
        try:
            user_profile = await user.aget_profile_data()
            prompt = get_prompt(
                key='next_entry_prompt_generation',
                language=language,
                first_name=user_profile.get('first_name', 'Друг'),
                awareness_level=user.awareness_level,
                days_since_last_entry=days_since_last,
                analysis_context=analysis_context
            )
            result = await deepseek_api_service.send_prompt_and_parse(prompt, language)
            if result.get('success'):
                ai_response = result.get('result', {})
                prompt_text = ai_response.get('prompt_text')
                if prompt_text:
                    logger.debug(f"[SmartPrompt] AI успешно сгенерировал подсказку")
                    return prompt_text
            logger.warning(f"[SmartPrompt] AI не вернул подсказку, используем fallback")
            return None
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка вызова AI: {e}")
            return None

    async def _get_days_since_last_entry(self, user: User) -> int:
        """Считает дни с последней записи"""
        try:
            @sync_to_async
            def _get_last_entry_date():
                try:
                    last_entry = DiaryEntry.objects.filter(user=user).latest('created_at')
                    return last_entry.created_at.date()
                except DiaryEntry.DoesNotExist:
                    return None
            last_date = await _get_last_entry_date()
            if last_date:
                return (date.today() - last_date).days
            return 999
        except:
            return 1            

    async def _get_prompt_for_date(self, user: User, target_date: date) -> Optional[str]:
        """
        Ищет подсказку для конкретной даты и помечает как использованную
        """
        try:
            @sync_to_async
            def _get_and_mark_used():
                try:
                    prompt = NextEntryPrompt.objects.get(
                        user=user, 
                        target_date=target_date, 
                        is_used=False
                    )
                    prompt.is_used = True
                    prompt.save()
                    return prompt.prompt_text
                except NextEntryPrompt.DoesNotExist:
                    return None
            return await _get_and_mark_used()
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка поиска подсказки для даты {target_date}: {e}")
            return None

    async def _prepare_next_prompt_today(self, user: User, entry: DiaryEntry, language: str):
        """
        Готовит подсказку для следующей записи СЕГОДНЯ
        """
        try:
            entry_date = await entry.aentry_date()
            entries_today = await self._get_entries_for_date(user, entry_date)
            if len(entries_today) == 1:
                prompt_text = get_message('add_more_prompt', language)
            else:
                prompt_text = get_message('continue_prompt', language)
            await self._save_prompt(user, entry_date, prompt_text)
            logger.debug(f"[SmartPrompt] Подсказка на сегодня подготовлена для {user.telegram_id}")
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка подготовки подсказки на сегодня: {e}")

    async def _prepare_first_prompt_tomorrow(self, user: User, language: str):
        """
        Готовит подсказку для первой записи ЗАВТРА
        """
        try:
            tomorrow = date.today() + timedelta(days=1)
            today_analysis = await self._get_todays_analysis(user)
            if today_analysis:
                prompt_text = await self._generate_prompt_from_daily_analysis(user, today_analysis, language)
            else:
                user_profile = await user.aget_profile_data()
                first_name = user_profile.get('first_name', 'Друг')
                prompt_text = f"📝 <b>Привет, {first_name}!</b>\n\n💬 <i>Расскажи, как прошел твой день?</i>"
            if prompt_text:
                await self._save_prompt(user, tomorrow, prompt_text)
                logger.debug(f"[SmartPrompt] Подсказка на завтра подготовлена для {user.telegram_id}")
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка подготовки подсказки на завтра: {e}")

    async def _generate_prompt_from_daily_analysis(self, user: User, daily_analysis: DailyAnalysis, language: str) -> str:
        """
        Генерирует подсказку на основе анализа дня
        """
        try:
            user_profile = await user.aget_profile_data()
            first_name = user_profile.get('first_name', 'Друг')
            if (hasattr(daily_analysis, 'key_themes') and 
                daily_analysis.key_themes and 
                len(daily_analysis.key_themes) > 0):
                theme_data = daily_analysis.key_themes[0]
                if isinstance(theme_data, dict):
                    theme = theme_data.get('theme', 'день')
                else:
                    theme = str(theme_data)
                return get_message('theme_followup', language, first_name=first_name, theme=theme)
            return get_message('morning_greeting', language, first_name=first_name)
        except Exception as e:
            logger.error(f"[SmartPrompt] Ошибка генерации подсказки из анализа: {e}")
            user_profile = await user.aget_profile_data()
            first_name = user_profile.get('first_name', 'Друг')
            return f"📝 <b>Привет, {first_name}!</b>\n\n💬 <i>Расскажи, как прошел твой день?</i>"

    async def _save_prompt(self, user: User, target_date: date, prompt_text: str, force_overwrite: bool = False):
        """Сохраняет подсказку с детальным логированием"""
        try:
            @sync_to_async
            def _save():
                logger.debug(f"[SmartPrompt-SAVE] Начало сохранения подсказки для {target_date}")
                
                # Проверяем существующую подсказку
                existing_prompt = None
                try:
                    existing_prompt = NextEntryPrompt.objects.get(
                        user=user, 
                        target_date=target_date,
                    )
                    logger.debug(f"[SmartPrompt-SAVE] Найдена существующая подсказка ID {existing_prompt.id}, is_used={existing_prompt.is_used}")
                except NextEntryPrompt.DoesNotExist:
                    logger.debug(f"[SmartPrompt-SAVE] Существующая подсказка не найдена")
                
                if force_overwrite or not existing_prompt or existing_prompt.is_used:
                    # СОЗДАЕМ/ОБНОВЛЯЕМ подсказку
                    prompt, created = NextEntryPrompt.objects.update_or_create(
                        user=user,
                        target_date=target_date,
                        defaults={
                            'prompt_text': prompt_text,
                            'is_used': False  # Важно: сбрасываем флаг!
                        }
                    )
                    
                    if created:
                        logger.debug(f"[SmartPrompt-SAVE] СОЗДАНА новая подсказка ID {prompt.id} для {target_date}")
                    else:
                        logger.debug(f"[SmartPrompt-SAVE] ОБНОВЛЕНА существующая подсказка ID {prompt.id} для {target_date}")
                        
                    return prompt
                else:
                    logger.debug(f"[SmartPrompt-SAVE] Подсказка уже существует, пропускаем сохранение")
                    return existing_prompt
            
            result = await _save()
            logger.debug(f"[SmartPrompt-SAVE] Сохранение завершено успешно")
            return result
            
        except Exception as e:
            logger.error(f"[SmartPrompt-SAVE] Ошибка сохранения подсказки: {e}", exc_info=True)
            return None

    async def _get_entries_for_date(self, user: User, target_date: date) -> list:
        try:
            @sync_to_async
            def _get_entries():
                return list(DiaryEntry.objects.filter(
                    user=user, 
                    created_at__date=target_date
                ).order_by('created_at'))
            return await _get_entries()
        except:
            return []

    async def _get_todays_analysis(self, user: User) -> Optional[DailyAnalysis]:
        try:
            today = date.today()
            @sync_to_async
            def _get_analysis():
                try:
                    combined = CombinedDiaryEntry.objects.get(user=user, date=today)
                    if hasattr(combined, 'daily_analysis'):
                        return combined.daily_analysis
                    return None
                except CombinedDiaryEntry.DoesNotExist:
                    return None
            return await _get_analysis()
        except:
            return None

smart_prompt_manager = SmartPromptManager()