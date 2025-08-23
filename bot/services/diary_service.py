"""
Сервис для работы с записями дневника
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from django.db import transaction
from django.db.models import Q
from diary.models import DiaryEntry, KeyPoint, PsychoAnalysis, VoiceToText
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
    def update_entry_analysis_sync(
        self, 
        entry: DiaryEntry,
        mood_score: int, 
        comment: str, 
        recommendation: str,
        analysis_text: str = "Анализ записан",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Синхронное обновление анализа записи (обёртка для async)
        """
        logger.info(f"Обновление анализа записи {entry.id} пользователя {entry.user.telegram_id}")
        
        try:
            with transaction.atomic():
                try:
                    # --- СИНХРОННЫЙ ORM вызов ---
                    analysis = PsychoAnalysis.objects.select_for_update().get(entry=entry)
                    # ----------------------------
                    logger.info(f"Существующий анализ найден, ID: {analysis.id}")
                    
                    analysis.mood_score = mood_score
                    analysis.comment = comment
                    analysis.recommendation = recommendation
                    analysis.analysis_text = analysis_text
                    # --- НЕТ language и processing_error ---
                    if api_response is not None:
                        analysis.api_response = api_response
                        
                    # --- СИНХРОННЫЙ ORM вызов ---
                    analysis.save(update_fields=[
                        'mood_score', 'comment', 'recommendation', 
                        'analysis_text', 'api_response'
                    ])
                    # ----------------------------
                    logger.info(f"Существующий анализ обновлен, ID: {analysis.id}")
                    
                except PsychoAnalysis.DoesNotExist:
                    logger.info("Анализ не найден, создаем новый")
                    
                    # --- СИНХРОННЫЙ ORM вызов ---
                    analysis = PsychoAnalysis.objects.create(
                        entry=entry,
                        mood_score=mood_score,
                        comment=comment,
                        recommendation=recommendation,
                        analysis_text=analysis_text,
                        # --- НЕТ language и processing_error ---
                        api_response=api_response or {}
                    )
                    # ----------------------------
                    logger.info(f"Новый анализ создан, ID: {analysis.id}")
                
                entry.is_processed = True
                entry.processing_error = ""
                # --- СИНХРОННЫЙ ORM вызов ---
                entry.save(update_fields=['is_processed', 'processing_error'])
                # ----------------------------
                logger.info(f"Статус записи обновлен на 'обработана'")
            
            logger.info(f"Анализ записи {entry.id} успешно обновлен")
            return analysis
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении анализа записи {entry.id}: {e}")
            # Создание анализа с ошибкой обработки (тоже синхронно)
            # ... (реализуй по аналогии) ...
            raise

    # --- ИСПРАВЛЕННЫЙ update_entry_analysis ---
    # Обрати внимание: async def
    async def update_entry_analysis(
        self, 
        entry: DiaryEntry,
        mood_score: int, 
        comment: str, 
        recommendation: str,
        analysis_text: str = "Анализ записан",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Асинхронное обновление анализа записи
        """
        logger.info(f"Асинхронное обновление анализа записи {entry.id} пользователя {entry.user.telegram_id}")
        
        try:
            # --- ПРАВИЛЬНО: sync_to_async вокруг СИНХРОННОГО метода ---
            analysis = await sync_to_async(self.update_entry_analysis_sync)(
                entry, mood_score, comment, recommendation, analysis_text, api_response
            )
            # ---------------------------------------------------------
            logger.info(f"Асинхронный анализ записи {entry.id} обновлен, ID: {analysis.id}")
            return analysis
            
        except Exception as e:
            logger.error(f"Ошибка при асинхронном обновлении анализа записи {entry.id}: {e}")
            raise

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

async def update_entry_analysis(
    entry: DiaryEntry,
    mood_score: int, 
    comment: str, 
    recommendation: str,
    analysis_text: str = "Анализ записан",
    api_response: Optional[Dict[str, Any]] = None
) -> PsychoAnalysis:
    """
    Удобная функция для асинхронного обновления анализа записи
    """
    # --- ПРАВИЛЬНО: await асинхронного метода diary_service ---
    return await diary_service.update_entry_analysis(
        entry, mood_score, comment, recommendation, analysis_text, api_response
    )
