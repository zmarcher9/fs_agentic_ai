"""
Generic per-key sliding-window rate limiter.

Two things live here:
  - SlidingWindowRateLimiter: caps N events per key per time window.
    Used by chat_rate_limiter (per /chat turn) and session_issue_limiter
    (per client IP on /api/session) in api/main.py.
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
            # The key is a session token or client IP — never echo it back.
            raise RateLimitExceededError(
                f"Rate limit exceeded for {action}: "
                f"max {self.max_events} per {self.window_seconds:.0f}s"
            )


# ---- module-level limiters shared across the process -----------------------

CHAT_MAX_TURNS_PER_MINUTE = 15
chat_rate_limiter = SlidingWindowRateLimiter(
    max_events=CHAT_MAX_TURNS_PER_MINUTE, window_seconds=60.0
)

# Keyed by client IP. Without this, minting a fresh session resets every
# per-session limit. Behind a reverse proxy all clients share the proxy's IP,
# so keep this generous.
SESSION_ISSUES_PER_MINUTE = 20
session_issue_limiter = SlidingWindowRateLimiter(
    max_events=SESSION_ISSUES_PER_MINUTE, window_seconds=60.0
)


class SessionTokenBudget:
    """
    Per-session LLM token budget so a hijacked or looping agent can't
    burn unbounded quota.

    Usage per turn (app/agent/agent.run_agent, inside the session lock):
        await llm_token_budget.ensure_available(session_id)   # before the LLM call
        ...call the model...
        llm_token_budget.record_now(session_id, tokens)       # always, in a finally

    Checking before the call is what actually caps spend: once a session is
    over budget no further LLM call is made. Recording always succeeds, so a
    turn that pushes the session over — or fails after being billed — is
    still counted.
    """

    def __init__(self, max_tokens_per_window: int, window_seconds: float = 3600.0):
        self.max_tokens_per_window = max_tokens_per_window
        self.window_seconds = window_seconds
        self._usage: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        self._usage.clear()

    def _used(self, session_id: str, now: float) -> int:
        window_start = now - self.window_seconds
        entries = self._usage[session_id]
        while entries and entries[0][0] < window_start:
            entries.pop(0)
        return sum(t for _, t in entries)

    async def ensure_available(self, session_id: str) -> None:
        """Raise if the session has already used its whole budget."""
        async with self._lock:
            used = self._used(session_id, time.monotonic())
            if used >= self.max_tokens_per_window:
                raise RateLimitExceededError(
                    f"Token budget exhausted: {used} >= {self.max_tokens_per_window} "
                    f"per {self.window_seconds:.0f}s"
                )

    def record_now(self, session_id: str, tokens: int) -> None:
        """Record tokens a call actually spent. Never raises and never
        awaits, so it is safe in a `finally` while a request is being
        cancelled (no await means nothing can interleave on the loop)."""
        now = time.monotonic()
        self._used(session_id, now)  # trims expired entries
        self._usage[session_id].append((now, max(0, tokens)))

    async def record(self, session_id: str, tokens: int) -> None:
        async with self._lock:
            self.record_now(session_id, tokens)


# Demo-scale default — tune against your real OpenRouter/Anthropic pricing.
llm_token_budget = SessionTokenBudget(max_tokens_per_window=200_000, window_seconds=3600.0)
