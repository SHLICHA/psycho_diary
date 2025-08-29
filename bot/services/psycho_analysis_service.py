"""
Сервис для работы с результатами психоанализа (PsychoAnalysis).
"""

import logging
from typing import Optional, Dict, Any
from asgiref.sync import sync_to_async
from diary.models import DiaryEntry, PsychoAnalysis

logger = logging.getLogger(__name__)

class PsychoAnalysisService:
    """Сервис для создания и обновления объектов PsychoAnalysis."""

    async def create_or_update_analysis(
        self,
        entry: DiaryEntry,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str = "Анализ записан",
        api_response: Optional[Dict[str, Any]] = None
    ) -> PsychoAnalysis:
        """
        Асинхронно создает новый объект PsychoAnalysis для записи или обновляет существующий.
        Вся логика выполняется в одной транзакции для обеспечения согласованности данных.
        """
        try:
            @sync_to_async
            def _create_or_update_analysis_sync():
                from django.db import transaction
                with transaction.atomic():
                    try:
                        analysis_obj = PsychoAnalysis.objects.select_for_update().get(entry=entry)
                        logger.info(f"Найден и заблокирован существующий анализ ID {analysis_obj.id} для записи {entry.id}. Будет обновлен.")
                        is_update = True
                    except PsychoAnalysis.DoesNotExist:
                        analysis_obj = None
                        logger.info(f"Анализ для записи {entry.id} не найден. Будет создан новый.")
                        is_update = False
                    if is_update:
                        analysis_obj.mood_score = mood_score
                        analysis_obj.comment = comment
                        analysis_obj.recommendation = recommendation
                        analysis_obj.analysis_text = analysis_text
                        if api_response is not None:
                            analysis_obj.api_response = api_response
                        update_fields = ['mood_score', 'comment', 'recommendation', 'analysis_text']
                        if api_response is not None:
                            update_fields.append('api_response')   
                        analysis_obj.save(update_fields=update_fields)
                        entry.is_processed = True
                        entry.processing_error = ""
                        entry.save(update_fields=['is_processed', 'processing_error'])
                        
                        logger.info(f"Обновлен анализ ID {analysis_obj.id} для записи {entry.id}.")
                        return analysis_obj
                    else:
                        analysis_data = {
                            'entry': entry,
                            'mood_score': mood_score,
                            'comment': comment,
                            'recommendation': recommendation,
                            'analysis_text': analysis_text,
                            'processing_time': 0.0, # TODO: Получать реальное время обработки
                            'insights_extracted': 0, # TODO: Получать реальное количество
                            'api_response': api_response or {}
                        }
                        new_analysis = PsychoAnalysis.objects.create(**analysis_data)
                        entry.is_processed = True
                        entry.processing_error = ""
                        entry.save(update_fields=['is_processed', 'processing_error'])
                        return new_analysis
            return await _create_or_update_analysis_sync()
        except Exception as e:
            logger.error(f"Ошибка при создании/обновлении анализа для записи {entry.id}: {e}", exc_info=True)
            try:
                @sync_to_async
                def _mark_entry_error():
                    entry.is_processed = False
                    entry.processing_error = str(e)[:255]
                    entry.save(update_fields=['is_processed', 'processing_error'])
                await _mark_entry_error()
            except Exception as entry_error:
                logger.error(f"Не удалось обновить статус ошибки записи {entry.id}: {entry_error}")
            raise

    async def _create_analysis_object(
        self,
        entry: DiaryEntry,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str,
        api_response: Optional[Dict[str, Any]]
    ) -> PsychoAnalysis:
        """Создает новый объект PsychoAnalysis."""
        @sync_to_async
        def _create_analysis_sync():
            from django.db import transaction
            with transaction.atomic():
                analysis_data = {
                    'entry': entry,
                    'mood_score': mood_score,
                    'comment': comment,
                    'recommendation': recommendation,
                    'analysis_text': analysis_text,
                    'processing_time': 0.0, # TODO: Получать реальное время обработки
                    'insights_extracted': 0, # TODO: Получать реальное количество
                    'api_response': api_response or {}
                }
                new_analysis = PsychoAnalysis.objects.create(**analysis_data)
                entry.is_processed = True
                entry.processing_error = ""
                entry.save(update_fields=['is_processed', 'processing_error'])
                
                logger.info(f"Создан новый анализ ID {new_analysis.id} для записи {entry.id}.")
                return new_analysis
        
        return await _create_analysis_sync()

    async def _update_analysis_object(
        self,
        analysis_obj: PsychoAnalysis,
        mood_score: int,
        comment: str,
        recommendation: str,
        analysis_text: str,
        api_response: Optional[Dict[str, Any]]
    ) -> PsychoAnalysis:
        """Обновляет существующий объект PsychoAnalysis."""
        @sync_to_async
        def _update_analysis_sync():
            from django.db import transaction
            with transaction.atomic():
                analysis_obj.mood_score = mood_score
                analysis_obj.comment = comment
                analysis_obj.recommendation = recommendation
                analysis_obj.analysis_text = analysis_text
                if api_response is not None:
                    analysis_obj.api_response = api_response
                
                update_fields = ['mood_score', 'comment', 'recommendation', 'analysis_text']
                if api_response is not None:
                    update_fields.append('api_response')
                analysis_obj.save(update_fields=update_fields)
                entry = analysis_obj.entry
                entry.is_processed = True
                entry.processing_error = ""
                entry.save(update_fields=['is_processed', 'processing_error'])
                
                logger.info(f"Обновлен анализ ID {analysis_obj.id} для записи {entry.id}.")
                return analysis_obj
        return await _update_analysis_sync()

# Глобальный экземпляр сервиса
psycho_analysis_service = PsychoAnalysisService()

# Удобные функции (опционально, для обратной совместимости или краткости)
async def create_or_update_analysis(
    entry: DiaryEntry,
    mood_score: int,
    comment: str,
    recommendation: str,
    analysis_text: str = "Анализ записан",
    api_response: Optional[Dict[str, Any]] = None
) -> PsychoAnalysis:
    """
    Удобная асинхронная функция для создания или обновления анализа записи.
    """
    return await psycho_analysis_service.create_or_update_analysis(
        entry, mood_score, comment, recommendation, analysis_text, api_response
    )
