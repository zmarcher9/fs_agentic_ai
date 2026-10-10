"""HTTP client for the local firesim-ai API — used by playwright/guide.py and demo/run_demo.py."""

import os

import requests

from app.config import get_settings

_settings = get_settings()
API_BASE_URL = _settings.api_base_url.rstrip("/")
API_URL = f"{API_BASE_URL}/chat"
SESSION_URL = f"{API_BASE_URL}/api/session"

# Prefer FIRESIM_SESSION_ID if set; otherwise issue a new one.
_SESSION_ID = os.environ.get("FIRESIM_SESSION_ID")


def get_session_id() -> str:
    global _SESSION_ID
    if _SESSION_ID:
        return _SESSION_ID
    resp = requests.post(SESSION_URL, timeout=30)
    resp.raise_for_status()
    _SESSION_ID = resp.json()["session_id"]
    print(f"  Issued session_id={_SESSION_ID[:12]}…")
    return _SESSION_ID


def _post_chat(message: str) -> requests.Response:
    return requests.post(
        API_URL,
        json={"message": message},
        headers={"X-Session-Id": get_session_id()},
        # Longer than the server can take (60 s LLM timeout x 3 attempts,
        # plus queueing) so the guide doesn't give up on a turn still billing.
        timeout=240,
    )


def chat(message: str) -> dict:
    """
    Send a message to the firesim-ai agent and return the parsed response
    ({"reply", "session_id", "highlight"}).

    Sessions live in API process memory with a fixed TTL, so they vanish on
    expiry or any server restart (including every --reload). On a 401, mint
    a fresh session and retry once rather than failing every message after.
    """
    global _SESSION_ID
    resp = _post_chat(message)
    if resp.status_code == 401:
        _SESSION_ID = None
        print("  Session expired or server restarted — starting a new conversation.")
        resp = _post_chat(message)
    resp.raise_for_status()
    return resp.json()
