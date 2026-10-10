import time

import pytest

from app.core.session_tokens import (
    clear_sessions,
    is_valid_session,
    issue_session_token,
    revoke_session,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_sessions()
    yield
    clear_sessions()


def test_issued_token_is_valid():
    token = issue_session_token()
    assert is_valid_session(token)


def test_unknown_token_is_invalid():
    assert not is_valid_session("forged-token")
    assert not is_valid_session(None)
    assert not is_valid_session("")


def test_revoked_token_is_invalid():
    token = issue_session_token()
    revoke_session(token)
    assert not is_valid_session(token)


def test_expired_token_is_invalid(monkeypatch):
    token = issue_session_token()
    # Force issued_at into the past beyond TTL
    from app.core import session_tokens as st

    st._sessions[token] = time.time() - (st.DEFAULT_TOKEN_TTL_SECONDS + 10)
    assert not is_valid_session(token)


def test_issuing_sweeps_expired_tokens_once_registry_is_large(monkeypatch):
    from app.core import session_tokens as st

    monkeypatch.setattr(st, "_EXPIRED_SWEEP_THRESHOLD", 3)
    stale = [issue_session_token() for _ in range(3)]
    for token in stale:
        st._sessions[token] = time.time() - (st.DEFAULT_TOKEN_TTL_SECONDS + 10)

    fresh = issue_session_token()

    assert set(st._sessions) == {fresh}
