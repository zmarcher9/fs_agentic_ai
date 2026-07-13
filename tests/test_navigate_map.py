import json

import pytest
from langchain_core.runnables import RunnableConfig

from app.agent import tools_navigate_map
from app.agent.tools_navigate_map import navigate_map


def _config(thread_id="thread-abc"):
    return RunnableConfig(configurable={"thread_id": thread_id})


@pytest.fixture(autouse=True)
def fake_pool_navigate(monkeypatch):
    """Stand in for BrowserSessionPool.navigate so these tests don't touch
    a real pool/browser — they're only checking the tool's own contract:
    args in, session_id resolved from config, JSON out."""
    calls = []

    async def fake_navigate(session_id, lat, lon, zoom=None, label=None, **kwargs):
        calls.append(dict(session_id=session_id, lat=lat, lon=lon, zoom=zoom, label=label))
        return {
            "ok": True,
            "lat": lat,
            "lon": lon,
            "zoom": zoom or 13,
            "label": label,
            "message": f"Moved map to {label or f'{lat}, {lon}'}",
        }

    monkeypatch.setattr(tools_navigate_map.pool, "navigate", fake_navigate)
    return calls


@pytest.mark.asyncio
async def test_ainvoke_returns_json_string(fake_pool_navigate):
    raw = await navigate_map.ainvoke(
        {"lat": 34.2368, "lon": -84.4908, "zoom": 13}, config=_config()
    )
    result = json.loads(raw)
    assert result["ok"] is True
    assert result["lat"] == 34.2368
    assert result["zoom"] == 13


@pytest.mark.asyncio
async def test_session_id_pulled_from_thread_id(fake_pool_navigate):
    await navigate_map.ainvoke(
        {"lat": 34.2368, "lon": -84.4908, "zoom": 13}, config=_config(thread_id="my-thread-42")
    )
    assert fake_pool_navigate[0]["session_id"] == "my-thread-42"


@pytest.mark.asyncio
async def test_label_passed_through(fake_pool_navigate):
    await navigate_map.ainvoke(
        {"lat": 34.2368, "lon": -84.4908, "zoom": 13, "label": "Canton, GA"},
        config=_config(),
    )
    assert fake_pool_navigate[0]["label"] == "Canton, GA"


@pytest.mark.asyncio
async def test_missing_thread_id_raises_value_error(fake_pool_navigate):
    with pytest.raises(Exception):
        # config with no configurable/thread_id at all
        await navigate_map.ainvoke({"lat": 34.2368, "lon": -84.4908, "zoom": 13}, config={})


@pytest.mark.asyncio
async def test_schema_rejects_out_of_range_lat_before_reaching_pool(fake_pool_navigate):
    # Field(ge=-90, le=90) on NavigateMapInput should reject this before
    # the tool body (and therefore pool.navigate) ever runs.
    with pytest.raises(Exception):
        await navigate_map.ainvoke({"lat": 95.0, "lon": -84.4908, "zoom": 13}, config=_config())
    assert fake_pool_navigate == []


@pytest.mark.asyncio
async def test_schema_rejects_bad_zoom_before_reaching_pool(fake_pool_navigate):
    with pytest.raises(Exception):
        await navigate_map.ainvoke({"lat": 34.2368, "lon": -84.4908, "zoom": 999}, config=_config())
    assert fake_pool_navigate == []


@pytest.mark.asyncio
async def test_zoom_none_passed_through_for_pool_to_default(fake_pool_navigate):
    # The tool no longer resolves DEFAULT_ZOOM itself — that's pool.navigate's
    # job (via validate_zoom), so this confirms None flows through untouched.
    await navigate_map.ainvoke({"lat": 34.2368, "lon": -84.4908}, config=_config())
    assert fake_pool_navigate[0]["zoom"] is None


@pytest.mark.asyncio
async def test_pool_error_surfaces_as_tool_error(monkeypatch):
    from app.browser.pool import NoActiveSessionError

    async def raising_navigate(session_id, lat, lon, zoom=None, label=None, **kwargs):
        raise NoActiveSessionError("session dead")

    monkeypatch.setattr(tools_navigate_map.pool, "navigate", raising_navigate)

    with pytest.raises(Exception):
        await navigate_map.ainvoke(
            {"lat": 34.2368, "lon": -84.4908, "zoom": 13}, config=_config()
        )
