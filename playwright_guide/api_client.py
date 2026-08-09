"""HTTP client for the local firesim-ai API — used by playwright/guide.py."""

import os

import requests

from app.config import get_settings

_settings = get_settings()
API_URL = f"{_settings.api_base_url.rstrip('/')}/chat"
SESSION_URL = f"{_settings.api_base_url.rstrip('/')}/api/session"

# Prefer FIRESIM_SESSION_ID from demo/run_demo.py; otherwise issue a new one.
_SESSION_ID = os.environ.get("FIRESIM_SESSION_ID")


def get_session_id() -> str:
    global _SESSION_ID
    if _SESSION_ID:
        return _SESSION_ID
    resp = requests.post(SESSION_URL, timeout=30)
    resp.raise_for_status()
    _SESSION_ID = resp.json()["session_id"]
    print(f"  Issued session_id={_SESSION_ID[:12]}… (set FIRESIM_SESSION_ID to share with demo)")
    return _SESSION_ID


def chat(message: str) -> dict:
    """
    Send a message to the firesim-ai agent and return the parsed response
    ({"reply", "session_id", "navigated_to"}). navigated_to is set when this
    turn moved the map — the caller uses it to re-pan guide.py's own page.
    """
    session_id = get_session_id()
    resp = requests.post(
        API_URL,
        json={"message": message},
        headers={"X-Session-Id": session_id},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()
