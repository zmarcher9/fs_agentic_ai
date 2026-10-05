# firesim-ai

[![Tests](https://github.com/zmarcher9/fs_agentic_ai/actions/workflows/tests.yml/badge.svg)](https://github.com/zmarcher9/fs_agentic_ai/actions/workflows/tests.yml)

Q&A helper for the SIMS Lab FireMapSim wildfire simulation website. Non-technical users (farmers, land managers) ask questions in plain language — "how do I set wind speed?", "what does Cell Resolution change?" — and the helper answers while highlighting the relevant control on the live page.

The helper **never operates the site**: it doesn't move the map, fill in fields, click buttons, or start runs. The user stays in the driver's seat; the agent narrates and points.

## Tech stack

- Python 3.11+
- LangChain / LangGraph — ReAct agent with tool calling and conversation memory
- OpenRouter — anthropic/claude-sonnet-4 via OpenAI-compatible API
- FastAPI / Uvicorn — HTTP API for chat clients, the guide sidebar, and demos
- Pydantic — settings and API models
- Playwright — local guide script only (`playwright/guide.py`): opens FireMapSim, injects the chat sidebar, highlights controls. The API server itself has no browser dependency.

## Quick start

### 1. Install dependencies

```powershell
cd fs_agentic_ai
python -m pip install -r requirements.txt
python -m playwright install chromium   # only needed for playwright/guide.py
```

If Node cannot verify the browser download certificate on managed Windows,
set `NODE_OPTIONS=--use-system-ca` for the install command.

### 2. Configure environment

Create a `.env` file in the project root (start from `.env.example`):

```
OPENROUTER_API_KEY=sk-or-v1-...
FIREMAP_URL=http://localhost:5173
```

### 3. Run the agent (CLI smoke test)

```powershell
python -m app.agent.agent
```

### 4. Run the HTTP API

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

Use exactly one worker. Authentication, LangGraph memory, and rate limits
are process-local.

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### 5. Run the live guide (optional)

With the API running and FireMapSim available at `FIREMAP_URL`:

```powershell
python playwright/guide.py
```

This opens FireMapSim in a visible browser, adds an orange launcher button
(bottom-right) for the chat sidebar, and highlights whichever control the
agent's reply mentions. It runs on your machine, not in the container.

### Container

```powershell
docker compose up --build
```

Compose runs `uvicorn` with `--workers 1`. Secrets are read from `.env` at
runtime and excluded from the Docker build context. If `pip install` fails
during `docker build` with an SSL certificate error (common on corporate
networks), the Dockerfile already trusts PyPI hosts for the install step.

### Chat from a terminal

```powershell
.\scripts\chat.ps1
```

Or by hand:

```powershell
$session = Invoke-RestMethod -Uri http://localhost:8000/api/session -Method POST
$headers = @{ "X-Session-Id" = $session.session_id }

$body = @{ message = "How do I draw an ignition line?" } | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/chat -Method POST -ContentType "application/json" -Headers $headers -Body $body
```

Demo / guide can share a session via `FIRESIM_SESSION_ID` (must be issued by this API process):

```powershell
$env:FIRESIM_SESSION_ID = $session.session_id
python demo/run_demo.py
python playwright/guide.py
```

## Project layout

```
fs_agentic_ai/
├── api/
│   └── main.py              # FastAPI app — /health, /api/session, /chat
├── app/
│   ├── agent/
│   │   ├── agent.py         # LangGraph agent + run_agent() → (reply, tokens)
│   │   ├── prompts.py       # FIRESIM_SYSTEM_PROMPT (Q&A helper; never operates the site)
│   │   ├── registry.py      # TOOLS — aggregates tools_*.py
│   │   └── tools_ui_help.py # explain_ui_step — plain-English per-control instructions
│   ├── core/
│   │   ├── rate_limiter.py  # chat turn limiter + LLM token budget
│   │   ├── sanitize.py      # strip injection-style text from external tool content
│   │   └── session_tokens.py
│   └── config.py
├── playwright/
│   └── guide.py              # Local live guide: sidebar + highlighting
├── playwright_guide/         # Support modules for guide.py
│   ├── api_client.py         # get_session_id(), chat()
│   ├── highlighting.py       # STEP_SELECTORS, KEYWORD_MAP, detect_step(), highlight_on/off()
│   └── sidebar.py            # inject_sidebar() + chat sidebar JS
├── demo/
│   └── run_demo.py           # Scripted Q&A walkthrough against /chat
├── scripts/
│   └── chat.ps1              # Interactive terminal chat
├── tests/
├── main.py                   # Re-exports api.main:app; uvicorn --workers 1
├── Dockerfile
├── compose.yaml
├── .env.example
├── requirements.in
├── requirements.lock
└── requirements.txt
```

## How highlighting works

`playwright/guide.py` sends each message to `/chat`, then scans the reply
text with `detect_step()` for a known control name ("Wind Speed",
"Set Line Ignition", …) and outlines that control on the page. It works off
the reply text alone, so it highlights for both UI how-to answers and
background answers that mention a control. `tools_ui_help._UI_STEPS` and
`highlighting.STEP_SELECTORS` use the same key names for the same controls;
`tests/test_agent_tools.py` guards against them drifting apart.

## Work completed

| Component | Status | Notes |
|---|---|---|
| `FIRESIM_SYSTEM_PROMPT` | Done | Q&A scope; "cannot move the map / fill fields / click"; tool payloads are untrusted data (stated as a partial mitigation) |
| `agent.py` | Done | LangGraph ReAct agent; async `run_agent` → `(reply, tokens_used)`; per-session lock + global concurrency cap |
| `explain_ui_step` | Done | JSON on hit and miss; keys aligned with highlight selectors; no actuation-era phrasing |
| `POST /api/session`, `POST /chat` | Done | Issued unguessable session tokens; chat rate limit + LLM token budget |
| `GET /health` | Done | Liveness only — no browser to wait on |
| CORS | Done | From `CORS_ORIGINS`; production rejects localhost origins |
| Live guide | Done | Sidebar + text-based highlighting; never pans or edits the page |

### Tests

| File | Covers |
|---|---|
| `tests/test_adversarial_agent.py` | Only narration tools registered; no tool takes a path/URL argument; hostile step names; prompt forbids operating the site; server never imports a browser driver |
| `tests/test_agent_tools.py` | `explain_ui_step` shape; `_UI_STEPS` ↔ `STEP_SELECTORS` key alignment |
| `tests/test_api_main.py` | `/health`, `/api/session`, `/chat` round trips (mocked LLM) |
| `tests/test_agent.py` | Tool registry, agent factory wiring, async `ainvoke`, stale-lock pruning |
| `tests/test_config.py` / `test_rate_limiter.py` / `test_sanitize.py` / `test_session_tokens.py` | Settings validation and core utilities |

## Work remaining

- [ ] Domain/background knowledge grounded in Dr. Hu's reference material. Once the files are in hand: if they're short-form/FAQ-shaped, fold them into a dict like `_UI_STEPS`; only build a file-backed `answer_domain_question` tool (reading `docs/knowledge/`) if the material is genuinely long-form. A file-backed tool must take a free-text query resolved against its own fixed file list (never an LLM-supplied path), cap per-file size, accept plain text/markdown only, and come with doc-content-injection cases in `tests/test_adversarial_agent.py`.
- [ ] Confirm with Dr. Hu whether recommending specific simulation parameter values is in scope (currently: no — the helper explains settings, ranges, and trade-offs only).
- [ ] Add `_UI_STEPS` entries for `go_project_location` and `selected_area` once their visible labels/behavior are confirmed on the live site.
- [ ] Streaming `POST /chat/stream`.
- [ ] Slim the container image now that the server runs no Chromium (see Known issues).

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (agent) | OpenRouter API key |
| `OPENROUTER_BASE_URL` | No | Default `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | No | Default `anthropic/claude-sonnet-4` |
| `LLM_MAX_CONCURRENT_TURNS` | No | Global cap on concurrent agent turns; default 4 |
| `FIREMAP_URL` | Guide only | FireMapSim page opened by `playwright/guide.py` |
| `API_BASE_URL` | Guide/demo | Where `guide.py` / `run_demo.py` reach the API; default `http://localhost:8000` |
| `CORS_ORIGINS` | No | Comma-separated allowlist; no localhost in production |
| `FIRESIM_SESSION_ID` | Demo | Shared issued session between `demo/` and `guide.py` |
| `APP_ENV` | No | Default `development` |

## Known issues

- **Container image is oversized** — the base image is still `mcr.microsoft.com/playwright/python` and `compose.yaml` sets `shm_size: 1gb`, both left over from server-side Chromium. The API no longer needs either; `guide.py` is a local script and doesn't run in the container.
- **CORS production origin** — confirm `https://firesim.cs.gsu.edu` matches the real deploy; localhost is rejected when `APP_ENV=production`.
- **Highlighting is text-matched** — `detect_step()` picks one control per reply (the highest-priority match in `KEYWORD_MAP`), so a reply that mentions several controls highlights only one.

## API reference

### `GET /health`

```json
{ "status": "ready", "version": "0.1.0" }
```

### `POST /api/session`

Response:

```json
{ "session_id": "<unguessable token>" }
```

### `POST /chat`

Header: `X-Session-Id: <issued token>`

Request:

```json
{ "message": "How do I set the wind direction?" }
```

Response:

```json
{ "reply": "...", "session_id": "<same token>" }
```

Optional deprecated body field `thread_id` must match `X-Session-Id` if present. Failures: `401` missing/invalid session · `429` rate limit / token budget · `500` agent error.

## License / attribution

SIMS Lab — Georgia State University. FireMapSim wildfire simulation tool.
