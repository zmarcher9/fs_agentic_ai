"""
Generic per-key sliding-window rate limiter.

Two things live here:
  - SlidingWindowRateLimiter: caps N events per key per time window.
    Used by navigate_rate_limiter (wired into pool.navigate() — see
    app/browser/pool.py) and available for a /chat turn limiter.
  - SessionTokenBudget: caps LLM token usage per session per window.

In-memory, per-process — fine at demo scale. Move to Redis/similar if
you run more than one API worker, since counts won't be shared across
processes otherwise.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class RateLimitExceededError(Exception):
    """Raised by .enforce(). Maps to 429 at the HTTP layer."""


class SlidingWindowRateLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        """Clear all recorded events. For tests / process-local diagnostics."""
        self._events.clear()

    async def check(self, key: str) -> bool:
        """True (and records the event) if under the limit; False (and
        does NOT record) if `key` is already at/over the limit."""
        async with self._lock:
            now = time.monotonic()
            window_start = now - self.window_seconds
            events = self._events[key]
            while events and events[0] < window_start:
                events.pop(0)
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    async def enforce(self, key: str, action: str = "action") -> None:
        """Raises RateLimitExceededError instead of returning False."""
        allowed = await self.check(key)
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded for {action} (session {key!r}): "
                f"max {self.max_events} per {self.window_seconds:.0f}s"
            )


# ---- module-level limiters shared across the process -----------------------

NAVIGATE_MAX_PER_MINUTE = 20
navigate_rate_limiter = SlidingWindowRateLimiter(
    max_events=NAVIGATE_MAX_PER_MINUTE, window_seconds=60.0
)

CHAT_MAX_TURNS_PER_MINUTE = 15
chat_rate_limiter = SlidingWindowRateLimiter(
    max_events=CHAT_MAX_TURNS_PER_MINUTE, window_seconds=60.0
)


class SessionTokenBudget:
    """
    Per-session LLM token budget so a hijacked or looping agent can't
    burn unbounded quota. Call
        await llm_token_budget.enforce(session_id, tokens=usage)
    after each agent turn.
    """

    def __init__(self, max_tokens_per_window: int, window_seconds: float = 3600.0):
        self.max_tokens_per_window = max_tokens_per_window
        self.window_seconds = window_seconds
        self._usage: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        self._usage.clear()

    async def enforce(self, session_id: str, tokens: int) -> None:
        async with self._lock:
            now = time.monotonic()
            window_start = now - self.window_seconds
            entries = self._usage[session_id]
            while entries and entries[0][0] < window_start:
                entries.pop(0)
            used = sum(t for _, t in entries)
            if used + tokens > self.max_tokens_per_window:
                raise RateLimitExceededError(
                    f"Session {session_id!r} exceeded token budget: "
                    f"{used + tokens} > {self.max_tokens_per_window} per "
                    f"{self.window_seconds:.0f}s"
                )
            entries.append((now, tokens))


# Demo-scale default — tune against your real OpenRouter/Anthropic pricing.
llm_token_budget = SessionTokenBudget(max_tokens_per_window=200_000, window_seconds=3600.0)
