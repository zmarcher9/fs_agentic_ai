import pytest

from app.core import resolve_location as rl_module
from app.core.geocoder import GeocodeCandidate
from app.core.resolve_location import resolve_location


def _mock_geocode(monkeypatch, candidates):
    async def fake(query, limit=5, client=None):
        return candidates

    monkeypatch.setattr(rl_module, "geocode", fake)


# ---- coordinates: no geocoding involved ------------------------------------

@pytest.mark.asyncio
async def test_coordinates_resolved_without_geocoding(monkeypatch):
    calls = []

    async def fake(query, limit=5, client=None):
        calls.append(query)
        return []

    monkeypatch.setattr(rl_module, "geocode", fake)

    result = await resolve_location("34.2368, -84.4908")

    assert result.status == "resolved"
    assert result.lat == pytest.approx(34.2368)
    assert result.lon == pytest.approx(-84.4908)
    assert result.label is None
    assert calls == []  # geocoder never called for coordinate input


@pytest.mark.asyncio
async def test_malformed_coordinates_raise(monkeypatch):
    _mock_geocode(monkeypatch, [])
    with pytest.raises(ValueError):
        await resolve_location("95, -84.4908")  # out of range, propagated from classify_location


# ---- place: not_found -------------------------------------------------------

@pytest.mark.asyncio
async def test_no_results_returns_not_found(monkeypatch):
    _mock_geocode(monkeypatch, [])

    result = await resolve_location("asdkfjalskdjf nowhere place")

    assert result.status == "not_found"
    assert result.lat is None
    assert "couldn't find" in result.message.lower()


# ---- place: single confident hit -> resolved -------------------------------

@pytest.mark.asyncio
async def test_single_hit_resolved(monkeypatch):
    _mock_geocode(
        monkeypatch,
        [GeocodeCandidate(lat=34.2368, lon=-84.4908, display_name="Canton, GA", importance=0.6)],
    )

    result = await resolve_location("Canton, GA")

    assert result.status == "resolved"
    assert result.lat == pytest.approx(34.2368)
    assert result.label == "Canton, GA"


@pytest.mark.asyncio
async def test_clear_winner_among_multiple_resolved_without_asking(monkeypatch):
    _mock_geocode(
        monkeypatch,
        [
            GeocodeCandidate(lat=48.8566, lon=2.3522, display_name="Paris, France", importance=0.9),
            GeocodeCandidate(lat=33.66, lon=-95.55, display_name="Paris, Texas, USA", importance=0.3),
        ],
    )

    result = await resolve_location("Paris")

    assert result.status == "resolved"
    assert result.label == "Paris, France"


# ---- place: comparably-important results -> ambiguous ---------------------

@pytest.mark.asyncio
async def test_close_importance_scores_returns_ambiguous(monkeypatch):
    _mock_geocode(
        monkeypatch,
        [
            GeocodeCandidate(lat=37.98, lon=23.73, display_name="Athens, Greece", importance=0.75),
            GeocodeCandidate(lat=33.95, lon=-83.36, display_name="Athens, Georgia, USA", importance=0.72),
        ],
    )

    result = await resolve_location("Athens")

    assert result.status == "ambiguous"
    assert result.lat is None  # never guess coordinates for an ambiguous match
    assert len(result.candidates) == 2
    assert "Athens, Greece" in result.message
    assert "Athens, Georgia, USA" in result.message


@pytest.mark.asyncio
async def test_ambiguous_shortlist_capped_at_three(monkeypatch):
    candidates = [
        GeocodeCandidate(lat=float(i), lon=float(i), display_name=f"Place {i}", importance=0.5)
        for i in range(5)
    ]
    _mock_geocode(monkeypatch, candidates)

    result = await resolve_location("Place")

    assert result.status == "ambiguous"
    assert len(result.candidates) == 3
