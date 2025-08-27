"""
Сервис для работы с записями дневника
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from django.db import transaction
from django.db.models import Q
from diary.models import DiaryEntry, KeyPoint, PsychoAnalysis, VoiceToText, CombinedDiaryEntry, TaskCompletion, TherapyTask
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
    
    @sync_to_async
    def create_text_entry_sync(
        self, 
        user: User, 
        text: str, 
        language: str = 'ru',
        entry_datetime: datetime = None
    ) -> DiaryEntry:
        """
        Синхронное создание текстовой записи (обёртка для async)
        
        Args:
            user: Пользователь
            text: Текст записи
            language: Язык записи
            
        Returns:
            DiaryEntry: Созданная запись
        """
        logger.info(f"Создание текстовой записи для пользователя {user.telegram_id}")
        logger.info(f"Текст записи длиной: {len(text)} символов")
        logger.info(f"Язык: {language}")
        logger.info(f"Время записи (переданное): {entry_datetime}")
        
        try:
            # Создаем запись в транзакции
            with transaction.atomic():
                diary_entry = DiaryEntry.objects.create(
                    user=user,
                    text=text,
                    language=language,
                    word_count=len(text.split()),
                    is_processed=False  # Пока не обработана
                )
                logger.info(f"Текстовая запись создана, ID: {diary_entry.id}")
                if entry_datetime:
                    # entry_datetime уже должно быть в часовом поясе пользователя
                    # Устанавливаем его как есть в created_at
                    diary_entry.created_at = entry_datetime
                    logger.info(f"Установлено пользовательское время created_at: {diary_entry.created_at}")
                diary_entry.save()             
                # Создаем анализ записи (заглушка)
                psycho_analysis = PsychoAnalysis.objects.create(
                    entry=diary_entry,
                    mood_score=7,  # Заглушка - оценка настроения 1-10
                    comment="Хорошая запись!",  # Заглушка - комментарий
                    recommendation="Продолжайте в том же духе",  # Заглушка - рекомендация
                    processing_time=2.0,  # Заглушка - время обработки в секундах
                    insights_extracted=3  # Заглушка - количество извлеченных инсайтов
                )
                logger.info(f"Анализ текстовой записи создан, ID: {psycho_analysis.id}")
                
                # Обновляем статус обработки записи
                diary_entry.is_processed = True
                diary_entry.processing_error = ""
                diary_entry.save(update_fields=['is_processed', 'processing_error'])
                logger.info(f"Статус текстовой записи обновлен на 'обработана'")
            
            return diary_entry
            
        except Exception as e:
            logger.error(f"Ошибка при создании текстовой записи: {e}")
            raise
    
    async def create_text_entry(
        self, 
        user: User, 
        text: str, 
        language: str = 'ru',
        entry_datetime: datetime = None
    ) -> DiaryEntry:
        """
        Асинхронное создание текстовой записи
        
        Args:
            user: Пользователь
            text: Текст записи
            language: Язык записи
            
        Returns:
            DiaryEntry: Созданная запись
        """
        logger.info(f"Асинхронное создание текстовой записи для пользователя {user.telegram_id}")
        logger.info(f"Текст записи длиной: {len(text)} символов")
        logger.info(f"Язык: {language}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            diary_entry = await self.create_text_entry_sync(user, text, language, entry_datetime)
            # ===============
            logger.info(f"Асинхронная текстовая запись создана, ID: {diary_entry.id}")
            return diary_entry
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании текстовой записи: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании текстовой записи: {e}")
            raise

    @sync_to_async
    def create_voice_entry_sync(
        self, 
        user: User, 
        voice_file_id: str, 
        duration: int, 
        recognized_text: str,
        language: str = 'ru',
        entry_datetime: datetime = None,
        # === Добавлены параметры для ответов API ===
        speechkit_api_response: Optional[Dict[str, Any]] = None,
        deepseek_api_response: Optional[Dict[str, Any]] = None
        # =====================================
    ) -> DiaryEntry:
        """
        Синхронное создание голосовой записи (обёртка для async)
        
        Args:
            user: Пользователь
            voice_file_id: ID голосового файла в Telegram
            duration: Длительность голосового сообщения (сек)
            recognized_text: Распознанный текст
            language: Язык записи
            # === Добавлены аргументы для ответов API ===
            speechkit_api_response: Ответ API Yandex SpeechKit (для сохранения)
            deepseek_api_response: Результат обработки DeepSeek (для сохранения)
            # =====================================
        Returns:
            DiaryEntry: Созданная запись
        """
        logger.info(f"Создание голосовой записи для пользователя {user.telegram_id}")
        logger.info(f"ID голосового файла: {voice_file_id}")
        logger.info(f"Длительность: {duration} секунд")
        logger.info(f"Распознанный текст длиной: {len(recognized_text)} символов")
        logger.info(f"Язык: {language}")
        logger.info(f"Время записи (переданное): {entry_datetime}")
        
        try:
            # Создаем запись в транзакции
            with transaction.atomic():
                diary_entry = DiaryEntry.objects.create(
                    user=user,
                    text=recognized_text,
                    language=language,
                    word_count=len(recognized_text.split()),
                    is_processed=False  # Пока не обработана
                )
                if entry_datetime:
                    diary_entry.created_at = entry_datetime
                    logger.info(f"Установлено пользовательское время created_at: {diary_entry.created_at}")

                diary_entry.save()
                logger.info(f"Голосовая запись создана, ID: {diary_entry.id}")
                
                # Подготавливаем данные для VoiceToText
                voice_to_text_data = {
                    'entry': diary_entry,
                    'original_duration': duration, # ИСПРАВЛЕНО: было original_file_id
                    'processed_text': recognized_text,
                    'processing_time': 2.5,  # Заглушка - время обработки в секундах
                    # === ИСПРАВЛЕНО: сохраняем ответы от обоих API ===
                    'speechkit_response': speechkit_api_response or {}, # Сохраняем ответ SpeechKit
                    'api_response': deepseek_api_response or {} # Сохраняем ответ DeepSeek (или другого сервиса постобработки)
                    # ==========================================
                }
                
                # Создаем запись о голосовом сообщении
                VoiceToText.objects.create(**voice_to_text_data)
                logger.info(f"Информация о голосовом сообщении сохранена (включая ответы API)")
                
                # Создаем анализ записи (заглушка)
                psycho_analysis = PsychoAnalysis.objects.create(
                    entry=diary_entry,
                    mood_score=8,  # Заглушка - оценка настроения 1-10
                    comment="Отличная дикция!",  # Заглушка - комментарий
                    recommendation="Продолжайте в том же духе",  # Заглушка - рекомендация
                    processing_time=2.5,  # Заглушка - время обработки в секундах
                    insights_extracted=5  # Заглушка - количество извлеченных инсайтов
                )
                logger.info(f"Анализ голосовой записи создан, ID: {psycho_analysis.id}")
                
                diary_entry.is_processed = True
                diary_entry.processing_error = ""
                diary_entry.save(update_fields=['is_processed', 'processing_error'])
                logger.info(f"Статус голосовой записи обновлен на 'обработана'")
            
            return diary_entry
            
        except Exception as e:
            logger.error(f"Ошибка при создании голосовой записи: {e}")
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
        Асинхронное создание голосовой записи
        
        Args:
            user: Пользователь
            voice_file_id: ID голосового файла в Telegram
            duration: Длительность голосового сообщения (сек)
            recognized_text: Распознанный текст
            language: Язык записи
            
        Returns:
            DiaryEntry: Созданная запись
        """
        logger.info(f"Асинхронное создание голосовой записи для пользователя {user.telegram_id}")
        logger.info(f"ID голосового файла: {voice_file_id}")
        logger.info(f"Длительность: {duration} секунд")
        logger.info(f"Распознанный текст длиной: {len(recognized_text)} символов")
        logger.info(f"Язык: {language}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            diary_entry = await self.create_voice_entry_sync(
                user, voice_file_id, duration, recognized_text, language, entry_datetime,
                speechkit_api_response, # <- Передать
                deepseek_api_response   # <- Передать
            )
            logger.info(f"Асинхронная голосовая запись создана, ID: {diary_entry.id}")
            
            return diary_entry
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании голосовой записи: {e}")
            raise
    
    @sync_to_async
    def update_entry_text_sync(self, entry_id: int, user: User, new_text: str) -> bool:
        """
        Синхронное обновление текста записи и соответствующего CombinedDiaryEntry.
        Аргументы см. в асинхронной обёртке.
        """
        logger.info(f"[Сервис] Обновление текста записи {entry_id} для пользователя {user.telegram_id}")
        try:
            with transaction.atomic():
                # 1. Получаем запись
                entry = DiaryEntry.objects.select_related('user').get(id=entry_id, user=user)
                old_text = entry.text
                entry.text = new_text
                entry.word_count = len(new_text.split())
                # Удаляем старый анализ, он больше не актуален
                if hasattr(entry, 'analysis'):
                    entry.analysis.delete()
                    logger.debug("[Сервис] Старый PsychoAnalysis удален.")
                
                entry.is_processed = False # Сбрасываем флаг обработки, так как текст изменился
                entry.processing_error = ""
                entry.save(update_fields=['text', 'word_count', 'is_processed', 'processing_error'])
                logger.info(f"[Сервис] Текст записи {entry_id} обновлен.")

                # 2. Работа с CombinedDiaryEntry
                target_date = entry.entry_date
                logger.info(f"[Сервис] Обновление CombinedDiaryEntry для даты {target_date}")

                try:
                    combined_entry = CombinedDiaryEntry.objects.get(user=user, date=target_date)
                    logger.debug("[Сервис] Найден существующий CombinedDiaryEntry.")

                    # --- ИСПРАВЛЕНИЕ: Обновляем text и entry_count НЕМЕДЛЕННО ---
                    # Получаем все записи за день
                    all_entries_for_day = DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at')
                    
                    # Формируем новый объединенный текст
                    # Используем тот же формат, что и в get_combined_entry_text_sync
                    texts = [e.text for e in all_entries_for_day]
                    new_combined_text = "\n\n---\n\n".join(texts) # Используем \n\n---\n\n как в модели DiaryEntry.combined_text
                    new_entry_count = all_entries_for_day.count()
                    
                    logger.debug(f"[Сервис] Новый объединенный текст длиной {len(new_combined_text)} символов. Новое количество записей: {new_entry_count}.")

                    # Обновляем поля CombinedDiaryEntry
                    combined_entry.text = new_combined_text
                    combined_entry.entry_count = new_entry_count
                    # combined_entry.daily_mood_scores - не обновляется, так как мы не пересчитываем анализы всех записей
                    # combined_entry.average_mood_score - тоже не обновляется
                    # Сбрасываем флаг анализа
                    combined_entry.reset_analysis_flag() # is_analyzed = False
                    # combined_entry.ai_state_data - не обновляется, так как анализ еще не проводился
                    
                    combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed'])
                    logger.info(f"[Сервис] CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                    
                except CombinedDiaryEntry.DoesNotExist:
                    logger.info(f"[Сервис] CombinedDiaryEntry для {target_date} не найден. Создание нового...")
                    # Если по какой-то причине CombinedDiaryEntry отсутствует, создаем его заново
                    # Это нестандартная ситуация, но обработаем её.
                    # Получаем все записи за день (должна быть хотя бы текущая)
                    all_entries_for_day = DiaryEntry.objects.filter(user=user, created_at__date=target_date).order_by('created_at')
                    if not all_entries_for_day.exists():
                        logger.error(f"[Сервис] Критическая ошибка: Запись {entry_id} существует, но записей за день {target_date} нет!")
                        # Это внутренняя ошибка, но продолжим
                    
                    texts = [e.text for e in all_entries_for_day]
                    new_combined_text = "\n\n---\n\n".join(texts)
                    new_entry_count = all_entries_for_day.count()
                    
                    combined_entry = CombinedDiaryEntry.objects.create(
                        user=user,
                        date=target_date,
                        text=new_combined_text,
                        entry_count=new_entry_count,
                        ai_state_data='', # Изначально пустое
                        is_analyzed=False,
                    )
                    logger.info(f"[Сервис] Новый CombinedDiaryEntry ID {combined_entry.id} создан при обновлении записи.")

                # 3. Не удаляем TherapyTask (как указано в спецификации)
                # 4. Старый анализ удален выше

            logger.info(f"[Сервис] Текст записи {entry_id} и CombinedDiaryEntry успешно обновлены.")
            return True
        except DiaryEntry.DoesNotExist:
            logger.warning(f"[Сервис] Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            return False
        except Exception as e:
            logger.error(f"[Сервис] Ошибка при обновлении текста записи {entry_id}: {e}", exc_info=True)
            # Обновляем запись об ошибке в самой DiaryEntry
            try:
                DiaryEntry.objects.filter(id=entry_id, user=user).update(is_processed=True, processing_error=str(e)[:255])
            except:
                pass # Игнорируем ошибки при обновлении поля ошибки
            return False

    async def update_entry_text(self, entry_id: int, user: User, new_text: str) -> bool:
        """
        Асинхронное обновление текста записи.

        Args:
            entry_id: ID записи.
            user: Пользователь.
            new_text: Новый текст записи.

        Returns:
            bool: True, если успешно, иначе False.
        """
        logger.info(f"Асинхронное обновление текста записи {entry_id} для пользователя {user.telegram_id}")
        try:
            success = await self.update_entry_text_sync(entry_id, user, new_text)
            logger.info(f"Асинхронное обновление текста записи {entry_id}: {'успешно' if success else 'неудачно'}")
            return success
        except Exception as e:
            logger.error(f"Ошибка в асинхронном обновлении текста записи {entry_id}: {e}")
            return False
    # ==========================================

    # === НОВЫЙ МЕТОД: Удаление записи с обновлением CombinedDiaryEntry ===
    @sync_to_async
    def delete_entry_and_update_combined_sync(self, entry_id: int, user: User) -> bool:
        """
        Синхронное удаление записи и обновление/удаление связанного CombinedDiaryEntry.
        Аргументы см. в асинхронной обёртке.
        """
        from diary.models import DiaryEntry, CombinedDiaryEntry, TherapyTask # Импортируем внутри
        try:
            with transaction.atomic():
                # 1. Получаем запись
                entry = DiaryEntry.objects.select_related('user').get(id=entry_id, user=user)
                entry_date = entry.entry_date
                logger.info(f"Удаление записи {entry_id} за {entry_date}")

                # 2. Удаляем связанные объекты
                # PsychoAnalysis
                if hasattr(entry, 'analysis'):
                    entry.analysis.delete()
                    logger.debug("Связанный PsychoAnalysis удален.")
                
                # KeyPoint
                entry.key_points.all().delete()
                logger.debug("Связанные KeyPoint удалены.")
                
                # VoiceToText
                if hasattr(entry, 'voicetotext'):
                    entry.voicetotext.delete()
                    logger.debug("Связанный VoiceToText удален.")
                
                # TaskCompletion и связанные
                # Предполагается, что TaskCompletion ссылается на DiaryEntry
                # from diary.models import TaskCompletion
                # TaskCompletion.objects.filter(entry=entry).delete() # Если есть такая связь
                # Или если TaskCompletion ссылается на запись по тексту:
                # TaskCompletion.objects.filter(completion_text=entry.text).delete()
                
                # 3. Удаляем связанные TherapyTask (как указано в спецификации)
                # Удаляем TherapyTask, где related_entry указывает на удаляемую запись
                TherapyTask.objects.filter(related_entry=entry).delete()
                logger.info("Связанные TherapyTask (related_entry) удалены.")

                # 4. Удаляем саму запись
                entry.delete()
                logger.info(f"Запись {entry_id} успешно удалена")

                # 5. Работа с CombinedDiaryEntry
                try:
                    combined_entry = CombinedDiaryEntry.objects.get(user=user, date=entry_date)
                    # Получаем оставшиеся записи за этот день
                    remaining_entries = DiaryEntry.objects.filter(user=user, created_at__date=entry_date).order_by('created_at')
                    
                    if remaining_entries.exists():
                        logger.info("Остались другие записи за этот день. Обновляем CombinedDiaryEntry.")
                        # --- ИСПРАВЛЕНИЕ: Обновляем text и entry_count ---
                        # Формируем новый объединенный текст
                        texts = [e.text for e in remaining_entries]
                        new_combined_text = "\n\n---\n\n".join(texts) # Используем тот же формат, что и в модели DiaryEntry.combined_text
                        new_entry_count = remaining_entries.count()
                        
                        # Обновляем поля CombinedDiaryEntry
                        combined_entry.text = new_combined_text
                        combined_entry.entry_count = new_entry_count
                        # combined_entry.daily_mood_scores - не обновляется, так как мы не пересчитываем анализы всех записей
                        # combined_entry.average_mood_score - тоже не обновляется
                        # Сбрасываем флаг анализа
                        combined_entry.reset_analysis_flag() # is_analyzed = False
                        # combined_entry.ai_state_data - не обновляется, так как анализ еще не проводился
                        
                        combined_entry.save(update_fields=['text', 'entry_count', 'is_analyzed'])
                        logger.info(f"CombinedDiaryEntry ID {combined_entry.id} обновлен (text, entry_count, is_analyzed).")
                        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                    else:
                        logger.info("Это была последняя запись за день. Удаляем CombinedDiaryEntry.")
                        combined_entry.delete()
                except CombinedDiaryEntry.DoesNotExist:
                    logger.info(f"CombinedDiaryEntry для {entry_date} не найден при удалении записи {entry_id}. Возможно, он уже был удален.")
                return True
                
        except DiaryEntry.DoesNotExist:
            logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при удалении записи {entry_id} и обновлении CombinedDiaryEntry: {e}")
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
        logger.info(f"Асинхронное удаление записи {entry_id} и обновление CombinedDiaryEntry для пользователя {user.telegram_id}")
        try:
            success = await self.delete_entry_and_update_combined_sync(entry_id, user)
            logger.info(f"Асинхронное удаление записи {entry_id} и обновление CombinedDiaryEntry: {'успешно' if success else 'неудачно'}")
            return success
        except Exception as e:
            logger.error(f"Ошибка в асинхронном удалении записи {entry_id} и обновлении CombinedDiaryEntry: {e}")
            return False

    @sync_to_async
    def get_entries_for_day_sync(self, user: User, target_date: date) -> List[DiaryEntry]:
        """
        Синхронное получение списка записей пользователя за конкретный день.

        Args:
            user: Пользователь.
            target_date: Целевая дата.

        Returns:
            List[DiaryEntry]: Список записей.
        """
        try:
            entries = list(
                DiaryEntry.objects.filter(
                    user=user,
                    created_at__date=target_date
                ).order_by('created_at')
            )
            logger.info(f"Найдено {len(entries)} записей за {target_date} для пользователя {user.telegram_id}")
            return entries
        except Exception as e:
            logger.error(f"Ошибка при получении записей за {target_date}: {e}")
            return []

    async def get_entries_for_day(self, user: User, target_date: date) -> List[DiaryEntry]:
        """
        Асинхронное получение списка записей пользователя за конкретный день.

        Args:
            user: Пользователь.
            target_date: Целевая дата.

        Returns:
            List[DiaryEntry]: Список записей.
        """
        logger.info(f"Асинхронное получение записей за {target_date} для пользователя {user.telegram_id}")
        try:
            entries = await self.get_entries_for_day_sync(user, target_date)
            logger.info(f"Асинхронно получено {len(entries)} записей за {target_date}")
            return entries
        except Exception as e:
            logger.error(f"Ошибка в асинхронном получении записей за {target_date}: {e}")
            return []

    @sync_to_async
    def get_user_entries_for_date_sync(
        self, 
        user: User, 
        target_date: date
    ) -> List[DiaryEntry]:
        """
        Синхронное получение записей пользователя за конкретную дату (обёртка для async)
        
        Args:
            user: Пользователь
            target_date: Целевая дата
            
        Returns:
            List[DiaryEntry]: Список записей за дату
        """
        logger.info(f"Получение записей пользователя {user.telegram_id} за {target_date}")
        
        try:
            entries = list(
                DiaryEntry.objects.filter(
                    user=user,
                    created_at__date=target_date
                ).order_by('created_at')
            )
            
            logger.info(f"Найдено {len(entries)} записей за {target_date}")
            return entries
            
        except Exception as e:
            logger.error(f"Ошибка при получении записей за дату: {e}")
            return []
    
    async def get_user_entries_for_date(
        self, 
        user: User, 
        target_date: date
    ) -> List[DiaryEntry]:
        """
        Асинхронное получение записей пользователя за конкретную дату
        
        Args:
            user: Пользователь
            target_date: Целевая дата
            
        Returns:
            List[DiaryEntry]: Список записей за дату
        """
        logger.info(f"Асинхронное получение записей пользователя {user.telegram_id} за {target_date}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            entries = await self.get_user_entries_for_date_sync(user, target_date)
            logger.info(f"Асинхронно получено {len(entries)} записей за {target_date}")
            
            return entries
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении записей за дату: {e}")
            return []
    
    @sync_to_async
    def get_combined_entry_text_sync(
        self, 
        user: User, 
        target_date: date
    ) -> str:
        """
        Синхронное получение объединенного текста всех записей за день (обёртка для async)
        
        Args:
            user: Пользователь
            target_date: Целевая дата
            
        Returns:
            str: Объединенный текст всех записей дня
        """
        logger.info(f"Получение объединенного текста записей пользователя {user.telegram_id} за {target_date}")
        
        try:
            # Получаем записи пользователя за день
            entries = list(
                DiaryEntry.objects.filter(
                    user=user,
                    created_at__date=target_date
                ).order_by('created_at')
            )
            
            if not entries:
                logger.info("Нет записей за указанный день")
                return ""
            
            # Объединяем тексты всех записей
            texts = [entry.text for entry in entries]
            combined_text = "\n\n---\n\n".join(texts)  # Разделяем записями
            
            logger.info(f"Объединенный текст создан, длина: {len(combined_text)} символов")
            return combined_text
            
        except Exception as e:
            logger.error(f"Ошибка при создании объединенного текста: {e}")
            return ""
    
    async def get_combined_entry_text(
        self, 
        user: User, 
        target_date: date
    ) -> str:
        """
        Асинхронное получение объединенного текста всех записей за день
        
        Args:
            user: Пользователь
            target_date: Целевая дата
            
        Returns:
            str: Объединенный текст всех записей дня
        """
        logger.info(f"Асинхронное получение объединенного текста записей пользователя {user.telegram_id} за {target_date}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            combined_text = await self.get_combined_entry_text_sync(user, target_date)
            logger.info(f"Асинхронно получен объединенный текст длиной {len(combined_text)} символов")
            
            return combined_text
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении объединенного текста: {e}")
            return ""
    
    @sync_to_async
    def delete_entry_sync(self, entry_id: int, user: User) -> bool:
        """
        Синхронное удаление записи (обёртка для async)
        
        Args:
            entry_id: ID записи
            user: Пользователь
            
        Returns:
            bool: Успешность удаления
        """
        logger.info(f"Удаление записи {entry_id} пользователя {user.telegram_id}")
        
        try:
            # Получаем запись с проверкой владельца
            try:
                entry = DiaryEntry.objects.get(
                    id=entry_id,
                    user=user
                )
                logger.info(f"Запись найдена: {entry.text[:50]}...")
            except DiaryEntry.DoesNotExist:
                logger.warning(f"Запись {entry_id} не найдена или не принадлежит пользователю {user.telegram_id}")
                return False
            
            # Удаляем запись синхронно
            with transaction.atomic():
                # Удаляем связанные данные
                if hasattr(entry, 'analysis'):
                    try:
                        analysis = PsychoAnalysis.objects.get(entry=entry)
                        analysis.delete()
                    except PsychoAnalysis.DoesNotExist:
                        pass
                
                if hasattr(entry, 'key_points'):
                    entry.key_points.all().delete()
                
                if hasattr(entry, 'voice_to_text'):
                    try:
                        voice_to_text = entry.voice_to_text
                        voice_to_text.delete()
                    except Exception:
                        pass
                
                # Удаляем саму запись
                entry.delete()
            
            logger.info(f"Запись {entry_id} успешно удалена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при удалении записи {entry_id}: {e}")
            return False
    
    async def delete_entry(self, entry_id: int, user: User) -> bool:
        """
        Асинхронное удаление записи
        
        Args:
            entry_id: ID записи
            user: Пользователь
            
        Returns:
            bool: Успешность удаления
        """
        logger.info(f"Асинхронное удаление записи {entry_id} пользователя {user.telegram_id}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            success = await self.delete_entry_sync(entry_id, user)
            logger.info(f"Асинхронное удаление записи {entry_id}: {'успешно' if success else 'неудачно'}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном удалении записи {entry_id}: {e}")
            return False
    
    @sync_to_async
    def get_days_with_entries_sync(
        self, 
        user: User, 
        year: int, 
        month: int
    ) -> set:
        """
        Синхронное получение дней месяца, в которые есть записи (обёртка для async)
        
        Args:
            user: Пользователь
            year: Год
            month: Месяц
            
        Returns:
            set: Множество дней с записями
        """
        logger.info(f"Получение дней с записями пользователя {user.telegram_id} за {month}.{year}")
        
        try:
            days_with_entries = set()
            
            # Получаем записи пользователя за месяц
            entries = DiaryEntry.objects.filter(
                user=user,
                created_at__year=year,
                created_at__month=month
            ).distinct()
            
            # Извлекаем дни
            for entry in entries:
                day = entry.created_at.day
                days_with_entries.add(day)
            
            logger.info(f"Найдено {len(days_with_entries)} дней с записями в {month}.{year} (sync)")
            return days_with_entries
            
        except Exception as e:
            logger.error(f"Ошибка при синхронном получении дней с записями: {e}")
            return set()
    
    async def get_days_with_entries(
        self, 
        user: User, 
        year: int, 
        month: int
    ) -> set:
        """
        Асинхронное получение дней месяца, в которые есть записи
        
        Args:
            user: Пользователь
            year: Год
            month: Месяц
            
        Returns:
            set: Множество дней с записями
        """
        logger.info(f"Асинхронное получение дней с записями пользователя {user.telegram_id} за {month}.{year}")
        
        try:
            # Используем синхронную обёртку через sync_to_async
            days_with_entries = await self.get_days_with_entries_sync(user, year, month)
            logger.info(f"Асинхронно получено {len(days_with_entries)} дней с записями")
            
            return days_with_entries
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном получении дней с записями: {e}")
            return set()

    @sync_to_async
    def create_initial_analysis_sync(
        self,
        entry: DiaryEntry,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str = "Анализ записан",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Синхронное создание нового объекта PsychoAnalysis для записи.

        Args:
            entry: Запись дневника (DiaryEntry).
            mood_score: Оценка настроения (1-10).
            comment: Комментарий от ИИ.
            recommendation: Рекомендация от ИИ.
            analysis_text: Подробный текст анализа.
            api_response: Сырой ответ API для сохранения (опционально).

        Returns:
            PsychoAnalysis: Созданный объект анализа.
        """
        logger.info(f"Создание начального анализа для записи {entry.id} пользователя {entry.user.telegram_id}")
        try:
            with transaction.atomic():
                # Удаляем существующий анализ, если он вдруг есть (например, после редактирования)
                # Это гарантирует, что у записи всегда будет только один актуальный анализ.
                try:
                    old_analysis = PsychoAnalysis.objects.get(entry=entry)
                    logger.info(f"Удаление старого анализа ID {old_analysis.id} перед созданием нового")
                    old_analysis.delete()
                except PsychoAnalysis.DoesNotExist:
                    pass # Ничего не делаем, если старого анализа нет

                # Создаем новый анализ
                analysis_data = {
                    'entry': entry,
                    'mood_score': mood_score,
                    'comment': comment,
                    'recommendation': recommendation,
                    'analysis_text': analysis_text,
                    'processing_time': 0.0, # Можно уточнить, если есть метрики времени
                    'insights_extracted': 0, # Будет обновлено позже сервисом анализа
                    #'language': entry.language, # Берем язык из записи
                    'api_response': api_response or {}
                }
                new_analysis = PsychoAnalysis.objects.create(**analysis_data)
                logger.info(f"Новый анализ создан, ID: {new_analysis.id}")

                # Обновляем статус обработки записи
                entry.is_processed = True
                entry.processing_error = ""
                entry.save(update_fields=['is_processed', 'processing_error'])
                logger.info(f"Статус записи {entry.id} обновлен на 'обработана'")

            return new_analysis
        except Exception as e:
            logger.error(f"Ошибка при создании начального анализа для записи {entry.id}: {e}")
            # В случае ошибки создания, помечаем запись как необработанную с ошибкой
            entry.is_processed = False
            entry.processing_error = str(e)[:255] # Ограничиваем длину
            entry.save(update_fields=['is_processed', 'processing_error'])
            raise # Пробрасываем ошибку

    async def create_initial_analysis(
        self,
        entry: DiaryEntry,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str = "Анализ записан",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Асинхронное создание нового объекта PsychoAnalysis для записи.

        Args:
            entry: Запись дневника (DiaryEntry).
            mood_score: Оценка настроения (1-10).
            comment: Комментарий от ИИ.
            recommendation: Рекомендация от ИИ.
            analysis_text: Подробный текст анализа.
            api_response: Сырой ответ API для сохранения (опционально).

        Returns:
            PsychoAnalysis: Созданный объект анализа.
        """
        logger.info(f"Асинхронное создание начального анализа для записи {entry.id}")
        try:
            # Используем синхронную обёртку через sync_to_async
            analysis = await self.create_initial_analysis_sync(
                entry, mood_score, comment, recommendation, analysis_text, api_response
            )
            logger.info(f"Асинхронный анализ записи {entry.id} создан, ID: {analysis.id}")
            return analysis
        except Exception as e:
            logger.error(f"Ошибка при асинхронном создании начального анализа для записи {entry.id}: {e}")
            raise
    # =========================================================

    # === Обновление существующего анализа ===
    @sync_to_async
    def update_existing_analysis_sync(
        self,
        analysis_obj: PsychoAnalysis,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str = "Анализ обновлен",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Синхронное обновление существующего объекта PsychoAnalysis.

        Args:
            analysis_obj: Существующий объект PsychoAnalysis.
            mood_score: Новая оценка настроения (1-10).
            comment: Новый комментарий от ИИ.
            recommendation: Новая рекомендация от ИИ.
            analysis_text: Новый подробный текст анализа.
            api_response: Новый сырой ответ API для сохранения (опционально).

        Returns:
            PsychoAnalysis: Обновленный объект анализа.
        """
        logger.info(f"Обновление существующего анализа ID {analysis_obj.id} для записи {analysis_obj.entry.id}")
        try:
            with transaction.atomic():
                analysis_obj.mood_score = mood_score
                analysis_obj.comment = comment
                analysis_obj.recommendation = recommendation
                analysis_obj.analysis_text = analysis_text
                # processing_time и insights_extracted обновляются отдельно сервисом анализа при необходимости
                if api_response is not None:
                    analysis_obj.api_response = api_response

                # Сохраняем только измененные поля
                update_fields = ['mood_score', 'comment', 'recommendation', 'analysis_text']
                if api_response is not None:
                    update_fields.append('api_response')
                analysis_obj.save(update_fields=update_fields)
                logger.info(f"Анализ ID {analysis_obj.id} успешно обновлен")

                # Обновляем статус обработки записи
                entry = analysis_obj.entry
                entry.is_processed = True
                entry.processing_error = ""
                entry.save(update_fields=['is_processed', 'processing_error'])
                logger.info(f"Статус записи {entry.id} обновлен на 'обработана'")

            return analysis_obj
        except Exception as e:
            logger.error(f"Ошибка при обновлении анализа ID {analysis_obj.id}: {e}")
            # В случае ошибки обновления, можно пометить запись
            entry = analysis_obj.entry
            entry.is_processed = False
            entry.processing_error = f"Ошибка обновления анализа: {str(e)[:200]}"
            entry.save(update_fields=['is_processed', 'processing_error'])
            raise # Пробрасываем ошибку

    async def update_existing_analysis(
        self,
        analysis_obj: PsychoAnalysis,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str = "Анализ обновлен",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Асинхронное обновление существующего объекта PsychoAnalysis.

        Args:
            analysis_obj: Существующий объект PsychoAnalysis.
            mood_score: Новая оценка настроения (1-10).
            comment: Новый комментарий от ИИ.
            recommendation: Новая рекомендация от ИИ.
            analysis_text: Новый подробный текст анализа.
            api_response: Новый сырой ответ API для сохранения (опционально).

        Returns:
            PsychoAnalysis: Обновленный объект анализа.
        """
        logger.info(f"Асинхронное обновление анализа ID {analysis_obj.id}")
        try:
            # Используем синхронную обёртку через sync_to_async
            analysis = await self.update_existing_analysis_sync(
                analysis_obj, mood_score, comment, recommendation, analysis_text, api_response
            )
            logger.info(f"Асинхронный анализ ID {analysis_obj.id} обновлен")
            return analysis
        except Exception as e:
            logger.error(f"Ошибка при асинхронном обновлении анализа ID {analysis_obj.id}: {e}")
            raise        

    # === Делегирование в DailyStateService ===

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
        logger.info(f"DiaryService: Получение CombinedDiaryEntry для пользователя {user.telegram_id} за {target_date}")
        # Делегируем в глобальную функцию daily_state_service
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
        logger.info(f"DiaryService: Получение или создание CombinedDiaryEntry для пользователя {user.telegram_id} за {target_date}")
        # Делегируем в глобальную функцию daily_state_service
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
        logger.info(f"DiaryService: Обновление CombinedDiaryEntry ID {combined_entry.id} с новым состоянием ИИ")
        # Делегируем в глобальную функцию daily_state_service
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
        logger.info(f"DiaryService: Обновление текста и счетчика в CombinedDiaryEntry ID {combined_entry.id}")
        # Делегируем в глобальную функцию daily_state_service
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
        logger.info(f"DiaryService: Создание CombinedDiaryEntry из DiaryEntry ID {diary_entry.id}")
        # Делегируем в глобальную функцию daily_state_service
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
                    # 1. Найти все записи за день
                    entries = DiaryEntry.objects.filter(user=user, created_at__date=target_date)
                    entry_ids = list(entries.values_list('id', flat=True))
                    logger.info(f"[Сервис] Найдено {len(entry_ids)} записей для удаления.")

                    if not entry_ids:
                        # Удалять больше нечего
                        # Убедимся, что CombinedDiaryEntry тоже удален, на всякий случай
                        CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                        return True

                    # 2. Удалить связанные объекты для всех записей
                    # PsychoAnalysis
                    PsychoAnalysis.objects.filter(entry_id__in=entry_ids).delete()
                    logger.info("[Сервис] Удалены PsychoAnalysis.")

                    # KeyPoint
                    KeyPoint.objects.filter(entry_id__in=entry_ids).delete()
                    logger.info("[Сервис] Удалены KeyPoint.")

                    # VoiceToText
                    VoiceToText.objects.filter(entry_id__in=entry_ids).delete()
                    logger.info("[Сервис] Удалены VoiceToText.")

                    # TaskCompletion и TaskAnalysis, TaskCompletionAnalysis
                    # Сначала найдем TaskCompletion, связанные с DiaryEntry
                    task_completions = TaskCompletion.objects.filter(completion_text__in=[entry.text for entry in entries]) # Не лучший способ, но если Completion.text == Entry.text
                    # Лучше: если TaskCompletion ссылается на DiaryEntry каким-то образом (например, через поле), то:
                    # task_completions = TaskCompletion.objects.filter(related_entry_id__in=entry_ids) # Если такое поле есть
                    # Пока предположим, что Completion напрямую не связаны с Entry через FK. Пропустим их удаление через Entry.
                    # Или они удаляются каскадно при удалении Task?
                    # TaskCompletionAnalysis
                    # task_completion_analyses = TaskCompletionAnalysis.objects.filter(completion__task__related_entry_id__in=entry_ids)
                    # task_completion_analyses.delete()
                    # logger.info("[Сервис] Удалены TaskCompletionAnalysis.")
                    
                    # 3. Удалить TherapyTask, связанные с DiaryEntry (related_entry)
                    # Это ключевой момент из спецификации.
                    TherapyTask.objects.filter(related_entry_id__in=entry_ids).delete()
                    logger.info("[Сервис] Удалены TherapyTask, связанные с записями дня.")

                    # 4. Удалить сами DiaryEntry
                    entries.delete()
                    logger.info("[Сервис] Удалены DiaryEntry.")

                    # 5. Удалить CombinedDiaryEntry за этот день
                    CombinedDiaryEntry.objects.filter(user=user, date=target_date).delete()
                    logger.info("[Сервис] Удален CombinedDiaryEntry за день.")

                return True

            result = await _delete_sync()
            logger.info(f"[Сервис] Удаление записей за {target_date} завершено успешно: {result}")
            return result

        except Exception as e:
            logger.error(f"[Сервис] Ошибка при удалении записей за {target_date}: {e}")
            return False
    
# Глобальный экземпляр сервиса дневника
diary_service = DiaryService()

# Удобные функции для использования
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

async def get_combined_entry_text(user: User, target_date: date) -> str:
    """Удобная функция для получения объединенного текста"""
    return await diary_service.get_combined_entry_text(user, target_date)

async def delete_entry(entry_id: int, user: User) -> bool:
    """Удобная функция для удаления записи"""
    return await diary_service.delete_entry(entry_id, user)

async def get_days_with_entries(user: User, year: int, month: int) -> set:
    """Удобная функция для получения дней с записями"""
    return await diary_service.get_days_with_entries(user, year, month)

async def create_initial_analysis(
    entry: DiaryEntry,
    mood_score: int,
    comment: str,
    recommendation: str,
    analysis_text: str = "Анализ записан",
    api_response: Optional[Dict[str, Any]] = None
) -> PsychoAnalysis:
    """
    Удобная функция для асинхронного создания начального анализа записи.
    """
    return await diary_service.create_initial_analysis(
        entry, mood_score, comment, recommendation, analysis_text, api_response
    )

async def update_existing_analysis(
    analysis_obj: PsychoAnalysis,
    mood_score: int,
    comment: str,
    recommendation: str,
    analysis_text: str = "Анализ обновлен",
    api_response: Optional[Dict[str, Any]] = None
) -> PsychoAnalysis:
    """
    Удобная функция для асинхронного обновления существующего анализа.
    """
    return await diary_service.update_existing_analysis(
        analysis_obj, mood_score, comment, recommendation, analysis_text, api_response
    )

async def delete_all_entries_for_day(user: User, target_date: date) -> bool:
    """Удобная асинхронная функция для удаления всех записей за день."""
    return await diary_service.delete_all_entries_for_day(user, target_date)
