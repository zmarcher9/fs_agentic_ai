import pytest

from app.core.map_bounds import DEFAULT_ZOOM, MAX_ZOOM, MIN_ZOOM, validate_zoom


def test_none_applies_default():
    assert validate_zoom(None) == DEFAULT_ZOOM


def test_boundary_values_accepted():
    assert validate_zoom(MIN_ZOOM) == MIN_ZOOM
    assert validate_zoom(MAX_ZOOM) == MAX_ZOOM


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        validate_zoom(MIN_ZOOM - 1)
    with pytest.raises(ValueError):
        validate_zoom(MAX_ZOOM + 1)


def test_non_int_raises():
    with pytest.raises(ValueError):
        validate_zoom(13.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_zoom(True)  # type: ignore[arg-type]
