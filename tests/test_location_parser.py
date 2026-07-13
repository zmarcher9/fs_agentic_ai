import pytest

from app.core.location_parser import ParsedLocation, classify_location


# ---- decimal ----------------------------------------------------------

def test_decimal_pair_comma():
    r = classify_location("34.2368, -84.4908")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


def test_decimal_pair_no_comma():
    r = classify_location("34.2368 -84.4908")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


def test_decimal_pair_compact():
    r = classify_location("34.2368,-84.4908")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


# ---- labeled ------------------------------------------------------------

def test_labeled_lat_lon():
    r = classify_location("lat: 34.2368 lon: -84.4908")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


def test_labeled_full_words_case_insensitive():
    r = classify_location("Latitude=34.2368, Longitude=-84.4908")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


# ---- decimal + hemisphere -----------------------------------------------

def test_decimal_hemisphere_spaced():
    r = classify_location("34.2368 N, 84.4908 W")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


def test_decimal_hemisphere_compact():
    r = classify_location("34.2368N 84.4908W")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


def test_decimal_hemisphere_order_independent():
    r = classify_location("84.4908 W, 34.2368 N")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.2368)
    assert r.lon == pytest.approx(-84.4908)


# ---- DMS ------------------------------------------------------------------

def test_dms_symbols():
    r = classify_location("""34°14'12.5"N 84°29'26.7"W""")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34 + 14 / 60 + 12.5 / 3600)
    assert r.lon == pytest.approx(-(84 + 29 / 60 + 26.7 / 3600))


def test_dms_letter_variant():
    r = classify_location("34d14m12.5sN 84d29m26.7sW")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34 + 14 / 60 + 12.5 / 3600)
    assert r.lon == pytest.approx(-(84 + 29 / 60 + 26.7 / 3600))


def test_dms_degrees_only():
    r = classify_location("34°N 84°W")
    assert r.kind == "coordinates"
    assert r.lat == pytest.approx(34.0)
    assert r.lon == pytest.approx(-84.0)


# ---- bounds (hard gate) ----------------------------------------------------

def test_out_of_range_latitude_raises():
    with pytest.raises(ValueError):
        classify_location("95, -84.4908")


def test_out_of_range_longitude_raises():
    with pytest.raises(ValueError):
        classify_location("34.2368, -184.4908")


def test_out_of_range_never_returns_partial():
    try:
        classify_location("95, -84.4908")
        assert False, "expected ValueError"
    except ValueError:
        pass  # no ParsedLocation should have been constructed/returned


# ---- empty / invalid input -------------------------------------------------

def test_empty_string_raises():
    with pytest.raises(ValueError):
        classify_location("")


def test_whitespace_only_raises():
    with pytest.raises(ValueError):
        classify_location("   ")


def test_none_raises():
    with pytest.raises(ValueError):
        classify_location(None)  # type: ignore[arg-type]


# ---- place text -------------------------------------------------------------

def test_free_text_place():
    r = classify_location("near Canton, GA")
    assert r == ParsedLocation(kind="place", raw="near Canton, GA", place_query="near Canton, GA")


def test_simple_place_name():
    r = classify_location("Kennesaw Mountain")
    assert r.kind == "place"
    assert r.place_query == "Kennesaw Mountain"


def test_place_strips_whitespace():
    r = classify_location("  Blue Ridge, GA  ")
    assert r.kind == "place"
    assert r.raw == "Blue Ridge, GA"
    assert r.place_query == "Blue Ridge, GA"


# ---- malformed coordinate attempts (reject, don't silently geocode) --------

def test_three_numbers_hard_fails():
    with pytest.raises(ValueError):
        classify_location("34.2368, -84.4908, 100")


def test_single_bare_number_hard_fails():
    # A lone number is neither a valid place query nor a coordinate pair —
    # fail loudly rather than send "34.2368" to the geocoder.
    with pytest.raises(ValueError):
        classify_location("34.2368")


def test_mixed_place_and_number_treated_as_place():
    r = classify_location("Canton GA 34.2368")
    assert r.kind == "place"
    assert r.place_query == "Canton GA 34.2368"


def test_ambiguous_hemisphere_letters_falls_to_place():
    # "N" and "S" both present but no E/W axis — can't be real coordinates,
    # and the string contains ordinary text, so it should be a place query,
    # not an error.
    r = classify_location("I-85 N Exit 5 S")
    assert r.kind == "place"
