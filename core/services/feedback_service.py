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

    def build_admin_feedback_list_keyboard(
        self,
        feedback_id: int,
        index: int,
        total: int,
    ):
        """Клавиатура навигации по списку обращений (admin)."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        nav_buttons = [
            InlineKeyboardButton(
                text='Ответить',
                callback_data=f"reply_feedback_{feedback_id}",
            )
        ]
        if index > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущее", callback_data="feedback_prev")
            )
        if index < total - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="Следующее ➡️", callback_data="feedback_next")
            )

        return InlineKeyboardMarkup(
            inline_keyboard=[
                nav_buttons,
                [InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_feedbacks_list")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_feedback_list")],
            ]
        )

    async def build_admin_feedback_item_view(
        self,
        feedback_ids: List[int],
        index: int,
    ) -> Dict[str, Any]:
        """
        Use-case payload для экрана одного обращения в admin-списке.

        modes: not_found | empty | item
        """
        if not feedback_ids or index < 0 or index >= len(feedback_ids):
            return {
                'success': False,
                'mode': 'not_found',
                'text': '❌ Обращение не найдено.',
                'feedback_ids': [],
                'index': 0,
                'clear_state': True,
            }

        working_ids = list(feedback_ids)
        working_index = index

        while working_ids:
            if working_index < 0 or working_index >= len(working_ids):
                working_index = max(0, len(working_ids) - 1)

            feedback_id = working_ids[working_index]
            feedback = await self.get_feedback_by_id(feedback_id)
            if feedback:
                display_data = await self.format_feedback_for_display(feedback)
                return {
                    'success': True,
                    'mode': 'item',
                    'text': self.build_description_text(display_data),
                    'reply_markup': self.build_admin_feedback_list_keyboard(
                        feedback.id, working_index, len(working_ids)
                    ),
                    'has_photo': bool(
                        feedback.is_photo
                        and getattr(feedback, 'photo_file_id', None)
                    ),
                    'photo_file_id': getattr(feedback, 'photo_file_id', None),
                    'feedback_ids': working_ids,
                    'index': working_index,
                    'clear_state': False,
                }

            logger.error(
                f"Обращение с ID {feedback_id} не найдено при отображении."
            )
            working_ids.remove(feedback_id)
            if not working_ids:
                return {
                    'success': False,
                    'mode': 'empty',
                    'text': f'❌ Обращение с ID {feedback_id} больше не существует.',
                    'empty_text': 'Список обращений пуст.',
                    'feedback_ids': [],
                    'index': 0,
                    'clear_state': True,
                }
            if working_index >= len(working_ids):
                working_index = len(working_ids) - 1

        return {
            'success': False,
            'mode': 'empty',
            'text': 'Список обращений пуст.',
            'feedback_ids': [],
            'index': 0,
            'clear_state': True,
        }

    async def submit_user_feedback_use_case(
        self,
        user: Optional[User],
        message_text: str,
        language: str = 'ru',
        voice_data: Optional[bytes] = None,
        photo_bytes: Optional[bytes] = None,
        photo_file_id: Optional[str] = None,
        photo_file_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Use-case отправки обратной связи пользователем.

        Создаёт Feedback в БД и возвращает payload для transport-уведомления
        разработчику через send_feedback_to_developer.
        """
        from messages import get_message

        if not user:
            return {
                'success': False,
                'mode': 'error',
                'error': 'user_not_found',
                'thanks_text': get_message('error_generic', language),
                'clear_state': True,
            }

        if photo_file_size is not None and not self.validate_photo_size(photo_file_size):
            return {
                'success': False,
                'mode': 'photo_too_large',
                'error': 'photo_too_large',
                'thanks_text': get_message('photo_too_large', language),
                'clear_state': False,
            }

        try:
            feedback = await self.create_feedback(
                user=user,
                message_text=message_text,
                voice_data=voice_data,
                photo_data=photo_bytes,
                photo_file_id=photo_file_id,
            )
        except Exception as exc:
            logger.error(
                f"Error creating feedback for user {getattr(user, 'telegram_id', '?')}: {exc}",
                exc_info=True,
            )
            return {
                'success': False,
                'mode': 'error',
                'error': 'feedback_create_failed',
                'thanks_text': get_message('error_generic', language),
                'clear_state': True,
            }

        return {
            'success': True,
            'mode': 'success',
            'feedback_id': feedback.id,
            'feedback': feedback,
            'thanks_text': get_message('feedback_thanks', language),
            'notify_payload': {
                'user': user,
                'message_text': message_text,
                'voice_data': voice_data,
                'photo_data': photo_bytes,
                'photo_file_id': photo_file_id,
            },
            'clear_state': True,
        }

    async def process_admin_feedback_reply_use_case(
        self,
        admin_user: User,
        feedback_id: int,
        reply_text: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Use-case ответа администратора на обращение.

        Возвращает payload для отправки ответа пользователю (transport в handler).
        """
        from messages import get_message

        _ = admin_user

        try:
            can_reply, feedback = await self.can_reply_to_feedback(feedback_id)

            if not feedback:
                return {
                    'success': False,
                    'mode': 'not_found',
                    'error': 'feedback_not_found',
                    'admin_ack_text': '❌ Обращение больше не существует.',
                    'clear_state': True,
                }
            if not can_reply:
                return {
                    'success': False,
                    'mode': 'already_processed',
                    'error': 'feedback_already_processed',
                    'admin_ack_text': '❌ Обращение уже обработано кем-то другим.',
                    'clear_state': True,
                }

            # Persist reply only after transport delivery (handler calls reply_to_feedback).
            display_data = await self.format_feedback_for_display(feedback)
            username = display_data.username

            return {
                'success': True,
                'mode': 'ready_to_send',
                'feedback_id': feedback_id,
                'reply_text': reply_text,
                'notify_chat_id': feedback.user.telegram_id,
                'notify_text': get_message(
                    'support_response',
                    language,
                    feedback_id=feedback_id,
                    message_text=reply_text,
                ),
                'admin_ack_text': (
                    f"✅ Ответ на обращение #{feedback_id} "
                    f"отправлен пользователю {username}!"
                ),
                'persist_reply': True,
                'clear_state': True,
            }
        except Exception as exc:
            logger.error(
                f"Error processing admin feedback reply #{feedback_id}: {exc}",
                exc_info=True,
            )
            return {
                'success': False,
                'mode': 'error',
                'error': 'feedback_reply_failed',
                'admin_ack_text': '❌ Не удалось отправить ответ',
                'clear_state': True,
            }

    def compute_admin_feedback_nav_index(
        self,
        feedback_ids: List[int],
        current_index: int,
        direction: str,
    ) -> Dict[str, Any]:
        """
        Вычисляет новый индекс навигации по списку обращений (admin).

        direction: 'next' | 'prev'
        """
        total = len(feedback_ids)
        if direction == 'next':
            new_index = current_index + 1
            if new_index < total:
                return {
                    'success': True,
                    'new_index': new_index,
                    'at_bound': False,
                }
            return {
                'success': False,
                'new_index': current_index,
                'at_bound': True,
                'alert_text': 'Больше обращений нет.',
            }

        if direction == 'prev':
            new_index = current_index - 1
            if new_index >= 0:
                return {
                    'success': True,
                    'new_index': new_index,
                    'at_bound': False,
                }
            return {
                'success': False,
                'new_index': current_index,
                'at_bound': True,
                'alert_text': 'Это первое обращение.',
            }

        return {
            'success': False,
            'new_index': current_index,
            'at_bound': True,
            'alert_text': '❌ Некорректное направление навигации.',
        }

    async def build_admin_reply_prompt_view(
        self,
        feedback_id: int,
        language: str,
    ) -> Dict[str, Any]:
        """Payload старта ответа админа на обращение."""
        from messages import get_message
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        can_reply, feedback = await self.can_reply_to_feedback(feedback_id)
        if not feedback:
            return {
                'success': False,
                'mode': 'not_found',
                'error': 'feedback_not_found',
                'alert_text': '❌ Обращение не найдено.',
            }
        if not can_reply:
            return {
                'success': False,
                'mode': 'already_processed',
                'error': 'feedback_already_processed',
                'alert_text': '❌ Обращение уже обработано.',
            }

        display_data = await self.format_feedback_for_display(feedback)
        return {
            'success': True,
            'mode': 'prompt',
            'feedback_id': feedback_id,
            'text': get_message(
                'reply_feedback_prompt',
                language,
                feedback_id=feedback_id,
                username=display_data.username,
                created_at=display_data.created_at,
                message_text=feedback.message,
            ),
            'reply_markup': InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=get_message('btn_cancel_reply', language),
                            callback_data='cancel_reply',
                        )
                    ]
                ]
            ),
        }


feedback_service = FeedbackService()
