import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from diary.tasks.reminder_ask_questions import _send_reminder_async, _user_log_id
from users.models import User


def test_user_log_id_max_only():
    user = User(pk=314, telegram_id=None, max_id=555)
    assert _user_log_id(user) == 'id=314 max=555'


@pytest.mark.asyncio
async def test_send_reminder_uses_dual_channel_send():
    """MAX-only пользователь должен получать напоминание через send_message_to_user."""
    user = MagicMock()
    user.pk = 314
    user.telegram_id = None
    user.max_id = 555
    user.language = 'ru'

    entry = MagicMock()
    entry.id = 42
    entry.user = user

    bot = MagicMock()
    bot.session = MagicMock()
    bot.session.close = AsyncMock()

    def _sync_to_async(func):
        async def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

    with (
        patch(
            'diary.tasks.reminder_ask_questions.create_bot_for_task',
            new=AsyncMock(return_value=bot),
        ),
        patch(
            'diary.tasks.reminder_ask_questions.send_message_to_user',
            new=AsyncMock(return_value=True),
        ) as send_mock,
        patch('diary.tasks.reminder_ask_questions.sync_to_async', side_effect=_sync_to_async),
        patch('diary.tasks.reminder_ask_questions.get_message', return_value='reminder'),
        patch(
            'diary.tasks.reminder_ask_questions.get_skip_clarification_keyboard',
            return_value=None,
        ),
        patch('diary.tasks.reminder_ask_questions.timezone') as tz,
    ):
        tz.now.return_value = 'now'
        await _send_reminder_async(entry)

    send_mock.assert_awaited_once()
    assert send_mock.await_args.args[1] is user
    entry.save.assert_called()
    bot.session.close.assert_awaited()
