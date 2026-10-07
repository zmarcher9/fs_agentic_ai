"""Tests for the local clients: demo/run_demo.py, playwright/guide.py, and
playwright_guide/api_client.py."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("script", ["demo/run_demo.py", "playwright/guide.py"])
def test_script_imports_when_run_from_anywhere(script, tmp_path):
    # Regression: `python demo/run_demo.py` crashed with ModuleNotFoundError
    # because the project root wasn't on sys.path.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    code = f"import runpy; runpy.run_path({str(REPO_ROOT / script)!r}, run_name='not_main')"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


class _Response:
    def __init__(self, status_code: int, body: dict):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def api_client(monkeypatch):
    from playwright_guide import api_client

    monkeypatch.setattr(api_client, "_SESSION_ID", "expired-session")
    return api_client


def test_chat_mints_a_new_session_and_retries_once_on_401(api_client, monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, (headers or {}).get("X-Session-Id")))
        if url == api_client.SESSION_URL:
            return _Response(200, {"session_id": "fresh-session"})
        if headers["X-Session-Id"] == "expired-session":
            return _Response(401, {"detail": "Missing or invalid X-Session-Id"})
        return _Response(200, {"reply": "ok", "session_id": "fresh-session", "highlight": []})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    assert api_client.chat("q")["reply"] == "ok"
    assert calls == [
        (api_client.API_URL, "expired-session"),
        (api_client.SESSION_URL, None),
        (api_client.API_URL, "fresh-session"),
    ]


def test_chat_gives_up_after_a_second_401(api_client, monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        if url == api_client.SESSION_URL:
            return _Response(200, {"session_id": "also-rejected"})
        return _Response(401, {"detail": "nope"})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="401"):
        api_client.chat("q")
