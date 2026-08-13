import pytest
from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.transports.identity_merge_dispatcher import dispatch_target_merge_confirmation
from bot.transports.max.client import MaxClient
from users.models import User
from users.services.email_merge_service import EmailMergeService


pytestmark = pytest.mark.django_db


def test_max_client_serializes_inline_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='OK', callback_data='merge_target:yes:1')],
            [InlineKeyboardButton(text='Cancel', callback_data='merge_target:no:1')],
        ]
    )

    payload = MaxClient._serialize_inline_keyboard(keyboard)

    assert payload is not None
    assert payload[0][0]['text'] == 'OK'
    assert payload[0][0]['payload'] == 'merge_target:yes:1'
    assert payload[1][0]['text'] == 'Cancel'


@pytest.mark.asyncio
async def test_dispatch_target_merge_confirmation_returns_deferred_when_max_transport_disabled(settings):
    settings.MAX_TRANSPORT_ENABLED = False
    uid = uuid4().hex[:8]
    uid_num = int(uid, 16)

    target_user = await User.objects.acreate(
        username=f'max_target_disabled_{uid}',
        email=f'max-disabled-{uid}@example.com',
        max_id=500000000 + uid_num,
    )
    requester_user = await User.objects.acreate(
        username=f'tg_requester_disabled_{uid}',
        email='',
        telegram_id=400000000 + uid_num,
    )

    merge_request = await EmailMergeService.acreate_merge_request(
        requester_user=requester_user,
        email=target_user.email,
        source_platform='telegram',
        source_context='profile_edit',
    )

    result = await dispatch_target_merge_confirmation(merge_request)

    assert result['success'] is False
    assert result['delivery'] == 'max_deferred'
    assert result['reason'] == 'max_transport_disabled'


@pytest.mark.asyncio
async def test_dispatch_target_merge_confirmation_sends_to_max_when_enabled(settings, monkeypatch):
    settings.MAX_TRANSPORT_ENABLED = True
    settings.MAX_BOT_TOKEN = 'token'
    settings.MAX_API_BASE_URL = 'https://platform-api2.max.ru'
    settings.MAX_API_TIMEOUT_SECONDS = 5
    uid = uuid4().hex[:8]
    uid_num = int(uid, 16)

    target_user = await User.objects.acreate(
        username=f'max_target_enabled_{uid}',
        email=f'max-enabled-{uid}@example.com',
        max_id=500000000 + uid_num,
    )
    requester_user = await User.objects.acreate(
        username=f'tg_requester_enabled_{uid}',
        email='',
        telegram_id=400000000 + uid_num,
    )

    merge_request = await EmailMergeService.acreate_merge_request(
        requester_user=requester_user,
        email=target_user.email,
        source_platform='telegram',
        source_context='profile_edit',
    )

    sent_payload = {}

    class FakeMaxClient:
        def __init__(self, api_token, base_url, timeout_seconds):
            sent_payload['api_token'] = api_token
            sent_payload['base_url'] = base_url
            sent_payload['timeout_seconds'] = timeout_seconds

        async def send_message(self, *, user_id, text, reply_markup=None):
            sent_payload['user_id'] = user_id
            sent_payload['text'] = text
            sent_payload['reply_markup'] = reply_markup
            return True, 'fake-mid'

    monkeypatch.setattr('bot.transports.unified_send_port.MaxClient', FakeMaxClient)

    result = await dispatch_target_merge_confirmation(merge_request)

    assert result['success'] is True
    assert result['delivery'] == 'max'
    assert result['reason'] == 'sent'
    assert sent_payload['user_id'] == target_user.max_id
    assert sent_payload['api_token'] == settings.MAX_BOT_TOKEN
