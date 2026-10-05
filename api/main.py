"""
api/main.py

FastAPI wrapper for the firesim-ai Q&A helper agent.

Routes:
  POST /api/session       — issue unguessable X-Session-Id
  POST /chat              — auth via X-Session-Id; { message } → { reply }
  GET  /health            — sanity check

Run locally:
  uvicorn api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.agent import run_agent
from app.config import get_settings
from app.core.rate_limiter import RateLimitExceededError, chat_rate_limiter, llm_token_budget
from app.core.session_tokens import issue_session_token, is_valid_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    logger.info("firesim-ai API starting up")
    yield
    logger.info("firesim-ai API shutting down")


app = FastAPI(
    title="firesim-ai",
    description="Q&A helper for the FireMapSim wildfire simulation website",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Id"],
)


class SessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's natural-language input")
    # Deprecated: prefer X-Session-Id. If present must match the issued session token.
    thread_id: Optional[str] = Field(
        default=None,
        description="Deprecated — use X-Session-Id. Must match that header if set.",
    )


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class HealthResponse(BaseModel):
    status: str
    version: str


def require_session_id(x_session_id: Optional[str] = Header(default=None)) -> str:
    if not x_session_id or not is_valid_session(x_session_id):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Session-Id")
    return x_session_id


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    """Liveness check for the API process."""
    return HealthResponse(status="ready", version=app.version)


@app.post("/api/session", response_model=SessionResponse, tags=["auth"])
async def create_session():
    """
    Issue an unguessable session token. Clients must send it as
    X-Session-Id on /chat. The same value is the LangGraph thread_id.
    """
    token = issue_session_token()
    logger.info("issued session_id=%s…", token[:8])
    return SessionResponse(session_id=token)


@app.post("/chat", response_model=ChatResponse, tags=["agent"])
async def chat(req: ChatRequest, session_id: str = Depends(require_session_id)):
    """
    Send a message to the firesim-ai Q&A helper and get a reply.

    Requires a valid X-Session-Id from POST /api/session. That id is the
    conversation thread.
    """
    if req.thread_id is not None and req.thread_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="thread_id must match X-Session-Id when both are provided",
        )

    try:
        await chat_rate_limiter.enforce(session_id, "chat turn")
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    logger.info("session=%s… | user: %s", session_id[:8], req.message[:120])

    try:
        reply, tokens_used = await run_agent(
            user_message=req.message,
            thread_id=session_id,
        )
        await llm_token_budget.enforce(session_id, tokens=max(1, tokens_used))
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Agent error on session=%s…", session_id[:8])
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("session=%s… | agent: %s", session_id[:8], reply[:120])
    return ChatResponse(reply=reply, session_id=session_id)
