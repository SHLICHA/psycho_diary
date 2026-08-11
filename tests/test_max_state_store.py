from bot.transports.max.state_store import MaxStateStore


def test_max_state_store_set_get_clear(db):
    store = MaxStateStore(ttl_seconds=60)

    store.set_state(12345, {'step': 'onboarding', 'foo': 'bar'})
    state = store.get_state(12345)
    assert state == {'step': 'onboarding', 'foo': 'bar'}

    store.clear_state(12345)
    assert store.get_state(12345) is None


def test_max_state_store_full_overwrite_wipes_fsm_state(db):
    """Полный set_state без merge стирает fsm — так ломался онбординг в runtime."""
    store = MaxStateStore(ttl_seconds=60)
    store.set_state(42, {'fsm_state': 'OnboardingStates:waiting_for_agreement_1', 'origin': 'x'})

    raw = store.get_state(42) or {}
    raw['chat_id'] = 99
    store.set_state(42, raw)
    assert store.get_state(42)['fsm_state'] == 'OnboardingStates:waiting_for_agreement_1'

    store.set_state(42, {'event_type': 'message_callback'})
    assert 'fsm_state' not in (store.get_state(42) or {})
