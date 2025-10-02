"""
Сервис для работы с записями дневника
"""
import pytz
import logging

from asgiref.sync import sync_to_async
from typing import List, Dict, Any, Optional
from datetime import datetime, date, time, timedelta
from django.db import transaction
from django.db.models import F
from django.core.cache import cache

from bot.utils.decorators import async_error_handler, database_retry 
from diary.models import DiaryEntry, PsychoAnalysis, CombinedDiaryEntry, TherapyTask
from diary.services.daily_state_service import (
    get_daily_state,
    get_or_create_daily_state,
    update_daily_state,
    update_daily_state_text_and_count,
    create_daily_state_from_entry
)
from users.models import User
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class DiaryService:
    """Сервис для работы с записями дневника"""

    @async_error_handler('diary_service')
    @database_retry(max_retries=3)
    async def create_text_entry(
        self, 
        user: User, 
        text: str, 
        language: str = 'ru',
        entry_datetime: datetime = None
    ) -> DiaryEntry:
        """
        Асинхронное создание текстовой записи - ОПТИМИЗИРОВАНО
        """
        try:
            @sync_to_async
            def _create_entry():
                with transaction.atomic():
                    return DiaryEntry.objects.create(
                        user=user,
                        text=text,
                        language=language,
                        word_count=len(text.split()),
                        is_processed=False,
                        created_at=entry_datetime or datetime.now()
                    )
            diary_entry = await _create_entry()
            logger.info(f"Текстовая запись создана: Entry ID {diary_entry.id}")
            entry_date = await diary_entry.aentry_date()
            cache.delete_many([
                f'user_{user.id}_entries_{entry_date}',
                f'user_{user.id}_calendar_{entry_date.year}_{entry_date.month}'
            ])
            return diary_entry
        except Exception as e:
            logger.error(f"Ошибка при создании текстовой записи: {e}")
            raise
    
    async def update_entry_text(self, entry_id: int, user: User, new_text: str) -> bool:
        """
        Асинхронное обновление текста записи и соответствующего CombinedDiaryEntry.

        Args:
            entry_id: ID записи.
            user: Пользователь.
            new_text: Новый текст записи.

        Returns:
            bool: True, если успешно, иначе False.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            target_date = entry.entry_date
            @sync_to_async
            def _update_entry_and_related():
                with transaction.atomic():
                    entry.text = new_text
                    entry.word_count = len(new_text.split())
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                    entry.is_processed = False
                    entry.processing_error = ""
                    entry.save(update_fields=['text', 'word_count', 'is_processed', 'processing_error'])
                    return True
            await _update_entry_and_related()
            @sync_to_async
            def _update_or_create_combined_entry():
                with transaction.atomic():
                    try:
                        combined_entry = CombinedDiaryEntry.objects.select_for_update().get(user=user, date=target_date) 
                        all_entries_for_day = list(DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at'))
                        if not all_entries_for_day:
                             logger.error(f"[Сервис] Критическая ошибка: Запись {entry_id} существует, но записей за день {target_date} нет!")
                             texts = [entry.text]
                             new_combined_text = "\n\n---\n\n".join(texts)
                             new_entry_count = 1
                             combined_entry = CombinedDiaryEntry.objects.create(
                                 user=user,
                                 date=target_date,
                                 text=new_combined_text,
                                 entry_count=new_entry_count,
                                 ai_state_data='',
                                 is_analyzed=False,
                             )
                        else:
                             texts = [e.text for e in all_entries_for_day]
                             new_combined_text = "\n\n---\n\n".join(texts)
                             new_entry_count = len(all_entries_for_day) 
                             combined_entry.text = new_combined_text
                             combined_entry.entry_count = new_entry_count
                             combined_entry.reset_analysis_flag()
                             combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed'])
                    except CombinedDiaryEntry.DoesNotExist:
                        all_entries_for_day = list(DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at'))
                        if not all_entries_for_day:
                            logger.warning(f"[Сервис] CombinedDiaryEntry и записи за день {target_date} не найдены при обновлении. Создаем новый CombinedDiaryEntry с текущей записью.")
                            texts = [entry.text] 
                            new_entry_count = 1
                        else:
                            texts = [e.text for e in all_entries_for_day]
                            new_entry_count = len(all_entries_for_day)                   
                        new_combined_text = "\n\n---\n\n".join(texts)
                        combined_entry = CombinedDiaryEntry.objects.create(
                            user=user,
                            date=target_date,
                            text=new_combined_text,
                            entry_count=new_entry_count,
                            ai_state_data='',
                            is_analyzed=False,
                        )
                    return True
            await _update_or_create_combined_entry()
            return True
        except DiaryEntry.DoesNotExist:
            logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id} (внешний блок)")
            return False
        except Exception as e:
            logger.error(f"Ошибка в асинхронном обновлении текста записи {entry_id}: {e}", exc_info=True)
            try:
                @sync_to_async
                def _set_error_flag():
                     DiaryEntry.objects.filter(id=entry_id, user=user).update(is_processed=False, processing_error=str(e)[:255])
                await _set_error_flag()
            except Exception as flag_error:
                 logger.error(f"Не удалось установить флаг ошибки для записи {entry_id}: {flag_error}")
            return False

    async def delete_entry_and_update_combined(self, entry_id: int, user: User) -> bool:
        """
        Асинхронное удаление записи и обновление/удаление связанного CombinedDiaryEntry.

        Args:
            entry_id: ID записи.
            user: Пользователь.

        Returns:
            bool: True, если успешно, иначе False.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            entry_date = entry.entry_date
            @sync_to_async
            def _delete_related_and_entry():
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                    entry.key_points.all().delete() 
                    if hasattr(entry, 'voicetotext'):
                        entry.voicetotext.delete()             
                    TherapyTask.objects.filter(related_entry=entry).delete()
                    entry.delete() 
            await _delete_related_and_entry()
            try:
                combined_entry = await CombinedDiaryEntry.objects.aget(user=user, date=entry_date)
                @sync_to_async
                def _get_remaining_entries():
                    return list(DiaryEntry.objects.filter(user=user, created_at__date=entry_date).order_by('created_at'))
                remaining_entries = await _get_remaining_entries()
                if remaining_entries:
                    texts = [e.text for e in remaining_entries]
                    new_combined_text = "\n\n---\n\n".join(texts)
                    new_entry_count = len(remaining_entries)
                    combined_entry.text = new_combined_text
                    combined_entry.entry_count = new_entry_count
                    combined_entry.reset_analysis_flag()
                    await combined_entry.asave(update_fields=['text', 'entry_count', 'is_analyzed'])
                    logger.info(f"CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                else:
                    await combined_entry.adelete()                 
            except CombinedDiaryEntry.DoesNotExist:
                logger.warning(f"CombinedDiaryEntry для {entry_date} не найден при удалении записи {entry_id}. Возможно, он уже был удален.")
            return True
        except Exception as e:
            logger.error(f"Ошибка в асинхронном удалении записи {entry_id} и обновлении CombinedDiaryEntry: {e}", exc_info=True)
            return False

    async def get_or_update_daily_state_with_entries(
        self,
        user: User,
        diary_entry: DiaryEntry
    ) -> tuple[CombinedDiaryEntry, bool]:
        """
        Получает или создаёт CombinedDiaryEntry и обновляет его текст и счётчик.
        Возвращает объект и флаг is_first_entry_of_day.
        """
        entry_date = diary_entry.entry_date
        combined_entry = await self.get_daily_state(user, entry_date)
        if combined_entry is None:
            combined_entry = await self.create_daily_state_from_entry(diary_entry)
            return combined_entry, True
        entries = await self.get_user_entries_for_date(user, entry_date)
        combined_text = await self.get_combined_entry_text(user, entry_date, entries_list=entries)
        await self.update_daily_state_text_and_count(
            combined_entry, combined_text, len(entries)
        )
        return combined_entry, False

    @async_error_handler('diary_service')
    async def get_user_entries_for_date(
        self, 
        user: User, 
        target_date: date
    ) -> List[DiaryEntry]:
        """
        Асинхронное получение записей за дату - С КЭШИРОВАНИЕМ
        """
        cache_key = f'user_{user.id}_entries_{target_date}'
        cached_entries = cache.get(cache_key)
        if cached_entries is not None:
            return cached_entries
        try:
            user_timezone_str = user.timezone or 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            start_of_day_user_tz = user_tz.localize(
                datetime.combine(target_date, time.min)
            )
            end_of_day_user_tz = user_tz.localize(
                datetime.combine(target_date, time.max)
            )
            start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
            end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)
            entries = await sync_to_async(list)(
                DiaryEntry.objects
                .select_related('user')
                .filter(
                    user=user,
                    created_at__gte=start_of_day_utc,
                    created_at__lte=end_of_day_utc
                )
                .order_by('created_at')
            )
            if entries:
                cache.set(cache_key, entries, timeout=300)
            logger.info(f"Найдено {len(entries)} записей за {target_date}")
            return entries
        except Exception as e:
            logger.error(f"Ошибка при получении записей за дату: {e}")
            return []

    async def get_combined_entry_text(
        self, 
        user: User, 
        target_date: date, 
        entries_list: Optional[List[DiaryEntry]] = None
    ) -> str:
        """
        Асинхронное получение объединенного текста всех записей пользователя за конкретную дату,
        с учетом часового пояса пользователя.

        Args:
            user: Пользователь.
            target_date: Целевая дата (в терминах пользователя).
            entries_list: (Опционально) Список уже полученных записей DiaryEntry за эту дату.
                        Если предоставлен, будет использован вместо нового запроса к БД.

        Returns:
            str: Объединенный текст всех записей дня. Пустая строка, если записей нет или произошла ошибка.
        """
        try:
            if entries_list is not None:
                entries = entries_list
            else:
                entries = await self.get_user_entries_for_date(user, target_date) 
            if not entries:
                return ""
            texts = [entry.text for entry in entries]
            combined_text = "\n\n---\n\n".join(texts)
            return combined_text
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении объединенного текста за {target_date} для пользователя {user.telegram_id} (с учетом часового пояса): {e}", exc_info=True)
            return ""

    async def delete_entry(self, entry_id: int, user: User) -> bool:
        """
        Асинхронное удаление записи дневника и всех связанных объектов.

        Args:
            entry_id: ID записи.
            user: Пользователь (для проверки прав доступа).

        Returns:
            bool: True, если запись была успешно удалена или не существовала, False в случае ошибки.
        """
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user)
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return True 
            @sync_to_async
            def _delete_entry_atomic():
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        try:
                            entry.analysis.delete() 
                        except Exception as analysis_delete_error:
                            logger.warning(f"Ошибка при удалении связанного PsychoAnalysis для записи {entry_id}: {analysis_delete_error}")
                    entry.delete()
                    logger.info(f"Запись дневника {entry_id} успешно удалена для пользователя {user.telegram_id}.")
            await _delete_entry_atomic()
            return True
        except Exception as e:
            logger.error(f"Ошибка при асинхронном удалении записи {entry_id} для пользователя {user.telegram_id}: {e}", exc_info=True)
            return False
    
    @async_error_handler('diary_service')
    async def get_days_with_entries(self, user: User, year: int, month: int) -> set:
        """
        Получение дней с записями - С КЭШИРОВАНИЕМ
        """
        cache_key = f'user_{user.id}_calendar_{year}_{month}'
        cached_days = cache.get(cache_key)
        if cached_days:
            return cached_days
        
        try:
            @sync_to_async
            def _get_days():
                return set(
                    DiaryEntry.objects
                    .filter(user=user, created_at__year=year, created_at__month=month)
                    .annotate(day=F('created_at__day'))
                    .values_list('day', flat=True)
                    .distinct()
                )
            days_with_entries = await _get_days()
            cache.set(cache_key, days_with_entries, timeout=3600)
            return days_with_entries
        except Exception as e:
            logger.error(f"Ошибка при получении дней с записями: {e}")
            return set()

    async def get_daily_state(self, user: User, target_date: date) -> Optional[CombinedDiaryEntry]:
        """
        Асинхронно получает CombinedDiaryEntry для пользователя и даты.
        Делегирует вызов DailyStateService.

        Args:
            user: Пользователь.
            target_date: Целевая дата.

        Returns:
            CombinedDiaryEntry: Объект состояния дня или None, если не найден.
        """
        return await get_daily_state(user, target_date)

    async def get_or_create_daily_state(self, user: User, target_date: date, initial_text: str) -> CombinedDiaryEntry:
        """
        Асинхронно получает или создает CombinedDiaryEntry для пользователя и даты.
        Делегирует вызов DailyStateService.

        Args:
            user: Пользователь.
            target_date: Целевая дата.
            initial_text: Начальный объединенный текст для создания записи.

        Returns:
            CombinedDiaryEntry: Существующий или новый объект состояния дня.
        """
        return await get_or_create_daily_state(user, target_date, initial_text)

    async def update_daily_state(self, combined_entry: CombinedDiaryEntry, new_ai_state_data: str) -> bool:
        """
        Асинхронно обновляет существующий CombinedDiaryEntry с новым состоянием от ИИ.
        Делегирует вызов DailyStateService.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_ai_state_data: Новое текстовое состояние дня от ИИ.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        return await update_daily_state(combined_entry, new_ai_state_data)

    async def update_daily_state_text_and_count(
        self, combined_entry: CombinedDiaryEntry, new_text: str, new_entry_count: int
    ) -> bool:
        """
        Асинхронно обновляет текст и счетчик записей в CombinedDiaryEntry.
        Делегирует вызов DailyStateService.

        Args:
            combined_entry: Объект CombinedDiaryEntry для обновления.
            new_text: Новый объединенный текст.
            new_entry_count: Новое количество записей.

        Returns:
            bool: True, если обновление прошло успешно, иначе False.
        """
        return await update_daily_state_text_and_count(combined_entry, new_text, new_entry_count)

    async def create_daily_state_from_entry(self, diary_entry: DiaryEntry) -> Optional[CombinedDiaryEntry]:
        """
        Создает новый CombinedDiaryEntry на основе одной DiaryEntry.
        Делегирует вызов DailyStateService.

        Args:
            diary_entry: Объект DiaryEntry.

        Returns:
            CombinedDiaryEntry: Созданный объект состояния дня или None при ошибке.
        """
        return await create_daily_state_from_entry(diary_entry)
    
    async def delete_all_entries_for_day(self, user: User, target_date: date) -> bool:
        """
        Асинхронно удаляет все записи DiaryEntry за указанный день для пользователя,
        а также все связанные объекты и TherapyTask, созданные для этих записей.
        Также удаляет CombinedDiaryEntry за этот день.
        """
        logger.info(f"[Сервис] Удаление всех записей за {target_date} для пользователя {user.telegram_id}")
        try:
            @sync_to_async
            def _delete_sync():
                with transaction.atomic():
                    entries = DiaryEntry.objects.filter(user=user, created_at__date=target_date)
                    entry_ids = list(entries.values_list('id', flat=True))
                    if not entry_ids:
                        CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                        return True
                    PsychoAnalysis.objects.filter(entry_id__in=entry_ids).delete()
                    TherapyTask.objects.filter(related_entry_id__in=entry_ids).delete()
                    entries.delete()
                    CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                return True
            result = await _delete_sync()
            logger.info(f"[Сервис] Удаление записей за {target_date} завершено успешно: {result}")
            return result
        except Exception as e:
            logger.error(f"[Сервис] Ошибка при удалении записей за {target_date}: {e}")
            return False

diary_service = DiaryService()

#============================================УДОБНЫЕ ФУНКЦИИ=================================================
async def create_text_entry(user: User, text: str, language: str = 'ru', entry_datetime: datetime = None) -> DiaryEntry:
    """Удобная функция для создания текстовой записи"""
    return await diary_service.create_text_entry(user, text, language, entry_datetime)

async def create_voice_entry(
        user: User,
        voice_file_id: str,
        duration: int,
        recognized_text: str,
        language: str = 'ru',
        entry_datetime: datetime = None,
        speechkit_api_response: Optional[Dict[str, Any]] = None,
        deepseek_api_response: Optional[Dict[str, Any]] = None) -> DiaryEntry:
    """Удобная функция для создания голосовой записи"""
    return await diary_service.create_voice_entry(user, voice_file_id, duration, recognized_text, language, entry_datetime, speechkit_api_response, deepseek_api_response)

async def get_user_entries_for_date(user: User, target_date: date) -> List[DiaryEntry]:
    """Удобная функция для получения записей за дату"""
    return await diary_service.get_user_entries_for_date(user, target_date)

async def get_combined_entry_text(
    user: User, 
    target_date: date, 
    entries_list: Optional[List[DiaryEntry]] = None
) -> str:
    """Удобная функция для получения объединенного текста (с учетом часового пояса)."""
    return await diary_service.get_combined_entry_text(user, target_date, entries_list)

async def delete_entry(entry_id: int, user: User) -> bool:
    """Удобная функция для удаления записи"""
    return await diary_service.delete_entry(entry_id, user)

async def get_days_with_entries(user: User, year: int, month: int) -> set:
    """Удобная функция для получения дней с записями"""
    return await diary_service.get_days_with_entries(user, year, month)

async def delete_all_entries_for_day(user: User, target_date: date) -> bool:
    """Удобная асинхронная функция для удаления всех записей за день."""
    return await diary_service.delete_all_entries_for_day(user, target_date)
  
async def get_entry_date(entry: DiaryEntry) -> date:
        try:
            user = await entry.user.aget()
            user_timezone_str = user.timezone or 'UTC'
            user_tz = pytz.timezone(user_timezone_str)
            created_at = entry.created_at
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            return created_at.astimezone(user_tz).date()
        except Exception as e:
            logger.error(f"Ошибка при получении даты записи {entry.id}: {e}")
            return entry.created_at.date()
        
def get_user_entries_for_date_sync(user: User, target_date: date) -> List[DiaryEntry]:
    """
    Синхронная удобная функция для получения записей за дату.
    """
    from asgiref.sync import async_to_sync
    return async_to_sync(diary_service.get_user_entries_for_date)(user, target_date)

def get_user_streaks(user):
    """
    Подсчитывает текущую и максимальную серию дней с записями для пользователя.
    """
    try:
        import pytz
        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)
        now = datetime.now(user_tz)
        today = now.date()
        # Получаем все даты, когда пользователь делал записи
        entry_dates = DiaryEntry.objects.filter(
            user=user
        ).order_by('-created_at').distinct().values_list('created_at', flat=True)
        # Преобразуем в даты в часовом поясе пользователя
        user_entry_dates = []
        for dt in entry_dates:
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            user_entry_dates.append(dt.astimezone(user_tz).date())
        # Убираем дубликаты и сортируем по убыванию
        unique_dates = sorted(set(user_entry_dates), reverse=True)
        if not unique_dates:
            return 0, 0
        # Подсчитываем текущую серию
        current_streak = 0
        current_date = today
        for entry_date in unique_dates:
            if entry_date == current_date:
                current_streak += 1
                current_date -= timedelta(days=1)
            elif entry_date < current_date:
                break
        # Подсчитываем максимальную серию
        max_streak = 0
        current_run = 0
        prev_date = None
        for entry_date in sorted(set(user_entry_dates)):
            if prev_date is None:
                current_run = 1
            elif entry_date == prev_date + timedelta(days=1):
                current_run += 1
            else:
                max_streak = max(max_streak, current_run)
                current_run = 1
            prev_date = entry_date
        max_streak = max(max_streak, current_run)
        return current_streak, max_streak
    except Exception as e:
        logger.error(f"Ошибка при подсчете серий пользователя {user.telegram_id}: {e}")
        return 0, 0