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
from app.core.projection_converter import acres_to_sim_bounds, geocode_location


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


@patch("app.core.projection_converter.Nominatim")
def test_geocode_location_success(mock_nominatim: MagicMock) -> None:
    mock_geo = MagicMock()
    mock_geo.latitude = 33.749
    mock_geo.longitude = -84.388
    mock_nominatim.return_value.geocode.return_value = mock_geo

    lat, lon = geocode_location("Atlanta, GA")
    assert lat == 33.749
    assert lon == -84.388


@patch("app.core.projection_converter.Nominatim")
def test_geocode_location_failure(mock_nominatim: MagicMock) -> None:
    mock_nominatim.return_value.geocode.return_value = None
    with pytest.raises(ValueError, match="Could not geocode"):
        geocode_location("nowhereonthemapxyz123")


@patch("app.agent.tools.geocode_location")
@patch("app.agent.tools.acres_to_sim_bounds")
def test_geocode_and_configure(
    mock_bounds: MagicMock,
    mock_geocode: MagicMock,
) -> None:
    mock_geocode.return_value = (33.749, -84.388)
    mock_bounds.return_value = {
        "center_lat": 33.749,
        "center_lon": -84.388,
        "acres": 50.0,
        "side_m": 450.0,
        "cellResolution": 30,
        "cellSpaceDimension": 50,
    }

    out = geocode_and_configure.invoke({"location": "Atlanta, GA", "acres": 50.0})
    parsed = json.loads(out)
    assert parsed["proj_center_lat"] == 33.749
    assert parsed["cellResolution"] == 30
    assert parsed["windSpeed"] == 10


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
    parsed = json.loads(out)
    assert parsed["step"] == "set_line_ignition"
    assert "Left-click" in parsed["explanation"]


def test_explain_ui_step_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown step"):
        explain_ui_step.invoke({"step": "not_a_real_step"})
