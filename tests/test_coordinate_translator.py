"""Tests for natural language location to coordinate translation."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.tools.coordinate_translator import (
    _acres_to_half_degrees,
    _bounding_box_corners,
    _parse_input,
    coordinate_translator,
    resolve_location,
)


def test_parse_input_valid() -> None:
    location, acres = _parse_input("location: Yosemite Valley, acres: 50")
    assert location == "Yosemite Valley"
    assert acres == 50.0


def test_parse_input_invalid_format() -> None:
    with pytest.raises(ValueError, match="Input must be in the format"):
        _parse_input("Yosemite Valley, 50 acres")


def test_acres_to_half_degrees_at_equator() -> None:
    half_lat, half_lon = _acres_to_half_degrees(1.0, 0.0)
    assert half_lat == pytest.approx(half_lon, rel=1e-3)
    assert half_lat > 0


def test_bounding_box_has_four_corners() -> None:
    corners = _bounding_box_corners(37.0, -119.0, 0.01, 0.01)
    assert len(corners) == 4
    for lat, lon in corners:
        assert isinstance(lat, float)
        assert isinstance(lon, float)


@patch("app.tools.coordinate_translator.Nominatim")
def test_resolve_location_success(mock_nominatim: MagicMock) -> None:
    mock_geo = MagicMock()
    mock_geo.latitude = 37.8651
    mock_geo.longitude = -119.5383
    mock_nominatim.return_value.geocode.return_value = mock_geo

    result = resolve_location("location: Yosemite Valley, acres: 10")
    assert result["center_lat"] == 37.8651
    assert result["center_lon"] == -119.5383
    assert result["acres"] == 10.0
    assert result["confirmed"] is False
    assert len(result["bounding_box"]) == 4


@patch("app.tools.coordinate_translator.Nominatim")
def test_resolve_location_no_geocode_result(mock_nominatim: MagicMock) -> None:
    mock_nominatim.return_value.geocode.return_value = None
    with pytest.raises(ValueError, match="Could not geocode"):
        resolve_location("location: nowhereonthemapxyz123, acres: 5")


@patch("app.tools.coordinate_translator.resolve_location")
def test_coordinate_translator_returns_json(mock_resolve: MagicMock) -> None:
    mock_resolve.return_value = {
        "location_query": "location: test, acres: 1",
        "center_lat": 1.0,
        "center_lon": 2.0,
        "bounding_box": [[0.0, 1.0], [0.0, 3.0], [2.0, 3.0], [2.0, 1.0]],
        "acres": 1.0,
        "confirmed": False,
    }
    out = coordinate_translator.invoke({"input": "location: test, acres: 1"})
    parsed = json.loads(out)
    assert parsed["confirmed"] is False
    assert parsed["center_lat"] == 1.0
