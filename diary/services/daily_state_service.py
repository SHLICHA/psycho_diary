# diary/services/daily_state_service.py
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
        logger.info(f"Получение CombinedDiaryEntry для пользователя {user.telegram_id} за {target_date}")
        try:
            # Используем sync_to_async для ORM-запроса
            @sync_to_async
            def _get_sync():
                try:
                    return CombinedDiaryEntry.objects.select_related('user').get(
                        user=user, date=target_date
                    )
                except CombinedDiaryEntry.DoesNotExist:
                    return None

            combined_entry = await _get_sync()
            if combined_entry:
                logger.info(f"CombinedDiaryEntry найден, ID: {combined_entry.id}")
            else:
                logger.info("CombinedDiaryEntry не найден")
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
        logger.info(f"Получение или создание CombinedDiaryEntry для пользователя {user.telegram_id} за {target_date}")
        try:
            # Используем sync_to_async для ORM-запроса
            @sync_to_async
            def _get_or_create_sync():
                obj, created = CombinedDiaryEntry.objects.select_related('user').get_or_create(
                    user=user,
                    date=target_date,
                    defaults={
                        'text': initial_text,
                        'entry_count': 1, # Предполагаем, что это первая запись
                        'ai_state_data': '', # Изначально пустое
                        'is_analyzed': False,
                    }
                )
                return obj, created

            combined_entry, created = await _get_or_create_sync()
            if created:
                logger.info(f"Новый CombinedDiaryEntry создан, ID: {combined_entry.id}")
            else:
                logger.info(f"Существующий CombinedDiaryEntry загружен, ID: {combined_entry.id}")
            return combined_entry
        except Exception as e:
            logger.error(f"Ошибка при получении или создании CombinedDiaryEntry за {target_date}: {e}")
            raise # Пусть ошибка пробрасывается, если не удалось создать/загрузить

    async def update_daily_state(
        self, 
        combined_entry: CombinedDiaryEntry, 
        new_ai_state_data: str,
        latest_mood_score: Optional[int] = None # НОВЫЙ АРГУМЕНТ
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
        logger.info(f"Обновление CombinedDiaryEntry ID {combined_entry.id} с новым состоянием ИИ")
        try:
            from bot.services.diary_service import diary_service
            combined_text = await diary_service.get_combined_entry_text(combined_entry.user, combined_entry.date)
            entries_today = await diary_service.get_user_entries_for_date(combined_entry.user, combined_entry.date)
            entry_count = len(entries_today)

            @sync_to_async
            def _update_sync():
                with transaction.atomic():
                    # Обновляем текст и счетчик
                    combined_entry.text = combined_text
                    combined_entry.entry_count = entry_count
                    combined_entry.ai_state_data = new_ai_state_data
                    combined_entry.is_analyzed = True
                    
                    # --- НОВОЕ: Обновляем список и среднее оценок, если передана новая оценка ---
                    if latest_mood_score is not None:
                        logger.debug(f"Обновление оценок: новая оценка {latest_mood_score}")
                        # Вызываем метод модели, который обновит список и среднее
                        combined_entry.update_mood_scores(latest_mood_score)
                        # update_mood_scores уже вызвал save() внутри себя, поэтому повторный save() не нужен
                        # Но если он не вызывает save(), тогда нужно:
                        # combined_entry.save(update_fields=['text', 'entry_count', 'daily_mood_scores', 'average_mood_score', 'ai_state_data', 'is_analyzed', 'updated_at'])
                    else:
                         # Если новая оценка не передана, сохраняем остальное
                         combined_entry.save(update_fields=['text', 'entry_count', 'ai_state_data', 'is_analyzed', 'updated_at'])
                    # ----------------------------------------------------------------------------
                        
                return True

            await _update_sync()
            logger.info(f"CombinedDiaryEntry ID {combined_entry.id} успешно обновлен (включая текст, счетчик и оценки)")
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
        logger.info(f"Обновление текста, счетчика и оценок в CombinedDiaryEntry ID {combined_entry.id}")
        try:
            @sync_to_async
            def _update_text_sync():
                with transaction.atomic():
                    combined_entry.text = new_text
                    combined_entry.entry_count = new_entry_count
                    
                    # Если передана новая оценка, обновляем список и среднее
                    if latest_mood_score is not None:
                        logger.debug(f"Обновление оценок: новая оценка {latest_mood_score}")
                        # Вызываем метод модели для обновления
                        combined_entry.update_mood_scores(latest_mood_score)
                        # combined_entry.daily_mood_scores.append(latest_mood_score)
                        # if combined_entry.daily_mood_scores:
                        #     combined_entry.average_mood_score = sum(combined_entry.daily_mood_scores) / len(combined_entry.daily_mood_scores)
                        # logger.debug(f"Обновлен список оценок: {combined_entry.daily_mood_scores}, среднее: {combined_entry.average_mood_score}")
                    
                    # combined_entry.save(update_fields=['text', 'entry_count', 'daily_mood_scores', 'average_mood_score'])
                    combined_entry.save(update_fields=['text', 'entry_count']) # update_mood_scores уже вызвал save
                return True

            await _update_text_sync()
            logger.info(f"Текст, счетчик и оценки в CombinedDiaryEntry ID {combined_entry.id} успешно обновлены")
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
        logger.info(f"Создание CombinedDiaryEntry из DiaryEntry ID {diary_entry.id}")
        try:
            target_date = diary_entry.entry_date # Используем свойство из модели
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
                        ai_state_data='', # Изначально пустое
                        is_analyzed=False,
                    )
                return combined_entry

            new_combined_entry = await _create_sync()
            logger.info(f"CombinedDiaryEntry ID {new_combined_entry.id} создан из DiaryEntry")
            return new_combined_entry
        except Exception as e:
            logger.error(f"Ошибка при создании CombinedDiaryEntry из DiaryEntry ID {diary_entry.id}: {e}")
            return None

# Глобальный экземпляр сервиса
daily_state_service = DailyStateService()

# Удобные функции для использования (опционально)
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