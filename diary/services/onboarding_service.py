"""
Сервис онбординга: routing /start и view builders шагов.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from messages import get_message, get_mood_text
from users.models import User

logger = logging.getLogger(__name__)


class OnboardingService:
    """Доменные view/use-case для онбординга и старта."""

    @classmethod
    async def build_onboarding_timezone_prompt_view(
        cls,
        user: User,
        language: str,
        *,
        include_info_prefix: bool = True,
        show_back_button: bool = False,
    ) -> Dict[str, Any]:
        """Экран выбора TZ в онбординге/перенаправлении."""
        from diary.services.settings_service import get_timezone_info
        from bot.keyboards import get_timezone_selection_method_keyboard

        info_result = await get_timezone_info(user)
        if not info_result.get('success'):
            return {
                'success': False,
                'mode': 'error',
                'error': info_result.get('error'),
                'text': get_message('error_generic', language),
            }

        current_timezone = info_result['current_timezone']
        timezone_msg = get_message(
            'ask_timezone_selection', language, current_timezone=current_timezone
        )
        text = timezone_msg
        if include_info_prefix:
            text = get_message('onboarding_timezone_info', language) + "\n\n" + timezone_msg

        return {
            'success': True,
            'mode': 'timezone_prompt',
            'text': text,
            'reply_markup': get_timezone_selection_method_keyboard(
                language, current_timezone, show_back_button=show_back_button
            ),
            'current_timezone': current_timezone,
            'set_origin': 'onboarding_timezone_setup',
        }

    @classmethod
    def build_first_onboarding_entry_result_view(
        cls,
        response: Any,
        language: str,
    ) -> Dict[str, Any]:
        """Payload результата первой записи онбординга."""
        processing_result = getattr(response, 'data', None) or {}

        if not getattr(response, 'success', False):
            return {
                'success': False,
                'mode': 'validation_failed',
                'text': processing_result.get('formatted_message_ai')
                or get_message('error_generic', language),
                'clear_state': False,
            }

        mood_score = processing_result.get('mood_score', 5)
        comment = processing_result.get('comment', get_message('no_comment', language))
        recommendation = processing_result.get(
            'recommendation', get_message('no_recommendation', language)
        )
        mood_text = get_mood_text(mood_score, language)
        return {
            'success': True,
            'mode': 'entry_saved',
            'text': get_message(
                'entry_saved',
                language,
                score=mood_score,
                mood=mood_text,
                comment=comment,
                recommendation=recommendation,
            ),
            'clear_state': True,
            'use_main_menu_keyboard': True,
        }

    @classmethod
    async def resolve_start_routing_use_case(
        cls,
        user: User,
        language: str,
        current_fsm_state: Any,
        *,
        was_reactivated: bool = False,
    ) -> Dict[str, Any]:
        """
        Решает, что показать на /start.

        modes:
          agreement_1 | agreement_2 | timezone | first_entry_prompt |
          start_onboarding | main_menu | error
        """
        from bot.states.onboarding_states import OnboardingStates
        from bot.keyboards import get_single_button_keyboard
        from diary.services.main_menu_service import build_main_menu_data

        if current_fsm_state == OnboardingStates.waiting_for_agreement_1:
            return {
                'success': True,
                'mode': 'agreement_1',
                'text': get_message('onboarding_welcome_extended_first_entry', language),
                'reply_markup': get_single_button_keyboard(
                    language, button_callback_data='onboarding_agree_1', button_text='btn_next'
                ),
                'set_state': None,
                'clear_state': False,
            }

        if current_fsm_state == OnboardingStates.waiting_for_agreement_2:
            return {
                'success': True,
                'mode': 'agreement_2',
                'text': get_message('onboarding_project_info', language),
                'reply_markup': get_single_button_keyboard(
                    language, button_callback_data='onboarding_agree_2', button_text='btn_next'
                ),
                'set_state': None,
                'clear_state': False,
            }

        if current_fsm_state == OnboardingStates.waiting_for_timezone_confirmation:
            tz_view = await cls.build_onboarding_timezone_prompt_view(
                user, language, include_info_prefix=True, show_back_button=False
            )
            if not tz_view.get('success'):
                return tz_view
            return {
                **tz_view,
                'mode': 'timezone',
                'set_state': None,
                'clear_state': False,
            }

        if not user.is_onboarding_completed:
            if current_fsm_state == OnboardingStates.waiting_for_first_entry:
                return {
                    'success': True,
                    'mode': 'first_entry_prompt',
                    'text': get_message('onboarding_prompt_first_entry', language),
                    'reply_markup': None,
                    'set_state': None,
                    'clear_state': False,
                }
            return {
                'success': True,
                'mode': 'start_onboarding',
                'text': get_message('onboarding_welcome_extended_first_entry', language),
                'reply_markup': get_single_button_keyboard(
                    language, button_callback_data='onboarding_agree_1', button_text='btn_next'
                ),
                'set_state': 'waiting_for_agreement_1',
                'clear_state': True,
            }

        menu_data = await build_main_menu_data(user=user, language=language)
        reactivation_text: Optional[str] = None
        if was_reactivated:
            reactivation_text = get_message(
                'welcome_back_reactivated',
                language,
                first_name=user.first_name
                or user.username
                or get_message('user_default_name', language),
            )
        return {
            'success': True,
            'mode': 'main_menu',
            'text': menu_data['message_text'],
            'reply_markup': menu_data['keyboard'],
            'reactivation_text': reactivation_text,
            'set_state': None,
            'clear_state': True,
        }


async def build_onboarding_timezone_prompt_view(
    user: User,
    language: str,
    *,
    include_info_prefix: bool = True,
    show_back_button: bool = False,
) -> Dict[str, Any]:
    return await OnboardingService.build_onboarding_timezone_prompt_view(
        user,
        language,
        include_info_prefix=include_info_prefix,
        show_back_button=show_back_button,
    )


def build_first_onboarding_entry_result_view(response: Any, language: str) -> Dict[str, Any]:
    return OnboardingService.build_first_onboarding_entry_result_view(response, language)


async def resolve_start_routing_use_case(
    user: User,
    language: str,
    current_fsm_state: Any,
    *,
    was_reactivated: bool = False,
) -> Dict[str, Any]:
    return await OnboardingService.resolve_start_routing_use_case(
        user,
        language,
        current_fsm_state,
        was_reactivated=was_reactivated,
    )
