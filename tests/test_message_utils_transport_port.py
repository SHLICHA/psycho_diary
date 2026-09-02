import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.transports.send_port import SendResult
from bot.utils.message_utils import _build_normalized_output, send_message_to_user, send_message_to_user_all_channels
from users.models import User


pytestmark = pytest.mark.asyncio


async def test_build_normalized_output_with_inline_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Yes', callback_data='merge_target:yes:1')],
            [InlineKeyboardButton(text='No', callback_data='merge_target:no:1')],
        ]
    )

    output = _build_normalized_output('hello', keyboard)

    assert output is not None
    assert output.text == 'hello'
    assert output.buttons[0][0].text == 'Yes'
    assert output.buttons[0][0].callback_data == 'merge_target:yes:1'


async def test_build_normalized_output_rejects_non_callback_buttons():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Open', url='https://example.com')],
        ]
    )

    output = _build_normalized_output('hello', keyboard)

    assert output is None


async def test_send_message_to_user_uses_unified_send_port_success(mocker):
    bot = mocker.Mock()
    bot.send_message = mocker.AsyncMock()
    user = mocker.Mock(telegram_id=123456)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='Yes', callback_data='merge_target:yes:1')]]
    )

    send_mock = mocker.AsyncMock(return_value=SendResult(success=True, reason='sent'))
    mark_unblocked_mock = mocker.AsyncMock()
    mark_blocked_mock = mocker.AsyncMock()
    mark_user_unblocked_mock = mocker.AsyncMock()
    mark_user_blocked_mock = mocker.AsyncMock()

    mocker.patch('bot.utils.message_utils.UnifiedSendPort.send', new=send_mock)
    mocker.patch.object(User, 'mark_unblocked', new=mark_unblocked_mock)
    mocker.patch.object(User, 'mark_blocked', new=mark_blocked_mock)
    mocker.patch.object(User, 'mark_user_unblocked', new=mark_user_unblocked_mock)
    mocker.patch.object(User, 'mark_user_blocked', new=mark_user_blocked_mock)

    result = await send_message_to_user(bot, user, 'hello', reply_markup=keyboard)

    assert result is True
    send_mock.assert_awaited_once()
    bot.send_message.assert_not_awaited()
    mark_user_unblocked_mock.assert_awaited_once_with(user)
    mark_user_blocked_mock.assert_not_awaited()


async def test_max_dialog_suspended_marks_user_blocked(mocker):
    bot = mocker.Mock()
    user = mocker.Mock(telegram_id=None, max_id=159706904, pk=42)

    send_mock = mocker.AsyncMock(return_value=SendResult(success=False, reason='max_dialog_suspended'))
    mark_user_unblocked_mock = mocker.AsyncMock()
    mark_user_blocked_mock = mocker.AsyncMock()

    mocker.patch('bot.utils.message_utils.UnifiedSendPort.send', new=send_mock)
    mocker.patch('bot.utils.message_utils.settings.MAX_TRANSPORT_ENABLED', True)
    mocker.patch.object(User, 'mark_user_unblocked', new=mark_user_unblocked_mock)
    mocker.patch.object(User, 'mark_user_blocked', new=mark_user_blocked_mock)

    result = await send_message_to_user_all_channels(bot, user, 'hello')

    assert result is False
    send_mock.assert_awaited_once_with(
        platform='max',
        recipient_id=159706904,
        output=mocker.ANY,
    )
    mark_user_blocked_mock.assert_awaited_once_with(user)
    mark_user_unblocked_mock.assert_not_awaited()


async def test_max_success_marks_user_unblocked(mocker):
    bot = mocker.Mock()
    user = mocker.Mock(telegram_id=None, max_id=159706904, pk=42)

    send_mock = mocker.AsyncMock(return_value=SendResult(success=True, reason='sent'))
    mark_user_unblocked_mock = mocker.AsyncMock()
    mark_user_blocked_mock = mocker.AsyncMock()

    mocker.patch('bot.utils.message_utils.UnifiedSendPort.send', new=send_mock)
    mocker.patch('bot.utils.message_utils.settings.MAX_TRANSPORT_ENABLED', True)
    mocker.patch.object(User, 'mark_user_unblocked', new=mark_user_unblocked_mock)
    mocker.patch.object(User, 'mark_user_blocked', new=mark_user_blocked_mock)

    result = await send_message_to_user_all_channels(bot, user, 'hello')

    assert result is True
    mark_user_unblocked_mock.assert_awaited_once_with(user)
    mark_user_blocked_mock.assert_not_awaited()
