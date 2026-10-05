"""Round-trip tests for the canonical FastAPI application."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

import app.agent.agent as agent_module
from api import main as api_main
from app.core.rate_limiter import chat_rate_limiter, llm_token_budget
from app.core.session_tokens import clear_sessions


@pytest.fixture(autouse=True)
def reset_process_state():
    clear_sessions()
    chat_rate_limiter.reset()
    llm_token_budget.reset()
    agent_module.reset_agent()
    yield
    clear_sessions()
    chat_rate_limiter.reset()
    llm_token_budget.reset()
    agent_module.reset_agent()


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
        return "Use the Wind Speed box in the config bar.", 12

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "How do I set wind speed?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Use the Wind Speed box in the config bar.",
        "session_id": session_id,
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
    class ScriptedAgent:
        async def ainvoke(self, payload, config):
            return {
                "messages": payload["messages"]
                + [AIMessage(content="Click Set Line Ignition in the map drawing row.")]
            }

    monkeypatch.setattr(agent_module, "get_agent", lambda: ScriptedAgent())
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "Where's the ignition line tool?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Click Set Line Ignition in the map drawing row.",
        "session_id": session_id,
    }
