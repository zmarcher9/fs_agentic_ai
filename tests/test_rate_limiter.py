import pytest

from app.core.rate_limiter import (
    RateLimitExceededError,
    SessionTokenBudget,
    SlidingWindowRateLimiter,
)


@pytest.mark.asyncio
async def test_sliding_window_allows_under_limit():
    lim = SlidingWindowRateLimiter(max_events=2, window_seconds=60.0)
    assert await lim.check("s1") is True
    assert await lim.check("s1") is True
    assert await lim.check("s1") is False


@pytest.mark.asyncio
async def test_enforce_raises_without_echoing_the_key():
    lim = SlidingWindowRateLimiter(max_events=1, window_seconds=60.0)
    await lim.enforce("secret-session-token", "chat turn")
    with pytest.raises(RateLimitExceededError) as exc_info:
        await lim.enforce("secret-session-token", "chat turn")
    assert "secret-session-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_token_budget_blocks_only_once_exhausted():
    budget = SessionTokenBudget(max_tokens_per_window=100, window_seconds=3600.0)
    await budget.ensure_available("s1")
    await budget.record("s1", 60)
    await budget.ensure_available("s1")
    await budget.record("s1", 70)  # the turn that crosses the line is still recorded
    with pytest.raises(RateLimitExceededError):
        await budget.ensure_available("s1")
    await budget.ensure_available("s2")  # other sessions unaffected


@pytest.mark.asyncio
async def test_token_budget_window_expires(monkeypatch):
    budget = SessionTokenBudget(max_tokens_per_window=100, window_seconds=60.0)
    now = [1000.0]
    monkeypatch.setattr("app.core.rate_limiter.time.monotonic", lambda: now[0])
    await budget.record("s1", 150)
    with pytest.raises(RateLimitExceededError):
        await budget.ensure_available("s1")
    now[0] += 61
    await budget.ensure_available("s1")


@pytest.mark.asyncio
async def test_different_keys_independent():
    lim = SlidingWindowRateLimiter(max_events=1, window_seconds=60.0)
    await lim.enforce("a")
    await lim.enforce("b")  # other key still allowed
