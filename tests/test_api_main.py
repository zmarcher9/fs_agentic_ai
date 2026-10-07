"""Round-trip tests for the canonical FastAPI application."""

from __future__ import annotations

import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

import app.agent.agent as agent_module
from api import main as api_main
from app.agent.agent import AgentAnswer, TurnResult
from app.core import rate_limiter
from app.core import session_tokens
from app.core.rate_limiter import chat_rate_limiter, llm_token_budget, session_issue_limiter
from app.core.session_tokens import clear_sessions


def _reset_all():
    clear_sessions()
    chat_rate_limiter.reset()
    session_issue_limiter.reset()
    llm_token_budget.reset()
    agent_module.reset_agent()


@pytest.fixture(autouse=True)
def reset_process_state():
    _reset_all()
    yield
    _reset_all()


@pytest.fixture
async def client():
    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _new_session(client: AsyncClient) -> str:
    response = await client.post("/api/session")
    assert response.status_code == 200
    return response.json()["session_id"]


@pytest.mark.asyncio
async def test_health_is_ready_without_any_browser(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "version": api_main.app.version}


@pytest.mark.asyncio
async def test_chat_round_trip_awaits_async_agent(client, monkeypatch):
    calls = []

    async def fake_run_agent(user_message: str, thread_id: str):
        calls.append((user_message, thread_id))
        return TurnResult("Use the Wind Speed box.", 12, ui_steps=["wind_speed"])

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "How do I set wind speed?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Use the Wind Speed box.",
        "session_id": session_id,
        "highlight": ["wind_speed"],
    }
    assert calls == [("How do I set wind speed?", session_id)]


@pytest.mark.asyncio
async def test_chat_requires_issued_session(client):
    response = await client.post(
        "/chat",
        headers={"X-Session-Id": "guessed-id"},
        json={"message": "hello"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_round_trip_through_real_run_agent(client, monkeypatch):
    class ScriptedChain:
        async def ainvoke(self, messages):
            return {
                "raw": AIMessage(content=""),
                "parsed": AgentAnswer(
                    reply="Click Set Line Ignition in the button row.",
                    highlight=["Set Line Ignition", "not-a-step"],
                ),
            }

    monkeypatch.setattr(agent_module, "get_chain", lambda: ScriptedChain())
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "Where's the ignition line tool?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Click Set Line Ignition in the button row.",
        "session_id": session_id,
        "highlight": ["set_line_ignition"],
    }


def _counting_agent(calls: list, tokens: int = 10):
    async def fake_run_agent(user_message: str, thread_id: str):
        calls.append(user_message)
        return TurnResult("ok", tokens)

    return fake_run_agent


class BillingChain:
    """Fake structured-output chain that bills `tokens` per call."""

    def __init__(self, reply: str = "ok", tokens: int = 150, delay: float = 0.0):
        self.reply, self.tokens, self.delay, self.calls = reply, tokens, delay, 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        raw = AIMessage(
            content="",
            usage_metadata={"input_tokens": self.tokens - 10, "output_tokens": 10, "total_tokens": self.tokens},
        )
        return {"raw": raw, "parsed": AgentAnswer(reply=self.reply)}


def _use_chain(monkeypatch, chain: BillingChain, budget: int) -> BillingChain:
    monkeypatch.setattr(agent_module, "get_chain", lambda: chain)
    monkeypatch.setattr(llm_token_budget, "max_tokens_per_window", budget)
    return chain


@pytest.mark.asyncio
async def test_over_budget_session_stops_calling_the_llm(client, monkeypatch):
    # Regression: the budget used to be checked only after the (billed) LLM
    # call, and over-budget turns were never recorded, so a blocked session
    # kept spending on every request.
    chain = _use_chain(monkeypatch, BillingChain(tokens=150), budget=100)
    session_id = await _new_session(client)
    headers = {"X-Session-Id": session_id}

    first = await client.post("/chat", headers=headers, json={"message": "q"})
    later = [await client.post("/chat", headers=headers, json={"message": "q"}) for _ in range(3)]

    assert first.status_code == 200  # the turn that crosses the line is answered and counted
    assert [r.status_code for r in later] == [429, 429, 429]
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_billed_turn_that_fails_still_counts_against_the_budget(client, monkeypatch):
    # Regression (council review): an empty answer (Haiku once returned ": ")
    # raised after the call was billed, so nothing was recorded and the
    # session could keep spending through 500s.
    chain = _use_chain(monkeypatch, BillingChain(reply=": ", tokens=150), budget=100)
    session_id = await _new_session(client)
    headers = {"X-Session-Id": session_id}

    codes = [(await client.post("/chat", headers=headers, json={"message": "q"})).status_code for _ in range(3)]

    assert codes == [500, 429, 429]
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_provider_error_records_an_estimate(client, monkeypatch):
    class TimingOutChain:
        calls = 0

        async def ainvoke(self, messages):
            TimingOutChain.calls += 1
            raise TimeoutError("provider timed out")

    monkeypatch.setattr(agent_module, "get_chain", lambda: TimingOutChain())
    session_id = await _new_session(client)

    response = await client.post("/chat", headers={"X-Session-Id": session_id}, json={"message": "q"})

    assert response.status_code == 500
    assert sum(t for _, t in llm_token_budget._usage[session_id]) > 0


@pytest.mark.asyncio
async def test_concurrent_requests_in_one_session_cannot_overshoot_the_budget(client, monkeypatch):
    # Regression (council review): the pre-check ran before the session lock,
    # so requests queued behind each other all passed it.
    chain = _use_chain(monkeypatch, BillingChain(tokens=150, delay=0.05), budget=100)
    session_id = await _new_session(client)
    headers = {"X-Session-Id": session_id}

    responses = await asyncio.gather(
        *[client.post("/chat", headers=headers, json={"message": f"q{i}"}) for i in range(3)]
    )

    assert sorted(r.status_code for r in responses) == [200, 429, 429]
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_reply_that_is_empty_once_markdown_is_stripped_is_an_error(client, monkeypatch):
    # "json" has letters, so this only fails if markdown is stripped BEFORE
    # the empty-answer check (council review: "```\n```" passed either way).
    _use_chain(monkeypatch, BillingChain(reply="```json\n```", tokens=10), budget=1000)
    session_id = await _new_session(client)

    response = await client.post("/chat", headers={"X-Session-Id": session_id}, json={"message": "q"})

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_chat_rejects_oversized_message_before_the_agent(client, monkeypatch):
    calls: list = []
    monkeypatch.setattr(api_main, "run_agent", _counting_agent(calls))
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "x" * (api_main.MAX_MESSAGE_CHARS + 1)},
    )

    assert response.status_code == 422
    assert calls == []


