"""Tests for LangChain agent setup and executor wiring."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.agent import agent as agent_module
from app.agent.agent import run_agent
from app.agent.tools import TOOLS


def test_get_tools_returns_expected_tools() -> None:
    """Agent should expose geocode, config, UI, resolve, and navigate tools."""
    assert len(TOOLS) == 5
    assert {t.name for t in TOOLS} == {
        "geocode_and_configure",
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

    reply, tokens = await run_agent("hello", thread_id="session-1")

    assert reply == "Async response"
    assert tokens > 0
    assert calls[0][1]["configurable"]["thread_id"] == "session-1"
