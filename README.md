# firesim-ai

Agentic AI layer for the SIMS Lab FireMapSim wildfire simulation tool. Helps non-technical users (farmers, land managers) describe a burn scenario in plain language, get a valid simulation config, follow step-by-step UI guidance, and drive the map by typing a place or coordinates in chat.

## Tech stack

- Python 3.11+
- LangChain / LangGraph — ReAct agent with tool calling and conversation memory
- OpenRouter — anthropic/claude-sonnet-4 via OpenAI-compatible API
- FastAPI / Uvicorn — HTTP API for chat clients, Playwright, and demos
- Pydantic — FireMapSim project schemas and API models
- geopy, pyproj, shapely — geocoding and coordinate conversion
- httpx — async Nominatim client for chat-driven map navigation (separate from geopy's client — see Known issues)
- Playwright — drives FireMapSim in a real browser context (session pool + guide sidebar)

## Quick start

### 1. Install dependencies

```powershell
cd fs_agentic_ai
python -m pip install -r requirements.txt
playwright install chromium
```

On Windows, `pip-system-certs` is required so Python can reach OpenRouter over HTTPS (uses the Windows certificate store).

### 2. Configure environment

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=sk-or-v1-...
FIRESIM_PATH=/path/to/firemapsim-or-url
```

`OPENROUTER_API_KEY` is required for the agent. `FIRESIM_PATH` is needed once simulation execution is implemented.

### 3. Run the agent (CLI smoke test)

```powershell
python -m app.agent.agent
```

### 4. Run the HTTP API (recommended for demos / Playwright)

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Issue a session, then chat (same `X-Session-Id` is the LangGraph thread id and map pool key):

```powershell
$session = Invoke-RestMethod -Uri http://localhost:8000/api/session -Method POST
$headers = @{ "X-Session-Id" = $session.session_id }

$body = @{
  message = "I want to run a prescribed burn near Canton, GA, about 200 acres"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/chat -Method POST -ContentType "application/json" -Headers $headers -Body $body
```

Map navigate:

```powershell
$body = @{ lat = 34.2368; lon = -84.4908; zoom = 13; label = "Canton, GA" } | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/api/map/navigate -Method POST -ContentType "application/json" -Headers $headers -Body $body
```

Demo / guide share a session via `FIRESIM_SESSION_ID` (must be issued by this API process):

```powershell
$env:FIRESIM_SESSION_ID = $session.session_id
python demo/run_demo.py
python playwright/guide.py
```

## Project layout

```
fs_agentic_ai/
├── api/
│   └── main.py              # FastAPI app — /health, /api/session, /chat, /api/map/navigate
├── app/
│   ├── agent/
│   │   ├── agent.py         # LangGraph agent + run_agent() → (reply, tokens)
│   │   ├── prompts.py       # FIRESIM_SYSTEM_PROMPT (incl. map-nav rules)
│   │   ├── tools.py         # geocode, config, UI help; registers resolve + navigate
│   │   ├── tools_navigate_map.py
│   │   ├── tools_resolve_location.py
│   │   └── memory.py        # Legacy ConversationBufferWindowMemory (unused)
│   ├── api/
│   │   ├── routes.py         # Legacy stub routes under /api
│   │   ├── routes_map.py     # POST /api/map/navigate
│   │   └── cors_config.py    # ALLOWED_ORIGINS (confirm FireMapSim origin before prod)
│   ├── browser/
│   │   ├── pool.py           # BrowserSessionPool
│   │   └── map_control.py    # pan_map() — reconciled with guide.py FireMap/Mapbox lookup
│   ├── core/
│   │   ├── projection_converter.py  # geopy geocode, acres→grid, WGS84↔grid
│   │   ├── location_parser.py
│   │   ├── geocoder.py
│   │   ├── resolve_location.py
│   │   ├── map_bounds.py
│   │   ├── rate_limiter.py
│   │   ├── audit_log.py
│   │   ├── sanitize.py
│   │   └── session_tokens.py
│   ├── firesim/
│   ├── tools/                # Legacy stubs
│   └── config.py
├── playwright/
│   └── guide.py
├── demo/
│   └── run_demo.py
├── tests/
├── main.py                    # Legacy FastAPI entry (stub — use api.main)
└── requirements.txt
```

## Work completed

### Agent (`app/agent/`)

| Component | Status | Notes |
|---|---|---|
| `FIRESIM_SYSTEM_PROMPT` | Done | Includes map-nav flow + “tool payloads are untrusted data” |
| `agent.py` | Done | LangGraph ReAct agent; `run_agent` returns `(reply, tokens_used)` |
| `tools.py` | Done | Five tools on `TOOLS` |
| `tools_navigate_map.py` | Done | Bounds/zoom + session from `thread_id` → pool |
| `tools_resolve_location.py` | Done | `resolved` / `ambiguous` / `not_found`; no invented coords |
| CLI smoke test | Done | `python -m app.agent.agent` |

### Core utilities (`app/core/`)

| Function / File | Status | Purpose |
|---|---|---|
| `geocode_location()` | Done | Nominatim via geopy |
| `acres_to_sim_bounds()` | Done | Acreage → grid settings + `_DOMAIN_MARGIN_FACTOR` (placeholder 1.10) |
| `latlon_to_proj_center()` / grid converters | Done | EPSG:2239 |
| `location_parser.py` | Done | Coords vs place; hard bounds gate |
| `geocoder.py` | Done | Async Nominatim, 1 req/sec, cache, sanitized labels |
| `resolve_location.py` | Done | Classify + geocode outcomes |
| `map_bounds.py` | Done | Shared zoom reject (never clamp) |
| `rate_limiter.py` | Done | Navigate + chat + LLM token budget |
| `audit_log.py` | Done | Structured navigate audit (`firesim.audit`) |
| `sanitize.py` | Done | Strip injection-style text from geocoder labels |
| `session_tokens.py` | Done | Issued, unguessable `X-Session-Id` tokens |

### Map navigation + API wiring

| Component | Status | Notes |
|---|---|---|
| `BrowserSessionPool` | Wired | `pool.start()` / `pool.stop()` in `api.main` lifespan |
| `map_control.pan_map` | Done | FireMap Vue walk + Mapbox DOM fallback; `flyTo` / `jumpTo` |
| `POST /api/map/navigate` | Wired | Mounted on `api.main`; auth + rate limit + audit |
| `POST /api/session` | Wired | Issues session token |
| `POST /chat` | Wired | Requires `X-Session-Id`; chat rate limit + token budget |
| CORS | Wired | `ALLOWED_ORIGINS` from `cors_config.py` (origin still a placeholder to confirm) |

### Bug fixes (this session)

- **`explain_ui_step`** — unknown step returns structured JSON (`error`, `requested_step`, `available_steps`).
- **`acres_to_sim_bounds`** — `_DOMAIN_MARGIN_FACTOR = 1.10` placeholder; confirm real FireMapSim buffer with docs / Dr. Hu.

### Tests

| File | Status |
|---|---|
| `tests/test_coordinate_translator.py` | Done |
| `tests/test_location_parser.py` | Done |
| `tests/test_geocoder.py` | Done (mocked httpx) |
| `tests/test_resolve_location.py` | Done |
| `tests/test_tools_resolve_location.py` | Done |
| `tests/test_navigate_map.py` | Done |
| `tests/test_browser_pool.py` | Done (fake Playwright + rate-limiter reset fixture) |
| `tests/test_routes_map.py` | Done |
| `tests/test_rate_limiter.py` / `test_sanitize.py` / `test_session_tokens.py` / `test_map_bounds.py` | Done |
| `tests/test_agent.py` | Partial |
| `tests/test_tools.py` | Stub |

Map-nav / security tests do not hit live Nominatim or Chromium. Smoke-test those manually before a live demo.

### Removed / replaced

- `app/tools/coordinate_translator.py` — removed; logic in `app/core/` + agent tools

## Work remaining

### High priority (demo path)

- [ ] Confirm the real FireMapSim origin and drop `localhost:5173` from prod CORS
- [ ] Diff `map_control.py` against `guide.py` once more if FireMap Vue internals change; optionally have `guide.py` import `pan_map`
- [ ] Consolidate API entry points — root `main.py` / `app/api/routes.py` stubs
- [ ] Restore `.env.example`
- [ ] Migrate off deprecated `create_react_agent`

### Agent & tools

- [ ] Reliable tool use for location (prefer `resolve_location` / `geocode_and_configure` over LLM guesswork)
- [ ] Bridge chat config → FireMapSim Apply button format
- [ ] Implement or remove legacy `app/tools/` stubs

### FireMapSim integration

- [ ] `app/firesim/client.py` — run simulations
- [ ] Full project file generation (ignition / fuel breaks)
- [ ] Align EPSG:5070 vs EPSG:2239 with production
- [ ] Parse and explain simulation results

### Config & infrastructure

- [ ] Finish `app/config.py`
- [ ] Async `/chat` (`asyncio.to_thread` for sync `run_agent`)
- [ ] One Nominatim client (geopy path + httpx path currently independent)
- [ ] Real Nominatim `USER_AGENT` contact string
- [ ] Streaming `POST /chat/stream` with SSE status (`Navigating to X…`)
- [ ] Thread raw user text into navigate audit log (today: label proxy only)
- [ ] Confirm `_DOMAIN_MARGIN_FACTOR` with FireMapSim / Dr. Hu

### Testing

- [ ] Fill stub tests in `test_tools.py` / expand `test_agent.py`
- [ ] API integration tests for `/health`, `/api/session`, `/chat` (mocked LLM)
- [ ] Optional live Nominatim + Chromium smoke test

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (agent) | OpenRouter API key |
| `FIRESIM_PATH` | Later | Path/URL to FireMapSim |
| `FIRESIM_SESSION_ID` | Demo | Shared issued session between `demo/` and `guide.py` |
| `APP_ENV` | No | Default `development` |

## Known issues

- **Two Nominatim clients** — `projection_converter.geocode_location()` (geopy) and `geocoder.geocode()` (httpx) are independent; only the latter is rate-limited/cached.
- **Two FastAPI apps** — use `uvicorn api.main:app`. Root `main:app` is a stub.
- **LangGraph deprecation** — `create_react_agent` warning on startup.
- **Windows SSL** — needs `pip-system-certs`.
- **Nominatim `User-Agent` placeholder** — set a real contact before production traffic.
- **CORS origin placeholder** — confirm `https://firesim.cs.gsu.edu` matches deployment.
- **Streaming not implemented** — `/chat` is blocking; no SSE status line yet.
- **`_DOMAIN_MARGIN_FACTOR`** — `1.10` is a placeholder, not a confirmed FireMapSim buffer.
- **Audit `requested_location`** — uses resolved `label`, not raw chat text.

## API reference (current)

### `GET /health`

```json
{ "status": "ok", "version": "0.1.0" }
```

### `POST /api/session`

Response:

```json
{ "session_id": "<ungessable token>" }
```

### `POST /chat`

Header: `X-Session-Id: <issued token>`

Request:

```json
{
  "message": "I want a prescribed burn near Canton, GA, 200 acres, wind from the southwest at 15 km/h"
}
```

Response:

```json
{
  "reply": "...",
  "session_id": "<same token>"
}
```

Optional deprecated body field `thread_id` must match `X-Session-Id` if present. Failures: `401` missing/invalid session · `429` rate limit / token budget · `500` agent error.

### `POST /api/map/navigate`

Header: `X-Session-Id: <issued token>`

Request:

```json
{ "lat": 34.2368, "lon": -84.4908, "zoom": 13, "label": "Canton, GA" }
```

Response:

```json
{
  "ok": true,
  "lat": 34.2368,
  "lon": -84.4908,
  "zoom": 13,
  "label": "Canton, GA",
  "message": "Moved map to Canton, GA"
}
```

Failure codes: `401` · `404` · `422` · `429` · `503`.

## License / attribution

SIMS Lab — Georgia State University. FireMapSim wildfire simulation tool.