@pytest.mark.asyncio
async def test_chat_500_body_does_not_echo_provider_errors(client, monkeypatch):
    async def failing_run_agent(user_message: str, thread_id: str):
        raise RuntimeError("upstream 401: key sk-or-v1-abc invalid at https://openrouter.ai/")

    monkeypatch.setattr(api_main, "run_agent", failing_run_agent)
    session_id = await _new_session(client)

    response = await client.post(
        "/chat", headers={"X-Session-Id": session_id}, json={"message": "q"}
    )

    assert response.status_code == 500
    assert "sk-or" not in response.text
    assert "openrouter" not in response.text


@pytest.mark.asyncio
async def test_chat_turn_rate_limit_returns_429_without_echoing_the_token(client, monkeypatch):
    calls: list = []
    monkeypatch.setattr(api_main, "run_agent", _counting_agent(calls))
    session_id = await _new_session(client)
    headers = {"X-Session-Id": session_id}

    codes = [
        (await client.post("/chat", headers=headers, json={"message": "q"})).status_code
        for _ in range(rate_limiter.CHAT_MAX_TURNS_PER_MINUTE)
    ]
    blocked = await client.post("/chat", headers=headers, json={"message": "q"})

    assert set(codes) == {200}
    assert blocked.status_code == 429
    assert session_id not in blocked.text


@pytest.mark.asyncio
async def test_session_minting_is_throttled_per_client(client):
    codes = [
        (await client.post("/api/session")).status_code
        for _ in range(rate_limiter.SESSION_ISSUES_PER_MINUTE + 1)
    ]

    assert codes[:-1] == [200] * rate_limiter.SESSION_ISSUES_PER_MINUTE
    assert codes[-1] == 429


@pytest.mark.asyncio
async def test_chat_rejects_mismatched_thread_id(client):
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "q", "thread_id": "someone-else"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_rejects_expired_session(client):
    session_id = await _new_session(client)
    session_tokens._sessions[session_id] = time.time() - (
        session_tokens.DEFAULT_TOKEN_TTL_SECONDS + 10
    )

    response = await client.post(
        "/chat", headers={"X-Session-Id": session_id}, json={"message": "q"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_reply_is_plain_text_and_keeps_fenced_steps(client, monkeypatch):
    _use_chain(
        monkeypatch,
        BillingChain(reply="## Steps\n```\n1. Click **Set Line Ignition**.\n```", tokens=10),
        budget=1000,
    )
    session_id = await _new_session(client)

    response = await client.post(
        "/chat", headers={"X-Session-Id": session_id}, json={"message": "q"}
    )

    assert response.json()["reply"] == "Steps\n1. Click Set Line Ignition."
