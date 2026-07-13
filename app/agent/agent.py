"""LangGraph ReAct agent wiring for the FireMapSim setup co-pilot."""

import os
from pathlib import Path

import pip_system_certs.wrapt_requests  # noqa: F401 — use Windows trust store for HTTPS
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import FIRESIM_SYSTEM_PROMPT
from app.agent.tools import TOOLS

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
if not _openrouter_api_key:
    raise ValueError(
        "OPENROUTER_API_KEY is not set. Add it to the .env file in the project root."
    )

_llm = ChatOpenAI(
    model="anthropic/claude-sonnet-4",
    openai_api_key=_openrouter_api_key,
    openai_api_base="https://openrouter.ai/api/v1",
)

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


def run_agent(user_message: str, thread_id: str = "default") -> tuple[str, int]:
    """
    Run the FireMapSim co-pilot agent.

    Returns (reply_text, tokens_used). Token count is summed from
    message usage_metadata when the provider reports it; otherwise a
    rough char-based estimate so llm_token_budget still has something to enforce.
    """
    result = _agent.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    tokens_used = _estimate_tokens(result["messages"], user_message)
    for message in reversed(result["messages"]):
        if isinstance(message, AIMessage):
            return _content_to_text(message.content), tokens_used
    raise ValueError("Agent did not return an AIMessage")


def _estimate_tokens(messages: list, user_message: str) -> int:
    total = 0
    for message in messages:
        usage = getattr(message, "usage_metadata", None) or {}
        if isinstance(usage, dict) and usage.get("total_tokens"):
            total += int(usage["total_tokens"])
            continue
        meta = getattr(message, "response_metadata", None) or {}
        token_usage = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(token_usage, dict) and token_usage.get("total_tokens"):
            total += int(token_usage["total_tokens"])
    if total > 0:
        return total
    # Fallback when the provider omits usage — approximate, not billing-grade.
    reply_chars = sum(len(_content_to_text(getattr(m, "content", "") or "")) for m in messages)
    return max(1, (len(user_message) + reply_chars) // 4)


if __name__ == "__main__":
    text, _tokens = run_agent(
        "I want to do a prescribed burn near Canton, GA, about 200 acres, "
        "wind from the southwest at 15 km/h"
    )
    print(text)
