import pytest
from types import SimpleNamespace
from unittest.mock import patch

from users.models import User
from bot.transports.max.inbound import (
    extract_message_callback_payload,
    parse_merge_target_callback,
    process_merge_target_callback,
)


pytestmark = pytest.mark.django_db


def test_extract_message_callback_payload_from_callback_sender():
    update = {
        'type': 'message_callback',
        'callback': {
            'sender': {'user_id': 445566},
            'payload': 'merge_target:yes:10',
        },
    }

    user_id, payload = extract_message_callback_payload(update)

    assert user_id == 445566
    assert payload == 'merge_target:yes:10'


def test_parse_merge_target_callback_success():
    update = {
        'type': 'message_callback',
        'callback': {
            'sender': {'user_id': 1122},
            'payload': 'merge_target:no:77',
        },
    }

    parsed = parse_merge_target_callback(update)

    assert parsed == (1122, 'no', 77)


def test_process_merge_target_callback_ignores_non_callback_update():
    result = process_merge_target_callback({'type': 'message_new'})

    assert result == {'ok': True, 'ignored': True}


def test_process_merge_target_callback_ignores_missing_target_user():
    update = {
        'type': 'message_callback',
        'callback': {
            'sender': {'user_id': 998877},
            'payload': 'merge_target:yes:123',
        },
    }

    result = process_merge_target_callback(update)

    assert result == {'ok': True, 'ignored': True}


def test_process_merge_target_callback_calls_email_merge_service():
    target_user = User.objects.create_user(
        username='inbound_target',
        email='inbound-target@example.com',
        max_id=700777,
    )
    update = {
        'update_type': 'message_callback',
        'callback': {
            'sender': {'user_id': target_user.max_id},
            'payload': 'merge_target:yes:55',
        },
    }

    with patch('bot.transports.max.inbound.EmailMergeService.confirm_target_transport_by_request_id') as mock_confirm:
        mock_confirm.return_value = SimpleNamespace(status='confirmed', code=None)
        result = process_merge_target_callback(update)

    assert result == {'ok': True, 'status': 'confirmed', 'code': None}
    mock_confirm.assert_called_once_with(
        target_user=target_user,
        merge_request_id=55,
        approve=True,
    )
