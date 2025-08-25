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
        self, combined_entry: CombinedDiaryEntry, new_ai_state_data: str
    ) -> bool:
        """
        Асинхронно обновляет существующий CombinedDiaryEntry с новым состоянием от ИИ.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_ai_state_data: Новое текстовое состояние дня от ИИ.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"Обновление CombinedDiaryEntry ID {combined_entry.id} с новым состоянием ИИ")
        try:
            # Используем sync_to_async для ORM-запроса
            @sync_to_async
            def _update_sync():
                with transaction.atomic():
                    # Пересчитываем объединенный текст и количество записей
                    # при каждом обновлении, чтобы держать его актуальным.
                    # Это может быть избыточно, если текст обновляется отдельно,
                    # но гарантирует согласованность.
                    # TODO: Оценить, нужно ли это здесь или делать отдельно.
                    # diary_service.get_combined_entry_text можно использовать.
                    # Пока оставим обновление только ai_state_data и флага.
                    combined_entry.ai_state_data = new_ai_state_data
                    combined_entry.is_analyzed = True
                    combined_entry.save(update_fields=['ai_state_data', 'is_analyzed', 'updated_at'])
                return True

            await _update_sync()
            logger.info(f"CombinedDiaryEntry ID {combined_entry.id} успешно обновлен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении CombinedDiaryEntry ID {combined_entry.id}: {e}")
            return False

    async def update_daily_state_text_and_count(
        self, combined_entry: CombinedDiaryEntry, new_text: str, new_entry_count: int
    ) -> bool:
        """
        Асинхронно обновляет текст и счетчик записей в CombinedDiaryEntry.
        Используется, например, при редактировании записи или добавлении новой.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_text: Новый объединенный текст.
            new_entry_count: Новое количество записей.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        logger.info(f"Обновление текста и счетчика в CombinedDiaryEntry ID {combined_entry.id}")
        try:
            @sync_to_async
            def _update_text_sync():
                with transaction.atomic():
                    combined_entry.text = new_text
                    combined_entry.entry_count = new_entry_count
                    # Сбрасываем флаг анализа, если текст изменился кардинально
                    # combined_entry.is_analyzed = False # Опционально
                    combined_entry.save(update_fields=['text', 'entry_count', 'updated_at'])
                return True

            await _update_text_sync()
            logger.info(f"Текст и счетчик в CombinedDiaryEntry ID {combined_entry.id} успешно обновлены")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении текста/счетчика в CombinedDiaryEntry ID {combined_entry.id}: {e}")
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

async def update_daily_state(combined_entry: CombinedDiaryEntry, new_ai_state_data: str) -> bool:
    """Удобная функция для обновления состояния дня."""
    return await daily_state_service.update_daily_state(combined_entry, new_ai_state_data)

async def update_daily_state_text_and_count(
    combined_entry: CombinedDiaryEntry, new_text: str, new_entry_count: int
) -> bool:
    """Удобная функция для обновления текста и счетчика записей."""
    return await daily_state_service.update_daily_state_text_and_count(combined_entry, new_text, new_entry_count)

async def create_daily_state_from_entry(diary_entry: DiaryEntry) -> Optional[CombinedDiaryEntry]:
    """Удобная функция для создания состояния дня из одной записи."""
    return await daily_state_service.create_daily_state_from_entry(diary_entry)