# firesim-ai

Agentic AI layer for the SIMS Lab FireMapSim wildfire simulation tool. Helps non-technical users (farmers, land managers) describe a burn scenario in plain language, get a valid simulation config, follow step-by-step UI guidance, and drive the map by typing a place or coordinates in chat.

## Tech stack

- Python 3.11+
- LangChain / LangGraph — ReAct agent with tool calling and conversation memory
- OpenRouter — anthropic/claude-sonnet-4 via OpenAI-compatible API
- FastAPI / Uvicorn — HTTP API for chat clients, Playwright, and demos
- Pydantic — FireMapSim project schemas and API models
- pyproj — coordinate conversion
- httpx — shared async Mapbox/Nominatim geocoding client
- Playwright — drives FireMapSim in a real browser context (session pool + guide sidebar)

## Quick start

### 1. Install dependencies

```powershell
cd fs_agentic_ai
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If Node cannot verify the browser download certificate on managed Windows,
set `NODE_OPTIONS=--use-system-ca` for the install command.

### 2. Configure environment

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=sk-or-v1-...
GEOCODER_PROVIDER=nominatim
FIREMAP_URL=http://localhost:5173
```

Start from `.env.example`. Production requires `GEOCODER_PROVIDER=mapbox`
and `MAPBOX_ACCESS_TOKEN`; public Nominatim is development-only.

### 3. Run the agent (CLI smoke test)

```powershell
python -m app.agent.agent
```

### 4. Run the HTTP API (recommended for demos / Playwright)

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

Use exactly one worker. Authentication, LangGraph memory, rate limits,
geocoder cache, and Playwright browser sessions are process-local.

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

The endpoint reports readiness and returns 503 if Chromium is disconnected.

### Container

The image pins Playwright and its browser image to `1.60.0`:

```powershell
docker compose up --build
```

Compose runs `uvicorn` with `--workers 1`. Secrets are read from `.env` at
runtime and excluded from the Docker build context. If `pip install` fails
during `docker build` with an SSL certificate error (common on corporate
networks), the Dockerfile already trusts PyPI hosts for the install step.

### Browser capacity benchmark

Run this while the real FireMap page is available at `FIREMAP_URL`:

```powershell
python -m scripts.benchmark_playwright --contexts 1 2 4 --output playwright-benchmark.json
```

