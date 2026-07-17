"""Round-trip tests for the canonical FastAPI application."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

import app.agent.agent as agent_module
from api import main as api_main
from app.agent.tools_navigate_map import navigate_map
from app.agent.tools_resolve_location import resolve_location_tool
from app.core import resolve_location as resolve_module
from app.core.geocoder import GeocodeCandidate
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
async def test_health_reports_browser_pool_readiness(client, monkeypatch):
    monkeypatch.setattr(
        api_main.pool,
        "readiness",
        lambda: {
            "browser_connected": True,
            "active_contexts": 1,
            "max_contexts": 2,
            "waiting_requests": 0,
        },
    )

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["browser_connected"] is True


@pytest.mark.asyncio
async def test_health_returns_503_when_browser_is_not_ready(client, monkeypatch):
    monkeypatch.setattr(
        api_main.pool,
        "readiness",
        lambda: {
            "browser_connected": False,
            "active_contexts": 0,
            "max_contexts": 2,
            "waiting_requests": 0,
        },
    )

    response = await client.get("/health")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chat_round_trip_awaits_async_agent(client, monkeypatch):
    calls = []

    async def fake_run_agent(user_message: str, thread_id: str):
        calls.append((user_message, thread_id))
        return "The map is ready.", 12

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "Move the map to Canton, Georgia"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "The map is ready.",
        "session_id": session_id,
    }
    assert calls == [("Move the map to Canton, Georgia", session_id)]


@pytest.mark.asyncio
async def test_full_chat_resolve_and_navigation_round_trip(
    client, monkeypatch
):
    async def fake_geocode(query, limit=5, client=None, settings=None):
        return [
            GeocodeCandidate(
                lat=34.2368,
                lon=-84.4908,
                display_name="Canton, Cherokee County, Georgia, USA",
                importance=0.9,
            )
        ]

    monkeypatch.setattr(resolve_module, "geocode", fake_geocode)
    navigation_calls = []

    async def fake_navigate(**kwargs):
        navigation_calls.append(kwargs)
        return {
            "ok": True,
            "lat": kwargs["lat"],
            "lon": kwargs["lon"],
            "zoom": kwargs["zoom"] or 13,
            "label": kwargs["label"],
            "message": f"Moved map to {kwargs['label']}",
        }

    monkeypatch.setattr("app.agent.tools_navigate_map.pool.navigate", fake_navigate)

    class ScriptedAgent:
        async def ainvoke(self, payload, config):
            user_text = payload["messages"][0].content
            resolved = json.loads(
                await resolve_location_tool.ainvoke({"text": user_text}, config=config)
            )
            moved = json.loads(
                await navigate_map.ainvoke(
                    {
                        "lat": resolved["lat"],
                        "lon": resolved["lon"],
                        "label": resolved["label"],
                    },
                    config=config,
                )
            )
            return {
                "messages": payload["messages"]
                + [AIMessage(content=moved["message"])]
            }

    monkeypatch.setattr(agent_module, "get_agent", lambda: ScriptedAgent())
    session_id = await _new_session(client)

    response = await client.post(
        "/chat",
        headers={"X-Session-Id": session_id},
        json={"message": "Canton, Georgia"},
    )

    assert response.status_code == 200
    assert "Moved map to Canton" in response.json()["reply"]
    assert len(navigation_calls) == 1
    assert navigation_calls[0]["session_id"] == session_id
    assert navigation_calls[0]["source"] == "tool"
