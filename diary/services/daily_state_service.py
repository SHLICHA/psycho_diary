"""
Сервис для работы с объединенными записями дня (состоянием дня) для инкрементального анализа ИИ.
"""

import logging
from datetime import date
from typing import Optional
from django.db import transaction
from diary.models import CombinedDiaryEntry, DiaryEntry
from users.models import User
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class DailyStateService:
    """Сервис для управления состоянием дня (CombinedDiaryEntry)."""

    async def get_daily_state(self, user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
        """
        Асинхронно получает CombinedDiaryEntry для пользователя и даты.

        Args:
            user: Пользователь.
            target_date: Целевая дата.

        Returns:
            CombinedDiaryEntry: Объект состояния дня или None, если не найден.
        """
        try:
            @sync_to_async
            def _get_sync():
                try:
                    return CombinedDiaryEntry.objects.select_related('user').get(
                        user=user, date=target_date
                    )
                except CombinedDiaryEntry.DoesNotExist:
                    return None
            combined_entry = await _get_sync()
            return combined_entry
        except Exception as e:
            logger.error(f"Ошибка при получении CombinedDiaryEntry за {target_date}: {e}")
            return None

    async def get_or_create_daily_state(
        self, user: User, target_date: date, initial_text: str
    ) -> CombinedDiaryEntry:
        """
        Асинхронно получает или создает CombinedDiaryEntry для пользователя и даты.

        Args:
            user: Пользователь.
            target_date: Целевая дата.
            initial_text: Начальный объединенный текст для создания записи.

        Returns:
            CombinedDiaryEntry: Существующий или новый объект состояния дня.
        """
        try:
            @sync_to_async
            def _get_or_create_sync():
                obj, created = CombinedDiaryEntry.objects.select_related('user').get_or_create(
                    user=user,
                    date=target_date,
                    defaults={
                        'text': initial_text,
                        'entry_count': 1,
                        'ai_state_data': '',
                        'is_analyzed': False,
                    }
                )
                return obj, created
            combined_entry, created = await _get_or_create_sync()
            return combined_entry
        except Exception as e:
            logger.error(f"Ошибка при получении или создании CombinedDiaryEntry за {target_date}: {e}")
            raise

    async def get_day_context(self, user: User, target_date: date) -> dict:
        """
        Возвращает структурированный контекст дня для промпта.
        Включает все записи, инсайты, ключевые моменты, настроение и т.д.
        """
        from bot.services.diary_service import diary_service
        try:
            # Получаем все записи за день
            entries = await diary_service.get_user_entries_for_date(user, target_date)
            entry_ids = [e.id for e in entries]

            # Получаем инсайты и ключевые моменты
            insights = await diary_service.get_insights_for_entries(entry_ids)
            keypoints = await diary_service.get_keypoints_for_entries(entry_ids)

            # Получаем CombinedDiaryEntry (если есть)
            combined_entry = await self.get_daily_state(user, target_date)

            # Собираем контекст
            context = {
                "all_entries_combined": "\n\n---\n\n".join([e.text for e in entries]) if entries else "",
                "entry_count": len(entries),
                "average_mood_score": round(combined_entry.average_mood_score, 2) if combined_entry else 0.0,
                "key_points": [
                    {
                        "text": kp.text,
                        "type": kp.get_type_display(),
                        "confidence": round(kp.confidence, 2)
                    }
                    for kp in sorted(keypoints, key=lambda x: x.confidence, reverse=True)[:10]
                ],
                "user_insights": [
                    {
                        "text": insight.text,
                        "category": insight.get_category_display(),
                        "weight": insight.weight,
                        "last_mentioned": insight.last_mentioned.isoformat()
                    }
                    for insight in insights[:15]  # Топ-15 по весу
                ],
                "is_analyzed": combined_entry.is_analyzed if combined_entry else False,
                "last_analysis_summary": combined_entry.ai_state_data if combined_entry and combined_entry.ai_state_data else "No previous analysis.",
                "daily_mood_scores": combined_entry.daily_mood_scores if combined_entry else []
            }

            return context

        except Exception as e:
            logger.error(f"Ошибка при получении контекста дня: {e}", exc_info=True)
            return {
                "all_entries_combined": "",
                "entry_count": 0,
                "average_mood_score": 0.0,
                "key_points": [],
                "user_insights": [],
                "is_analyzed": False,
                "last_analysis_summary": "",
                "daily_mood_scores": []
            }

    async def update_daily_state(
        self, 
        combined_entry: CombinedDiaryEntry, 
        new_ai_state_data: str,
        latest_mood_score: Optional[int] = None
    ) -> bool:
        """
        Асинхронно обновляет существующий CombinedDiaryEntry с новым состоянием от ИИ.
        Также обновляет текст, счетчик записей и список/среднее значение настроения.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_ai_state_data: Новое текстовое состояние дня от ИИ.
            latest_mood_score: (Новое) mood_score из последней записи.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"[Обновление состояния дня] Начало обновления CombinedDiaryEntry ID {combined_entry.id}")
        try:
            # === ИСПОЛЬЗУЕМ УНИВЕРСАЛЬНУЮ ФУНКЦИЮ ===
            # Сначала получаем актуальные текст и счетчик
            from bot.services.diary_service import diary_service
            combined_text = await diary_service.get_combined_entry_text(combined_entry.user, combined_entry.date)
            entries_today = await diary_service.get_user_entries_for_date(combined_entry.user, combined_entry.date)
            entry_count = len(entries_today)

            # Вызываем универсальную функцию обновления
            update_success = await self._update_combined_entry_internal(
                combined_entry=combined_entry,
                text=combined_text,
                entry_count=entry_count,
                ai_state_data=new_ai_state_data,
                is_analyzed=True, # При обновлении состояния анализ считается завершенным
                latest_mood_score=latest_mood_score
            )
            
            if update_success:
                logger.info(f"[Обновление состояния дня] CombinedDiaryEntry ID {combined_entry.id} успешно обновлен.")
            else:
                logger.error(f"[Обновление состояния дня] Не удалось обновить CombinedDiaryEntry ID {combined_entry.id}.")
            
            return update_success

        except Exception as e:
            logger.error(f"[Обновление состояния дня] Ошибка при обновлении CombinedDiaryEntry ID {combined_entry.id}: {e}", exc_info=True)
            return False

    async def update_daily_state_text_and_count(
        self, 
        combined_entry: CombinedDiaryEntry, 
        new_text: str, 
        new_entry_count: int,
        latest_mood_score: Optional[int] = None # Новая оценка от последней записи
    ) -> bool:
        """
        Асинхронно обновляет текст и счетчик записей в CombinedDiaryEntry.
        Также обновляет список и среднее значение настроения, если передана новая оценка.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_text: Новый объединенный текст.
            new_entry_count: Новое количество записей.
            latest_mood_score: (Новое) mood_score из последней записи.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"[Обновление текста и счетчика] Начало обновления CombinedDiaryEntry ID {combined_entry.id}")
        
        # === ИСПОЛЬЗУЕМ УНИВЕРСАЛЬНУЮ ФУНКЦИЮ ===
        # Обновляем только текст и счетчик, остальные поля не трогаем
        update_success = await self._update_combined_entry_internal(
            combined_entry=combined_entry,
            text=new_text,
            entry_count=new_entry_count,
            ai_state_data=None,      # Не обновляем
            is_analyzed=None,        # Не обновляем
            latest_mood_score=latest_mood_score
        )
        
        if update_success:
            logger.info(f"[Обновление текста и счетчика] CombinedDiaryEntry ID {combined_entry.id} успешно обновлен (текст и счетчик).")
        else:
            logger.error(f"[Обновление текста и счетчика] Не удалось обновить CombinedDiaryEntry ID {combined_entry.id}.")
        
        return update_success

    async def create_daily_state_from_entry(
        self, diary_entry: DiaryEntry
    ) -> Optional[CombinedDiaryEntry]:
        """
        Создает новый CombinedDiaryEntry на основе одной DiaryEntry.
        Используется при первой записи дня.

        Args:
            diary_entry: Объект DiaryEntry.

        Returns:
            CombinedDiaryEntry: Созданный объект состояния дня или None при ошибке.
        """
        try:
            target_date = diary_entry.entry_date
            initial_text = diary_entry.text
            user = diary_entry.user
            @sync_to_async
            def _create_sync():
                with transaction.atomic():
                    combined_entry = CombinedDiaryEntry.objects.create(
                        user=user,
                        date=target_date,
                        text=initial_text,
                        entry_count=1,
                        ai_state_data='',
                        is_analyzed=False,
                    )
                return combined_entry
            new_combined_entry = await _create_sync()
            return new_combined_entry
        except Exception as e:
            logger.error(f"Ошибка при создании CombinedDiaryEntry из DiaryEntry ID {diary_entry.id}: {e}")
            return None
        
    async def _update_combined_entry_internal(
        self,
        combined_entry: CombinedDiaryEntry,
        text: Optional[str] = None,
        entry_count: Optional[int] = None,
        ai_state_data: Optional[str] = None,
        is_analyzed: Optional[bool] = None,
        latest_mood_score: Optional[int] = None
    ) -> bool:
        """
        Внутренняя универсальная функция для обновления CombinedDiaryEntry.
        Обновляет только те поля, которые переданы (не None).

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            text: Новый текст (если нужно обновить).
            entry_count: Новый счетчик записей (если нужно обновить).
            ai_state_data: Новое состояние ИИ (если нужно обновить).
            is_analyzed: Новый статус анализа (если нужно обновить).
            latest_mood_score: Новая оценка настроения для обновления статистики.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        try:
            # Собираем список полей для обновления
            fields_to_update = []
            
            # Обновляем текст, если передан
            if text is not None:
                combined_entry.text = text
                fields_to_update.append('text')
                
            # Обновляем счетчик, если передан
            if entry_count is not None:
                combined_entry.entry_count = entry_count
                fields_to_update.append('entry_count')
                
            # Обновляем состояние ИИ, если передано
            if ai_state_data is not None:
                combined_entry.ai_state_data = ai_state_data
                fields_to_update.append('ai_state_data')
                
            # Обновляем статус анализа, если передан
            if is_analyzed is not None:
                combined_entry.is_analyzed = is_analyzed
                fields_to_update.append('is_analyzed')
                
            # Обновляем оценки настроения, если передана новая оценка
            # (Это логика из оригинального update_daily_state_text_and_count)
            if latest_mood_score is not None:
                logger.debug(f"[Универсальное обновление] Обновление оценок: новая оценка {latest_mood_score}")
                # combined_entry.update_mood_scores(latest_mood_score)
                # update_mood_scores вызывает save, что может конфликтовать с нашей транзакцией.
                # Лучше обновить поля напрямую и сохранить всё вместе.
                if not isinstance(latest_mood_score, int) or not (1 <= latest_mood_score <= 10):
                    logger.warning(f"[Универсальное обновление] Некорректная оценка {latest_mood_score} для CombinedDiaryEntry ID {combined_entry.id}")
                else:
                    # Добавляем новую оценку
                    combined_entry.daily_mood_scores.append(latest_mood_score)
                    logger.debug(f"[Универсальное обновление] Добавлена оценка {latest_mood_score}. Список: {combined_entry.daily_mood_scores}")
                    # Пересчитываем среднее
                    if combined_entry.daily_mood_scores:
                        combined_entry.average_mood_score = sum(combined_entry.daily_mood_scores) / len(combined_entry.daily_mood_scores)
                        logger.debug(f"[Универсальное обновление] Средняя оценка пересчитана: {combined_entry.average_mood_score:.2f}")
                    else:
                        combined_entry.average_mood_score = 0.0
                        logger.debug("[Универсальное обновление] Список оценок пуст, средняя оценка установлена в 0.0")
                    
                    fields_to_update.extend(['daily_mood_scores', 'average_mood_score'])

            # Если нет полей для обновления, выходим
            if not fields_to_update:
                logger.info(f"[Универсальное обновление] Нет полей для обновления в CombinedDiaryEntry ID {combined_entry.id}.")
                return True

            # Добавляем updated_at, который обновляется автоматически, но явно указываем для полноты
            fields_to_update.append('updated_at')

            # Выполняем обновление в транзакции
            @sync_to_async
            def _update_sync():
                with transaction.atomic():
                    combined_entry.save(update_fields=fields_to_update)
                return True
            
            await _update_sync()
            logger.debug(f"[Универсальное обновление] CombinedDiaryEntry ID {combined_entry.id} обновлен. Поля: {fields_to_update}")
            return True

        except Exception as e:
            logger.error(f"[Универсальное обновление] Ошибка при обновлении CombinedDiaryEntry ID {combined_entry.id}: {e}", exc_info=True)
            return False

daily_state_service = DailyStateService()

async def get_daily_state(user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
    """Удобная функция для получения состояния дня."""
    return await daily_state_service.get_daily_state(user, target_date)

async def get_or_create_daily_state(user: User, target_date: date, initial_text: str) -> CombinedDiaryEntry:
    """Удобная функция для получения или создания состояния дня."""
    return await daily_state_service.get_or_create_daily_state(user, target_date, initial_text)

async def update_daily_state(combined_entry: CombinedDiaryEntry, new_ai_state_data: str, latest_mood_score: Optional[int] = None) -> bool:
    """Удобная функция для обновления состояния дня."""
    return await daily_state_service.update_daily_state(combined_entry, new_ai_state_data, latest_mood_score)

async def update_daily_state_text_and_count(
    combined_entry: CombinedDiaryEntry, new_text: str, new_entry_count: int
) -> bool:
    """Удобная функция для обновления текста и счетчика записей."""
    return await daily_state_service.update_daily_state_text_and_count(combined_entry, new_text, new_entry_count)

async def create_daily_state_from_entry(diary_entry: DiaryEntry) -> Optional[CombinedDiaryEntry]:
    """Удобная функция для создания состояния дня из одной записи."""
    return await daily_state_service.create_daily_state_from_entry(diary_entry)
