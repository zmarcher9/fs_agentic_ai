"""
Session token issuance — replaces "any string is a valid X-Session-Id"
with server-issued, unguessable tokens.

Call issue_session_token() wherever a chat session starts (first
/chat request, or a dedicated POST /api/session). The returned token
should become both:
  - the X-Session-Id your client sends on every subsequent request
  - the thread_id that keys the agent's conversation history

so once tokens aren't guessable, you can't read or append to someone
else's conversation by guessing an id.

In-memory registry — fine at demo scale, single process. Move to
Redis/a DB if you run multiple workers or need sessions to survive a
restart.
"""

from __future__ import annotations

import secrets
import time
from typing import Optional

DEFAULT_TOKEN_TTL_SECONDS = 4 * 60 * 60  # 4 hours

_sessions: dict[str, float] = {}  # token -> issued_at (wall clock)

# Expired tokens are otherwise only dropped when someone looks them up again,
# which an abandoned session never does. Sweep on issue once the registry is
# big enough for the O(n) scan to be worth it.
_EXPIRED_SWEEP_THRESHOLD = 1000


def _sweep_expired(now: float, ttl_seconds: float = DEFAULT_TOKEN_TTL_SECONDS) -> None:
    expired = [token for token, issued_at in _sessions.items() if now - issued_at > ttl_seconds]
    for token in expired:
        del _sessions[token]


def issue_session_token() -> str:
    """Generate a new, unguessable session token and register it as valid."""
    now = time.time()
    if len(_sessions) >= _EXPIRED_SWEEP_THRESHOLD:
        _sweep_expired(now)
    token = secrets.token_urlsafe(32)
    _sessions[token] = now
    return token


def is_valid_session(
    token: Optional[str], ttl_seconds: float = DEFAULT_TOKEN_TTL_SECONDS
) -> bool:
    """True if `token` was issued by this process and hasn't expired."""
    if not token:
        return False
    issued_at = _sessions.get(token)
    if issued_at is None:
        return False
    if time.time() - issued_at > ttl_seconds:
        del _sessions[token]
        return False
    return True


def revoke_session(token: str) -> None:
    _sessions.pop(token, None)


def clear_sessions() -> None:
    """Mainly for tests — wipe the in-memory registry."""
    _sessions.clear()
