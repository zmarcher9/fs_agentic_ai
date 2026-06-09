"""LangGraph ReAct agent wiring for the FireMapSim setup co-pilot."""

import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import FIRESIM_SYSTEM_PROMPT
from app.agent.tools import TOOLS

load_dotenv()

_llm = ChatOpenAI(
    model="anthropic/claude-sonnet-4-20250514",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    openai_api_base="https://openrouter.ai/api/v1",
).bind_tools(TOOLS)

_agent = create_react_agent(
    model=_llm,
    tools=TOOLS,
    checkpointer=MemorySaver(),
    prompt=FIRESIM_SYSTEM_PROMPT,
)


def _content_to_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if content:
        block = content[0]
        if isinstance(block, dict):
            return str(block.get("text", block))
        return str(block)
    return ""


def run_agent(user_message: str, thread_id: str = "default") -> str:
    """Run the FireMapSim co-pilot agent and return the assistant reply text."""
    result = _agent.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    for message in reversed(result["messages"]):
        if isinstance(message, AIMessage):
            return _content_to_text(message.content)
    raise ValueError("Agent did not return an AIMessage")


if __name__ == "__main__":
    print(
        run_agent(
            "I want to do a prescribed burn near Canton, GA, about 200 acres, "
            "wind from the southwest at 15 km/h"
        )
    )
