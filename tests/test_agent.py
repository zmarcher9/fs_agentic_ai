"""Tests for LangChain agent setup and executor wiring."""

import pytest

from app.agent.agent import create_agent_executor, create_llm, get_tools
from app.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Minimal settings for agent tests without real API keys."""
    pass  # TODO: return Settings(FIRESIM_PATH="/tmp/firemapsim", LLM_PROVIDER="openai", ...)


def test_get_tools_returns_expected_tools() -> None:
    """Agent should expose coordinate, parameter, run, and parse tools."""
    pass  # TODO: tools = get_tools(); assert len(tools) == 4


def test_create_llm_respects_provider(mock_settings: Settings) -> None:
    """LLM factory should select OpenAI or Anthropic based on settings."""
    pass  # TODO: llm = create_llm(mock_settings); assert llm is not None


def test_create_agent_executor_builds_without_error(mock_settings: Settings) -> None:
    """Executor scaffolding should instantiate with mocked dependencies."""
    pass  # TODO: executor = create_agent_executor(mock_settings); assert executor is not None
