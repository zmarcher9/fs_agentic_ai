"""Tests for LangChain agent setup and executor wiring."""

import pytest

from app.agent.agent import run_agent
from app.agent.tools import TOOLS
from app.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Minimal settings for agent tests without real API keys."""
    pass  # TODO: return Settings(FIRESIM_PATH="/tmp/firemapsim", LLM_PROVIDER="openai", ...)


def test_get_tools_returns_expected_tools() -> None:
    """Agent should expose geocode, config, and UI guidance tools."""
    assert len(TOOLS) == 3


def test_run_agent_is_callable() -> None:
    """run_agent should be importable and callable."""
    assert callable(run_agent)
