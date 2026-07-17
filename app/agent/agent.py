"""LangGraph ReAct agent wiring for the FireMapSim setup co-pilot."""

import asyncio
from collections import defaultdict
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from app.agent.prompts import FIRESIM_SYSTEM_PROMPT
from app.agent.tools import TOOLS
from app.config import get_settings

_turn_semaphore: asyncio.Semaphore | None = None
_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@lru_cache
def get_agent() -> Any:
    """Build the process-wide agent lazily after settings have been validated."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required to run the agent")
    llm = ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
    )
    return create_agent(
        model=llm,
        tools=TOOLS,
        checkpointer=MemorySaver(),
        system_prompt=FIRESIM_SYSTEM_PROMPT,
        name="firesim_setup_copilot",
    )


def reset_agent() -> None:
    """Reset lazy process state for tests or an explicit configuration reload."""
    global _turn_semaphore
    get_agent.cache_clear()
    _turn_semaphore = None
    _session_locks.clear()


def _content_to_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if content:
        block = content[0]
        if isinstance(block, dict):
            return str(block.get("text", block))
        return str(block)
    return ""


async def run_agent(user_message: str, thread_id: str = "default") -> tuple[str, int]:
    """
    Run the FireMapSim co-pilot agent.

    Returns (reply_text, tokens_used). Token count is summed from
    message usage_metadata when the provider reports it; otherwise a
    rough char-based estimate so llm_token_budget still has something to enforce.
    """
    global _turn_semaphore
    if _turn_semaphore is None:
        _turn_semaphore = asyncio.Semaphore(get_settings().llm_max_concurrent_turns)

    # Preserve LangGraph message order within a session while bounding total
    # provider concurrency across independent sessions.
    async with _session_locks[thread_id]:
        async with _turn_semaphore:
            result = await get_agent().ainvoke(
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
    async def _main() -> None:
        text, _tokens = await run_agent(
            "I want to do a prescribed burn near Canton, GA, about 200 acres, "
            "wind from the southwest at 15 km/h"
        )
        print(text)

    asyncio.run(_main())
