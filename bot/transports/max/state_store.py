"""State storage for MAX transport with cache backend and TTL."""

from __future__ import annotations

from django.core.cache import cache


class MaxStateStore:
    """Cache-backed state storage for MAX user state."""

    def __init__(self, ttl_seconds: int = 3600, prefix: str = 'max_state'):
        self.ttl_seconds = max(int(ttl_seconds), 1)
        self.prefix = prefix

    def _key(self, user_id: int) -> str:
        return f'{self.prefix}:{int(user_id)}'

    def get_state(self, user_id: int) -> dict | None:
        value = cache.get(self._key(user_id))
        return value if isinstance(value, dict) else None

    def set_state(self, user_id: int, state: dict) -> None:
        cache.set(self._key(user_id), dict(state or {}), timeout=self.ttl_seconds)

    def clear_state(self, user_id: int) -> None:
        cache.delete(self._key(user_id))
