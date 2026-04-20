"""Tests for bot rate limit middleware behavior."""

import pytest
from django.core.cache import cache

from bot.middlewares.rate_limit_middleware import RateLimitMiddleware


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()


class TestRateLimitMiddleware:
    def test_resolve_scope_for_entry_state(self):
        middleware = RateLimitMiddleware()

        scope, limit, period = middleware._resolve_scope_and_limit(
            "DiaryStates:waiting_for_text_entry"
        )

        assert scope == "entries"
        assert limit == 3
        assert period == 60

    def test_resolve_scope_for_default_state(self):
        middleware = RateLimitMiddleware()

        scope, limit, period = middleware._resolve_scope_and_limit(None)

        assert scope == "default"
        assert isinstance(limit, int)
        assert period == 60

    @pytest.mark.asyncio
    async def test_is_rate_limited_respects_limit_and_period(self):
        middleware = RateLimitMiddleware()
        cache_key = middleware._build_cache_key(telegram_id=1, scope="entries")

        # First 3 requests pass for entries scope.
        for _ in range(3):
            limited = await middleware._is_rate_limited(cache_key, limit=3, period=60)
            assert limited is False
            await middleware._record_request(cache_key, period=60)

        # Next request is limited.
        limited = await middleware._is_rate_limited(cache_key, limit=3, period=60)
        assert limited is True


def test_diary_handler_no_local_rate_limiter_calls():
    """Entry flow should rely on middleware rate limiting only."""
    with open("bot/handlers/diary.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "rate_limiter.is_rate_limited" not in content
