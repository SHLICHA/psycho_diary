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
        try:
            from bot.services.diary_service import diary_service
            combined_text = await diary_service.get_combined_entry_text(combined_entry.user, combined_entry.date)
            entries_today = await diary_service.get_user_entries_for_date(combined_entry.user, combined_entry.date)
            entry_count = len(entries_today)
            @sync_to_async
            def _update_sync():
                with transaction.atomic():
                    combined_entry.text = combined_text
                    combined_entry.entry_count = entry_count
                    combined_entry.ai_state_data = new_ai_state_data
                    combined_entry.is_analyzed = True
                    if latest_mood_score is not None:
                        logger.debug(f"Обновление оценок: новая оценка {latest_mood_score}")
                        combined_entry.update_mood_scores(latest_mood_score)
                    else:
                         combined_entry.save(update_fields=['text', 'entry_count', 'ai_state_data', 'is_analyzed', 'updated_at'])
                return True
            await _update_sync()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении CombinedDiaryEntry ID {combined_entry.id}: {e}")
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
        try:
            @sync_to_async
            def _update_text_sync():
                with transaction.atomic():
                    combined_entry.text = new_text
                    combined_entry.entry_count = new_entry_count
                    if latest_mood_score is not None:
                        logger.debug(f"Обновление оценок: новая оценка {latest_mood_score}")
                        combined_entry.update_mood_scores(latest_mood_score)
                    combined_entry.save(update_fields=['text', 'entry_count'])
                return True
            await _update_text_sync()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении текста/счетчика/оценок в CombinedDiaryEntry ID {combined_entry.id}: {e}")
            return False

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