"""Tests for agent config/UI tools."""

import json

import pytest

from app.agent.tools_config import build_project_config
from app.agent.tools_ui_help import explain_ui_step


def test_build_project_config_valid() -> None:
    out = build_project_config.invoke(
        {
            "center_lat": 33.749,
            "center_lon": -84.388,
            "cell_resolution": 30,
            "cell_space_dimension": 200,
            "wind_speed": 10,
            "wind_degree": 90,
            "total_sim_time": 12000,
        }
    )
    parsed = json.loads(out)
    assert parsed["windDegree"] == 90


def test_build_project_config_invalid_resolution() -> None:
    with pytest.raises(ValueError, match="cell_resolution"):
        build_project_config.invoke(
            {
                "center_lat": 33.749,
                "center_lon": -84.388,
                "cell_resolution": 7,
                "cell_space_dimension": 200,
                "wind_speed": 10,
                "wind_degree": 0,
                "total_sim_time": 12000,
            }
        )


def test_explain_ui_step_known() -> None:
    out = explain_ui_step.invoke({"step": "set_line_ignition"})
    assert "Left-click" in out


def test_explain_ui_step_unknown() -> None:
    out = explain_ui_step.invoke({"step": "not_a_real_step"})
    parsed = json.loads(out)
    assert parsed["error"] == "Unknown step"
    assert "set_line_ignition" in parsed["available_steps"]
