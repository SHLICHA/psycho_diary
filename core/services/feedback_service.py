# /core/services/feedback_service.py
"""
Сервис для работы с обратной связью.
Универсальный сервис: работает и для бота, и для API.

Отвечается за:
- Создание обращений в поддержку
- Получение необработанных обращений с пагинацией
- Ответы администратора на обращения
- Форматирование обращений для отображения
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.conf import settings

from users.models import User, Feedback
from core.services.admin_service import admin_service

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@dataclass
class FeedbackDisplayData:
    """Данные для отображения одного обращения."""
    feedback_id: int
    username: str
    created_at: str
    is_voice: bool
    is_photo: bool
    message_preview: str
    full_message: str
    photo_file_id: Optional[str]
    status: str


class FeedbackService:
    """Сервис для работы с обратной связью."""

    def is_developer(self, telegram_id: int) -> bool:
        """
        Проверяет, является ли пользователь разработчиком.
        Делегирует в единый метод admin_service.

        Args:
            telegram_id: Telegram ID пользователя.

        Returns:
            bool: True если разработчик.
        """
        return admin_service.is_developer(telegram_id)

    async def create_feedback(
        self,
        user: User,
        message_text: str,
        voice_data: Optional[bytes] = None,
        photo_data: Optional[bytes] = None,
        photo_file_id: Optional[str] = None,
    ) -> Feedback:
        """
        Создаёт обращение в поддержку и сохраняет в БД.

        Args:
            user: Пользователь.
            message_text: Текст сообщения.
            voice_data: Байты голосового сообщения (если есть).
            photo_data: Байты фото (если есть).
            photo_file_id: file_id фото в Telegram (если есть).

        Returns:
            Feedback: Созданный объект обращения.
        """
        is_voice = voice_data is not None
        is_photo = photo_data is not None or photo_file_id is not None

        feedback_message = message_text or (
            "Голосовое сообщение" if is_voice
            else "Фото" if is_photo
            else "Сообщение"
        )

        feedback = await sync_to_async(Feedback.objects.create)(
            user=user,
            message=feedback_message,
            is_voice=is_voice,
            is_photo=is_photo,
            photo_file_id=photo_file_id if photo_file_id else None,
            status='new',
        )
        logger.info(f"Feedback #{feedback.id} created by user {user.telegram_id}")
        return feedback

    async def get_unprocessed_feedbacks(self, limit: int = 50) -> List[Feedback]:
        """
        Получает необработанные обращения.

        Args:
            limit: Максимальное количество.

        Returns:
            List[Feedback]: Список обращений.
        """
        return await Feedback.aget_unprocessed(limit=limit)

    async def get_feedback_by_id(self, feedback_id: int) -> Optional[Feedback]:
        """
        Получает обращение по ID.

        Args:
            feedback_id: ID обращения.

        Returns:
            Optional[Feedback]: Обращение или None.
        """
        try:
            return await Feedback.aget_by_id(feedback_id)
        except Feedback.DoesNotExist:
            return None

    async def get_feedbacks_with_pagination(
        self, page: int = 1, page_size: int = 1
    ) -> Dict[str, Any]:
        """
        Получает обращения с пагинацией.

        Args:
            page: Номер страницы (1-based).
            page_size: Размер страницы.

        Returns:
            Dict[str, Any]:
                - feedbacks: Список обращений
                - total: Общее количество
                - page: Текущая страница
                - page_size: Размер страницы
                - has_next: Есть ли следующая
                - has_prev: Есть ли предыдущущая
        """
        all_feedback = await self.get_unprocessed_feedbacks(limit=200)
        total = len(all_feedback)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_feedback[start:end]

        return {
            'feedbacks': page_items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_next': end < total,
            'has_prev': page > 1,
        }

    async def format_feedback_for_display(
        self, feedback: Feedback, include_full_message: bool = False
    ) -> FeedbackDisplayData:
        """
        Форматирует обращение для отображения.

        Args:
            feedback: Объект обращения.
            include_full_message: Включать полное сообщение или превью.

        Returns:
            FeedbackDisplayData: Структурированные данные для отображения.
        """
        @sync_to_async
        def _get_details():
            username = feedback.user.username or f"user_{feedback.user.telegram_id}"
            created_at = feedback.created_at.strftime('%d.%m.%Y %H:%M')
            return username, created_at

        username, created_at = await _get_details()

        if include_full_message:
            message_preview = feedback.message
            full_message = feedback.message
        else:
            message_preview = (
                feedback.message[:200] + ('...' if len(feedback.message) > 200 else '')
            )
            full_message = feedback.message

        return FeedbackDisplayData(
            feedback_id=feedback.id,
            username=username,
            created_at=created_at,
            is_voice=feedback.is_voice,
            is_photo=feedback.is_photo,
            message_preview=message_preview,
            full_message=full_message,
            photo_file_id=getattr(feedback, 'photo_file_id', None),
            status=feedback.status,
        )

    def build_description_text(
        self, display_data: FeedbackDisplayData
    ) -> str:
        """
        Строит текстовое описание обращения для отправки пользователю.

        Args:
            display_data: Структурированные данные обращения.

        Returns:
            str: Отформатированное описание.
        """
        type_label = 'голосовое' if display_data.is_voice else 'текстовое'
        photo_label = 'да' if display_data.is_photo else 'нет'

        return (
            f"📬 Обращение #{display_data.feedback_id} от {display_data.username}\n"
            f"Дата: {display_data.created_at}\n"
            f"Тип: {type_label}\n"
            f"Фото: {photo_label}\n\n"
            f"Сообщение:\n{display_data.message_preview}"
        )

    async def reply_to_feedback(self, feedback_id: int, admin_response: str) -> Optional[Feedback]:
        """
        Отвечает на обращение от имени администратора.

        Args:
            feedback_id: ID обращения.
            admin_response: Текст ответа.

        Returns:
            Optional[Feedback]: Обновлённый объект или None если не найдено.
        """
        try:
            return await Feedback.areply_to_feedback(feedback_id, admin_response)
        except Feedback.DoesNotExist:
            logger.warning(f"Feedback #{feedback_id} not found for reply")
            return None

    async def can_reply_to_feedback(self, feedback_id: int) -> Tuple[bool, Optional[Feedback]]:
        """
        Проверяет, можно ли ответить на обращение (статус 'new' или 'processed').

        Args:
            feedback_id: ID обращения.

        Returns:
            Tuple[bool, Optional[Feedback]]: (можно ответить, объект обращения).
        """
        try:
            @sync_to_async
            def _check():
                try:
                    fb = Feedback.objects.select_related('user').get(id=feedback_id)
                    return fb.status in ['new', 'processed'], fb
                except Feedback.DoesNotExist:
                    return False, None
            return await _check()
        except Exception as e:
            logger.error(f"Error checking feedback {feedback_id}: {e}")
            return False, None

    def validate_photo_size(self, file_size: int) -> bool:
        """
        Проверяет размер фото.

        Args:
            file_size: Размер файла в байтах.

        Returns:
            bool: True если размер в пределах лимита.
        """
        return file_size <= MAX_FILE_SIZE


feedback_service = FeedbackService()
