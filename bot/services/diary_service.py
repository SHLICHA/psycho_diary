"""
Сервис для работы с записями дневника
"""
import pytz
import logging

from asgiref.sync import sync_to_async
from typing import List, Dict, Any, Optional
from datetime import datetime, date, time
from django.db import transaction
from django.db.models import F
from diary.models import DiaryEntry, KeyPoint, PsychoAnalysis, VoiceToText, CombinedDiaryEntry, TaskCompletion, TherapyTask, UserInsight
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

    async def create_text_entry(
        self, 
        user: User, 
        text: str, 
        language: str = 'ru',
        entry_datetime: datetime = None
    ) -> DiaryEntry:
        """
        Асинхронное создание текстовой записи.

        Args:
            user: Пользователь
            text: Текст записи
            language: Язык записи
            entry_datetime: Дата и время создания записи

        Returns:
            DiaryEntry: Созданная запись
        """
        try:
            @sync_to_async
            def _create_text_entry_atomic() -> DiaryEntry:
                from django.db import transaction
                with transaction.atomic():
                    diary_entry = DiaryEntry(
                        user=user,
                        text=text,
                        language=language,
                        word_count=len(text.split()),
                        is_processed=False
                    )
                    if entry_datetime:
                        diary_entry.created_at = entry_datetime
                    diary_entry.save() 
                    logger.info(f"Текстовая запись создана: Entry ID {diary_entry.id}")
                    return diary_entry 
            diary_entry = await _create_text_entry_atomic()
            return diary_entry
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании текстовой записи для пользователя {user.telegram_id}: {e}", exc_info=True)

            raise

    async def create_voice_entry(
        self, 
        user: User, 
        voice_file_id: str, 
        duration: int, 
        recognized_text: str,
        language: str = 'ru',
        entry_datetime: datetime = None,
        speechkit_api_response: Optional[Dict[str, Any]] = None,
        deepseek_api_response: Optional[Dict[str, Any]] = None
    ) -> DiaryEntry:
        """
        Асинхронное создание голосовой записи.

        Args:
            user: Пользователь
            voice_file_id: ID голосового файла в Telegram
            duration: Длительность голосового сообщения (сек)
            recognized_text: Распознанный текст
            language: Язык записи
            entry_datetime: Дата и время создания записи
            speechkit_api_response: Ответ API Yandex SpeechKit (для сохранения)
            deepseek_api_response: Результат обработки DeepSeek (для сохранения)

        Returns:
            DiaryEntry: Созданная запись
        """
        try:
            @sync_to_async
            def _create_voice_entry_atomic() -> DiaryEntry:
                from django.db import transaction
                with transaction.atomic():
                    diary_entry = DiaryEntry(
                        user=user,
                        text=recognized_text,
                        language=language,
                        word_count=len(recognized_text.split()),
                        is_processed=False
                    )
                    if entry_datetime:
                        diary_entry.created_at = entry_datetime
                    diary_entry.save()
                    voice_to_text_data = {
                        'entry': diary_entry,
                        'original_duration': duration,
                        'processed_text': recognized_text,
                        'processing_time': 0.0,
                        'speechkit_response': speechkit_api_response or {},
                        'api_response': deepseek_api_response or {}
                    }
                    VoiceToText.objects.create(**voice_to_text_data)
                    return diary_entry
            diary_entry = await _create_voice_entry_atomic()
            return diary_entry
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании голосовой записи для пользователя {user.telegram_id}: {e}", exc_info=True)
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
        logger.info(f"Асинхронное обновление текста записи {entry_id} для пользователя {user.telegram_id}")
        try:
            try:
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user) # Асинхронно
            except DiaryEntry.DoesNotExist:
                logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            target_date = entry.entry_date # Сохраняем дату до изменений
            @sync_to_async
            def _update_entry_and_related():
                from django.db import transaction
                with transaction.atomic():
                    entry.text = new_text
                    entry.word_count = len(new_text.split())
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                    entry.is_processed = False
                    entry.processing_error = ""
                    entry.save(update_fields=['text', 'word_count', 'is_processed', 'processing_error'])
                    logger.debug(f"Запись {entry_id} обновлена в БД.")
                    return True
            
            await _update_entry_and_related()
            @sync_to_async
            def _update_or_create_combined_entry():
                from django.db import transaction
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
                             logger.info(f"Создан новый CombinedDiaryEntry {combined_entry.id} после критической ошибки.")
                        else:
                             texts = [e.text for e in all_entries_for_day]
                             new_combined_text = "\n\n---\n\n".join(texts)
                             new_entry_count = len(all_entries_for_day) 
                             combined_entry.text = new_combined_text
                             combined_entry.entry_count = new_entry_count
                             combined_entry.reset_analysis_flag()
                             combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed'])
                             logger.info(f"CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                        
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
                        logger.info(f"Создан новый CombinedDiaryEntry {combined_entry.id} для даты {target_date}.")
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
                entry = await DiaryEntry.objects.select_related('user').aget(id=entry_id, user=user) # Асинхронно
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False

            entry_date = entry.entry_date
            @sync_to_async
            def _delete_related_and_entry():
                from django.db import transaction
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        entry.analysis.delete()
                        logger.debug("Связанный PsychoAnalysis удален.")
                    entry.key_points.all().delete() 
                    
                    if hasattr(entry, 'voicetotext'):
                        entry.voicetotext.delete()
                        logger.debug("Связанный VoiceToText удален.")                
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
                    combined_entry.reset_analysis_flag() # is_analyzed = False
                    # combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed']) # Синхронно
                    await combined_entry.asave(update_fields=['text', 'entry_count', 'is_analyzed']) # Асинхронно
                    logger.info(f"CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                else:
                    # combined_entry.delete() # Синхронно
                    await combined_entry.adelete() # Асинхронно
                    logger.info(f"CombinedDiaryEntry для {entry_date} удален, так как записей больше нет.")
                    
            except CombinedDiaryEntry.DoesNotExist:
                logger.warning(f"CombinedDiaryEntry для {entry_date} не найден при удалении записи {entry_id}. Возможно, он уже был удален.")

            return True
            
        except Exception as e:
            logger.error(f"Ошибка в асинхронном удалении записи {entry_id} и обновлении CombinedDiaryEntry: {e}", exc_info=True)
            return False

    async def get_user_entries_for_date(
        self, 
        user: User, 
        target_date: date # Дата в терминах пользователя (т.е. какую дату он видит в календаре)
    ) -> List[DiaryEntry]:
        """
        Асинхронное получение списка записей пользователя за конкретный день,
        с учетом часового пояса пользователя.

        Args:
            user: Пользователь.
            target_date: Целевая дата (в терминах пользователя).

        Returns:
            List[DiaryEntry]: Список записей за указанный день пользователя.
        """
        logger.info(f"[УНИФИЦИРОВАННЫЙ МЕТОД] Получение записей пользователя {user.telegram_id} за {target_date} (учитывая часовой пояс {user.timezone})")
        try:
            user_timezone_str = user.timezone if user.timezone else 'UTC'
            
            # 1. Определяем начало и конец target_date в часовом поясе пользователя
            @sync_to_async
            def _get_utc_boundaries():
                user_tz = pytz.timezone(user_timezone_str)
                # Начало дня пользователя
                start_of_day_user_tz = datetime.combine(target_date, time.min) # 00:00:00
                start_of_day_user_tz = user_tz.localize(start_of_day_user_tz)
                # Конец дня пользователя
                end_of_day_user_tz = datetime.combine(target_date, time.max) # 23:59:59.999999
                end_of_day_user_tz = user_tz.localize(end_of_day_user_tz)
                
                # Конвертируем в UTC для запроса к БД (created_at хранится в UTC)
                start_of_day_utc = start_of_day_user_tz.astimezone(pytz.utc)
                end_of_day_utc = end_of_day_user_tz.astimezone(pytz.utc)
                
                logger.debug(f"  Границы по UTC: {start_of_day_utc} - {end_of_day_utc}")
                return start_of_day_utc, end_of_day_utc

            start_of_day_utc, end_of_day_utc = await _get_utc_boundaries()

            # 2. Запрашиваем записи
            entries = []
            async for entry in DiaryEntry.objects.filter(
                user=user,
                created_at__gte=start_of_day_utc,
                created_at__lte=end_of_day_utc
            ).order_by('created_at'):
                entries.append(entry)
                
            logger.info(f"[УНИФИЦИРОВАННЫЙ МЕТОД] Найдено {len(entries)} записей.")
            return entries
            
        except Exception as e:
            logger.error(f"Ошибка в унифицированном get_user_entries_for_date для пользователя {user.telegram_id}, дата {target_date}: {e}", exc_info=True)
            return []

    async def get_combined_entry_text(
        self, 
        user: User, 
        target_date: date, 
        entries_list: Optional[List[DiaryEntry]] = None  # Новый опциональный параметр
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
            # === ОПТИМИЗАЦИЯ ===
            # Если список записей уже предоставлен, используем его.
            # Иначе - делаем запрос к БД.
            if entries_list is not None:
                logger.debug(f"[ОПТИМИЗАЦИЯ] Использование предоставленного списка записей ({len(entries_list)} шт.) для get_combined_entry_text.")
                entries = entries_list
            else:
                logger.debug(f"[ОПТИМИЗАЦИЯ] Выполнение запроса к БД для получения записей за {target_date} в get_combined_entry_text.")
                # Используем унифицированный метод, который учитывает часовой пояс
                entries = await self.get_user_entries_for_date(user, target_date) 
            
            if not entries:
                logger.info(f"Записи за {target_date} для пользователя {user.telegram_id} не найдены (в т.ч. с учетом часового пояса).")
                return ""
            
            # Объединяем текст
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
                from django.db import transaction
                with transaction.atomic():
                    if hasattr(entry, 'analysis'):
                        try:
                            entry.analysis.delete() 
                            logger.debug(f"Связанный PsychoAnalysis для записи {entry_id} удален.")
                        except Exception as analysis_delete_error:
                            logger.warning(f"Ошибка при удалении связанного PsychoAnalysis для записи {entry_id}: {analysis_delete_error}")
                    entry.key_points.all().delete()
                    logger.debug(f"Связанные KeyPoint для записи {entry_id} удалены.")
                    try:
                        if hasattr(entry, 'voicetotext'):
                             entry.voicetotext.delete()
                             logger.debug(f"Связанный VoiceToText для записи {entry_id} удален.")
                    except Exception as voice_delete_error:
                        logger.debug(f"Связанный VoiceToText для записи {entry_id} не найден или ошибка при удалении: {voice_delete_error}")
                    entry.delete()
                    logger.info(f"Запись дневника {entry_id} успешно удалена для пользователя {user.telegram_id}.")

            await _delete_entry_atomic()
            return True
        except Exception as e:
            logger.error(f"Ошибка при асинхронном удалении записи {entry_id} для пользователя {user.telegram_id}: {e}", exc_info=True)
            return False
    
    async def get_days_with_entries(self, user: User, year: int, month: int) -> set:
        """
        Асинхронное получение дней месяца, в которые есть записи у пользователя.

        Args:
            user: Пользователь.
            year: Год.
            month: Месяц.

        Returns:
            set: Множество дней (int) с записями.
        """
        logger.info(f"Асинхронное получение дней с записями пользователя {user.telegram_id} за {month}.{year}")
        
        try:
            days_with_entries = set()
            async for day in DiaryEntry.objects.filter(
                user=user,
                created_at__year=year,
                created_at__month=month
            ).annotate(
                day_of_month=F('created_at__day')
            ).values_list('day_of_month', flat=True).distinct():
                days_with_entries.add(day)
            return days_with_entries
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении дней с записями для пользователя {user.telegram_id} за {month}.{year}: {e}", exc_info=True)
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
                    KeyPoint.objects.filter(entry_id__in=entry_ids).delete()
                    VoiceToText.objects.filter(entry_id__in=entry_ids).delete()
                    task_completions = TaskCompletion.objects.filter(completion_text__in=[entry.text for entry in entries])
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
        
    async def get_insights_for_entries(self, entry_ids: list) -> List[UserInsight]:
        """
        Асинхронно получает инсайты, связанные со списком ID записей.

        Args:
            entry_ids (list): Список ID записей DiaryEntry.

        Returns:
            List[UserInsight]: Список объектов UserInsight, отсортированных по весу и дате.
        """
        logger.debug(f"Получение инсайтов для записей: {entry_ids}")
        insights = []
        try:
            # Используем асинхронный менеджер для итерации
            async for insight in UserInsight.objects.filter(
                source_entry_id__in=entry_ids
            ).order_by('-weight', '-last_mentioned'):
                insights.append(insight)
            logger.debug(f"Получено {len(insights)} инсайтов.")
        except Exception as e:
            logger.error(f"Ошибка при получении инсайтов для записей {entry_ids}: {e}", exc_info=True)
        return insights

    async def get_keypoints_for_entries(self, entry_ids: list) -> List[KeyPoint]:
        """
        Асинхронно получает ключевые моменты, связанные со списком ID записей.

        Args:
            entry_ids (list): Список ID записей DiaryEntry.

        Returns:
            List[KeyPoint]: Список объектов KeyPoint, отсортированных по уверенности и дате.
        """
        logger.debug(f"Получение ключевых моментов для записей: {entry_ids}")
        keypoints = []
        try:
            # Используем асинхронный менеджер для итерации
            async for kp in KeyPoint.objects.filter(
                entry_id__in=entry_ids
            ).order_by('-confidence', '-created_at'):
                keypoints.append(kp)
            logger.debug(f"Получено {len(keypoints)} ключевых моментов.")
        except Exception as e:
            logger.error(f"Ошибка при получении ключевых моментов для записей {entry_ids}: {e}", exc_info=True)
        return keypoints        

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

async def get_insights_for_entries(entry_ids: list) -> List[UserInsight]:
    """Удобная функция для получения инсайтов по списку ID записей."""
    return await diary_service.get_insights_for_entries(entry_ids)

async def get_keypoints_for_entries(entry_ids: list) -> List[KeyPoint]:
    """Удобная функция для получения ключевых моментов по списку ID записей."""
    return await diary_service.get_keypoints_for_entries(entry_ids)