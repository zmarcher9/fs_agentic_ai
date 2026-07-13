import json

import pytest

from app.agent import tools_resolve_location as tool_module
from app.core.geocoder import GeocodeCandidate
from app.core.resolve_location import ResolvedLocation


def _mock_resolve(monkeypatch, result: ResolvedLocation):
    async def fake(text):
        return result

    monkeypatch.setattr(tool_module, "resolve_location", fake)


@pytest.mark.asyncio
async def test_resolved_shape(monkeypatch):
    _mock_resolve(
        monkeypatch,
        ResolvedLocation(
            status="resolved", lat=34.2368, lon=-84.4908, label="Canton, GA", query="Canton, GA",
            message="Resolved to Canton, GA",
        ),
    )
    raw = await tool_module.resolve_location_tool.ainvoke({"text": "Canton, GA"})
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["status"] == "resolved"
    assert body["lat"] == 34.2368
    assert body["candidates"] == []


@pytest.mark.asyncio
async def test_ambiguous_shape_includes_candidates(monkeypatch):
    _mock_resolve(
        monkeypatch,
        ResolvedLocation(
            status="ambiguous",
            query="Athens",
            candidates=(
                GeocodeCandidate(lat=37.98, lon=23.73, display_name="Athens, Greece"),
                GeocodeCandidate(lat=33.95, lon=-83.36, display_name="Athens, Georgia, USA"),
            ),
            message="That matched several places — did you mean Athens, Greece or Athens, Georgia, USA?",
        ),
    )
    raw = await tool_module.resolve_location_tool.ainvoke({"text": "Athens"})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["status"] == "ambiguous"
    assert body["lat"] is None
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["display_name"] == "Athens, Greece"


@pytest.mark.asyncio
async def test_not_found_shape(monkeypatch):
    _mock_resolve(
        monkeypatch,
        ResolvedLocation(status="not_found", query="nowhere", message="I couldn't find that place."),
    )
    raw = await tool_module.resolve_location_tool.ainvoke({"text": "nowhere"})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["status"] == "not_found"
    assert body["lat"] is None


@pytest.mark.asyncio
async def test_malformed_coordinates_propagates_as_tool_error(monkeypatch):
    async def raising(text):
        raise ValueError("Latitude 95 out of range")

    monkeypatch.setattr(tool_module, "resolve_location", raising)

    with pytest.raises(Exception):
        await tool_module.resolve_location_tool.ainvoke({"text": "95, -84.4908"})
