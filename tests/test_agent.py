"""Tests for the single-call agent (app/agent/agent.py) with a scripted model."""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent import agent as agent_module
from app.agent.agent import AgentAnswer, TurnResult, _content_to_text, run_agent
from app.agent.prompts import build_system_prompt
from app.core.rate_limiter import RateLimitExceededError, llm_token_budget


def _raw(total_tokens: int = 100, cache_read: int = 0, content: str = "") -> AIMessage:
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": total_tokens - 10,
            "output_tokens": 10,
            "total_tokens": total_tokens,
            "input_token_details": {"cache_read": cache_read},
        },
    )


class ScriptedChain:
    """Stands in for ChatOpenAI.with_structured_output(..., include_raw=True)."""

    def __init__(self, outputs: list[dict]):
        self.outputs = list(outputs)
        self.calls: list[list] = []

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        return self.outputs.pop(0)


def _answer(reply: str, highlight=(), **raw) -> dict:
    return {"raw": _raw(**raw), "parsed": AgentAnswer(reply=reply, highlight=list(highlight))}


@pytest.fixture(autouse=True)
def _reset_agent_state():
    agent_module.reset_agent()
    llm_token_budget.reset()
    yield
    agent_module.reset_agent()
    llm_token_budget.reset()


@pytest.fixture
def settings(monkeypatch):
    settings = SimpleNamespace(
        openrouter_api_key="test-key",
        llm_model="anthropic/test-model",
        openrouter_base_url="https://openrouter.example/v1",
        llm_timeout_seconds=12.0,
        llm_max_retries=1,
        llm_max_concurrent_turns=4,
        llm_history_turns=2,
        llm_reasoning_effort=None,
        llm_max_output_tokens=2048,
    )
    monkeypatch.setattr(agent_module, "get_settings", lambda: settings)
    return settings


def _use(monkeypatch, chain: ScriptedChain) -> ScriptedChain:
    monkeypatch.setattr(agent_module, "get_chain", lambda: chain)
    return chain


