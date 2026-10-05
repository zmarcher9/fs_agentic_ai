"""Tests for the agent's UI help tool."""

import json

from app.agent.tools_ui_help import _UI_STEPS, explain_ui_step
from playwright_guide.highlighting import KEYWORD_MAP, STEP_SELECTORS

# _UI_STEPS entries that cover several controls (or a control with no
# stable selector yet), so they have no single STEP_SELECTORS key.
_MULTI_CONTROL_STEPS = {"set_dynamic_ignition", "wind_settings", "show_results"}


def test_explain_ui_step_known() -> None:
    out = json.loads(explain_ui_step.invoke({"step": "set_line_ignition"}))
    assert out["step"] == "set_line_ignition"
    assert "Left-click" in out["instructions"]


def test_explain_ui_step_unknown() -> None:
    out = json.loads(explain_ui_step.invoke({"step": "not_a_real_step"}))
    assert out["error"] == "Unknown step"
    assert "set_line_ignition" in out["available_steps"]


def test_ui_step_keys_match_highlight_selectors() -> None:
    # Both files must name the same control the same way (this drifted once:
    # "cell_space_dimension" vs "cell_dimension").
    unmatched = set(_UI_STEPS) - set(STEP_SELECTORS) - _MULTI_CONTROL_STEPS
    assert not unmatched


def test_keyword_map_targets_exist() -> None:
    assert {key for _, key in KEYWORD_MAP} <= set(STEP_SELECTORS)


def test_ui_steps_have_no_actuation_era_phrasing() -> None:
    stale = ("already moved", "apply on the config", "assistant provided", "automatically")
    for key, text in _UI_STEPS.items():
        assert not any(phrase in text.lower() for phrase in stale), key
