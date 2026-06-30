import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.transports.send_port import SendResult
from bot.utils.message_utils import _build_normalized_output, send_message_to_user
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

    mocker.patch('bot.utils.message_utils.UnifiedSendPort.send', new=send_mock)
    mocker.patch.object(User, 'mark_unblocked', new=mark_unblocked_mock)
    mocker.patch.object(User, 'mark_blocked', new=mark_blocked_mock)

    result = await send_message_to_user(bot, user, 'hello', reply_markup=keyboard)

    assert result is True
    send_mock.assert_awaited_once()
    bot.send_message.assert_not_awaited()
    mark_unblocked_mock.assert_awaited_once_with(123456)
    mark_blocked_mock.assert_not_awaited()