def test_get_chain_uses_openrouter_structured_output_without_tools(monkeypatch, settings) -> None:
    llm_kwargs = {}
    structured_kwargs = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            llm_kwargs.update(kwargs)

        def bind_tools(self, *args, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("the Q&A helper must not be given tools")

        def with_structured_output(self, schema, **kwargs):
            structured_kwargs.update(kwargs, schema=schema)
            return "chain"

    settings.llm_reasoning_effort = "low"
    monkeypatch.setattr(agent_module, "ChatOpenAI", FakeChatOpenAI)
    agent_module.get_chain.cache_clear()

    assert agent_module.get_chain() == "chain"
    assert llm_kwargs["base_url"] == "https://openrouter.example/v1"
    assert llm_kwargs["timeout"] == 12.0 and llm_kwargs["max_retries"] == 1
    assert llm_kwargs["max_tokens"] == 2048  # caps what one call can bill
    assert llm_kwargs["extra_body"] == {"reasoning": {"effort": "low"}}
    # function_calling would force tool_choice, which current Anthropic
    # models reject; json_schema is OpenRouter structured outputs.
    assert structured_kwargs == {"schema": AgentAnswer, "method": "json_schema", "include_raw": True}


@pytest.mark.asyncio
async def test_one_model_call_per_question_with_cached_system_prompt(monkeypatch, settings) -> None:
    chain = _use(monkeypatch, ScriptedChain([_answer("Use Wind Degree.", ["wind_degree"])]))

    await run_agent("How do I set wind direction?", thread_id="t")

    assert len(chain.calls) == 1
    system = chain.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert system.content == [
        {"type": "text", "text": build_system_prompt(), "cache_control": {"type": "ephemeral"}}
    ]


@pytest.mark.asyncio
async def test_highlight_keys_are_resolved_and_hostile_ones_dropped(monkeypatch, settings) -> None:
    _use(
        monkeypatch,
        ScriptedChain(
            [
                _answer(
                    "Type it into Wind Degree.",
                    ["Wind Degree", "wind_degree", "../../.env", "navigate_map", "wind_speed"],
                )
            ]
        ),
    )

    result = await run_agent("q", thread_id="t")

    assert result.ui_steps == ["wind_degree", "wind_speed"]


@pytest.mark.asyncio
async def test_tokens_are_per_call_with_cache_reads_at_ten_percent(monkeypatch, settings) -> None:
    _use(
        monkeypatch,
        ScriptedChain(
            [
                _answer("one", total_tokens=5000, cache_read=0),
                _answer("two", total_tokens=5000, cache_read=4000),
                _answer("three", total_tokens=5000, cache_read=4000),
            ]
        ),
    )

    charges = [(await run_agent(f"q{i}", thread_id="t")).tokens_used for i in range(3)]

    # Never cumulative over the thread (the old bug charged 1x, 2x, 3x…).
    assert charges == [5000, 1400, 1400]


@pytest.mark.asyncio
async def test_history_is_trimmed_to_the_configured_window(monkeypatch, settings) -> None:
    chain = _use(monkeypatch, ScriptedChain([_answer(f"a{i}") for i in range(4)]))

    for i in range(4):
        await run_agent(f"q{i}", thread_id="t")

    last_call = chain.calls[-1]
    assert [m.content for m in last_call[1:]] == ["q1", "a1", "q2", "a2", "q3"]
    assert isinstance(last_call[-1], HumanMessage)
    assert len(agent_module._histories["t"]) == 4  # never stores more than the window


@pytest.mark.asyncio
async def test_sessions_do_not_share_history(monkeypatch, settings) -> None:
    chain = _use(monkeypatch, ScriptedChain([_answer("for A"), _answer("for B")]))

    await run_agent("from A", thread_id="a")
    await run_agent("from B", thread_id="b")

    assert [m.content for m in chain.calls[1][1:]] == ["from B"]


@pytest.mark.asyncio
async def test_unparsed_output_falls_back_to_raw_json_then_text(monkeypatch, settings) -> None:
    _use(
        monkeypatch,
        ScriptedChain(
            [
                {"raw": _raw(content='{"reply": "From JSON.", "highlight": ["close_project"]}'), "parsed": None},
                {"raw": _raw(content="Just text."), "parsed": None},
            ]
        ),
    )

    first = await run_agent("q", thread_id="t")
    second = await run_agent("q", thread_id="t")

    assert (first.reply, first.ui_steps) == ("From JSON.", ["close_project"])
    assert (second.reply, second.ui_steps) == ("Just text.", [])


@pytest.mark.parametrize(
    "output",
    [
        {"raw": _raw(content=""), "parsed": None},
        # Haiku 4.5 returned exactly this as a "reply" in the model comparison.
        {"raw": _raw(), "parsed": AgentAnswer(reply=": ", highlight=["show_cell_info"])},
        # Structured output cut off at max_tokens: never show the JSON fragment.
        {"raw": _raw(content='{"reply": "1. Click Set Line Ignition, then left-cl'), "parsed": None},
    ],
)
@pytest.mark.asyncio
async def test_empty_answer_raises_instead_of_reaching_the_user(monkeypatch, settings, output) -> None:
    _use(monkeypatch, ScriptedChain([output]))

    with pytest.raises(ValueError):
        await run_agent("q", thread_id="t")
    assert "t" not in agent_module._histories  # no history for a failed turn
    assert llm_token_budget._usage["t"]  # but the billed call is counted


@pytest.mark.asyncio
async def test_highlight_is_capped_at_three(monkeypatch, settings) -> None:
    keys = ["wind_degree", "wind_speed", "simulation_duration", "start_simulation", "show_results"]
    _use(monkeypatch, ScriptedChain([_answer("Set them.", keys)]))

    assert (await run_agent("q", thread_id="t")).ui_steps == keys[:3]


@pytest.mark.asyncio
async def test_run_agent_returns_turn_result(monkeypatch, settings) -> None:
    _use(monkeypatch, ScriptedChain([_answer("Async response")]))

    result = await run_agent("hello", thread_id="session-1")

    assert isinstance(result, TurnResult)
    assert result.reply == "Async response"
    assert result.tokens_used > 0


@pytest.mark.parametrize(
    "content, expected",
    [
        ("plain", "plain"),
        ([{"type": "text", "text": "Click "}, {"type": "text", "text": "Start Simulation Run."}],
         "Click Start Simulation Run."),
        ([{"type": "reasoning", "reasoning": "hmm"}, {"type": "text", "text": "Answer"}], "Answer"),
        (["a", "b"], "ab"),
        ([], ""),
    ],
)
def test_content_to_text_joins_text_blocks_only(content, expected) -> None:
    assert _content_to_text(content) == expected


def test_prune_stale_locks_noop_below_threshold(monkeypatch) -> None:
    """No scan at all until _session_locks actually grows large enough to
    be worth the cost — expired entries just sit there below threshold."""
    monkeypatch.setattr(agent_module, "_STALE_LOCK_SWEEP_THRESHOLD", 100)
    monkeypatch.setattr(agent_module, "is_valid_session", lambda tid: False)

    agent_module._session_locks["expired-idle"]
    agent_module._prune_stale_locks()

    assert "expired-idle" in agent_module._session_locks


@pytest.mark.asyncio
async def test_prune_stale_locks_evicts_invalid_unlocked_sessions(monkeypatch) -> None:
    """Once past the threshold: drop lock + conversation for sessions whose
    token is no longer valid, but never touch one that's in flight."""
    monkeypatch.setattr(agent_module, "_STALE_LOCK_SWEEP_THRESHOLD", 1)
    monkeypatch.setattr(agent_module, "is_valid_session", lambda tid: tid == "still-active")

    for tid in ("still-active", "expired-idle", "expired-but-in-flight"):
        agent_module._session_locks[tid]
        agent_module._histories[tid] = [HumanMessage("q")]
    held_lock = agent_module._session_locks["expired-but-in-flight"]
    await held_lock.acquire()
    try:
        agent_module._prune_stale_locks()
        assert set(agent_module._session_locks) == {"still-active", "expired-but-in-flight"}
        assert set(agent_module._histories) == {"still-active", "expired-but-in-flight"}
    finally:
        held_lock.release()


class FailingChain:
    def __init__(self, exc: BaseException, then: dict | None = None):
        self.exc, self.then, self.calls = exc, then, 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            raise self.exc
        return self.then


@pytest.mark.asyncio
async def test_provider_error_records_an_estimate_and_leaves_the_session_usable(monkeypatch, settings) -> None:
    _use(monkeypatch, FailingChain(TimeoutError("timed out"), then=_answer("Recovered.")))

    with pytest.raises(TimeoutError):
        await run_agent("q1", thread_id="t")
    assert sum(t for _, t in llm_token_budget._usage["t"]) > 0
    assert not agent_module._session_locks["t"].locked()

    result = await run_agent("q2", thread_id="t")
    assert result.reply == "Recovered."
    assert [m.content for m in agent_module._histories["t"]] == ["q2", "Recovered."]


@pytest.mark.asyncio
async def test_cancelled_turn_is_recorded_and_releases_everything(monkeypatch, settings) -> None:
    class HangingChain:
        async def ainvoke(self, messages):
            await asyncio.sleep(10)

    _use(monkeypatch, HangingChain())
    task = asyncio.create_task(run_agent("q", thread_id="t"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert llm_token_budget._usage["t"]
    assert not agent_module._session_locks["t"].locked()
    assert agent_module._turn_semaphore._value == settings.llm_max_concurrent_turns
    assert "t" not in agent_module._histories


@pytest.mark.asyncio
async def test_exhausted_budget_raises_before_calling_the_model(monkeypatch, settings) -> None:
    chain = _use(monkeypatch, ScriptedChain([_answer("never")]))
    monkeypatch.setattr(llm_token_budget, "max_tokens_per_window", 100)
    llm_token_budget.record_now("t", 100)

    with pytest.raises(RateLimitExceededError):
        await run_agent("q", thread_id="t")
    assert chain.calls == []


@pytest.mark.asyncio
async def test_concurrent_turns_in_one_session_run_in_order(monkeypatch, settings) -> None:
    class SlowChain(ScriptedChain):
        async def ainvoke(self, messages):
            await asyncio.sleep(0.01)
            return await super().ainvoke(messages)

    chain = _use(monkeypatch, SlowChain([_answer("a0"), _answer("a1")]))

    await asyncio.gather(run_agent("q0", thread_id="t"), run_agent("q1", thread_id="t"))

    assert [m.content for m in chain.calls[1][1:]] == ["q0", "a0", "q1"]


@pytest.mark.asyncio
async def test_history_turns_zero_sends_and_keeps_no_history(monkeypatch, settings) -> None:
    settings.llm_history_turns = 0
    chain = _use(monkeypatch, ScriptedChain([_answer("a0"), _answer("a1")]))

    await run_agent("q0", thread_id="t")
    await run_agent("q1", thread_id="t")

    assert [type(m) for m in chain.calls[1]] == [SystemMessage, HumanMessage]
    assert agent_module._histories["t"] == []


@pytest.mark.asyncio
async def test_markdown_is_stripped_before_the_reply_is_stored(monkeypatch, settings) -> None:
    _use(monkeypatch, ScriptedChain([_answer("Click **Start Simulation Run**.")]))

    result = await run_agent("q", thread_id="t")

    assert result.reply == "Click Start Simulation Run."
    assert agent_module._histories["t"][-1].content == "Click Start Simulation Run."
