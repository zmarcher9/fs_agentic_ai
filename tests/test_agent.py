"""Tests for LangChain agent setup and executor wiring."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent import agent as agent_module
from app.agent.agent import run_agent
from app.agent.registry import TOOLS


def test_get_tools_returns_expected_tools() -> None:
    """Agent should expose config, UI, resolve, and navigate tools."""
    assert len(TOOLS) == 4
    assert {t.name for t in TOOLS} == {
        "build_project_config",
        "explain_ui_step",
        "resolve_location",
        "navigate_map",
    }


def test_run_agent_is_callable() -> None:
    """run_agent should be importable and callable."""
    assert callable(run_agent)


def test_get_agent_uses_current_langchain_factory(monkeypatch) -> None:
    captured = {}
    compiled_agent = object()
    fake_model = object()
    settings = SimpleNamespace(
        openrouter_api_key="test-key",
        llm_model="test-model",
        openrouter_base_url="https://openrouter.example/v1",
    )

    monkeypatch.setattr(agent_module, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: fake_model)

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return compiled_agent

    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)
    agent_module.get_agent.cache_clear()

    assert agent_module.get_agent() is compiled_agent
    assert captured["model"] is fake_model
    assert captured["tools"] is TOOLS
    assert captured["system_prompt"] == agent_module.FIRESIM_SYSTEM_PROMPT
    assert captured["name"] == "firesim_setup_copilot"

    agent_module.get_agent.cache_clear()


@pytest.mark.asyncio
async def test_run_agent_uses_async_graph_invocation(monkeypatch) -> None:
    calls = []

    class FakeAgent:
        async def ainvoke(self, payload, config):
            calls.append((payload, config))
            return {
                "messages": payload["messages"]
                + [AIMessage(content="Async response")]
            }

    agent_module.reset_agent()
    monkeypatch.setattr(agent_module, "get_agent", lambda: FakeAgent())

    reply, tokens, navigated_to = await run_agent("hello", thread_id="session-1")

    assert reply == "Async response"
    assert tokens > 0
    assert navigated_to is None
    assert calls[0][1]["configurable"]["thread_id"] == "session-1"


def test_prune_stale_locks_noop_below_threshold(monkeypatch) -> None:
    """No scan at all until _session_locks actually grows large enough to
    be worth the cost — expired entries just sit there below threshold."""
    agent_module.reset_agent()
    monkeypatch.setattr(agent_module, "_STALE_LOCK_SWEEP_THRESHOLD", 100)
    monkeypatch.setattr(agent_module, "is_valid_session", lambda tid: False)

    agent_module._session_locks["expired-idle"]
    agent_module._prune_stale_locks()

    assert "expired-idle" in agent_module._session_locks
    agent_module.reset_agent()


@pytest.mark.asyncio
async def test_prune_stale_locks_evicts_invalid_unlocked_sessions(monkeypatch) -> None:
    """Once past the threshold: drop locks for sessions whose token is no
    longer valid, but never touch one that's currently held (in-flight)."""
    agent_module.reset_agent()
    monkeypatch.setattr(agent_module, "_STALE_LOCK_SWEEP_THRESHOLD", 1)
    monkeypatch.setattr(agent_module, "is_valid_session", lambda tid: tid == "still-active")

    agent_module._session_locks["still-active"]  # valid session -> kept
    agent_module._session_locks["expired-idle"]  # invalid + unlocked -> pruned
    held_lock = agent_module._session_locks["expired-but-in-flight"]
    await held_lock.acquire()  # invalid but currently in use -> kept regardless
    try:
        agent_module._prune_stale_locks()
        assert set(agent_module._session_locks.keys()) == {
            "still-active",
            "expired-but-in-flight",
        }
    finally:
        held_lock.release()
        agent_module.reset_agent()


@pytest.mark.asyncio
async def test_run_agent_surfaces_last_successful_navigation(monkeypatch) -> None:
    """navigated_to should reflect the last ok navigate_map ToolMessage this turn."""

    class FakeAgent:
        async def ainvoke(self, payload, config):
            return {
                "messages": payload["messages"]
                + [
                    ToolMessage(
                        content=json.dumps(
                            {
                                "ok": False,
                                "error": "map not ready",
                                "lat": 34.0,
                                "lon": -84.0,
                                "label": "Canton, GA",
                            }
                        ),
                        name="navigate_map",
                        tool_call_id="call_1",
                    ),
                    ToolMessage(
                        content=json.dumps(
                            {
                                "ok": True,
                                "lat": 34.2367621,
                                "lon": -84.4907621,
                                "zoom": 13,
                                "label": "Canton, GA",
                                "message": "Moved map to Canton, GA",
                            }
                        ),
                        name="navigate_map",
                        tool_call_id="call_2",
                    ),
                    AIMessage(content="I moved the map to Canton, GA."),
                ]
            }

    agent_module.reset_agent()
    monkeypatch.setattr(agent_module, "get_agent", lambda: FakeAgent())

    reply, _tokens, navigated_to = await run_agent("Move to Canton, GA", thread_id="session-2")

    assert reply == "I moved the map to Canton, GA."
    assert navigated_to == {
        "lat": 34.2367621,
        "lon": -84.4907621,
        "zoom": 13,
        "label": "Canton, GA",
    }
