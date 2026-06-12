# firesim-ai

Agentic AI layer for the SIMS Lab **FireMapSim** wildfire simulation tool. Helps non-technical users (farmers, land managers) describe a burn scenario in plain language, get a valid simulation config, and follow step-by-step UI guidance to set up and run a simulation.

## Tech stack

- **Python 3.11+**
- **LangChain / LangGraph** — ReAct agent with tool calling and conversation memory
- **OpenRouter** — `anthropic/claude-sonnet-4` via OpenAI-compatible API
- **FastAPI / Uvicorn** — HTTP API for chat clients, Playwright, and demos
- **Pydantic** — FireMapSim project schemas and API models
- **geopy, pyproj, shapely** — geocoding and coordinate conversion

---

## Quick start

### 1. Install dependencies

```powershell
cd fs_agentic_ai
python -m pip install -r requirements.txt
```

On Windows, `pip-system-certs` is required so Python can reach OpenRouter over HTTPS (uses the Windows certificate store).

### 2. Configure environment

Create a `.env` file in the project root:

```env
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

**Health check:**

```powershell
Invoke-RestMethod http://localhost:8000/health
```

**Chat:**

```powershell
$body = @{
  message   = "I want to run a prescribed burn near Canton, GA, about 200 acres"
  thread_id = "demo-001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/chat -Method POST -ContentType "application/json" -Body $body
```

---

## Project layout

```
fs_agentic_ai/
├── api/
│   └── main.py              # FastAPI app — GET /health, POST /chat
├── app/
│   ├── agent/
│   │   ├── agent.py         # LangGraph agent + run_agent()
│   │   ├── prompts.py       # FIRESIM_SYSTEM_PROMPT
│   │   ├── tools.py         # LangChain tools (geocode, config, UI help)
│   │   └── memory.py        # Legacy ConversationBufferWindowMemory (unused by current agent)
│   ├── core/
│   │   └── projection_converter.py   # Geocoding, acres→grid, WGS84↔grid math
│   ├── firesim/
│   │   ├── schemas.py       # FireMapSim project file Pydantic models
│   │   ├── client.py        # FireMapSim runner (stub)
│   │   └── projection_converter.py   # Re-exports from app.core
│   ├── tools/               # Legacy LangChain tool stubs (parameter build, run, parse)
│   ├── api/routes.py        # Legacy routes under /api (stub)
│   └── config.py            # Settings loader (partial stub)
├── tests/
├── main.py                  # Legacy FastAPI entry (stub — use api.main instead)
└── requirements.txt
```

---

## Work completed

### Agent (`app/agent/`)

| Component | Status | Notes |
|-----------|--------|-------|
| `FIRESIM_SYSTEM_PROMPT` | Done | Farmer-facing co-pilot prompt; JSON config schema + FireMapSim UI knowledge |
| `agent.py` | Done | LangGraph `create_react_agent`, OpenRouter via `ChatOpenAI`, `MemorySaver` checkpointer |
| `run_agent(message, thread_id)` | Done | Invokes agent; returns last AI message text |
| `tools.py` | Done | Three tools: `geocode_and_configure`, `build_project_config`, `explain_ui_step` |
| CLI smoke test | Done | `python -m app.agent.agent` |

**LLM config:** `anthropic/claude-sonnet-4` on OpenRouter (`OPENROUTER_API_KEY`).

**Windows HTTPS fix:** `pip_system_certs.wrapt_requests` imported before HTTP clients so SSL works on lab/corporate networks.

### Core utilities (`app/core/projection_converter.py`)

| Function | Status | Purpose |
|----------|--------|---------|
| `geocode_location()` | Done | Nominatim geocoding (`user_agent="firesim-ai"`) |
| `acres_to_sim_bounds()` | Done | Acreage → `cellResolution` + `cellSpaceDimension` |
| `latlon_to_proj_center()` | Done | WGS84 → projected feet (EPSG:2239) |
| `latlon_to_grid()` / `latlon_to_grid_int()` | Done | WGS84 → grid indices |
| `grid_to_latlon()` | Done | Grid indices → WGS84 |

### FireMapSim schemas (`app/firesim/schemas.py`)

| Model | Status |
|-------|--------|
| `Segment`, `TeamInfo`, `SupLine` | Done — matches FireMapSim project JSON |
| `SimulationConfig` | Done — validators for `team_num`, `sup_num`, etc. |
| `SimulationResult`, `SimulationOutput`, `SimulationError` | Done — output/error placeholders |

### HTTP API (`api/main.py`)

| Route | Status |
|-------|--------|
| `GET /health` | Done |
| `POST /chat` | Done — `{ message, thread_id }` → `{ reply }` |
| CORS | Done — open for local demo (`allow_origins=["*"]`) |
| Error handling | Done — 500 with message; traceback logged server-side |

### Tests

| File | Status |
|------|--------|
| `tests/test_coordinate_translator.py` | Partial — geocoding, bounds, agent tools |
| `tests/test_agent.py` | Partial — tool count, `run_agent` callable |
| `tests/test_tools.py` | Stub — TODO placeholders |

### Removed / replaced

- `app/tools/coordinate_translator.py` — removed; logic moved to `app/core/` + `app/agent/tools.py`

---

## Work remaining

### High priority (demo path)

- [ ] **Playwright demo script** — drive FireMapSim UI or call `/chat` from a browser test; decide local vs `firesim.cs.gsu.edu`
- [ ] **Consolidate API entry points** — root `main.py` and `app/api/routes.py` are stubs; either wire them to `api.main` or remove to avoid confusion
- [ ] **Restore `.env.example`** — document required env vars (was deleted in a prior commit)
- [ ] **Migrate `create_react_agent`** — LangGraph deprecation warning; future: `from langchain.agents import create_agent`

### Agent & tools

- [ ] **Reliable tool use** — agent sometimes answers from LLM knowledge instead of calling `geocode_and_configure`; may need prompt tuning or forced tool use for location queries
- [ ] **Bridge chat JSON → FireMapSim Apply button** — agent outputs chat-widget JSON; confirm format matches what the FireMapSim frontend expects
- [ ] **Implement or remove legacy `app/tools/`** — `parameter_builder`, `run_simulation`, `parse_results` are still stubs

### FireMapSim integration

- [ ] **`app/firesim/client.py`** — run simulations via subprocess or HTTP API using `FIRESIM_PATH`
- [ ] **Full project file generation** — map agent chat config (`proj_center_lat/lng`, wind, grid) → full `SimulationConfig` with ignition lines / fuel breaks
- [ ] **EPSG:5070 vs EPSG:2239** — prompts say backend auto-converts to EPSG:5070; `projection_converter` still uses EPSG:2239 for grid math; align with production FireMapSim deployment
- [ ] **Parse and explain simulation results** — implement `parse_results` tool

### Config & infrastructure

- [ ] **`app/config.py`** — implement `get_settings()` and `validate_llm_config()`
- [ ] **Production CORS** — restrict `allow_origins` before public deployment
- [ ] **Async `/chat`** — `run_agent` is sync and blocks the event loop; consider `asyncio.to_thread` for production load

### Testing

- [ ] Fill in stub tests in `tests/test_tools.py` and `tests/test_agent.py`
- [ ] Add API integration tests for `/health` and `/chat` (mocked LLM)

---

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes (agent) | OpenRouter API key for Claude Sonnet 4 |
| `FIRESIM_PATH` | Later | Path or URL to FireMapSim executable/API |
| `APP_ENV` | No | Default `development` |
| `LLM_PROVIDER` | No | Legacy setting in `config.py`; agent uses OpenRouter directly |

---

## Known issues

1. **Two FastAPI apps** — Use `uvicorn api.main:app` for the working API. Root `main:app` mounts stub routes under `/api`.
2. **LangGraph deprecation** — `create_react_agent` warning on startup; still works.
3. **Windows SSL** — Requires `pip-system-certs` in addition to `certifi`; setting `$env:SSL_CERT_FILE` alone is not enough for the OpenAI client.
4. **Geocoding rate limits** — Nominatim has usage limits; production may need caching or a paid geocoder.

---

## API reference (current)

### `GET /health`

```json
{ "status": "ok", "version": "0.1.0" }
```

### `POST /chat`

**Request:**

```json
{
  "message": "I want a prescribed burn near Canton, GA, 200 acres, wind from the southwest at 15 km/h",
  "thread_id": "demo-001"
}
```

**Response:**

```json
{
  "reply": "...(markdown with JSON config block and UI steps)..."
}
```

---

## License / attribution

SIMS Lab — Georgia State University. FireMapSim wildfire simulation tool.
