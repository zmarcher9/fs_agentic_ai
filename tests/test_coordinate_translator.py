"""Tests for geocoding, sim bounds, and agent tools."""

import json
import math
from unittest.mock import MagicMock, patch

import pytest

from app.agent.tools import (
    build_project_config,
    explain_ui_step,
    geocode_and_configure,
)
from app.core.projection_converter import acres_to_sim_bounds
from app.core.resolve_location import ResolvedLocation


def test_acres_to_sim_bounds_small_area() -> None:
    result = acres_to_sim_bounds(33.75, -84.39, 10.0)
    assert result["cellResolution"] == 30
    assert result["cellSpaceDimension"] == 50
    assert result["side_m"] == pytest.approx(math.sqrt(10 * 4046.856), rel=1e-3)


def test_acres_to_sim_bounds_large_area() -> None:
    result = acres_to_sim_bounds(33.75, -84.39, 5000.0)
    assert result["cellSpaceDimension"] == 200


def test_acres_to_sim_bounds_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        acres_to_sim_bounds(0.0, 0.0, 0.0)


@patch("app.agent.tools.acres_to_sim_bounds")
@pytest.mark.asyncio
async def test_geocode_and_configure(
    mock_bounds: MagicMock,
    monkeypatch,
) -> None:
    async def fake_resolve(location):
        return ResolvedLocation(
            status="resolved",
            lat=33.749,
            lon=-84.388,
            label="Atlanta, Georgia, USA",
            query=location,
        )

    monkeypatch.setattr("app.agent.tools.resolve_location", fake_resolve)
    mock_bounds.return_value = {
        "center_lat": 33.749,
        "center_lon": -84.388,
        "acres": 50.0,
        "side_m": 450.0,
        "cellResolution": 30,
        "cellSpaceDimension": 50,
    }

    out = await geocode_and_configure.ainvoke(
        {"location": "Atlanta, GA", "acres": 50.0}
    )
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["center_lat"] == 33.749
    assert parsed["cellResolution"] == 30


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
