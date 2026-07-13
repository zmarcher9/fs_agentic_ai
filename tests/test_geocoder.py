import time

import httpx
import pytest

from app.core import geocoder
from app.core.geocoder import geocode


@pytest.fixture(autouse=True)
def clear_geocoder_cache():
    geocoder.clear_cache()
    yield
    geocoder.clear_cache()


@pytest.fixture(autouse=True)
def fast_rate_limit(monkeypatch):
    # Keep tests fast; the ordering behavior is checked separately with
    # its own explicit interval below.
    monkeypatch.setattr(geocoder._rate_limiter, "min_interval", 0.0)


def _client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


NOMINATIM_SINGLE = [
    {"lat": "34.2368", "lon": "-84.4908", "display_name": "Canton, Cherokee County, Georgia, USA", "importance": 0.6}
]

NOMINATIM_CLOSE_PAIR = [
    {"lat": "37.9838", "lon": "23.7275", "display_name": "Athens, Greece", "importance": 0.75},
    {"lat": "33.9519", "lon": "-83.3576", "display_name": "Athens, Georgia, USA", "importance": 0.72},
]

NOMINATIM_CLEAR_WINNER = [
    {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France", "importance": 0.9},
    {"lat": "33.6609", "lon": "-95.5555", "display_name": "Paris, Texas, USA", "importance": 0.3},
]


# ---- basic parsing ----------------------------------------------------

@pytest.mark.asyncio
async def test_single_result_parsed():
    def handler(request):
        return httpx.Response(200, json=NOMINATIM_SINGLE)

    async with _client_for(handler) as client:
        results = await geocode("Canton, GA", client=client)

    assert len(results) == 1
    assert results[0].lat == pytest.approx(34.2368)
    assert results[0].lon == pytest.approx(-84.4908)
    assert "Canton" in results[0].display_name


@pytest.mark.asyncio
async def test_empty_results():
    def handler(request):
        return httpx.Response(200, json=[])

    async with _client_for(handler) as client:
        results = await geocode("asdkfjaslkdfjalskdjf nowhere", client=client)

    assert results == []


@pytest.mark.asyncio
async def test_multiple_results_parsed_in_order():
    def handler(request):
        return httpx.Response(200, json=NOMINATIM_CLOSE_PAIR)

    async with _client_for(handler) as client:
        results = await geocode("Athens", client=client)

    assert len(results) == 2
    assert results[0].display_name == "Athens, Greece"
    assert results[1].display_name == "Athens, Georgia, USA"


@pytest.mark.asyncio
async def test_sends_user_agent_header():
    seen = {}

    def handler(request):
        seen["user_agent"] = request.headers.get("user-agent")
        return httpx.Response(200, json=NOMINATIM_SINGLE)

    async with _client_for(handler) as client:
        await geocode("Canton, GA", client=client)

    assert seen["user_agent"] == geocoder.USER_AGENT


# ---- caching ------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeated_query_uses_cache_not_second_request():
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json=NOMINATIM_SINGLE)

    async with _client_for(handler) as client:
        await geocode("Canton, GA", client=client)
        await geocode("Canton, GA", client=client)
        await geocode("canton, ga", client=client)  # case/whitespace-insensitive key

    assert call_count["n"] == 1


# ---- rate limiting --------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limiter_serializes_calls():
    limiter = geocoder._RateLimiter(min_interval=0.05)

    start = time.monotonic()
    await limiter.wait()
    await limiter.wait()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.05
