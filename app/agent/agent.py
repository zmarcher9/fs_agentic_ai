"""Core LangChain agent setup, tool binding, and executor for simulation workflows."""

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.agent.memory import get_memory
from app.agent.prompts import FIRESIM_SYSTEM_PROMPT
from app.config import Settings, get_settings
from app.tools.coordinate_translator import coordinate_translator


def create_llm(settings: Settings) -> ChatAnthropic:
    """Create the Anthropic chat model used by the FireMapSim agent."""
    if not settings.anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Add it to your environment or .env file."
        )
    return ChatAnthropic(
        model="claude-sonnet-4-20250514",
        anthropic_api_key=settings.anthropic_api_key,
    )


def get_tools() -> list[BaseTool]:
    """Return agent tools (coordinate translation for current scaffold)."""
    return [coordinate_translator]


def create_agent_executor(settings: Settings | None = None) -> AgentExecutor:
    """Build a configured AgentExecutor with prompt, tools, and memory."""
    settings = settings or get_settings()
    llm = create_llm(settings)
    tools = get_tools()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", FIRESIM_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=get_memory(),
        verbose=True,
    )


def get_agent() -> AgentExecutor:
    """Return the default FireMapSim agent executor."""
    return create_agent_executor()


def get_agent_executor(session_id: str | None = None) -> AgentExecutor:
    """Compatibility alias for existing imports; session_id is currently unused."""
    _ = session_id
    return get_agent()