Use the measured process-tree RSS and CPU results to set
`PLAYWRIGHT_MAX_CONTEXTS` and container resource limits. The deployed-page
benchmark in `benchmarks/playwright-contexts.json` measured approximately
721 MB / 1.07 GB / 1.75 GB loaded RSS for 1 / 2 / 4 contexts. The selected
default is 2 contexts with a 2 GiB, 2 CPU Compose limit.

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
│   │   ├── routes_map.py     # POST /api/map/navigate
│   │   └── cors_config.py    # CORS allowlist from settings
│   ├── browser/
│   │   ├── pool.py           # BrowserSessionPool (semaphore + readiness)
│   │   └── map_control.py    # pan_map() — reconciled with guide.py FireMap/Mapbox lookup
│   ├── core/
│   │   ├── projection_converter.py  # acres→grid, WGS84↔grid
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
├── benchmarks/
│   └── playwright-contexts.json
├── scripts/
│   └── benchmark_playwright.py
├── main.py                    # Re-exports api.main:app; uvicorn --workers 1
├── Dockerfile
├── compose.yaml
├── .env.example
├── requirements.in
├── requirements.lock
└── requirements.txt
```

## Work completed

### Agent (`app/agent/`)

| Component | Status | Notes |
|---|---|---|
| `FIRESIM_SYSTEM_PROMPT` | Done | Includes map-nav flow + “tool payloads are untrusted data” |
| `agent.py` | Done | LangGraph ReAct agent; async `run_agent` → `ainvoke` → `(reply, tokens_used)` |
| `tools.py` | Done | Five tools on `TOOLS` |
| `tools_navigate_map.py` | Done | Bounds/zoom + session from `thread_id` → pool |
| `tools_resolve_location.py` | Done | `resolved` / `ambiguous` / `not_found`; no invented coords |
| CLI smoke test | Done | `python -m app.agent.agent` |

### Core utilities (`app/core/`)

| Function / File | Status | Purpose |
|---|---|---|
| `acres_to_sim_bounds()` | Done | Acreage → grid settings + `_DOMAIN_MARGIN_FACTOR` (placeholder 1.10) |
| `latlon_to_proj_center()` / grid converters | Done | EPSG:2239 |
| `location_parser.py` | Done | Coords vs place; hard bounds gate |
| `geocoder.py` | Done | Single async Mapbox/Nominatim path; TTL cache; sanitized labels |
| `resolve_location.py` | Done | Classify + geocode outcomes |
| `map_bounds.py` | Done | Shared zoom reject (never clamp) |
| `rate_limiter.py` | Done | Navigate + chat + LLM token budget |
| `audit_log.py` | Done | Structured navigate audit with raw `requested_text` + `resolved_label` |
| `sanitize.py` | Done | Strip injection-style text from geocoder labels |
| `session_tokens.py` | Done | Issued, unguessable `X-Session-Id` tokens |
| `config.py` | Done | Pydantic settings for LLM, geocoder, Playwright, CORS, FireMap URL |

### Map navigation + API wiring

| Component | Status | Notes |
|---|---|---|
| `BrowserSessionPool` | Wired | Env-configured semaphore; readiness on `/health` |
| `map_control.pan_map` | Done | FireMap Vue walk + Mapbox DOM fallback; `flyTo` / `jumpTo` |
| `POST /api/map/navigate` | Wired | Mounted on `api.main`; auth + rate limit + audit |
| `POST /api/session` | Wired | Issues session token |
| `POST /chat` | Wired | `await run_agent()` / LangGraph `ainvoke` (not `to_thread`) |
| CORS | Wired | From `CORS_ORIGINS`; production rejects localhost origins |

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
| `tests/test_api_main.py` | Done (`/health`, `/api/session`, `/chat`, resolve→navigate) |
| `tests/test_adversarial_agent.py` | Done (grant gate + malicious geocoder labels) |
| `tests/test_config.py` / `test_audit_log.py` | Done |
| `tests/test_rate_limiter.py` / `test_sanitize.py` / `test_session_tokens.py` / `test_map_bounds.py` | Done |
| `tests/test_agent.py` | Done (tool registry + async `ainvoke`) |
| `tests/test_tools.py` | Skipped — legacy simulation stubs not implemented |

Map-nav / security tests do not hit live Nominatim or Chromium. Smoke-test those manually before a live demo.

### Removed / replaced

- `app/tools/coordinate_translator.py` — removed; logic in `app/core/` + agent tools
- `projection_converter.geocode_location()` / geopy — removed; all lookups go through `app.core.geocoder`
- Dual FastAPI stubs (`app/api/routes.py`, incomplete root app) — removed; `main.py` re-exports `api.main:app`

## Work remaining

### High priority (demo path)

- [ ] Confirm the real FireMapSim production origin string with the SIMS Lab deploy
- [ ] Diff `map_control.py` against `guide.py` once more if FireMap Vue internals change; optionally have `guide.py` import `pan_map`
- [x] Consolidate API entry points on `api.main:app`
- [x] Restore `.env.example`
- [x] Migrate to `langchain.agents.create_agent`

### Agent & tools

- [ ] Bridge chat config → FireMapSim Apply button format
- [ ] Implement or remove legacy `app/tools/` stubs

### FireMapSim integration

- [ ] `app/firesim/client.py` — run simulations
- [ ] Full project file generation (ignition / fuel breaks)
- [ ] Align EPSG:5070 vs EPSG:2239 with production
- [ ] Parse and explain simulation results

### Config & infrastructure

- [x] Finish `app/config.py` (Pydantic settings + runtime validation)
- [x] Async `/chat` via `await run_agent()` / LangGraph `ainvoke`
- [x] One async geocoder path (geopy removed; Mapbox/Nominatim provider selection)
- [x] Set `NOMINATIM_USER_AGENT=FireSim-AI/1.0 (+https://firesim.cs.gsu.edu/)`
- [ ] Streaming `POST /chat/stream` with SSE status (`Navigating to X…`)
- [x] Thread raw user/query text into navigate audit log
- [ ] Confirm `_DOMAIN_MARGIN_FACTOR` with FireMapSim / Dr. Hu

### Testing

- [x] Adversarial suite: navigate-only actuator, grant gate, malicious geocoder labels
- [x] API integration tests for `/health`, `/api/session`, `/chat` (mocked LLM)
- [ ] Optional live Nominatim/Mapbox + Chromium smoke test

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (agent) | OpenRouter API key |
| `GEOCODER_PROVIDER` | Yes | `mapbox` in production; `nominatim` for development |
| `MAPBOX_ACCESS_TOKEN` | Production | Mapbox geocoding credential |
| `NOMINATIM_USER_AGENT` | Dev Nominatim | Contactable User-Agent (policy requirement) |
| `FIREMAP_URL` | Yes | FireMap page loaded by Playwright |
| `PLAYWRIGHT_MAX_CONTEXTS` | No | Active context cap; default 2 |
| `CORS_ORIGINS` | No | Comma-separated allowlist; no localhost in production |
| `FIRESIM_PATH` | Later | Path/URL to FireMapSim |
| `FIRESIM_SESSION_ID` | Demo | Shared issued session between `demo/` and `guide.py` |
| `APP_ENV` | No | Default `development` |

## Known issues

- **CORS production origin** — confirm `https://firesim.cs.gsu.edu` matches the real deploy; localhost is rejected when `APP_ENV=production`.
- **Streaming not implemented** — `/chat` is async but has no SSE status line.
- **`_DOMAIN_MARGIN_FACTOR`** — `1.10` is a placeholder, not a confirmed FireMapSim buffer.
- **Dependency notes** — `geopy`/`shapely`/`pip-system-certs` are not runtime deps (geopy path removed; shapely unused; Windows cert helper not needed in the Playwright Linux image). `certifi` and `python-dotenv` arrive transitively via httpx/requests and pydantic-settings.

## API reference (current)

### `GET /health`

```json
{
  "status": "ready",
  "version": "0.1.0",
  "browser_connected": true,
  "active_contexts": 0,
  "max_contexts": 2,
  "waiting_requests": 0
}
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
