import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import routes_map
from app.browser.pool import MapNotReadyError, NoActiveSessionError, PoolExhaustedError
from app.core.rate_limiter import navigate_rate_limiter
from app.core.session_tokens import clear_sessions, issue_session_token


def make_app():
    app = FastAPI()
    app.include_router(routes_map.router)
    return app


VALID_BODY = {"lat": 34.2368, "lon": -84.4908, "zoom": 13, "label": "Canton, GA"}


@pytest.fixture(autouse=True)
def reset_auth_and_limits():
    clear_sessions()
    navigate_rate_limiter.reset()
    yield
    clear_sessions()
    navigate_rate_limiter.reset()


@pytest.fixture
async def client():
    app = make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def session_headers():
    token = issue_session_token()
    return {"X-Session-Id": token}


# ---- auth ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_session_header_returns_401(client):
    resp = await client.post("/api/map/navigate", json=VALID_BODY)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forged_session_header_returns_401(client):
    resp = await client.post(
        "/api/map/navigate",
        json=VALID_BODY,
        headers={"X-Session-Id": "not-issued-by-server"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_session_header_passes_auth(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        return {
            "ok": True,
            "lat": kwargs["lat"],
            "lon": kwargs["lon"],
            "zoom": kwargs["zoom"] or 13,
            "label": kwargs["label"],
            "message": "Moved map to Canton, GA",
        }

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 200


# ---- happy path -----------------------------------------------------------

@pytest.mark.asyncio
async def test_success_response_shape(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        return {
            "ok": True,
            "lat": kwargs["lat"],
            "lon": kwargs["lon"],
            "zoom": kwargs["zoom"] or 13,
            "label": kwargs["label"],
            "message": "Moved map to Canton, GA",
        }

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    body = resp.json()
    assert body == {
        "ok": True,
        "lat": 34.2368,
        "lon": -84.4908,
        "zoom": 13,
        "label": "Canton, GA",
        "message": "Moved map to Canton, GA",
    }


# ---- schema-level validation (422) ----------------------------------------

@pytest.mark.asyncio
async def test_out_of_range_lat_returns_422(client, session_headers):
    bad = {**VALID_BODY, "lat": 95.0}
    resp = await client.post(
        "/api/map/navigate", json=bad, headers=session_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_out_of_range_zoom_returns_422(client, session_headers):
    bad = {**VALID_BODY, "zoom": 999}
    resp = await client.post(
        "/api/map/navigate", json=bad, headers=session_headers
    )
    assert resp.status_code == 422


# ---- pool error -> HTTP status mapping ------------------------------------

@pytest.mark.asyncio
async def test_no_active_session_returns_404(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        raise NoActiveSessionError("session dead")

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pool_exhausted_returns_503(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        raise PoolExhaustedError("pool full")

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_map_not_ready_returns_503(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        raise MapNotReadyError("map instance not found")

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_value_error_from_pool_returns_422(client, monkeypatch, session_headers):
    async def fake_navigate(**kwargs):
        raise ValueError("bad zoom somehow slipped past schema")

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rate_limit_returns_429(client, monkeypatch, session_headers):
    from app.core.rate_limiter import RateLimitExceededError

    async def fake_navigate(**kwargs):
        raise RateLimitExceededError("too many")

    monkeypatch.setattr(routes_map.pool, "navigate", fake_navigate)
    resp = await client.post(
        "/api/map/navigate", json=VALID_BODY, headers=session_headers
    )
    assert resp.status_code == 429
