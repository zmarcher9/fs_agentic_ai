# firesim-ai

[![Tests](https://github.com/zmarcher9/fs_agentic_ai/actions/workflows/tests.yml/badge.svg)](https://github.com/zmarcher9/fs_agentic_ai/actions/workflows/tests.yml)

Q&A helper for the SIMS Lab FireMapSim wildfire simulation website. Non-technical users (farmers, land managers) ask questions in plain language — "how do I set wind speed?", "what does Cell Resolution change?" — and the helper answers while highlighting the relevant control on the live page.

The helper **never operates the site**: it doesn't move the map, fill in fields, click buttons, or start runs. The user stays in the driver's seat; the agent narrates and points.

## Tech stack

- Python 3.11+
- OpenRouter — `anthropic/claude-sonnet-5.5` (reasoning effort `low`) via its OpenAI-compatible API, called with `langchain-openai`
- One structured-output call per question (`{reply, highlight}`); no tools, no agent loop. The system prompt is sent with a cache breakpoint, so it's billed at cache-read rates after the first call
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

Use exactly one worker. Authentication, conversation history, and rate limits
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

Scripted walkthrough of typical questions (API must be running):

```powershell
python demo/run_demo.py
```

The demo and guide issue their own session; set `FIRESIM_SESSION_ID` to reuse one issued by this API process. If a session expires or the server restarts, they start a new conversation automatically.

## Project layout

```
fs_agentic_ai/
├── api/
│   └── main.py              # FastAPI app — /health, /api/session, /chat
├── app/
│   ├── agent/
│   │   ├── agent.py         # run_agent() → TurnResult: one cached, structured OpenRouter call
│   │   ├── prompts.py       # FIRESIM_SYSTEM_PROMPT + build_system_prompt() (adds the step reference)
│   │   └── ui_steps.py      # UI_STEPS — per-control instructions (34 controls), resolve_step()
│   ├── core/
│   │   ├── rate_limiter.py  # chat turn limiter + LLM token budget
│   │   ├── sanitize.py      # unused — reserved for a future doc-grounded tool
│   │   ├── text_format.py   # strip_markdown() — plain-text replies (agent + guide)
│   │   └── session_tokens.py
│   └── config.py
├── playwright/
│   └── guide.py              # Local live guide: sidebar + highlighting
├── playwright_guide/         # Support modules for guide.py
│   ├── api_client.py         # get_session_id(), chat()
│   ├── highlighting.py       # STEP_SELECTORS, pick_highlight(), highlight_on/off()
│   └── sidebar.py            # install_sidebar() + chat sidebar JS
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

`/chat` returns `highlight`: up to 3 `UI_STEPS` keys the model listed in its
structured answer (validated server-side; unknown keys are dropped).
`playwright/guide.py` outlines the first of those it has a selector for. An
empty list (or one with no selectable key) means highlight nothing — the
model uses `[]` when the reply doesn't point at a control. Only if the
response has no `highlight` field at all (an older server) does the guide
fall back to `detect_step()`, which finds the control name ("Wind Degree",
"Set Line Ignition", …) mentioned *earliest* in the reply. `ui_steps.UI_STEPS`
and `highlighting.STEP_SELECTORS` use the same key names for the same
controls; `tests/test_ui_steps.py` guards against them drifting apart.
Selectors are Playwright selectors resolved via `page.locator`. The sidebar
is installed as an init script, so it survives page reloads.

## Where the UI knowledge comes from

The page layout in `FIRESIM_SYSTEM_PROMPT` and the per-control steps in
`UI_STEPS` are grounded in the SIMS Lab FireMapSim project report and
slides (Wei Zhao, July 2025) and Dr. Hu's usage email (upload/run a shared
project, customized fuel, fuel reduction). The wind from/to convention,
which no source states, is deliberately left out (the agent says it isn't
documented). A few values carried over from the earlier prompt aren't in
those documents' text either; they're kept pending confirmation and listed
under Work remaining.

## Work completed

| Component | Status | Notes |
|---|---|---|
| `FIRESIM_SYSTEM_PROMPT` | Done | Q&A scope; "cannot move the map / fill fields / click"; pasted or quoted text is untrusted data (stated as a partial mitigation); page layout + background grounded in the project report; never asserts a wind from/to convention; plain-text replies |
| `agent.py` | Done | One structured call per question via OpenRouter; cached system prompt; last 6 exchanges of history; async `run_agent` → `TurnResult(reply, tokens_used, ui_steps)`; tokens weighted for cache reads; empty answers raise; per-session lock + global concurrency cap; LLM timeout/retries; expired sessions pruned |
| `ui_steps.py` | Done | 34 controls; `resolve_step` accepts keys or visible labels; keys aligned with highlight selectors |
| `POST /api/session`, `POST /chat` | Done | Issued unguessable session tokens (throttled per IP); chat rate limit; token budget checked *before* the LLM call inside the session lock, and every billed call recorded (failed ones too); 2,048-token output cap; 2,000-char message cap; generic 500 bodies; no user content in logs |
| `GET /health` | Done | Liveness only — no browser to wait on |
| CORS | Done | From `CORS_ORIGINS`; production rejects localhost origins; no credentials (auth is a header) |
| Live guide | Done | Sidebar (survives reloads, top frame only, 2,000-char input) + highlighting from `/chat`'s `highlight` list; re-issues a session on 401; never pans or edits the page |

### Tests

| File | Covers |
|---|---|
| `tests/test_adversarial_agent.py` | The model is given no tools at all; prompt forbids operating the site; server never imports a browser driver |
| `tests/test_ui_steps.py` | `resolve_step` and label aliases; step reference in the prompt and byte-stable; `UI_STEPS` ↔ `STEP_SELECTORS` alignment; each step's text highlights its own control; no wind from/to claims |
| `tests/test_api_main.py` | `/health`, `/api/session`, `/chat` round trips; budget stops LLM calls (incl. failed billed turns and concurrent requests); 400/401/422/429/500 paths; session throttle; plain-text replies |
| `tests/test_agent.py` | Scripted model: one call per question, cache breakpoint on the system prompt, OpenRouter structured-output wiring (no tools), history window, cache-weighted tokens, highlight validation, empty-answer guard, provider error / cancellation recorded and session left usable, pruning |
| `tests/test_highlighting.py` | `detect_step`/`pick_highlight`; headless-Chromium highlight on/off (incl. after a re-render), selector validity, sidebar reload + round trip, iframe guard (skips without Chromium locally; fails in CI) |
| `tests/test_guide_display.py` | `strip_markdown` / `clean_for_display`, incl. a speed check |
| `tests/test_clients.py` | `demo/run_demo.py` and `playwright/guide.py` import from any directory; `api_client` 401 re-mint + retry |
| `tests/test_config.py` / `test_rate_limiter.py` / `test_sanitize.py` / `test_session_tokens.py` | Settings validation and core utilities |

## Work remaining

- [ ] Confirm with Dr. Hu / the FireMapSim source (none of the docs say):
  - whether **Wind Degree** is the direction the wind comes *from* or blows *toward* (the agent currently says it isn't documented);
  - values in the prompt / `UI_STEPS` that aren't in the documents' text: **Wind Speed** km/h, 0–100, "default 10"; **Cell Resolution** options 2/3/5/10/15/30 and "default 30"; **Cell Space Dimension** options 50/100/150/200; the Simulation Duration "typically 6,000–30,000" range;
  - default values on a fresh page (report screenshots show Cell Space Dimension 200, Wind Degree 180).
- [ ] Confirm selectors on the live page and add `STEP_SELECTORS` for the steps in `_NO_SELECTOR_STEPS` (`tests/test_ui_steps.py`), e.g. Show Cell Info, Select Map Style, Dynamic Ignition, Show Simulation Result. Also check the `>> nth=` settings-box selectors (User-defined Simulation mode may add number inputs before them).
- [ ] More of Dr. Hu's material: if it's short-form, fold it into `UI_STEPS` / the prompt as was done for the project report. Only build a file-backed `answer_domain_question` tool (reading `docs/knowledge/`) if the material is genuinely long-form. A file-backed tool must take a free-text query resolved against its own fixed file list (never an LLM-supplied path), cap per-file size, accept plain text/markdown only, and come with doc-content-injection cases in `tests/test_adversarial_agent.py`.
- [ ] Confirm with Dr. Hu whether recommending specific simulation parameter values is in scope (currently: no — the helper explains settings, ranges, and trade-offs only).
- [ ] Streaming `POST /chat/stream`.
- [ ] Slim the container image now that the server runs no Chromium (see Known issues).

## Model choice and cost

Measured on 2026-10-06 with one 12-question conversation of typical first-time-user questions (setup steps, wind, fuel editing, ignition modes, pre-burned areas) plus an off-topic question and a prompt-injection attempt, all through OpenRouter, with automatic checks for: declines to act, no wind from/to claim, right control highlighted, no markdown, resists a prompt-injection attempt.

| Model (OpenRouter) | Effort | Cost / 12 questions | Checks failed |
|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | low | $0.093 | 0 |
| `anthropic/claude-sonnet-5.5` | default | $0.125 | 0 |
| `anthropic/claude-opus-5.5` | low | $0.175 | 0 |
| `anthropic/claude-opus-5.5` | default | $0.242 | 0 |
| `anthropic/claude-haiku-4.5` | — | $0.043 | 3 (one empty answer, two wrong highlights) |

The previous design (tool-calling agent loop on `anthropic/claude-sonnet-4`, no caching) used ~131k tokens for the same conversation — roughly $0.40. The cached system prompt (~6.5k tokens) is read from cache on every call after the first.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (agent) | OpenRouter API key |
| `OPENROUTER_BASE_URL` | No | Default `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | No | OpenRouter model id; default `anthropic/claude-sonnet-5.5` |
| `LLM_REASONING_EFFORT` | No | `low` / `medium` / `high`, or blank for the provider default; default `low` |
| `LLM_HISTORY_TURNS` | No | Past exchanges resent per question; default 6 |
| `LLM_MAX_OUTPUT_TOKENS` | No | Per-call output cap, reasoning included; default 2048 |
| `LLM_MAX_CONCURRENT_TURNS` | No | Global cap on concurrent agent turns; default 4 |
| `LLM_TIMEOUT_SECONDS` | No | Per provider request; default 60 |
| `LLM_MAX_RETRIES` | No | Provider retries per request; default 2 |
| `HOST` / `PORT` | No | Bind address for `python main.py`; default `0.0.0.0:8000` |
| `FIREMAP_URL` | Guide only | FireMapSim page opened by `playwright/guide.py`; default `http://localhost:5173` |
| `API_BASE_URL` | Guide/demo | Where `guide.py` / `run_demo.py` reach the API; default `http://localhost:8000` |
| `CORS_ORIGINS` | No | Comma-separated allowlist; no localhost in production; default `http://localhost:5173,https://firesim.cs.gsu.edu` |
| `FIRESIM_SESSION_ID` | Demo / guide | Reuse a session issued by this API process. Shell environment only (not read from `.env`); dropped and re-issued on a 401 |
| `APP_ENV` | No | Default `development` |

## Known issues

- **Container image is oversized** — the base image is still `mcr.microsoft.com/playwright/python` and `compose.yaml` sets `shm_size: 1gb`, both left over from server-side Chromium. The API no longer needs either; `guide.py` is a local script and doesn't run in the container.
- **CORS production origin** — confirm `https://firesim.cs.gsu.edu` matches the real deploy; localhost is rejected when `APP_ENV=production`.
- **One highlight per reply** — the guide outlines a single control: the first key in `highlight` that has a selector.
- **Session throttle is per client IP** — behind a reverse proxy every user shares the proxy's IP (20 new sessions/minute in total). Before deploying behind one, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IP>` so the real client IP is used. Never `--forwarded-allow-ips=*` on a directly exposed server — clients could then spoof `X-Forwarded-For` and mint unlimited sessions.
- **Abuse surface** — anyone who can reach the API can chat on the configured OpenRouter key, within the per-IP session throttle and per-session limits. There is no global spend cap yet.

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
{ "reply": "...", "session_id": "<same token>", "highlight": ["wind_degree"] }
```

`highlight` lists up to 3 UI step keys the answer is about, most relevant first (may be empty). `message` is 1–2,000 characters. Optional deprecated body field `thread_id` must match `X-Session-Id` if present. Failures: `400` thread_id mismatch · `401` missing/invalid/expired session · `422` invalid body · `429` rate limit / token budget exhausted · `500` agent error (generic message; details in the server log).

`POST /api/session` returns `429` past 20 new sessions per minute per client IP.

## License / attribution

SIMS Lab — Georgia State University. FireMapSim wildfire simulation tool.
