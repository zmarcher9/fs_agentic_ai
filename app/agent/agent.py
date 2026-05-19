"""Core LangChain agent setup, tool binding, and executor for simulation workflows."""

from langchain.agents import AgentExecutor
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.agent.memory import get_conversation_memory
from app.agent.prompts import get_agent_prompt
from app.config import Settings, get_settings
from app.tools.coordinate_translator import coordinate_translator
from app.tools.parameter_builder import build_parameters_tool
from app.tools.parse_results import parse_results_tool
from app.tools.run_simulation import run_simulation_tool


def create_llm(settings: Settings) -> BaseChatModel:
    """Instantiate OpenAI or Anthropic chat model based on LLM_PROVIDER."""
    pass  # TODO: branch on settings.llm_provider; use langchain_openai or langchain_anthropic


def get_tools() -> list[BaseTool]:
    """Return all LangChain tools available to the agent."""
    pass  # TODO: return [coordinate_translator, build_parameters_tool, run_simulation_tool, parse_results_tool]


def create_agent_executor(settings: Settings | None = None) -> AgentExecutor:
    """Build agent with prompt, tools, memory, and executor."""
    pass  # TODO: bind llm + tools + get_agent_prompt(); wrap in AgentExecutor with memory


def get_agent_executor(session_id: str | None = None) -> AgentExecutor:
    """Return a configured agent executor, optionally scoped to a conversation session."""
    pass  # TODO: use get_conversation_memory(session_id) when building executor
