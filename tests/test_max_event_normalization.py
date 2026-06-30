from bot.transports.max.inbound import normalize_update


def test_normalize_message_created_update_from_polling_payload():
    update = {
        'update_type': 'message_created',
        'message': {
            'sender': {'user_id': 1001},
            'recipient': {'chat_id': 2002},
            'body': {'text': 'hello from max'},
        },
    }

    event = normalize_update(update)

    assert event is not None
    assert event.event_type == 'message_created'
    assert event.user_id == 1001
    assert event.chat_id == 2002
    assert event.text == 'hello from max'


def test_normalize_bot_started_update():
    update = {
        'type': 'bot_started',
        'source': {'user_id': 77, 'chat_id': 88},
    }

    event = normalize_update(update)

    assert event is not None
    assert event.event_type == 'bot_started'
    assert event.user_id == 77
    assert event.chat_id == 88


def test_normalize_update_returns_none_for_unknown_type():
    assert normalize_update({'type': 'unknown'}) is None
