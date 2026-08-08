# /diary/services/task_display_service.py
"""
Сервис для отображения задач и результатов их анализа.
Универсальный сервис: работает и для бота, и для API.

Отвечается за:
- Форматирование уведомлений о результате анализа задания
- Форматирование истории заданий для отображения
- Получение детального анализа задания
- Создание клавиатур для заданий
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from diary.models import TherapyTask, TaskCompletion, TaskCompletionAnalysis
from users.models import User
from messages import get_message, get_button_text

logger = logging.getLogger(__name__)


@dataclass
class TaskAnalysisNotification:
    """Результат форматирования анализа задания для уведомления."""
    text: str
    keyboard: InlineKeyboardMarkup


@dataclass
class TaskHistoryDetail:
    """Детали задания для отображения в истории."""
    text: str


class TaskDisplayService:
    """Сервис для отображения задач и их анализа."""

    def build_task_completion_invalid_keyboard(
        self, task_id: int, language: str
    ) -> InlineKeyboardMarkup:
        """
        Создаёт клавиатуру для случая, когда выполнение задания невалидно.

        Args:
            task_id: ID задания.
            language: Язык интерфейса.

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками 'Попробовать ещё', 'Пропустить', 'Назад'.
        """
        buttons = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_try_again', language),
                    callback_data=f"complete_task:{task_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_skip_task', language),
                    callback_data=f"skip_task:{task_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_back', language),
                    callback_data="back_to_tasks"
                )
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    async def format_task_analysis_notification(
        self,
        analysis_result,
        user: User,
        task_completion: TaskCompletion,
    ) -> TaskAnalysisNotification:
        """
        Форматирует результат анализа выполнения задания для уведомления пользователя.

        Обрабатывает три сценария:
        1. Анализ невалиден (invalid=True)
        2. Анализ успешен (есть объект анализа)
        3. Ошибка анализа

        Args:
            analysis_result: Результат анализа (dict с 'invalid' или объект анализа).
            user: Пользователь.
            task_completion: Объект выполнения задания.

        Returns:
            TaskAnalysisNotification: Отформатированный текст и клавиатура.
        """
        language = user.language

        # Сценарий 1: Анализ невалиден
        if isinstance(analysis_result, dict) and analysis_result.get('invalid'):
            validation_comment = analysis_result.get(
                'validation_comment',
                get_message('task_completion_invalid_default_comment', language)
            )
            text = get_message(
                'task_completion_invalid_formatted',
                language,
                validation_comment=validation_comment
            )
            keyboard = self.build_task_completion_invalid_keyboard(
                task_completion.task.id, language
            )
            return TaskAnalysisNotification(text=text, keyboard=keyboard)

        # Сценарий 2: Анализ успешен
        if analysis_result and hasattr(analysis_result, 'id'):
            return await self._format_successful_analysis(
                analysis_result, user, task_completion
            )

        # Сценарий 3: Ошибка анализа
        text = get_message('task_analysis_error_formatted', language)
        keyboard = self._get_back_keyboard(language)
        return TaskAnalysisNotification(text=text, keyboard=keyboard)

    async def _format_successful_analysis(
        self,
        analysis_result,
        user: User,
        task_completion: TaskCompletion,
    ) -> TaskAnalysisNotification:
        """
        Форматирует успешный результат анализа задания.

        Args:
            analysis_result: Объект TaskCompletionAnalysis.
            user: Пользователь.
            task_completion: Объект выполнения задания.

        Returns:
            TaskAnalysisNotification: Отформатированный текст и клавиатура.
        """
        language = user.language
        parsed_result = analysis_result.api_response.get('result', {})
        formatted_message = parsed_result.get('formatted_message')
        tokens_awarded = analysis_result.tokens_awarded

        if formatted_message:
            # Вариант A: есть готовое форматированное сообщение
            text = formatted_message
            if tokens_awarded > 0:
                updated_user = await User.objects.aget(telegram_id=user.telegram_id)
                tokens_info = get_message(
                    'task_tokens_awarded', language,
                    tokens=tokens_awarded,
                    balance=updated_user.token_balance
                )
                if tokens_info not in text:
                    text += f"\n\n{tokens_info}"
        else:
            # Вариант B: собираем сообщение из отдельных полей
            text = await self._build_detailed_analysis_text(
                analysis_result, user, tokens_awarded
            )

        keyboard = self._get_back_keyboard(language)
        return TaskAnalysisNotification(text=text, keyboard=keyboard)

    async def _build_detailed_analysis_text(
        self,
        analysis_result,
        user: User,
        tokens_awarded: int,
    ) -> str:
        """
        Строит детальный текст анализа из отдельных полей.

        Args:
            analysis_result: Объект TaskCompletionAnalysis.
            user: Пользователь.
            tokens_awarded: Количество начисленных токенов.

        Returns:
            str: Полный текст анализа.
        """
        language = user.language

        effect_description = analysis_result.effect_description or get_message('no_effect_description', language)
        mood_impact_score = analysis_result.mood_impact_score
        mood_impact_display = self._format_mood_impact(mood_impact_score)
        comment_for_user = analysis_result.comment or get_message('no_comment', language)
        recommendation_for_user = analysis_result.recommendation or get_message('no_recommendation', language)
        detailed_analysis = analysis_result.detailed_analysis or ''

        main_text = get_message(
            'task_effect_analysis_result_formatted',
            language,
            effect_description=effect_description,
            mood_impact=mood_impact_display,
            detailed_analysis=detailed_analysis,
            comment=comment_for_user,
            recommendation=recommendation_for_user
        )

        if tokens_awarded > 0:
            updated_user = await User.objects.aget(telegram_id=user.telegram_id)
            tokens_info = get_message(
                'task_tokens_awarded', language,
                tokens=tokens_awarded,
                balance=updated_user.token_balance
            )
            return f"{main_text}\n\n{tokens_info}"

        return main_text

    def _format_mood_impact(self, mood_impact_score) -> str:
        """
        Форматирует влияние на настроение для отображения.

        Args:
            mood_impact_score: Числовая оценка влияния.

        Returns:
            str: Строка вида '🔺 +3', '🔻 -2' или 'N/A'.
        """
        if mood_impact_score is None:
            return "N/A"
        try:
            score_int = int(mood_impact_score)
            if score_int > 0:
                return f"🔺 +{score_int}"
            elif score_int < 0:
                return f"🔻 {score_int}"
            else:
                return f"➡️ {score_int}"
        except (ValueError, TypeError):
            return "N/A"

    def _get_back_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Возвращает клавиатуру с кнопкой 'Назад'."""
        from bot.keyboards import get_back_keyboard
        return get_back_keyboard(language)

    # === Task history ===

    async def format_task_history_detail(
        self, task: TherapyTask, language: str
    ) -> TaskHistoryDetail:
        """
        Форматирует детали задания для отображения в истории.

        Args:
            task: Объект TherapyTask.
            language: Язык интерфейса.

        Returns:
            TaskHistoryDetail: Отформатированный текст с деталями задания.
        """
        try:
            assigned_at = task.assigned_at.strftime('%d.%m.%Y %H:%M')
            status = task.get_status_display()
            complexity = task.complexity

            completed_at = ""
            if task.completed_at:
                completed_at = get_message(
                    'task_completed_at', language,
                    completed_at=task.completed_at.strftime('%d.%m.%Y %H:%M')
                )

            completion_text = get_message('completion_not_found', language)
            feelings_text = get_message('feelings_not_found', language)

            try:
                completion = await TaskCompletion.objects.aget(task=task)
                if completion:
                    completion_text = completion.completion_text or get_message('completion_text_missing', language)
                    feelings_text = completion.feelings_text or get_message('feelings_text_missing', language)
            except TaskCompletion.DoesNotExist:
                logger.debug(f"Выполнение для задания {task.id} не найдено.")
            except Exception as e:
                logger.error(f"Ошибка при доступе к выполнению задания {task.id}: {e}")
                completion_text = get_message('completion_load_error', language)
                feelings_text = get_message('feelings_load_error', language)

            text = get_message(
                'task_history_detail', language,
                title=task.title,
                assigned_at=assigned_at,
                completed_at=completed_at,
                status=status,
                complexity=complexity,
                description=task.description,
                completion_text=completion_text,
                feelings_text=feelings_text
            )
            return TaskHistoryDetail(text=text)

        except Exception as e:
            logger.error(f"Ошибка при форматировании деталей задания {task.id}: {e}")
            return TaskHistoryDetail(
                text=get_message('error_loading_task_details', language)
            )

    # === Detailed task analysis ===

    async def get_task_analysis_detail(
        self, user: User, task_id: int
    ) -> Dict[str, Any]:
        """
        Получает детальный анализ задания для отображения.

        Args:
            user: Пользователь.
            task_id: ID задания.

        Returns:
            Dict[str, Any]:
                - success: bool
                - text: str (если успех)
                - keyboard: InlineKeyboardMarkup
                - error: str (если ошибка)
        """
        try:
            task = await TherapyTask.objects.aget(id=task_id, user=user)
        except TherapyTask.DoesNotExist:
            return {
                'success': False,
                'error': 'task_not_found',
                'message': get_message('task_not_found', user.language),
            }

        if task.status != 'completed':
            return {
                'success': False,
                'error': 'not_completed',
                'message': get_message('task_not_completed_for_analysis', user.language),
            }

        try:
            completion = await TaskCompletion.objects.aget(task=task)
        except TaskCompletion.DoesNotExist:
            return {
                'success': False,
                'error': 'completion_not_found',
                'message': get_message('task_completion_not_found', user.language),
            }

        try:
            analysis = await TaskCompletionAnalysis.objects.aget(
                completion=completion, is_obsolete=False
            )
        except TaskCompletionAnalysis.DoesNotExist:
            return {
                'success': False,
                'error': 'analysis_not_found',
                'message': get_message('task_analysis_not_found', user.language),
            }
        except TaskCompletionAnalysis.MultipleObjectsReturned:
            analysis = await TaskCompletionAnalysis.objects.filter(
                completion=completion, is_obsolete=False
            ).afirst()
            if not analysis:
                return {
                    'success': False,
                    'error': 'analysis_not_found',
                    'message': get_message('task_analysis_error', user.language),
                }

        # Форматируем результат
        language = user.language
        tokens_awarded = analysis.tokens_awarded
        user_balance = user.token_balance

        if analysis.detailed_analysis:
            header = get_message('detailed_task_analysis_header', language).format(
                task_title=task.title
            )
            text = f"<b>{header}</b>\n\n{analysis.detailed_analysis}"
            if tokens_awarded > 0:
                tokens_msg = get_message(
                    'task_tokens_awarded', language,
                    tokens=tokens_awarded,
                    balance=user_balance
                )
                text += f"\n\n{tokens_msg}"
        else:
            text = get_message('task_analysis_no_details', language).format(
                task_title=task.title
            )
            if tokens_awarded > 0:
                tokens_msg = get_message(
                    'task_tokens_awarded', language,
                    tokens=tokens_awarded,
                    balance=user_balance
                )
                text += f"\n\n{tokens_msg}"

        from bot.keyboards import get_task_history_main_keyboard
        keyboard = get_task_history_main_keyboard(language)

        return {
            'success': True,
            'text': text,
            'keyboard': keyboard,
        }

    async def build_active_tasks_view(self, user: User, language: str) -> Dict[str, Any]:
        """Payload экрана активных заданий (active/empty), первая страница."""
        return await self.build_active_tasks_page_view(user, language, index=0)

    async def build_active_tasks_page_view(
        self,
        user: User,
        language: str,
        index: int = 0,
        direction: Optional[str] = None,
        *,
        empty_reply_mode: str = 'main_menu',
    ) -> Dict[str, Any]:
        """
        Payload экрана активных заданий с пагинацией (active/empty).

        empty_reply_mode:
            - main_menu — экран списка заданий (show_tasks, skip)
            - back_only — только «назад» (paginate_tasks при пустом списке)
        """
        from diary.services.task_management_service import (
            get_user_active_tasks,
            get_user_completed_tasks,
            get_user_skipped_tasks,
        )
        from bot.keyboards import (
            get_task_pagination_keyboard,
            get_task_main_menu_keyboard,
            get_single_button_keyboard,
        )

        active_tasks = await get_user_active_tasks(user)
        completed_tasks_check = await get_user_completed_tasks(user, limit=1)
        skipped_tasks_check = await get_user_skipped_tasks(user, limit=1)
        has_history = bool(completed_tasks_check or skipped_tasks_check)

        if not active_tasks:
            empty_keyboard = (
                get_single_button_keyboard(language)
                if empty_reply_mode == 'back_only'
                else get_task_main_menu_keyboard(
                    language=language,
                    show_history_button=has_history,
                )
            )
            return {
                'success': True,
                'mode': 'empty',
                'text': get_message('task_no_active', language),
                'keyboard': empty_keyboard,
                'tasks': [],
                'has_history': has_history,
                'current_index': 0,
            }

        current_index = index
        if direction == 'next':
            current_index = (index + 1) % len(active_tasks)
        elif direction == 'prev':
            current_index = (index - 1) % len(active_tasks)

        task = active_tasks[current_index]
        return {
            'success': True,
            'mode': 'active',
            'text': get_message(
                'task_assigned',
                language,
                title=task.title,
                description=task.description,
            ),
            'keyboard': get_task_pagination_keyboard(
                task_id=task.id,
                current_index=current_index,
                total_tasks=len(active_tasks),
                language=language,
                show_history_button=has_history,
            ),
            'tasks': active_tasks,
            'has_history': has_history,
            'current_index': current_index,
            'task': task,
        }

    async def build_task_detail_view(
        self,
        user: User,
        task_id: int,
        language: str,
    ) -> Dict[str, Any]:
        """Payload просмотра конкретного задания."""
        from diary.services.task_management_service import get_user_task_by_id
        from bot.keyboards import get_task_detail_keyboard

        task = await get_user_task_by_id(user, task_id)
        if not task:
            return {
                'success': False,
                'mode': 'not_found',
                'alert_text': get_message('task_not_found', language),
            }

        return {
            'success': True,
            'mode': 'detail',
            'text': get_message(
                'task_assigned',
                language,
                title=task.title,
                description=task.description,
            ),
            'keyboard': get_task_detail_keyboard(task_id, language),
            'task': task,
        }

    async def build_start_completion_view(
        self,
        user: User,
        task_id: int,
        language: str,
    ) -> Dict[str, Any]:
        """Payload начала выполнения задания (FSM + текст + клавиатура)."""
        from diary.services.task_management_service import get_user_task_by_id
        from bot.keyboards import get_single_button_keyboard
        from bot.states.task_states import TaskStates

        task = await get_user_task_by_id(user, task_id)
        if not task:
            return {
                'success': False,
                'mode': 'not_found',
                'alert_text': get_message('task_not_found', language),
            }

        completion_msg = get_message('ask_task_completion_with_context', language).format(
            title=task.title,
            description=task.description,
        )
        return {
            'success': True,
            'mode': 'start',
            'text': completion_msg,
            'keyboard': get_single_button_keyboard(language, 'tasks', 'btn_back'),
            'fsm_state': TaskStates.waiting_for_task_completion,
            'fsm_data': {
                'completing_task_id': task_id,
                'task_description': task.description,
            },
            'task': task,
        }

    async def build_task_history_view(
        self,
        user: User,
        language: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Payload экрана истории заданий (list/empty)."""
        from diary.services.task_management_service import (
            get_user_completed_tasks,
            get_user_skipped_tasks,
        )
        from bot.keyboards import get_task_history_main_keyboard, get_task_history_list_keyboard

        completed_tasks = await get_user_completed_tasks(user, limit=limit)
        skipped_tasks = await get_user_skipped_tasks(user, limit=limit)
        all_history_tasks = completed_tasks + skipped_tasks
        all_history_tasks.sort(key=lambda t: (t.completed_at or t.assigned_at), reverse=True)

        if not all_history_tasks:
            return {
                'success': True,
                'mode': 'empty',
                'text': get_message('task_history_empty', language),
                'keyboard': get_task_history_main_keyboard(language),
                'task_ids': [],
            }

        task_ids = [task.id for task in all_history_tasks]
        first_task = all_history_tasks[0]
        detail = await self.format_task_history_detail(first_task, language)
        return {
            'success': True,
            'mode': 'list',
            'text': detail.text,
            'keyboard': get_task_history_list_keyboard(
                task_ids=task_ids,
                current_index=0,
                current_task_status=first_task.status,
                language=language,
            ),
            'task_ids': task_ids,
            'current_task': first_task,
        }


task_display_service = TaskDisplayService()
