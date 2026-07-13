"""
Session token issuance — replaces "any string is a valid X-Session-Id"
with server-issued, unguessable tokens.

Call issue_session_token() wherever a chat session starts (first
/chat request, or a dedicated POST /api/session). The returned token
should become both:
  - the X-Session-Id your client sends on every subsequent request,
    including /api/map/navigate
  - the thread_id passed into the LangGraph agent

so navigate and chat are bound to the exact same identity end to end —
once tokens aren't guessable, you can't drive someone else's browser
context by guessing an id.

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


def issue_session_token() -> str:
    """Generate a new, unguessable session token and register it as valid."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time()
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
