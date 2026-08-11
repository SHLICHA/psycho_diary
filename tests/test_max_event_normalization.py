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


def test_normalize_message_callback_extracts_callback_id_and_user():
    update = {
        'update_type': 'message_callback',
        'callback': {
            'callback_id': 'cb_abc123',
            'payload': 'onboarding_agree_1',
            'user': {'user_id': 555},
        },
        'message': {
            # Автор сообщения с кнопкой — бот; не должен стать user_id.
            'sender': {'user_id': 401723968},
            'recipient': {'chat_id': 555, 'user_id': 555},
        },
    }

    event = normalize_update(update)

    assert event is not None
    assert event.event_type == 'message_callback'
    assert event.user_id == 555
    assert event.payload == 'onboarding_agree_1'
    assert event.callback_id == 'cb_abc123'
