import asyncio

import pytest

from app.browser.pool import (
    BrowserSessionPool,
    MapNotReadyError,
    NoActiveSessionError,
    PoolExhaustedError,
)
from app.core.rate_limiter import navigate_rate_limiter


@pytest.fixture(autouse=True)
def reset_navigate_rate_limiter():
    # Module-level singleton — without this, pool.navigate() tests that share
    # "session-1" leak events (and bounds-error tests consume a quota token).
    navigate_rate_limiter.reset()
    yield
    navigate_rate_limiter.reset()


# ---- fakes standing in for playwright.async_api objects --------------------

class FakePage:
    def __init__(self):
        self._closed = False
        self.goto_calls = []
        self.evaluate_calls = []
        self.evaluate_should_raise = False

    async def goto(self, url):
        self.goto_calls.append(url)

    async def evaluate(self, js, arg):
        if self.evaluate_should_raise:
            raise RuntimeError("No Vue FireMap / Mapbox instance found on page")
        self.evaluate_calls.append((js, arg))
        return True

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True
        for p in self.pages:
            p._closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []
        self.closed = False

    async def new_context(self):
        ctx = FakeContext()
        self.contexts.append(ctx)
        return ctx

    async def close(self):
        self.closed = True


async def _new_pool(max_contexts=8, idle_ttl_seconds=600.0):
    p = BrowserSessionPool(max_contexts=max_contexts, idle_ttl_seconds=idle_ttl_seconds)
    await p.start(browser=FakeBrowser())
    return p


# ---- get_or_create ----------------------------------------------------------

@pytest.mark.asyncio
async def test_same_session_reuses_page():
    pool = await _new_pool()
    entry_a = await pool.get_or_create("session-1")
    entry_b = await pool.get_or_create("session-1")
    assert entry_a is entry_b
    assert entry_a.page.goto_calls == ["http://localhost:5173"]


@pytest.mark.asyncio
async def test_different_sessions_get_different_pages():
    pool = await _new_pool()
    entry_a = await pool.get_or_create("session-1")
    entry_b = await pool.get_or_create("session-2")
    assert entry_a is not entry_b
    assert entry_a.page is not entry_b.page


@pytest.mark.asyncio
async def test_pool_exhausted_raises():
    pool = await _new_pool(max_contexts=2)
    await pool.get_or_create("session-1")
    await pool.get_or_create("session-2")
    with pytest.raises(PoolExhaustedError):
        await pool.get_or_create("session-3")


@pytest.mark.asyncio
async def test_idle_ttl_recreates_context():
    pool = await _new_pool(idle_ttl_seconds=0.05)
    first = await pool.get_or_create("session-1")
    await asyncio.sleep(0.1)
    second = await pool.get_or_create("session-1")
    assert first is not second
    assert first.context.closed is True


@pytest.mark.asyncio
async def test_idle_eviction_frees_room_for_new_session():
    pool = await _new_pool(max_contexts=1, idle_ttl_seconds=0.05)
    await pool.get_or_create("session-1")
    await asyncio.sleep(0.1)
    # session-1 is idle-expired; session-2 should be able to take its slot
    entry = await pool.get_or_create("session-2")
    assert entry is not None


# ---- navigate() ---------------------------------------------------------

@pytest.mark.asyncio
async def test_navigate_success_returns_structured_result():
    pool = await _new_pool()
    result = await pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13)
    assert result["ok"] is True
    assert result["lat"] == 34.2368
    assert result["lon"] == -84.4908
    assert result["zoom"] == 13
    assert result["message"] == "Moved map to 34.2368, -84.4908"


@pytest.mark.asyncio
async def test_navigate_uses_label_in_message():
    pool = await _new_pool()
    result = await pool.navigate(
        session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13, label="Canton, GA"
    )
    assert result["message"] == "Moved map to Canton, GA"


@pytest.mark.asyncio
async def test_navigate_calls_page_evaluate_with_flyto_by_default():
    pool = await _new_pool()
    await pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13)
    entry = await pool.get_or_create("session-1")
    _, arg = entry.page.evaluate_calls[-1]
    lng, lat, zoom, method = arg
    assert (lng, lat, zoom, method) == (-84.4908, 34.2368, 13, "flyTo")


@pytest.mark.asyncio
async def test_navigate_out_of_range_lat_raises_before_touching_page():
    pool = await _new_pool()
    with pytest.raises(ValueError):
        await pool.navigate(session_id="session-1", lat=95.0, lon=-84.4908, zoom=13)
    assert "session-1" not in pool._entries


@pytest.mark.asyncio
async def test_navigate_bad_zoom_raises():
    pool = await _new_pool()
    with pytest.raises(ValueError):
        await pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=999)


@pytest.mark.asyncio
async def test_navigate_empty_session_id_raises_no_active_session():
    pool = await _new_pool()
    with pytest.raises(NoActiveSessionError):
        await pool.navigate(session_id="", lat=34.2368, lon=-84.4908, zoom=13)


@pytest.mark.asyncio
async def test_navigate_dead_page_raises_no_active_session_and_clears_entry():
    pool = await _new_pool()
    entry = await pool.get_or_create("session-1")
    entry.page._closed = True  # simulate a crashed/closed page
    with pytest.raises(NoActiveSessionError):
        await pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13)
    assert "session-1" not in pool._entries  # self-heals: next call recreates


@pytest.mark.asyncio
async def test_navigate_map_not_found_raises_map_not_ready():
    pool = await _new_pool()
    entry = await pool.get_or_create("session-1")
    entry.page.evaluate_should_raise = True
    with pytest.raises(MapNotReadyError):
        await pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13)


@pytest.mark.asyncio
async def test_concurrent_navigates_same_session_serialize():
    pool = await _new_pool()
    entry = await pool.get_or_create("session-1")

    order = []

    original_evaluate = entry.page.evaluate

    async def slow_evaluate(js, arg):
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")
        return await original_evaluate(js, arg)

    entry.page.evaluate = slow_evaluate

    await asyncio.gather(
        pool.navigate(session_id="session-1", lat=34.2368, lon=-84.4908, zoom=13),
        pool.navigate(session_id="session-1", lat=35.0, lon=-85.0, zoom=10),
    )
    # serialized -> start/end pairs never interleave
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_shutdown_closes_all_contexts_and_browser():
    pool = await _new_pool()
    await pool.get_or_create("session-1")
    await pool.get_or_create("session-2")
    browser = pool._browser
    await pool.stop()
    assert pool._entries == {}
    assert browser.closed is True
