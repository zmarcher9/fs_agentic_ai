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
async def test_enforce_raises():
    lim = SlidingWindowRateLimiter(max_events=1, window_seconds=60.0)
    await lim.enforce("s1", "navigate")
    with pytest.raises(RateLimitExceededError):
        await lim.enforce("s1", "navigate")


@pytest.mark.asyncio
async def test_token_budget_enforces():
    budget = SessionTokenBudget(max_tokens_per_window=100, window_seconds=3600.0)
    await budget.enforce("s1", 60)
    await budget.enforce("s1", 30)
    with pytest.raises(RateLimitExceededError):
        await budget.enforce("s1", 20)


@pytest.mark.asyncio
async def test_different_keys_independent():
    lim = SlidingWindowRateLimiter(max_events=1, window_seconds=60.0)
    await lim.enforce("a")
    await lim.enforce("b")  # other key still allowed
