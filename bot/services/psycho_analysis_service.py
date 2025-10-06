"""
Сервис для работы с результатами психоанализа (PsychoAnalysis).
"""

import logging
from typing import Optional, Dict, Any
from asgiref.sync import sync_to_async
from django.db import transaction

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
        api_response: Optional[Dict[str, Any]] = None,
        processing_time: float = None
    ) -> PsychoAnalysis:
        """
        Асинхронно создает новый объект PsychoAnalysis для записи или обновляет существующий.
        Вся логика выполняется в одной транзакции для обеспечения согласованности данных.
        """
        logger.debug(f"📊 Создание/обновление анализа для записи {entry.id}, время: {processing_time}")
        try:
            @sync_to_async
            def _create_or_update_analysis_sync():
                with transaction.atomic():
                    try:
                        analysis_obj = PsychoAnalysis.objects.select_for_update().get(entry=entry)
                        is_update = True
                    except PsychoAnalysis.DoesNotExist:
                        analysis_obj = None
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
                        return analysis_obj
                    else:
                        formatted_processing_time = round(processing_time, 3) if processing_time is not None else 0.0
                        analysis_data = {
                            'entry': entry,
                            'mood_score': mood_score,
                            'comment': comment,
                            'recommendation': recommendation,
                            'analysis_text': analysis_text,
                            'processing_time': formatted_processing_time,
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
    # TODO
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
                return analysis_obj
        return await _update_analysis_sync()

psycho_analysis_service = PsychoAnalysisService()

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
