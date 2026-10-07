"""The FireMapSim Q&A helper: one structured LLM call per question, via OpenRouter.

There is no tool loop. The whole per-control Step reference sits in the
system prompt, which is sent with a cache_control breakpoint so Anthropic
models behind OpenRouter serve it from the prompt cache (cache reads bill at
~10% of input). The model returns {reply, highlight} as structured output, so
one call both answers and says which controls to highlight — the old agent
loop needed two calls per question for the same thing.
"""

import asyncio
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.prompts import build_system_prompt
from app.agent.ui_steps import resolve_step
from app.config import get_settings
from app.core.rate_limiter import llm_token_budget
from app.core.session_tokens import is_valid_session
from app.core.text_format import strip_markdown

# Cache reads are billed at a tenth of the input price; the token budget
# counts them at that weight so it tracks spend, not raw tokens.
_CACHE_READ_WEIGHT = 0.1

_turn_semaphore: asyncio.Semaphore | None = None
_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
# thread_id -> alternating HumanMessage / AIMessage (plain reply text only).
_histories: dict[str, list[BaseMessage]] = {}

# _session_locks gains one entry per distinct thread_id and never shrinks on
# its own — every request reaching run_agent already passed require_session_id's
# is_valid_session check, so a thread_id whose token has since expired/been
# revoked will never be looked up again and its lock (and its conversation)
# is safe to drop, as long as nothing is actively holding it. Gated on a size
# threshold so ordinary turns don't pay an O(n) scan just to keep it tidy.
_STALE_LOCK_SWEEP_THRESHOLD = 500


class AgentAnswer(BaseModel):
    reply: str = Field(description="Plain-text answer shown to the user word for word.")
    highlight: list[str] = Field(
        default_factory=list,
        description=(
            "Up to 3 step keys from the Step reference for the controls the reply "
            "tells the user to use or find, most important first. Empty for "
            "background, off-topic, or refusal replies."
        ),
    )


@dataclass
class TurnResult:
    reply: str
    # Spend-weighted tokens for this turn (cache reads count at 10%).
    tokens_used: int
    # Valid UI_STEPS keys the answer is about, most relevant first — the
    # guide highlights these instead of guessing from the reply text.
    ui_steps: list[str] = field(default_factory=list)


def _prune_stale_locks() -> None:
    """Evict lock + conversation for sessions that are no longer valid."""
    if len(_session_locks) < _STALE_LOCK_SWEEP_THRESHOLD:
        return
    stale = [
        thread_id
        for thread_id, lock in _session_locks.items()
        if not lock.locked() and not is_valid_session(thread_id)
    ]
    for thread_id in stale:
        _session_locks.pop(thread_id, None)
        _histories.pop(thread_id, None)


@lru_cache
def get_chain() -> Any:
    """Build the process-wide structured-output model lazily."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required to run the agent")
    extra_body = (
        {"reasoning": {"effort": settings.llm_reasoning_effort}}
        if settings.llm_reasoning_effort
        else None
    )
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        # Caps what one call can bill (reasoning tokens count toward it).
        max_tokens=settings.llm_max_output_tokens,
        extra_body=extra_body,
    )
    # json_schema = OpenRouter structured outputs. Deliberately not
    # function_calling: that forces tool_choice, which current Anthropic
    # models reject. The model gets no tools at all.
    return llm.with_structured_output(AgentAnswer, method="json_schema", include_raw=True)


@lru_cache
def _system_message() -> SystemMessage:
    # One text block with a cache breakpoint. Must stay byte-identical across
    # requests or every call pays full price to rewrite the cache.
    return SystemMessage(
        content=[
            {
                "type": "text",
                "text": build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ]
    )


def reset_agent() -> None:
    """Reset lazy process state for tests or an explicit configuration reload."""
    global _turn_semaphore
    get_chain.cache_clear()
    _turn_semaphore = None
    _session_locks.clear()
    _histories.clear()


def _content_to_text(content: str | list) -> str:
    """Join the text blocks of a message; skip reasoning/tool-use blocks."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


_MAX_HIGHLIGHT_STEPS = 3


def _valid_steps(keys: list[str]) -> list[str]:
    """Resolve model-supplied keys/labels; drop unknown ones and duplicates."""
    steps: list[str] = []
    for key in keys:
        step = resolve_step(key) if isinstance(key, str) else None
        if step and step not in steps:
            steps.append(step)
    return steps[:_MAX_HIGHLIGHT_STEPS]


