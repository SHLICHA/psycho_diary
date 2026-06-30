from bot.transports.max.state_store import MaxStateStore


def test_max_state_store_set_get_clear(db):
    store = MaxStateStore(ttl_seconds=60)

    store.set_state(12345, {'step': 'onboarding', 'foo': 'bar'})
    state = store.get_state(12345)
    assert state == {'step': 'onboarding', 'foo': 'bar'}

    store.clear_state(12345)
    assert store.get_state(12345) is None
