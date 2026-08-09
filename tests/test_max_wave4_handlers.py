"""Wave 4 MAX: feedback / support."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django.core.cache import cache

from bot.handlers.max import state as max_state
from bot.handlers.max.callbacks import route_callback
from bot.handlers.max.messages import route_text_message
from bot.states.feedback_states import FeedbackStates
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def max_user(db):
    return User.objects.create_user(
        username='max_wave4',
        email='max_wave4@example.com',
        max_id=880004,
        language='ru',
        is_onboarding_completed=True,
    )


@pytest.mark.asyncio
async def test_feedback_command_starts_fsm(max_user):
    send_func = AsyncMock(return_value=True)
    result = await route_text_message(max_user, '/feedback', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'feedback_start'
    assert max_state.matches_state(max_user.max_id, FeedbackStates.waiting_message)


@pytest.mark.asyncio
async def test_support_alias(max_user):
    send_func = AsyncMock(return_value=True)
    result = await route_text_message(max_user, '/support', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'feedback_start'


@pytest.mark.asyncio
async def test_feedback_text_then_skip_photo(max_user, mocker):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, FeedbackStates.waiting_message)

    text_result = await route_text_message(
        max_user, 'Нужна помощь с ботом', send_func, max_id=max_user.max_id
    )
    assert text_result['handled'] == 'feedback_text'
    assert max_state.matches_state(max_user.max_id, FeedbackStates.waiting_photo)

    mocker.patch(
        'bot.handlers.max.feedback.feedback_service.submit_user_feedback_use_case',
        new=AsyncMock(
            return_value={
                'success': True,
                'thanks_text': 'Спасибо!',
                'feedback': MagicMock(),
                'notify_payload': {'user': max_user, 'message_text': 'Нужна помощь с ботом'},
                'clear_state': True,
            }
        ),
    )
    mocker.patch(
        'bot.handlers.max.feedback.send_feedback_to_developer',
        new=AsyncMock(),
        create=True,
    )
    # Patch the imported path used inside handle_skip_photo
    mocker.patch(
        'bot.utils.admin_utils.send_feedback_to_developer',
        new=AsyncMock(),
    )

    skip = await route_callback(max_user, 'skip_photo', send_func, max_id=max_user.max_id)
    assert skip['handled'] == 'skip_photo'
    assert max_state.get_fsm_state(max_user.max_id) is None


@pytest.mark.asyncio
async def test_add_screenshot_prompts_for_photo(max_user):
    send_func = AsyncMock(return_value=True)
    max_state.set_fsm_state(max_user.max_id, FeedbackStates.waiting_photo, feedback_text='hi')
    result = await route_callback(max_user, 'add_screenshot', send_func, max_id=max_user.max_id)
    assert result['handled'] == 'add_screenshot'
    assert 'скриншот' in send_func.await_args.args[0].lower() or 'фото' in send_func.await_args.args[0].lower()