def _answer_from(output: dict) -> AgentAnswer:
    """The parsed answer, or a best-effort recovery from the raw message.

    The reply is converted to plain text here, then checked: a reply like
    ": " (seen from Haiku 4.5), or one that was only markdown, must surface
    as an error, not be shown to the user as the answer.
    """
    answer = output.get("parsed")
    if not isinstance(answer, AgentAnswer):
        text = _raw_text(output.get("raw")).strip()
        try:
            answer = AgentAnswer.model_validate(json.loads(text))
        except (ValueError, TypeError):
            if text.startswith("{"):
                # Structured output that doesn't parse — typically cut off at
                # max_tokens. Never show the user a JSON fragment.
                raise ValueError("Model returned malformed structured output") from None
            answer = AgentAnswer(reply=text)
    answer.reply = strip_markdown(answer.reply)
    if not re.search(r"\w", answer.reply):
        raise ValueError("Model returned an empty answer")
    return answer


def _raw_text(raw: Any) -> str:
    return _content_to_text(getattr(raw, "content", "") or "")


def _spend_tokens(raw: Any, messages: list[BaseMessage]) -> int:
    """Spend-weighted tokens for one billed call, from provider usage."""
    usage = getattr(raw, "usage_metadata", None) or {}
    total = int(usage.get("total_tokens") or 0)
    if total <= 0:
        # Provider omitted usage — approximate, not billing-grade.
        return _estimate_tokens(messages) + max(1, len(_raw_text(raw)) // 4)
    cache_read = int((usage.get("input_token_details") or {}).get("cache_read") or 0)
    return max(1, round(total - cache_read * (1 - _CACHE_READ_WEIGHT)))


def _estimate_tokens(messages: list[BaseMessage]) -> int:
    """Rough input cost of a call whose usage we never saw (timeout, provider
    error, cancellation). The system prompt is assumed cache-read."""
    system_chars = sum(len(_content_to_text(m.content)) for m in messages if isinstance(m, SystemMessage))
    other_chars = sum(len(_content_to_text(m.content)) for m in messages if not isinstance(m, SystemMessage))
    return max(1, round((system_chars * _CACHE_READ_WEIGHT + other_chars) / 4))


def _history_window(thread_id: str) -> list[BaseMessage]:
    turns = get_settings().llm_history_turns
    history = _histories.get(thread_id, [])
    return history[-2 * turns:] if turns else []


async def run_agent(user_message: str, thread_id: str = "default") -> TurnResult:
    """Answer one question in the context of the session's recent history.

    Enforces the session's token budget: raises RateLimitExceededError
    (before any LLM call) once it's exhausted, and records the spend of
    every call that was made — including ones that then fail (empty answer,
    timeout, provider error, cancelled request), since those are billed too.
    """
    global _turn_semaphore
    if _turn_semaphore is None:
        _turn_semaphore = asyncio.Semaphore(get_settings().llm_max_concurrent_turns)

    _prune_stale_locks()

    # Keep each session's turns in order while bounding total provider
    # concurrency across independent sessions. The budget check is inside
    # the session lock so concurrent requests can't all pass it at once.
    async with _session_locks[thread_id]:
        await llm_token_budget.ensure_available(thread_id)
        messages = [_system_message(), *_history_window(thread_id), HumanMessage(user_message)]
        spent = 0
        try:
            async with _turn_semaphore:
                try:
                    output = await get_chain().ainvoke(messages)
                except BaseException:
                    spent = _estimate_tokens(messages)
                    raise
            spent = _spend_tokens(output.get("raw"), messages)
            answer = _answer_from(output)
        finally:
            if spent:
                llm_token_budget.record_now(thread_id, spent)
        history = _histories.setdefault(thread_id, [])
        history.extend([HumanMessage(user_message), AIMessage(answer.reply)])
        # Only the window is ever resent; don't keep more than that.
        del history[: max(0, len(history) - 2 * get_settings().llm_history_turns)]

    return TurnResult(
        reply=answer.reply,
        tokens_used=spent,
        ui_steps=_valid_steps(answer.highlight),
    )


if __name__ == "__main__":
    async def _main() -> None:
        result = await run_agent(
            "How do I set the wind direction, and what does Cell Resolution change?"
        )
        print(result.reply)
        print("highlight:", result.ui_steps, "| tokens:", result.tokens_used)

    asyncio.run(_main())
