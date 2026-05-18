"""Tests for natural language location to coordinate translation."""

import pytest

from app.tools.coordinate_translator import CoordinateResult, translate_coordinates


def test_translate_coordinates_returns_result_model() -> None:
    """Translator should return a CoordinateResult with lat/lon."""
    pass  # TODO: result = translate_coordinates("north field near the barn"); assert isinstance(result, CoordinateResult)


def test_translate_coordinates_includes_description() -> None:
    """Result should preserve or normalize the location description."""
    pass  # TODO: result = translate_coordinates("main paddock"); assert result.description


def test_coordinate_result_validates_ranges() -> None:
    """Pydantic model should enforce latitude/longitude bounds when implemented."""
    pass  # TODO: CoordinateResult(latitude=91.0, longitude=0.0) should raise ValidationError
